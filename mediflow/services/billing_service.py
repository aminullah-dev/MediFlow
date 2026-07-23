"""Billing service: invoices, line items and payments."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select

from mediflow.core.constants import InvoiceStatus, PaymentMethod
from mediflow.core.exceptions import BusinessRuleError, ValidationError
from mediflow.core.logging_config import get_logger
from mediflow.data.base import utcnow
from mediflow.data.database import Database
from mediflow.data.models.billing import Invoice, InvoiceLine, Payment
from mediflow.data.repositories.patient_repository import PatientRepository
from mediflow.services.authz import require, require_any

log = get_logger("services.billing")


@dataclass(slots=True)
class LineInput:
    description: str
    quantity: int = 1
    unit_price: float = 0.0


@dataclass(slots=True)
class InvoiceInput:
    patient_id: int
    lines: list[LineInput] = field(default_factory=list)
    discount: float = 0.0
    tax: float = 0.0
    notes: str | None = None


@dataclass(slots=True)
class InvoiceDTO:
    id: int
    invoice_number: str
    patient_id: int
    patient_name: str
    mrn: str
    status: str
    issued_at: datetime
    total: float
    paid_amount: float

    @property
    def balance(self) -> float:
        return round(self.total - self.paid_amount, 2)

    @property
    def is_open(self) -> bool:
        return self.status in (InvoiceStatus.UNPAID.value,
                               InvoiceStatus.PARTIALLY_PAID.value)


@dataclass(slots=True)
class LineDTO:
    description: str
    quantity: int
    unit_price: float
    line_total: float


@dataclass(slots=True)
class PaymentDTO:
    amount: float
    method: str
    paid_at: datetime
    reference: str | None


@dataclass(slots=True)
class InvoiceDetailDTO:
    invoice: InvoiceDTO
    subtotal: float
    discount: float
    tax: float
    notes: str | None
    lines: list[LineDTO]
    payments: list[PaymentDTO]


class BillingService:
    def __init__(self, db: Database):
        self._db = db

    # -- commands -----------------------------------------------------------
    @require("billing.create")
    def create_invoice(self, data: InvoiceInput) -> int:
        clean_lines = [
            (line.description.strip(), max(1, int(line.quantity or 1)), float(line.unit_price or 0))
            for line in data.lines if line.description and line.description.strip()
        ]
        if not clean_lines:
            raise ValidationError("Add at least one line item.", field="lines")
        subtotal = round(sum(qty * price for _d, qty, price in clean_lines), 2)
        discount = max(0.0, float(data.discount or 0))
        tax = max(0.0, float(data.tax or 0))
        total = round(subtotal - discount + tax, 2)
        if total < 0:
            raise ValidationError("Discount cannot exceed the subtotal.", field="discount")

        with self._db.unit_of_work() as session:
            PatientRepository(session).get_or_raise(data.patient_id)
            number = self._next_number(session)
            invoice = Invoice(
                patient_id=data.patient_id,
                invoice_number=number,
                status=(InvoiceStatus.PAID.value if total == 0 else InvoiceStatus.UNPAID.value),
                issued_at=utcnow(),
                subtotal=subtotal,
                discount=discount,
                tax=tax,
                total=total,
                paid_amount=0,
                notes=(data.notes or "").strip() or None,
            )
            for desc, qty, price in clean_lines:
                invoice.lines.append(InvoiceLine(
                    description=desc, quantity=qty, unit_price=price,
                    line_total=round(qty * price, 2),
                ))
            session.add(invoice)
            session.flush()
            log.info("Created invoice %s total=%s", number, total)
            return invoice.id

    @require("billing.payment")
    def add_payment(self, invoice_id: int, amount: float,
                    method: PaymentMethod, *, reference: str | None = None) -> None:
        amount = round(float(amount or 0), 2)
        if amount <= 0:
            raise ValidationError("Payment amount must be positive.", field="amount")
        with self._db.unit_of_work() as session:
            invoice = session.get(Invoice, invoice_id)
            if invoice is None:
                raise ValidationError("Invoice not found.")
            if invoice.status == InvoiceStatus.CANCELLED.value:
                raise BusinessRuleError("Cannot pay a cancelled invoice.")
            balance = round(float(invoice.total) - float(invoice.paid_amount), 2)
            if amount > balance:
                raise BusinessRuleError(f"Payment exceeds the outstanding balance ({balance}).")
            invoice.paid_amount = round(float(invoice.paid_amount) + amount, 2)
            invoice.payments.append(Payment(
                amount=amount, method=method.value, paid_at=utcnow(),
                reference=(reference or "").strip() or None,
            ))
            invoice.status = (
                InvoiceStatus.PAID.value
                if invoice.paid_amount >= float(invoice.total)
                else InvoiceStatus.PARTIALLY_PAID.value
            )
            log.info("Payment %s on invoice %s", amount, invoice.invoice_number)

    @require_any("billing.create", "billing.refund")
    def cancel_invoice(self, invoice_id: int) -> None:
        with self._db.unit_of_work() as session:
            invoice = session.get(Invoice, invoice_id)
            if invoice is None:
                raise ValidationError("Invoice not found.")
            invoice.status = InvoiceStatus.CANCELLED.value

    # -- queries ------------------------------------------------------------
    def list_invoices(self, term: str = "", *, limit: int = 200) -> list[InvoiceDTO]:
        term = (term or "").strip()
        with self._db.unit_of_work() as session:
            stmt = select(Invoice).where(Invoice.is_deleted.is_(False))
            stmt = stmt.order_by(Invoice.issued_at.desc()).limit(limit)
            rows = session.execute(stmt).scalars().all()
            result = []
            for inv in rows:
                dto = self._to_dto(inv)
                if term:
                    haystack = f"{dto.invoice_number} {dto.patient_name} {dto.mrn}".lower()
                    if term.lower() not in haystack:
                        continue
                result.append(dto)
            return result

    def get_detail(self, invoice_id: int) -> InvoiceDetailDTO:
        with self._db.unit_of_work() as session:
            inv = session.get(Invoice, invoice_id)
            if inv is None:
                raise ValidationError("Invoice not found.")
            return InvoiceDetailDTO(
                invoice=self._to_dto(inv),
                subtotal=float(inv.subtotal or 0),
                discount=float(inv.discount or 0),
                tax=float(inv.tax or 0),
                notes=inv.notes,
                lines=[LineDTO(line.description, line.quantity, float(line.unit_price or 0),
                               float(line.line_total or 0))
                       for line in inv.lines],
                payments=[PaymentDTO(float(p.amount or 0), p.method, p.paid_at, p.reference)
                          for p in sorted(inv.payments, key=lambda p: p.paid_at)],
            )

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _next_number(session) -> str:
        year = utcnow().year
        prefix = f"INV-{year}-"
        count = session.execute(
            select(func.count()).select_from(Invoice).where(Invoice.invoice_number.like(f"{prefix}%"))
        ).scalar_one()
        return f"{prefix}{count + 1:06d}"

    @staticmethod
    def _to_dto(inv: Invoice) -> InvoiceDTO:
        patient = inv.patient
        return InvoiceDTO(
            id=inv.id,
            invoice_number=inv.invoice_number,
            patient_id=inv.patient_id,
            patient_name=patient.full_name if patient else "—",
            mrn=patient.mrn if patient else "",
            status=inv.status,
            issued_at=inv.issued_at,
            total=float(inv.total or 0),
            paid_amount=float(inv.paid_amount or 0),
        )
