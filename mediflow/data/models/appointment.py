"""Appointment and reception queue models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediflow.core.constants import AppointmentStatus
from mediflow.data.base import Base
from mediflow.data.mixins import AuditMixin
from mediflow.data.models.patient import Patient


class Appointment(Base, AuditMixin):
    __tablename__ = "appointments"

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Doctor references a user for now; a dedicated Doctor profile can be added
    # without breaking this FK (nullable to allow walk-in triage before assignment).
    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )

    scheduled_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(
        String(20), default=AppointmentStatus.BOOKED.value, nullable=False, index=True
    )
    is_walk_in: Mapped[bool] = mapped_column(default=False, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    patient: Mapped[Patient] = relationship()
    queue_token: Mapped[QueueToken | None] = relationship(
        back_populates="appointment", uselist=False, cascade="all, delete-orphan"
    )


class QueueToken(Base, AuditMixin):
    """Reception check-in token; ``number`` resets daily per department."""

    __tablename__ = "queue_tokens"

    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    service_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "A-014"
    qr_payload: Mapped[str | None] = mapped_column(String(120))

    appointment: Mapped[Appointment] = relationship(back_populates="queue_token")
