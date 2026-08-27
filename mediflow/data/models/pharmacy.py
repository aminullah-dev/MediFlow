"""Pharmacy: medication catalogue and dated stock batches.

Stock is tracked as dated batches so the dispensing logic can consume the
earliest-expiring stock first (FEFO) and the UI can raise expiry alerts.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediflow.data.base import Base
from mediflow.data.mixins import AuditMixin


class Medication(Base, AuditMixin):
    __tablename__ = "medications"

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    generic_name: Mapped[str | None] = mapped_column(String(120))
    form: Mapped[str | None] = mapped_column(String(40))       # tablet, syrup, injection…
    strength: Mapped[str | None] = mapped_column(String(60))   # e.g. "500 mg"
    barcode: Mapped[str | None] = mapped_column(String(60), index=True)
    unit: Mapped[str] = mapped_column(String(30), default="unit", nullable=False)
    reorder_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sale_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    batches: Mapped[list[StockBatch]] = relationship(
        back_populates="medication", cascade="all, delete-orphan"
    )


class StockBatch(Base, AuditMixin):
    __tablename__ = "stock_batches"

    medication_id: Mapped[int] = mapped_column(
        ForeignKey("medications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_number: Mapped[str | None] = mapped_column(String(60))
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)
    cost_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    received_on: Mapped[date | None] = mapped_column(Date)

    medication: Mapped[Medication] = relationship(back_populates="batches")
