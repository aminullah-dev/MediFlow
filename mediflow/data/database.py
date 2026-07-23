"""Thread-safe SQLite engine and unit-of-work session management.

Design notes
------------
* **WAL journaling** and ``foreign_keys=ON`` are enabled on every connection via
  a pool event listener — SQLite disables FK enforcement by default and WAL is
  essential for concurrent read while a background thread writes (e.g. backup).
* **Thread-affine sessions**: the desktop UI runs work on ``QThread`` workers.
  A ``scoped_session`` keyed by thread id gives each thread its own session and
  transaction, which SQLAlchemy sessions require (they are not thread-safe).
* **Current-user context** is stored in a :class:`contextvars.ContextVar`. A
  ``before_flush`` listener reads it to stamp ``created_by``/``updated_by`` and
  to emit audit-log rows, so business code never threads the user through.
"""
from __future__ import annotations

import contextlib
from contextvars import ContextVar
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from mediflow.core.logging_config import get_logger

log = get_logger("data.database")

# Identity of the acting user for the current thread/operation. Set by the auth
# layer on login and by worker threads before they touch the database.
current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)

# Effective permission codes of the acting user, so the service layer can
# enforce authorization (not just the UI). Populated on login, cleared on logout.
current_permissions: ContextVar[frozenset[str]] = ContextVar(
    "current_permissions", default=frozenset()
)


def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


class Database:
    """Owns the engine and session factory for one database file."""

    def __init__(self, url: str, *, echo: bool = False):
        # check_same_thread=False is safe here because access is serialised
        # through per-thread scoped sessions, not shared connections.
        self.engine: Engine = create_engine(
            url,
            echo=echo,
            future=True,
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", _configure_sqlite)

        self._session_factory = sessionmaker(
            bind=self.engine, autoflush=False, expire_on_commit=False, future=True
        )
        self._scoped = scoped_session(self._session_factory)
        _register_audit_listeners(self._session_factory)

    @property
    def session(self) -> Session:
        """The session bound to the current thread."""
        return self._scoped()

    @contextlib.contextmanager
    def unit_of_work(self) -> Iterator[Session]:
        """Transactional scope. Commits on success, rolls back on error."""
        session = self._scoped()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            # Return the session to a clean state for the next unit of work.
            self._scoped.remove()

    def remove_session(self) -> None:
        """Dispose the current thread's session (call at thread teardown)."""
        self._scoped.remove()

    def dispose(self) -> None:
        self._scoped.remove()
        self.engine.dispose()


def _register_audit_listeners(session_factory: sessionmaker) -> None:
    """Attach attribution + audit-trail listeners to all sessions."""
    from mediflow.data.audit import capture_changes, emit_audit_rows

    @event.listens_for(session_factory, "before_flush")
    def _before_flush(session: Session, _flush_context, _instances):  # noqa: ANN001
        capture_changes(session, current_user_id.get())

    @event.listens_for(session_factory, "after_flush")
    def _after_flush(session: Session, _flush_context):  # noqa: ANN001
        emit_audit_rows(session)
