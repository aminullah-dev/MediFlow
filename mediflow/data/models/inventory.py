"""General clinic inventory: supply items and their stock movements.

Distinct from pharmacy stock (medications with dated batches); this covers
consumables and general supplies (gloves, syringes, stationery, …) tracked as a
single quantity-on-hand with an append-only movement log.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediflow.data.base import Base, utcnow
from mediflow.data.mixins import AuditMixin


class InventoryItem(Base, AuditMixin):
    __tablename__ = "inventory_items"

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(60))
    code: Mapped[str | None] = mapped_column(String(40), index=True)
    unit: Mapped[str] = mapped_column(String(30), default="unit", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reorder_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    movements: Mapped[list["StockMovement"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class StockMovement(Base, AuditMixin):
    __tablename__ = "stock_movements"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Signed delta applied to the item quantity (positive in, negative out).
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    unit_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    item: Mapped[InventoryItem] = relationship(back_populates="movements")
