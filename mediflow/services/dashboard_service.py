"""Read-model service powering the dashboard.

Aggregates cheap COUNT queries into a single snapshot so the dashboard issues
one round trip. Extended as revenue, pharmacy alerts, etc. come online.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select

from mediflow.core.constants import AppointmentStatus
from mediflow.data.base import local_day_bounds
from mediflow.data.database import Database
from mediflow.data.models.appointment import Appointment
from mediflow.data.repositories.patient_repository import PatientRepository


@dataclass(slots=True)
class DashboardStats:
    total_patients: int = 0
    patients_today: int = 0
    appointments_today: int = 0
    waiting_now: int = 0
    completed_today: int = 0


class DashboardService:
    def __init__(self, db: Database):
        self._db = db

    def snapshot(self, now: datetime | None = None) -> DashboardStats:
        # scheduled_start holds user-entered *local* wall-clock times, so the
        # "today" bucket is the local calendar day (not the UTC one).
        day_start, day_end = local_day_bounds()

        with self._db.unit_of_work() as session:
            patients = PatientRepository(session)
            total_patients = patients.count()
            patients_today = patients.registered_today()

            def appt_count(*conditions) -> int:
                stmt = select(func.count()).select_from(Appointment).where(
                    Appointment.is_deleted.is_(False),
                    Appointment.scheduled_start >= day_start,
                    Appointment.scheduled_start < day_end,
                    *conditions,
                )
                return int(session.execute(stmt).scalar_one())

            appointments_today = appt_count()
            waiting_now = appt_count(
                Appointment.status.in_(
                    [AppointmentStatus.CHECKED_IN.value, AppointmentStatus.WAITLISTED.value]
                )
            )
            completed_today = appt_count(
                Appointment.status == AppointmentStatus.COMPLETED.value
            )

        return DashboardStats(
            total_patients=total_patients,
            patients_today=patients_today,
            appointments_today=appointments_today,
            waiting_now=waiting_now,
            completed_today=completed_today,
        )
