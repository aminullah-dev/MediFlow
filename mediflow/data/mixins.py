"""Reusable ORM mixins: timestamps, soft delete, and user attribution.

Soft delete
    Records are never physically removed by application code. ``is_deleted`` is
    flipped and ``deleted_at`` stamped. Repositories filter out soft-deleted
    rows by default, so the rest of the application is unaware of them, while
    audit and legal-retention requirements are satisfied.

Attribution
    ``created_by_id`` / ``updated_by_id`` reference the acting user. They are
    populated by the session layer from the current login context, giving every
    row an accountable owner without each service passing the user explicitly.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from mediflow.data.base import utcnow


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def soft_delete(self) -> None:
        self.is_deleted = True
        self.deleted_at = utcnow()

    def restore(self) -> None:
        self.is_deleted = False
        self.deleted_at = None


class UserAttributionMixin:
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_created_by", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_updated_by", ondelete="SET NULL"),
        nullable=True,
    )


class AuditMixin(TimestampMixin, SoftDeleteMixin, UserAttributionMixin):
    """Convenience mixin combining timestamps, soft delete, and attribution."""
