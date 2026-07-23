"""Laboratory: test catalogue and per-patient test requests with results."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediflow.core.constants import LabRequestStatus
from mediflow.data.base import Base, utcnow
from mediflow.data.mixins import AuditMixin
from mediflow.data.models.patient import Patient


class LabTest(Base, AuditMixin):
    __tablename__ = "lab_tests"

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(30), index=True)
    sample_type: Mapped[str | None] = mapped_column(String(60))   # blood, urine…
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    reference_range: Mapped[str | None] = mapped_column(String(120))
    unit: Mapped[str | None] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LabRequest(Base, AuditMixin):
    __tablename__ = "lab_requests"

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lab_test_id: Mapped[int] = mapped_column(
        ForeignKey("lab_tests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requested_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=LabRequestStatus.REQUESTED.value, nullable=False, index=True
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    result_value: Mapped[str | None] = mapped_column(String(120))
    result_flag: Mapped[str | None] = mapped_column(String(20))   # normal/high/low/abnormal
    result_notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    patient: Mapped[Patient] = relationship()
    lab_test: Mapped[LabTest] = relationship()
