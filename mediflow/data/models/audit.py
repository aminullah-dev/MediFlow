"""Immutable audit-trail model.

One row per create/update/delete of an audited entity. Rows are append-only —
the application never updates or deletes them — giving a tamper-evident history
for medico-legal and financial accountability.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from mediflow.data.base import Base, utcnow


class AuditLog(Base):
    __tablename__ = "audit_log"

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    # JSON diff of changed columns {field: [old, new]}; kept compact.
    changes: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )
    # HMAC chaining each row to the previous one, making after-the-fact edits or
    # deletions detectable via ``AuditService.verify_chain``.
    row_hash: Mapped[str | None] = mapped_column(String(64))
