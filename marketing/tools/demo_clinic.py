"""Seed a fictional clinic so the marketing screenshots show a working day.

Every screenshot in ``marketing/images/`` is the real PySide6 application, not
a mockup — which is the only way a clinic manager can tell the difference. That
only works if the database has something in it, so this module fills one with a
plausible Tuesday: a dozen patients, appointments in each state, stock that is
about to expire, lab work waiting on a result, and two weeks of invoices behind
it so the dashboard trend has a shape.

The names are common Afghan given names used as placeholders. No row here
describes a real person, and nothing in this module is imported by the
application itself.
"""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

from mediflow.core.constants import (
    AppointmentStatus,
    BloodGroup,
    Gender,
    InvoiceStatus,
    LabRequestStatus,
    PaymentMethod,
)
from mediflow.data.base import local_now, local_today, utcnow
from mediflow.data.database import Database
from mediflow.data.models.appointment import Appointment, QueueToken
from mediflow.data.models.billing import Invoice, Payment
from mediflow.data.models.inventory import InventoryItem
from mediflow.data.models.laboratory import LabRequest, LabTest
from mediflow.data.models.patient import Patient
from mediflow.data.models.pharmacy import Medication, StockBatch

# (first, last, father, gender, province) — placeholder names, not real people.
_PEOPLE = [
    ("زرغونه", "احمدزی", "عبدالغفور", Gender.FEMALE, "کابل"),
    ("عبدالرحمن", "نوری", "محمدنعیم", Gender.MALE, "کابل"),
    ("نجیبه", "حکیمی", "سیداکبر", Gender.FEMALE, "پروان"),
    ("احمدشاه", "کریمی", "گل‌محمد", Gender.MALE, "لوگر"),
    ("مریم", "صافی", "نصرالله", Gender.FEMALE, "ننگرهار"),
    ("بسم‌الله", "اکبری", "عزیزالله", Gender.MALE, "بامیان"),
    ("فرشته", "رحیمی", "محمدآصف", Gender.FEMALE, "کابل"),
    ("شیرآغا", "پوپل", "دین‌محمد", Gender.MALE, "قندهار"),
    ("حلیمه", "یوسفی", "عبدالقیوم", Gender.FEMALE, "هرات"),
    ("عبدالباسط", "منگل", "شاه‌ولی", Gender.MALE, "پکتیا"),
    ("پروین", "امیری", "غلام‌سخی", Gender.FEMALE, "کابل"),
    ("نورمحمد", "ستانکزی", "عبدالجبار", Gender.MALE, "وردک"),
]

# Extras on top of the catalogue MediFlow seeds itself. Generic names stay in
# Latin script on purpose: that is how they are printed on the boxes a clinic
# actually receives, and a half-transliterated shelf list is harder to read than
# either language alone. The chrome around them is what gets translated.
_EXTRA_MEDICATIONS = [
    # (name, generic, form, strength, unit, reorder_level, sale_price)
    ("Albendazole", "Albendazole", "Tablet", "400 mg", "tablet", 100, 20.0),
    ("Ferrous Sulfate", "Ferrous Sulfate", "Tablet", "200 mg", "tablet", 300, 8.0),
    ("Ciprofloxacin", "Ciprofloxacin", "Tablet", "500 mg", "tablet", 150, 18.0),
]




def populate(database: Database, *, doctor_id: int | None) -> None:
    """Fill ``database`` with one clinic's worth of believable activity."""
    rng = random.Random(20260919)  # fixed: the same screenshot every rebuild
    today = local_today()
    now = local_now()

    with database.unit_of_work() as session:
        patients = _add_patients(session, rng, today)
        _add_appointments(session, rng, patients, doctor_id, today, now)
        _add_pharmacy(session, rng, today)
        _add_laboratory(session, rng, patients, doctor_id)
        _add_inventory(session, rng)
        _add_billing(session, rng, patients, today)


def _add_patients(session, rng: random.Random, today: date) -> list[Patient]:
    patients: list[Patient] = []
    for index, (first, last, father, gender, province) in enumerate(_PEOPLE, start=1):
        age = rng.randint(2, 68)
        patient = Patient(
            mrn=f"MF-{today.year}-{index:04d}",
            first_name=first,
            last_name=last,
            father_name=father,
            gender=gender,
            date_of_birth=today - timedelta(days=age * 365 + rng.randint(0, 364)),
            blood_group=rng.choice(list(BloodGroup)),
            phone=f"07{rng.randint(10_000_000, 99_999_999)}",
            province=province,
        )
        session.add(patient)
        patients.append(patient)
    session.flush()
    return patients


def _add_appointments(session, rng, patients, doctor_id, today: date, now: datetime) -> None:
    """Today's list, spread across the statuses the reception board shows."""
    plan = [
        (AppointmentStatus.COMPLETED, 8), (AppointmentStatus.COMPLETED, 9),
        (AppointmentStatus.COMPLETED, 9), (AppointmentStatus.IN_CONSULTATION, 10),
        (AppointmentStatus.CHECKED_IN, 10), (AppointmentStatus.CHECKED_IN, 11),
        (AppointmentStatus.BOOKED, 11), (AppointmentStatus.BOOKED, 13),
        (AppointmentStatus.BOOKED, 14), (AppointmentStatus.BOOKED, 15),
    ]
    reasons = ["تب و سرفه", "معاینه دوره‌ای", "درد شکم", "کنترل فشار خون",
               "واکسین طفل", "زخم دست", "سردردی مزمن", "معاینه حاملگی"]
    issued = 0
    for slot, (status, hour) in enumerate(plan):
        start = datetime.combine(today, time(hour, (slot % 4) * 15))
        appointment = Appointment(
            patient_id=patients[slot % len(patients)].id,
            doctor_id=doctor_id,
            scheduled_start=start,
            scheduled_end=start + timedelta(minutes=15),
            status=status,
            reason=rng.choice(reasons),
            is_walk_in=slot in (4, 5),
        )
        if status in (AppointmentStatus.CHECKED_IN, AppointmentStatus.IN_CONSULTATION,
                      AppointmentStatus.COMPLETED):
            appointment.checked_in_at = start - timedelta(minutes=rng.randint(3, 20))
        if status is AppointmentStatus.COMPLETED:
            appointment.completed_at = start + timedelta(minutes=rng.randint(10, 25))
        session.add(appointment)
        if appointment.checked_in_at is not None:
            # Checking in is what mints the queue token, so anyone past the
            # front desk carries one. Without these the reception board's token
            # column is blank and the queue feature looks unimplemented.
            session.flush()
            issued += 1
            session.add(QueueToken(
                appointment_id=appointment.id,
                service_date=utcnow(),
                number=issued,
                label=f"{issued:03d}",
            ))

    # A fortnight of history, so the dashboard trend line has a real shape.
    for back in range(1, 15):
        day = today - timedelta(days=back)
        for slot in range(rng.randint(4, 13)):
            start = datetime.combine(day, time(8 + slot % 8, 0))
            session.add(Appointment(
                patient_id=patients[(slot + back) % len(patients)].id,
                doctor_id=doctor_id,
                scheduled_start=start,
                scheduled_end=start + timedelta(minutes=15),
                status=AppointmentStatus.COMPLETED,
                completed_at=start + timedelta(minutes=20),
                reason=rng.choice(reasons),
            ))
    _ = now


def _add_pharmacy(session, rng, today: date) -> None:
    """Put stock on the shelves MediFlow already seeds, then add a few more.

    Working from the seeded catalogue rather than a parallel one keeps the
    screenshot honest — it is the list a clinic sees on its first day — and
    avoids a duplicate row for every drug the product already ships.
    """
    for name, generic, form, strength, unit, reorder, price in _EXTRA_MEDICATIONS:
        session.add(Medication(name=name, generic_name=generic, form=form,
                               strength=strength, unit=unit,
                               reorder_level=reorder, sale_price=price))
    session.flush()

    medications = session.query(Medication).order_by(Medication.id).all()
    for index, medication in enumerate(medications):
        if medication.sale_price is None:
            medication.sale_price = float(rng.randint(3, 25))
        if index == 3:  # one empty shelf, so the out-of-stock alert is real
            continue
        cost = float(medication.sale_price or 10.0) * 0.6
        session.add(StockBatch(
            medication_id=medication.id,
            batch_number=f"B-{today.year}{index:02d}",
            quantity=rng.randint(120, 900),
            expiry_date=today + timedelta(days=rng.randint(200, 700)),
            cost_price=cost,
            received_on=today - timedelta(days=rng.randint(30, 200)),
        ))
        if index in (0, 2, 5):  # three batches inside the 90-day expiry horizon
            session.add(StockBatch(
                medication_id=medication.id,
                batch_number=f"B-{today.year}{index:02d}X",
                quantity=rng.randint(20, 90),
                expiry_date=today + timedelta(days=rng.randint(12, 70)),
                cost_price=cost,
                received_on=today - timedelta(days=rng.randint(200, 330)),
            ))


def _add_laboratory(session, rng, patients, doctor_id) -> None:
    """Requests against the seeded test menu: some open, some already resulted."""
    tests = session.query(LabTest).order_by(LabTest.id).all()
    for test in tests:
        if test.price is None:
            test.price = float(rng.randint(3, 8) * 50)

    # Open requests are an alert; resulted ones are history.
    for index in range(7):
        session.add(LabRequest(
            patient_id=patients[index % len(patients)].id,
            lab_test_id=tests[index % len(tests)].id,
            requested_by_id=doctor_id,
            status=(LabRequestStatus.REQUESTED if index < 4
                    else LabRequestStatus.SAMPLE_COLLECTED),
            requested_at=utcnow() - timedelta(hours=rng.randint(1, 30)),
        ))
    for index in range(6):
        session.add(LabRequest(
            patient_id=patients[index].id,
            lab_test_id=tests[index % len(tests)].id,
            requested_by_id=doctor_id,
            status=LabRequestStatus.COMPLETED,
            requested_at=utcnow() - timedelta(days=rng.randint(2, 12)),
            result_value=f"{rng.uniform(4.0, 11.0):.1f}",
            completed_at=utcnow() - timedelta(days=rng.randint(1, 2)),
        ))


def _add_inventory(session, rng) -> None:
    """Stock the seeded supply list, leaving two items under their reorder level."""
    items = session.query(InventoryItem).order_by(InventoryItem.id).all()
    for index, item in enumerate(items):
        floor = item.reorder_level or 20
        item.quantity = (rng.randint(1, floor - 1) if index in (0, 3)
                         else rng.randint(floor * 2, floor * 8))
        item.unit_cost = float(rng.randint(2, 90))


def _add_billing(session, rng, patients, today: date) -> None:
    """Paid invoices make the revenue figure; unpaid ones make the alert."""
    number = 1
    for back in range(14, -1, -1):
        day = today - timedelta(days=back)
        for _ in range(rng.randint(2, 7)):
            total = float(rng.randint(3, 22) * 50)
            paid_in_full = rng.random() > 0.22
            invoice = Invoice(
                patient_id=rng.choice(patients).id,
                invoice_number=f"INV-{today.year}-{number:04d}",
                issued_at=datetime.combine(day, time(rng.randint(9, 16), 0)),
                subtotal=total, discount=0.0, tax=0.0, total=total,
                paid_amount=total if paid_in_full else 0.0,
                status=InvoiceStatus.PAID if paid_in_full else InvoiceStatus.UNPAID,
            )
            session.add(invoice)
            session.flush()
            number += 1
            if paid_in_full:
                session.add(Payment(
                    invoice_id=invoice.id, amount=total,
                    method=PaymentMethod.CASH,
                    paid_at=datetime.combine(day, time(rng.randint(9, 16), 30)),
                ))
