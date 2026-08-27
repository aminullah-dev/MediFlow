"""Declarative ORM base with a deterministic constraint naming convention.

Explicit constraint names are required for Alembic autogenerate to produce
stable, reversible migrations on SQLite (which otherwise names constraints
anonymously and cannot ALTER them cleanly). Every model inherits an integer
surrogate primary key from :class:`Base`.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata_obj = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    metadata = metadata_obj

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} id={getattr(self, 'id', None)}>"


def utcnow() -> datetime:
    """Naive UTC timestamp used for all system-generated audit columns.

    Stored naive (tz-free) for stable SQLite comparisons, but derived from a
    timezone-aware ``now`` to avoid the deprecated ``datetime.utcnow()``.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# -- local-day bucketing ----------------------------------------------------
# Two timestamp domains coexist in the schema:
#   * wall-clock columns — user-entered local times (appointment schedules);
#   * UTC columns        — system stamps via utcnow() (created_at, issued_at).
# "Today" always means the *local* calendar day (Kabul is UTC+4:30, so UTC
# midnight is 19:30 the previous local evening); pick the helper matching the
# column's domain.

def _local_utc_offset() -> timedelta:
    return datetime.now().astimezone().utcoffset() or timedelta()


def local_now() -> datetime:
    """Timezone-aware ``now`` in the machine's own zone.

    Prefer this over ``datetime.now()``: the bare call reads the clock without
    ever naming a zone, so nothing in the signature says whose "now" it is.
    """
    return datetime.now().astimezone()


def local_today() -> date:
    """The local calendar date.

    Replaces ``date.today()`` throughout. Same value, but it states the domain
    it belongs to, and it keeps "today" anchored to the clinic's own calendar
    rather than to UTC — the distinction that makes 02:00 in Kabul still today.
    """
    return local_now().date()


def local_day_bounds(day: date | None = None) -> tuple[datetime, datetime]:
    """Half-open [midnight, next midnight) of a local calendar day, local time.

    Compare against wall-clock columns such as ``Appointment.scheduled_start``.
    """
    start = datetime.combine(day or local_today(), time.min)
    return start, start + timedelta(days=1)


def local_day_bounds_utc(day: date | None = None) -> tuple[datetime, datetime]:
    """The local calendar day expressed as naive-UTC bounds.

    Compare against utcnow()-stamped columns such as ``created_at``.
    """
    offset = _local_utc_offset()
    start, end = local_day_bounds(day)
    return start - offset, end - offset


def local_month_start_utc() -> datetime:
    """First instant of the local calendar month, expressed in naive UTC."""
    today = local_today()
    # Naive on purpose: this is the wall-clock domain described above, and the
    # offset is subtracted straight after to land in the naive-UTC domain.
    return datetime(today.year, today.month, 1) - _local_utc_offset()  # noqa: DTZ001
