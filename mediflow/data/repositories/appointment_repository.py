"""Appointment and queue-token repository."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from mediflow.data.models.appointment import Appointment, QueueToken
from mediflow.data.repositories.base_repository import BaseRepository


class AppointmentRepository(BaseRepository[Appointment]):
    model = Appointment

    def for_day(self, day_start: datetime, day_end: datetime) -> list[Appointment]:
        stmt = (
            self._base_select(include_deleted=False)
            .where(
                Appointment.scheduled_start >= day_start,
                Appointment.scheduled_start <= day_end,
            )
            .order_by(Appointment.scheduled_start)
        )
        return list(self.session.execute(stmt).scalars().all())

    def for_patient(self, patient_id: int, *, limit: int = 50) -> list[Appointment]:
        stmt = (
            self._base_select(include_deleted=False)
            .where(Appointment.patient_id == patient_id)
            .order_by(Appointment.scheduled_start.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def next_token_number(self, day_start: datetime, day_end: datetime) -> int:
        """Next sequential reception token for the given service day.

        ``day_end`` is exclusive (half-open window), matching the local-day
        bound helpers.
        """
        stmt = select(func.count()).select_from(QueueToken).where(
            QueueToken.service_date >= day_start,
            QueueToken.service_date < day_end,
        )
        return int(self.session.execute(stmt).scalar_one()) + 1
