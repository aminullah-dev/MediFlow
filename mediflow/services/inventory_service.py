"""Inventory service: supply items and stock movements."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from mediflow.core.constants import StockMovementType
from mediflow.core.exceptions import BusinessRuleError, ValidationError
from mediflow.core.logging_config import get_logger
from mediflow.data.base import utcnow
from mediflow.data.database import Database
from mediflow.data.models.inventory import InventoryItem, StockMovement
from mediflow.services.authz import require

log = get_logger("services.inventory")

# Movement types that add to (IN) or remove from (OUT) stock.
IN_TYPES = (StockMovementType.PURCHASE, StockMovementType.RETURN)
OUT_TYPES = (StockMovementType.SALE, StockMovementType.EXPIRY_WRITEOFF,
             StockMovementType.TRANSFER)


@dataclass(slots=True)
class ItemInput:
    name: str
    category: str | None = None
    code: str | None = None
    unit: str = "unit"
    reorder_level: int = 0
    unit_cost: float = 0.0
    notes: str | None = None


@dataclass(slots=True)
class InventoryItemDTO:
    id: int
    name: str
    category: str | None
    code: str | None
    unit: str
    quantity: int
    reorder_level: int
    unit_cost: float
    notes: str | None

    @property
    def is_low(self) -> bool:
        return self.quantity <= self.reorder_level

    @property
    def is_out(self) -> bool:
        return self.quantity <= 0


@dataclass(slots=True)
class MovementDTO:
    id: int
    movement_type: str
    quantity: int
    reason: str | None
    occurred_at: datetime


class InventoryService:
    def __init__(self, db: Database):
        self._db = db

    # -- items --------------------------------------------------------------
    def list_items(self, term: str = "") -> list[InventoryItemDTO]:
        term = (term or "").strip()
        with self._db.unit_of_work() as session:
            stmt = select(InventoryItem).where(InventoryItem.is_deleted.is_(False))
            if term:
                like = f"%{term}%"
                stmt = stmt.where(
                    InventoryItem.name.ilike(like)
                    | InventoryItem.category.ilike(like)
                    | InventoryItem.code.ilike(like)
                )
            stmt = stmt.order_by(InventoryItem.name)
            return [self._to_dto(i) for i in session.execute(stmt).scalars().all()]

    def get(self, item_id: int) -> InventoryItemDTO:
        with self._db.unit_of_work() as session:
            item = session.get(InventoryItem, item_id)
            if item is None:
                raise ValidationError("Item not found.")
            return self._to_dto(item)

    @require("inventory.manage")
    def create(self, data: ItemInput) -> int:
        self._validate(data)
        with self._db.unit_of_work() as session:
            item = InventoryItem(**self._fields(data))
            session.add(item)
            session.flush()
            return item.id

    @require("inventory.manage")
    def update(self, item_id: int, data: ItemInput) -> None:
        self._validate(data)
        with self._db.unit_of_work() as session:
            item = session.get(InventoryItem, item_id)
            if item is None:
                raise ValidationError("Item not found.")
            for key, value in self._fields(data).items():
                setattr(item, key, value)

    @require("inventory.manage")
    def delete(self, item_id: int) -> None:
        with self._db.unit_of_work() as session:
            item = session.get(InventoryItem, item_id)
            if item is not None:
                item.soft_delete()

    # -- movements ----------------------------------------------------------
    @require("inventory.manage")
    def record_movement(self, item_id: int, movement_type: StockMovementType,
                        delta: int, *, reason: str | None = None,
                        unit_cost: float = 0.0) -> None:
        if delta == 0:
            raise ValidationError("Quantity must not be zero.", field="quantity")
        with self._db.unit_of_work() as session:
            item = session.get(InventoryItem, item_id)
            if item is None:
                raise ValidationError("Item not found.")
            new_quantity = item.quantity + delta
            if new_quantity < 0:
                raise BusinessRuleError(
                    f"Only {item.quantity} {item.unit} in stock; cannot remove {-delta}."
                )
            item.quantity = new_quantity
            session.add(StockMovement(
                item_id=item_id,
                movement_type=movement_type.value,
                quantity=delta,
                reason=(reason or "").strip() or None,
                unit_cost=unit_cost,
                occurred_at=utcnow(),
            ))
            log.info("Inventory movement item=%s delta=%s (%s)", item_id, delta,
                     movement_type.value)

    def list_movements(self, item_id: int, *, limit: int = 50) -> list[MovementDTO]:
        with self._db.unit_of_work() as session:
            stmt = (
                select(StockMovement)
                .where(StockMovement.item_id == item_id,
                       StockMovement.is_deleted.is_(False))
                .order_by(StockMovement.occurred_at.desc())
                .limit(limit)
            )
            return [MovementDTO(m.id, m.movement_type, m.quantity, m.reason, m.occurred_at)
                    for m in session.execute(stmt).scalars().all()]

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _to_dto(item: InventoryItem) -> InventoryItemDTO:
        return InventoryItemDTO(
            id=item.id, name=item.name, category=item.category, code=item.code,
            unit=item.unit, quantity=item.quantity, reorder_level=item.reorder_level,
            unit_cost=float(item.unit_cost or 0), notes=item.notes,
        )

    @staticmethod
    def _fields(data: ItemInput) -> dict:
        return {
            "name": data.name.strip(),
            "category": (data.category or "").strip() or None,
            "code": (data.code or "").strip() or None,
            "unit": (data.unit or "unit").strip() or "unit",
            "reorder_level": max(0, int(data.reorder_level or 0)),
            "unit_cost": float(data.unit_cost or 0),
            "notes": (data.notes or "").strip() or None,
        }

    @staticmethod
    def _validate(data: ItemInput) -> None:
        if not data.name or not data.name.strip():
            raise ValidationError("Item name is required.", field="name")
