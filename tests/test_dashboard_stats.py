"""What the dashboard counts, and what it deliberately does not.

Every figure here is a database aggregate, so the tests seed real rows and
assert the number that comes back. The interesting cases are the exclusions:
an expired batch with nothing left in it, a supply nobody set a reorder level
for, an invoice that is already paid. Each of those would inflate an alert
count into noise, and a dashboard whose alerts are noise gets ignored — which
is worse than not having them.
"""
from __future__ import annotations

from datetime import timedelta
from itertools import pairwise

import pytest

from mediflow.core.constants import (
    AppointmentStatus,
    InvoiceStatus,
    LabRequestStatus,
)
from mediflow.data.base import local_now, local_today, utcnow
from mediflow.data.database import Database, current_user_id
from mediflow.data.models.appointment import Appointment
from mediflow.data.models.billing import Invoice, Payment
from mediflow.data.models.inventory import InventoryItem
from mediflow.data.models.laboratory import LabRequest, LabTest
from mediflow.data.models.patient import Patient
from mediflow.data.models.pharmacy import Medication, StockBatch
from mediflow.data.schema import create_all
from mediflow.services.dashboard_service import (
    EXPIRY_HORIZON_DAYS,
    TREND_DAYS,
    DashboardService,
)


@pytest.fixture()
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'dash.db'}")
    create_all(database)
    current_user_id.set(None)
    yield database
    database.dispose()


@pytest.fixture()
def stats(db):
    return lambda: DashboardService(db).snapshot()


def _patient(session, name: str = "Test") -> Patient:
    patient = Patient(first_name=name, last_name="Patient", mrn=f"MRN-{name}")
    session.add(patient)
    session.flush()
    return patient


# ── medication expiry ────────────────────────────────────────────────────────

def test_a_batch_expiring_inside_the_horizon_is_counted(db, stats):
    with db.unit_of_work() as session:
        med = Medication(name="Amoxicillin")
        session.add(med)
        session.flush()
        session.add(StockBatch(medication_id=med.id, quantity=40,
                               expiry_date=local_today() + timedelta(days=30)))

    assert stats().expiring_batches == 1


def test_an_empty_expired_batch_is_not_an_alert(db, stats):
    """It is a record, not a problem. Counting it trains people to ignore the number."""
    with db.unit_of_work() as session:
        med = Medication(name="Amoxicillin")
        session.add(med)
        session.flush()
        session.add(StockBatch(medication_id=med.id, quantity=0,
                               expiry_date=local_today() - timedelta(days=5)))

    assert stats().expiring_batches == 0


def test_a_batch_beyond_the_horizon_and_one_with_no_date_are_not_counted(db, stats):
    with db.unit_of_work() as session:
        med = Medication(name="Paracetamol")
        session.add(med)
        session.flush()
        session.add(StockBatch(medication_id=med.id, quantity=10,
                               expiry_date=local_today()
                               + timedelta(days=EXPIRY_HORIZON_DAYS + 1)))
        session.add(StockBatch(medication_id=med.id, quantity=10, expiry_date=None))

    assert stats().expiring_batches == 0


# ── stock ────────────────────────────────────────────────────────────────────

def test_a_medication_with_no_stock_left_counts_as_out(db, stats):
    with db.unit_of_work() as session:
        empty = Medication(name="Empty")
        stocked = Medication(name="Stocked")
        session.add_all([empty, stocked])
        session.flush()
        session.add(StockBatch(medication_id=empty.id, quantity=0))
        session.add(StockBatch(medication_id=stocked.id, quantity=12))

    assert stats().out_of_stock_medications == 1


def test_an_inactive_medication_is_not_reported_as_out_of_stock(db, stats):
    with db.unit_of_work() as session:
        session.add(Medication(name="Discontinued", is_active=False))

    assert stats().out_of_stock_medications == 0


def test_supplies_at_or_below_their_reorder_level_are_low(db, stats):
    with db.unit_of_work() as session:
        session.add_all([
            InventoryItem(name="Gloves", quantity=5, reorder_level=10),   # below
            InventoryItem(name="Masks", quantity=10, reorder_level=10),   # at
            InventoryItem(name="Syringes", quantity=99, reorder_level=10),
        ])

    assert stats().low_stock_items == 2


def test_a_supply_with_no_reorder_level_never_reports_low(db, stats):
    """Otherwise every item nobody configured shows low at zero, drowning the real ones."""
    with db.unit_of_work() as session:
        session.add(InventoryItem(name="Unconfigured", quantity=0, reorder_level=0))

    assert stats().low_stock_items == 0


# ── lab and billing ──────────────────────────────────────────────────────────

def test_only_unresulted_lab_requests_are_open(db, stats):
    with db.unit_of_work() as session:
        patient = _patient(session)
        test = LabTest(name="CBC")
        session.add(test)
        session.flush()
        for status in (LabRequestStatus.REQUESTED, LabRequestStatus.SAMPLE_COLLECTED,
                       LabRequestStatus.IN_PROGRESS, LabRequestStatus.COMPLETED,
                       LabRequestStatus.CANCELLED):
            session.add(LabRequest(patient_id=patient.id, lab_test_id=test.id,
                                   status=status.value))

    assert stats().open_lab_requests == 3


def test_unpaid_invoices_are_counted_by_what_they_still_owe(db, stats):
    with db.unit_of_work() as session:
        patient = _patient(session)
        session.add_all([
            Invoice(patient_id=patient.id, invoice_number="INV-1",
                    status=InvoiceStatus.UNPAID.value, total=100, paid_amount=0),
            Invoice(patient_id=patient.id, invoice_number="INV-2",
                    status=InvoiceStatus.PARTIALLY_PAID.value, total=200, paid_amount=50),
            Invoice(patient_id=patient.id, invoice_number="INV-3",
                    status=InvoiceStatus.PAID.value, total=500, paid_amount=500),
        ])

    snapshot = stats()
    assert snapshot.unpaid_invoices == 2
    assert snapshot.outstanding_total == pytest.approx(250.0)   # 100 + 150, not 300


def test_revenue_is_money_collected_today_not_invoices_raised(db, stats):
    """An invoice raised today and paid next month is not today's revenue."""
    with db.unit_of_work() as session:
        patient = _patient(session)
        invoice = Invoice(patient_id=patient.id, invoice_number="INV-9",
                          status=InvoiceStatus.PARTIALLY_PAID.value,
                          total=1000, paid_amount=120)
        session.add(invoice)
        session.flush()
        session.add(Payment(invoice_id=invoice.id, amount=70, method="cash",
                            paid_at=utcnow()))
        session.add(Payment(invoice_id=invoice.id, amount=50, method="cash",
                            paid_at=utcnow()))
        session.add(Payment(invoice_id=invoice.id, amount=900, method="cash",
                            paid_at=utcnow() - timedelta(days=3)))

    assert stats().revenue_today == pytest.approx(120.0)


# ── the headline number and the trend ───────────────────────────────────────

def test_alert_total_is_the_sum_of_the_things_wanting_attention(db, stats):
    with db.unit_of_work() as session:
        patient = _patient(session)
        med = Medication(name="Expiring")
        session.add(med)
        session.flush()
        session.add(StockBatch(medication_id=med.id, quantity=5,
                               expiry_date=local_today() + timedelta(days=10)))
        session.add(InventoryItem(name="Gloves", quantity=1, reorder_level=10))
        session.add(Invoice(patient_id=patient.id, invoice_number="INV-1",
                            status=InvoiceStatus.UNPAID.value, total=10, paid_amount=0))

    snapshot = stats()
    # expiring 1 + out-of-stock 0 + low 1 + lab 0 + unpaid 1
    assert snapshot.alert_total == 3


def test_the_trend_covers_every_day_including_the_empty_ones(db, stats):
    """A line that skips a closed day draws straight across it and reports it busy."""
    with db.unit_of_work() as session:
        patient = _patient(session)
        session.add(Appointment(patient_id=patient.id, scheduled_start=local_now(),
                                status=AppointmentStatus.COMPLETED.value))
        session.add(Appointment(patient_id=patient.id, scheduled_start=local_now(),
                                status=AppointmentStatus.BOOKED.value))

    trend = stats().trend
    assert len(trend) == TREND_DAYS
    assert trend[-1].day == local_today()
    assert trend[-1].appointments == 2
    assert trend[-1].completed == 1
    assert all(point.appointments == 0 for point in trend[:-1])


def test_the_trend_window_ends_today_and_is_contiguous(db, stats):
    days = [point.day for point in stats().trend]

    assert days[-1] == local_today()
    assert days == sorted(days)
    assert all((b - a).days == 1 for a, b in pairwise(days))


# ── the web chart's geometry ─────────────────────────────────────────────────
# Laid out server-side, so the rules that keep a chart honest are testable
# rather than a matter of looking at it.

def _points(values: list[int]) -> list:
    from mediflow.services.dashboard_service import DayPoint

    start = local_today() - timedelta(days=len(values) - 1)
    return [DayPoint(day=start + timedelta(days=i), appointments=v)
            for i, v in enumerate(values)]


def test_the_y_scale_starts_at_zero():
    """Cropping the baseline to the data's own minimum is how a chart lies."""
    from mediflow.web.charts import build_trend

    chart = build_trend(_points([11, 12, 13]))
    lowest = max(mark.y for mark in chart.marks)     # y grows downward

    # 11 is not on the floor: it is 11/13 of the way up, not 0.
    assert lowest < chart.baseline
    assert chart.marks[-1].y < chart.marks[0].y      # 13 sits above 11


def test_a_zero_day_sits_exactly_on_the_baseline():
    from mediflow.web.charts import build_trend

    chart = build_trend(_points([0, 5, 0]))

    assert chart.marks[0].y == chart.baseline
    assert chart.marks[2].y == chart.baseline


def test_only_the_peak_and_the_last_day_are_labelled():
    """A number on every point is how a fourteen-point line becomes unreadable."""
    from mediflow.web.charts import build_trend

    chart = build_trend(_points([3, 9, 4, 6]))
    labelled = [(mark.value, mark.label) for mark in chart.marks if mark.label]

    assert labelled == [(9, "9"), (6, "6")]


def test_a_flat_run_of_zeros_is_reported_as_empty_not_drawn_flat():
    from mediflow.web.charts import build_trend

    assert build_trend(_points([0, 0, 0])).is_empty
    assert not build_trend(_points([0, 1, 0])).is_empty


def test_a_single_peak_does_not_touch_the_ceiling_or_overflow():
    from mediflow.web.charts import build_trend

    chart = build_trend(_points([0, 1]))

    assert all(0 <= mark.y <= chart.baseline for mark in chart.marks)
    assert all(0 <= mark.x <= chart.width for mark in chart.marks)
