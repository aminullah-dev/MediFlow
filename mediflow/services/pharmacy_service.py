"""Pharmacy service: medication catalogue, stock batches and dispensing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select

from mediflow.core.exceptions import BusinessRuleError, ValidationError
from mediflow.core.logging_config import get_logger
from mediflow.data.base import local_today
from mediflow.data.database import Database
from mediflow.data.models.pharmacy import Medication, StockBatch
from mediflow.services.authz import require

log = get_logger("services.pharmacy")

EXPIRY_WARNING_DAYS = 30


@dataclass(slots=True)
class MedicationInput:
    name: str
    generic_name: str | None = None
    form: str | None = None
    strength: str | None = None
    barcode: str | None = None
    unit: str = "unit"
    reorder_level: int = 0
    sale_price: float = 0.0
    notes: str | None = None


@dataclass(slots=True)
class MedicationDTO:
    id: int
    name: str
    generic_name: str | None
    form: str | None
    strength: str | None
    barcode: str | None
    unit: str
    reorder_level: int
    sale_price: float
    notes: str | None
    stock_on_hand: int
    earliest_expiry: date | None

    @property
    def is_low(self) -> bool:
        return self.stock_on_hand <= self.reorder_level

    @property
    def is_out(self) -> bool:
        return self.stock_on_hand <= 0

    @property
    def is_expiring(self) -> bool:
        if self.earliest_expiry is None:
            return False
        return self.earliest_expiry <= local_today() + timedelta(days=EXPIRY_WARNING_DAYS)


class PharmacyService:
    def __init__(self, db: Database):
        self._db = db

    # -- catalogue ----------------------------------------------------------
    def list_medications(self, term: str = "") -> list[MedicationDTO]:
        term = (term or "").strip()
        with self._db.unit_of_work() as session:
            stmt = select(Medication).where(Medication.is_deleted.is_(False))
            if term:
                like = f"%{term}%"
                stmt = stmt.where(
                    Medication.name.ilike(like)
                    | Medication.generic_name.ilike(like)
                    | Medication.barcode.ilike(like)
                )
            stmt = stmt.order_by(Medication.name)
            return [self._to_dto(m) for m in session.execute(stmt).scalars().all()]

    def get(self, medication_id: int) -> MedicationDTO:
        with self._db.unit_of_work() as session:
            med = session.get(Medication, medication_id)
            if med is None:
                raise ValidationError("Medication not found.")
            return self._to_dto(med)

    @require("pharmacy.manage")
    def create(self, data: MedicationInput) -> int:
        self._validate(data)
        with self._db.unit_of_work() as session:
            med = Medication(**self._fields(data))
            session.add(med)
            session.flush()
            log.info("Created medication %s (id=%s)", med.name, med.id)
            return med.id

    @require("pharmacy.manage")
    def update(self, medication_id: int, data: MedicationInput) -> None:
        self._validate(data)
        with self._db.unit_of_work() as session:
            med = session.get(Medication, medication_id)
            if med is None:
                raise ValidationError("Medication not found.")
            for key, value in self._fields(data).items():
                setattr(med, key, value)

    @require("pharmacy.manage")
    def delete(self, medication_id: int) -> None:
        with self._db.unit_of_work() as session:
            med = session.get(Medication, medication_id)
            if med is not None:
                med.soft_delete()

    # -- stock --------------------------------------------------------------
    @require("pharmacy.purchase")
    def add_stock(self, medication_id: int, quantity: int, *,
                  batch_number: str | None = None, expiry_date: date | None = None,
                  cost_price: float = 0.0) -> None:
        if quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.", field="quantity")
        with self._db.unit_of_work() as session:
            med = session.get(Medication, medication_id)
            if med is None:
                raise ValidationError("Medication not found.")
            batch = StockBatch(
                medication_id=medication_id,
                batch_number=(batch_number or "").strip() or None,
                quantity=quantity,
                expiry_date=expiry_date,
                cost_price=cost_price,
                received_on=local_today(),  # local calendar date, matching expiry_date
            )
            session.add(batch)
            log.info("Added %s units to medication id=%s", quantity, medication_id)

    @require("pharmacy.sell")
    def dispense(self, medication_id: int, quantity: int) -> None:
        if quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.", field="quantity")
        with self._db.unit_of_work() as session:
            med = session.get(Medication, medication_id)
            if med is None:
                raise ValidationError("Medication not found.")
            batches = [b for b in med.batches if not b.is_deleted and b.quantity > 0]
            available = sum(b.quantity for b in batches)
            if quantity > available:
                raise BusinessRuleError(
                    f"Only {available} units in stock; cannot dispense {quantity}."
                )
            # First-expiry-first-out: consume nearest-expiry batches first.
            remaining = quantity
            for batch in sorted(batches, key=lambda b: (b.expiry_date is None, b.expiry_date)):
                if remaining <= 0:
                    break
                take = min(batch.quantity, remaining)
                batch.quantity -= take
                remaining -= take
            log.info("Dispensed %s units of medication id=%s", quantity, medication_id)

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _to_dto(med: Medication) -> MedicationDTO:
        live = [b for b in med.batches if not b.is_deleted and b.quantity > 0]
        stock = sum(b.quantity for b in live)
        expiries = [b.expiry_date for b in live if b.expiry_date is not None]
        return MedicationDTO(
            id=med.id,
            name=med.name,
            generic_name=med.generic_name,
            form=med.form,
            strength=med.strength,
            barcode=med.barcode,
            unit=med.unit,
            reorder_level=med.reorder_level,
            sale_price=float(med.sale_price or 0),
            notes=med.notes,
            stock_on_hand=stock,
            earliest_expiry=min(expiries) if expiries else None,
        )

    @staticmethod
    def _fields(data: MedicationInput) -> dict:
        return {
            "name": data.name.strip(),
            "generic_name": (data.generic_name or "").strip() or None,
            "form": (data.form or "").strip() or None,
            "strength": (data.strength or "").strip() or None,
            "barcode": (data.barcode or "").strip() or None,
            "unit": (data.unit or "unit").strip() or "unit",
            "reorder_level": max(0, int(data.reorder_level or 0)),
            "sale_price": float(data.sale_price or 0),
            "notes": (data.notes or "").strip() or None,
        }

    @staticmethod
    def _validate(data: MedicationInput) -> None:
        if not data.name or not data.name.strip():
            raise ValidationError("Medication name is required.", field="name")
