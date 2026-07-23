"""Appointment booking, reception check-in, and queue management."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from mediflow.core.constants import AppointmentStatus
from mediflow.core.exceptions import ValidationError
from mediflow.core.logging_config import get_logger
from mediflow.data.base import local_day_bounds_utc, utcnow
from mediflow.data.database import Database
from mediflow.data.models.appointment import Appointment, QueueToken
from mediflow.data.models.clinic import Department
from mediflow.data.models.user import User
from mediflow.data.repositories.appointment_repository import AppointmentRepository
from mediflow.data.repositories.patient_repository import PatientRepository
from mediflow.services.authz import require, require_any

log = get_logger("services.appointment")

# Which status transitions are offered, and the timestamp each one stamps.
_ACTIVE_STATUSES = (
    AppointmentStatus.BOOKED.value,
    AppointmentStatus.CHECKED_IN.value,
    AppointmentStatus.IN_CONSULTATION.value,
    AppointmentStatus.WAITLISTED.value,
)


@dataclass(slots=True)
class NamedRef:
    id: int
    name: str


@dataclass(slots=True)
class AppointmentBooking:
    patient_id: int
    scheduled_start: datetime
    doctor_id: int | None = None
    department_id: int | None = None
    reason: str | None = None
    is_walk_in: bool = False
    notes: str | None = None


@dataclass(slots=True)
class AppointmentDTO:
    id: int
    patient_id: int
    patient_name: str
    mrn: str
    doctor_name: str | None
    department_name: str | None
    scheduled_start: datetime
    status: str
    reason: str | None
    is_walk_in: bool
    token_label: str | None

    @property
    def is_active(self) -> bool:
        return self.status in _ACTIVE_STATUSES


class AppointmentService:
    def __init__(self, db: Database):
        self._db = db

    # -- commands -----------------------------------------------------------
    @require("appointment.create")
    def book(self, data: AppointmentBooking) -> int:
        if data.patient_id is None:
            raise ValidationError("Select a patient first.", field="patient_id")
        if data.scheduled_start is None:
            raise ValidationError("A date and time are required.", field="scheduled_start")
        with self._db.unit_of_work() as session:
            patients = PatientRepository(session)
            patients.get_or_raise(data.patient_id)  # ensure the patient exists
            appt = Appointment(
                patient_id=data.patient_id,
                doctor_id=data.doctor_id,
                department_id=data.department_id,
                scheduled_start=data.scheduled_start,
                status=AppointmentStatus.BOOKED.value,
                is_walk_in=data.is_walk_in,
                reason=(data.reason or "").strip() or None,
                notes=(data.notes or "").strip() or None,
            )
            session.add(appt)
            session.flush()
            appt_id = appt.id
            log.info("Booked appointment id=%s for patient=%s", appt_id, data.patient_id)
        return appt_id

    @require("reception.checkin")
    def check_in(self, appointment_id: int) -> str:
        """Mark an appointment checked-in and issue a reception queue token."""
        now = utcnow()
        # service_date is utcnow-stamped; the token sequence must reset at the
        # *local* midnight, so count within the local day expressed in UTC.
        day_start, day_end = local_day_bounds_utc()
        with self._db.unit_of_work() as session:
            repo = AppointmentRepository(session)
            appt = repo.get_or_raise(appointment_id)
            appt.status = AppointmentStatus.CHECKED_IN.value
            appt.checked_in_at = now
            token = session.execute(
                select(QueueToken).where(QueueToken.appointment_id == appt.id)
            ).scalars().first()
            if token is None:
                number = repo.next_token_number(day_start, day_end)
                label = f"{number:03d}"
                token = QueueToken(
                    appointment_id=appt.id,
                    service_date=now,
                    department_id=appt.department_id,
                    number=number,
                    label=label,
                )
                session.add(token)
            log.info("Checked in appointment id=%s token=%s", appointment_id, token.label)
            return token.label

    def set_status(self, appointment_id: int, status: AppointmentStatus) -> None:
        now = utcnow()
        with self._db.unit_of_work() as session:
            repo = AppointmentRepository(session)
            appt = repo.get_or_raise(appointment_id)
            appt.status = status.value
            if status is AppointmentStatus.COMPLETED:
                appt.completed_at = now
            elif status is AppointmentStatus.CHECKED_IN and appt.checked_in_at is None:
                appt.checked_in_at = now
            log.info("Appointment id=%s -> %s", appointment_id, status.value)

    @require_any("appointment.update", "reception.queue")
    def call(self, appointment_id: int) -> None:
        """Reception calls a waiting patient into consultation."""
        self.set_status(appointment_id, AppointmentStatus.IN_CONSULTATION)

    @require_any("appointment.update", "reception.queue")
    def complete(self, appointment_id: int) -> None:
        self.set_status(appointment_id, AppointmentStatus.COMPLETED)

    @require("appointment.cancel")
    def cancel(self, appointment_id: int) -> None:
        self.set_status(appointment_id, AppointmentStatus.CANCELLED)

    # -- queries ------------------------------------------------------------
    def list_for_day(self, day: datetime) -> list[AppointmentDTO]:
        day_start = datetime(day.year, day.month, day.day)
        day_end = datetime(day.year, day.month, day.day, 23, 59, 59)
        with self._db.unit_of_work() as session:
            repo = AppointmentRepository(session)
            rows = repo.for_day(day_start, day_end)
            doctor_names = self._doctor_name_map(session)
            dept_names = self._department_name_map(session)
            token_labels = self._token_label_map(session, [a.id for a in rows])
            result: list[AppointmentDTO] = []
            for a in rows:
                patient = a.patient
                result.append(AppointmentDTO(
                    id=a.id,
                    patient_id=a.patient_id,
                    patient_name=patient.full_name if patient else "—",
                    mrn=patient.mrn if patient else "",
                    doctor_name=doctor_names.get(a.doctor_id),
                    department_name=dept_names.get(a.department_id),
                    scheduled_start=a.scheduled_start,
                    status=a.status,
                    reason=a.reason,
                    is_walk_in=a.is_walk_in,
                    token_label=token_labels.get(a.id),
                ))
            return result

    def list_for_patient(self, patient_id: int, *, limit: int = 50) -> list[AppointmentDTO]:
        with self._db.unit_of_work() as session:
            repo = AppointmentRepository(session)
            rows = repo.for_patient(patient_id, limit=limit)
            doctor_names = self._doctor_name_map(session)
            dept_names = self._department_name_map(session)
            token_labels = self._token_label_map(session, [a.id for a in rows])
            result: list[AppointmentDTO] = []
            for a in rows:
                patient = a.patient
                result.append(AppointmentDTO(
                    id=a.id,
                    patient_id=a.patient_id,
                    patient_name=patient.full_name if patient else "—",
                    mrn=patient.mrn if patient else "",
                    doctor_name=doctor_names.get(a.doctor_id),
                    department_name=dept_names.get(a.department_id),
                    scheduled_start=a.scheduled_start,
                    status=a.status,
                    reason=a.reason,
                    is_walk_in=a.is_walk_in,
                    token_label=token_labels.get(a.id),
                ))
            return result

    def list_doctors(self) -> list[NamedRef]:
        with self._db.unit_of_work() as session:
            stmt = (
                select(User)
                .where(User.is_deleted.is_(False), User.is_active.is_(True))
                .order_by(User.full_name)
            )
            return [NamedRef(u.id, u.full_name) for u in session.execute(stmt).scalars().all()]

    def list_departments(self) -> list[NamedRef]:
        with self._db.unit_of_work() as session:
            stmt = (
                select(Department)
                .where(Department.is_deleted.is_(False), Department.is_active.is_(True))
                .order_by(Department.name)
            )
            return [NamedRef(d.id, d.name) for d in session.execute(stmt).scalars().all()]

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _doctor_name_map(session) -> dict[int, str]:
        return {u.id: u.full_name for u in session.execute(select(User)).scalars().all()}

    @staticmethod
    def _department_name_map(session) -> dict[int, str]:
        return {d.id: d.name for d in session.execute(select(Department)).scalars().all()}

    @staticmethod
    def _token_label_map(session, appt_ids: list[int]) -> dict[int, str]:
        if not appt_ids:
            return {}
        stmt = select(QueueToken).where(QueueToken.appointment_id.in_(appt_ids))
        return {t.appointment_id: t.label for t in session.execute(stmt).scalars().all()}
