"""Schema creation helper for first run and tests.

In production the schema is owned by Alembic migrations. For a brand-new
database (and for fast in-memory tests) ``create_all`` builds the current schema
directly. The two must stay consistent; the migration test guards that.
"""
from __future__ import annotations

from sqlalchemy import text

from mediflow.data.database import Database
from mediflow.data.models import Base


def create_all(db: Database) -> None:
    Base.metadata.create_all(db.engine)
    _ensure_lightweight_columns(db)


def _ensure_lightweight_columns(db: Database) -> None:
    """Add additive columns that post-date the original tables.

    ``create_all`` only creates missing *tables*, never alters existing ones, so
    a database created before a column was introduced needs a small idempotent
    ``ADD COLUMN``. (Full schema changes still go through Alembic.)
    """
    with db.engine.begin() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(audit_log)"))}
        if "row_hash" not in columns:
            conn.execute(text("ALTER TABLE audit_log ADD COLUMN row_hash VARCHAR(64)"))


def drop_all(db: Database) -> None:
    Base.metadata.drop_all(db.engine)
