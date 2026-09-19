"""Read-model service powering the dashboard.

Aggregates the day's figures into a single snapshot so the dashboard issues one
round trip rather than one query per tile.

What belongs here
-----------------
Two different jobs, deliberately separated because they answer different
questions for different people:

*Counters* say what happened — patients, appointments, revenue. They are the
report a manager reads.

*Alerts* say what is wrong and unattended — medication about to expire, stock
below its reorder level, lab results nobody has entered, invoices nobody has
collected. Every one of these was already in the database, computed nowhere and
shown to no one: the receptionist could only find an expiring batch by opening
the pharmacy module and looking. A dashboard that leads with counters and
buries the alerts is a report, not a dashboard.

Every figure is a database aggregate. Fetching the rows and counting them in
Python would be correct today and quietly quadratic once a clinic has three
years of invoices.

A note on which "today"
-----------------------
``scheduled_start`` holds user-entered wall-clock times, so an appointment's day
is the local calendar day. ``paid_at``, ``requested_at`` and ``issued_at`` are
stamped with ``utcnow()``, so their day is that same local window expressed in
UTC. Using one helper for both is the bug that makes revenue jump at midnight
plus the timezone offset.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import Float, case, cast, func, select

from mediflow.core.constants import AppointmentStatus, InvoiceStatus, LabRequestStatus
from mediflow.data.base import (
    local_day_bounds,
    local_day_bounds_utc,
    local_today,
)
from mediflow.data.database import Database
from mediflow.data.models.appointment import Appointment
from mediflow.data.models.billing import Invoice, Payment
from mediflow.data.models.inventory import InventoryItem
from mediflow.data.models.laboratory import LabRequest
from mediflow.data.models.pharmacy import Medication, StockBatch
from mediflow.data.repositories.patient_repository import PatientRepository

# How far ahead a batch counts as "expiring". Ninety days is the window in which
# a clinic can still use or return stock; shorter and the warning arrives too
# late to act on, longer and every batch is permanently amber.
EXPIRY_HORIZON_DAYS = 90

# Days of history behind the trend chart. Two weeks shows the working rhythm —
# including which weekday is quiet — without turning into a report.
TREND_DAYS = 14

_OPEN_INVOICE_STATUSES = (InvoiceStatus.UNPAID.value, InvoiceStatus.PARTIALLY_PAID.value)
_OPEN_LAB_STATUSES = (
    LabRequestStatus.REQUESTED.value,
    LabRequestStatus.SAMPLE_COLLECTED.value,
    LabRequestStatus.IN_PROGRESS.value,
)


@dataclass(slots=True)
class DayPoint:
    """One day on the trend chart."""

    day: date
    appointments: int = 0
    completed: int = 0


@dataclass(slots=True)
class DashboardStats:
    # -- counters: what happened -------------------------------------------
    total_patients: int = 0
    patients_today: int = 0
    appointments_today: int = 0
    waiting_now: int = 0
    completed_today: int = 0
    revenue_today: float = 0.0

    # -- alerts: what is wrong and unattended -------------------------------
    expiring_batches: int = 0
    out_of_stock_medications: int = 0
    low_stock_items: int = 0
    open_lab_requests: int = 0
    unpaid_invoices: int = 0
    outstanding_total: float = 0.0

    # -- trend --------------------------------------------------------------
    trend: list[DayPoint] = field(default_factory=list)

    @property
    def alert_total(self) -> int:
        """How many things want attention, for the one number the page leads with."""
        return (self.expiring_batches + self.out_of_stock_medications
                + self.low_stock_items + self.open_lab_requests + self.unpaid_invoices)


class DashboardService:
    def __init__(self, db: Database):
        self._db = db

    def snapshot(self, now: datetime | None = None) -> DashboardStats:
        day_start, day_end = local_day_bounds()
        utc_start, utc_end = local_day_bounds_utc()
        today = local_today()

        with self._db.unit_of_work() as session:
            patients = PatientRepository(session)

            def appt_count(*conditions) -> int:
                stmt = select(func.count()).select_from(Appointment).where(
                    Appointment.is_deleted.is_(False),
                    Appointment.scheduled_start >= day_start,
                    Appointment.scheduled_start < day_end,
                    *conditions,
                )
                return int(session.execute(stmt).scalar_one())

            return DashboardStats(
                total_patients=patients.count(),
                patients_today=patients.registered_today(),
                appointments_today=appt_count(),
                waiting_now=appt_count(
                    Appointment.status.in_([AppointmentStatus.CHECKED_IN.value,
                                            AppointmentStatus.WAITLISTED.value])
                ),
                completed_today=appt_count(
                    Appointment.status == AppointmentStatus.COMPLETED.value
                ),
                revenue_today=self._revenue(session, utc_start, utc_end),
                expiring_batches=self._expiring_batches(session, today),
                out_of_stock_medications=self._out_of_stock(session),
                low_stock_items=self._low_stock_items(session),
                open_lab_requests=self._open_lab_requests(session),
                unpaid_invoices=self._unpaid_invoices(session),
                outstanding_total=self._outstanding(session),
                trend=self._trend(session, today),
            )

    # -- counters -----------------------------------------------------------
    @staticmethod
    def _revenue(session, utc_start: datetime, utc_end: datetime) -> float:
        """Money actually collected today — payments, not invoices raised.

        An invoice issued today and paid next month is not today's revenue, and
        one issued last week and settled this morning is. Summing invoice totals
        would report the first and miss the second.
        """
        stmt = select(func.coalesce(func.sum(cast(Payment.amount, Float)), 0.0)).where(
            Payment.is_deleted.is_(False),
            Payment.paid_at >= utc_start,
            Payment.paid_at < utc_end,
        )
        return float(session.execute(stmt).scalar_one())

    # -- alerts -------------------------------------------------------------
    @staticmethod
    def _expiring_batches(session, today: date) -> int:
        """Batches with stock left that expire within the horizon — or already did.

        ``quantity > 0`` is the whole point: an empty expired batch is a record,
        not a problem, and counting it would train people to ignore the number.
        """
        horizon = today + timedelta(days=EXPIRY_HORIZON_DAYS)
        stmt = select(func.count()).select_from(StockBatch).where(
            StockBatch.is_deleted.is_(False),
            StockBatch.quantity > 0,
            StockBatch.expiry_date.is_not(None),
            StockBatch.expiry_date <= horizon,
        )
        return int(session.execute(stmt).scalar_one())

    @staticmethod
    def _out_of_stock(session) -> int:
        """Active medications whose remaining quantity across all batches is zero."""
        on_hand = (
            select(func.coalesce(func.sum(StockBatch.quantity), 0))
            .where(StockBatch.medication_id == Medication.id,
                   StockBatch.is_deleted.is_(False))
            .correlate(Medication)
            .scalar_subquery()
        )
        stmt = select(func.count()).select_from(Medication).where(
            Medication.is_deleted.is_(False),
            Medication.is_active.is_(True),
            on_hand <= 0,
        )
        return int(session.execute(stmt).scalar_one())

    @staticmethod
    def _low_stock_items(session) -> int:
        """Supplies at or below their own reorder level.

        ``reorder_level > 0`` excludes items nobody has set a level for: those
        would otherwise all report low at zero and drown the real ones.
        """
        stmt = select(func.count()).select_from(InventoryItem).where(
            InventoryItem.is_deleted.is_(False),
            InventoryItem.is_active.is_(True),
            InventoryItem.reorder_level > 0,
            InventoryItem.quantity <= InventoryItem.reorder_level,
        )
        return int(session.execute(stmt).scalar_one())

    @staticmethod
    def _open_lab_requests(session) -> int:
        """Requests raised but not yet resulted or cancelled."""
        stmt = select(func.count()).select_from(LabRequest).where(
            LabRequest.is_deleted.is_(False),
            LabRequest.status.in_(_OPEN_LAB_STATUSES),
        )
        return int(session.execute(stmt).scalar_one())

    @staticmethod
    def _unpaid_invoices(session) -> int:
        stmt = select(func.count()).select_from(Invoice).where(
            Invoice.is_deleted.is_(False),
            Invoice.status.in_(_OPEN_INVOICE_STATUSES),
        )
        return int(session.execute(stmt).scalar_one())

    @staticmethod
    def _outstanding(session) -> float:
        """What those invoices still owe, not what they were billed."""
        stmt = select(func.coalesce(
            func.sum(cast(Invoice.total, Float) - cast(Invoice.paid_amount, Float)), 0.0
        )).where(
            Invoice.is_deleted.is_(False),
            Invoice.status.in_(_OPEN_INVOICE_STATUSES),
        )
        return float(session.execute(stmt).scalar_one())

    # -- trend --------------------------------------------------------------
    @staticmethod
    def _trend(session, today: date) -> list[DayPoint]:
        """Appointments per day over the trend window, grouped in the database.

        Grouped by the date part of the local wall-clock column, so the buckets
        line up with the days a clinic recognises. Days with no appointments are
        filled in here rather than left out: a line chart that skips empty days
        draws a straight segment across a closed Friday and reports it as busy.
        """
        first = today - timedelta(days=TREND_DAYS - 1)
        window_start, _ = local_day_bounds(first)
        _, window_end = local_day_bounds(today)

        completed = case(
            (Appointment.status == AppointmentStatus.COMPLETED.value, 1), else_=0
        )
        day_column = func.date(Appointment.scheduled_start)
        stmt = (
            select(day_column, func.count(), func.coalesce(func.sum(completed), 0))
            .where(
                Appointment.is_deleted.is_(False),
                Appointment.scheduled_start >= window_start,
                Appointment.scheduled_start < window_end,
            )
            .group_by(day_column)
        )
        rows = {
            str(day): (int(total), int(done))
            for day, total, done in session.execute(stmt)
        }

        points: list[DayPoint] = []
        for offset in range(TREND_DAYS):
            day = first + timedelta(days=offset)
            total, done = rows.get(day.isoformat(), (0, 0))
            points.append(DayPoint(day=day, appointments=total, completed=done))
        return points
