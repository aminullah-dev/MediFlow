"""Patient repository with MRN generation support and search."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from mediflow.data.base import local_day_bounds_utc, utcnow
from mediflow.data.models.patient import Patient
from mediflow.data.repositories.base_repository import BaseRepository


class PatientRepository(BaseRepository[Patient]):
    model = Patient

    def get_by_mrn(self, mrn: str) -> Patient | None:
        stmt = select(Patient).where(Patient.mrn == mrn)
        return self.session.execute(stmt).scalars().first()

    def search(self, term: str, *, limit: int = 50) -> list[Patient]:
        like = f"%{term.strip()}%"
        stmt = (
            self._base_select(include_deleted=False)
            .where(
                Patient.mrn.ilike(like)
                | Patient.first_name.ilike(like)
                | Patient.last_name.ilike(like)
                | Patient.phone.ilike(like)
            )
            .order_by(Patient.last_name, Patient.first_name)
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def next_mrn_sequence(self, year: int) -> int:
        """Return the next per-year sequence number for MRN allocation.

        Counts existing patients whose MRN carries the given year prefix. The
        caller formats the MRN; concurrency on a single-machine offline install
        is bounded by the enclosing transaction.
        """
        prefix = f"P-{year}-"
        stmt = select(func.count()).select_from(Patient).where(Patient.mrn.like(f"{prefix}%"))
        return int(self.session.execute(stmt).scalar_one()) + 1

    def registered_today(self, now: datetime | None = None) -> int:
        # created_at is stored in UTC; bucket by the *local* calendar day.
        start, end = local_day_bounds_utc()
        stmt = (
            select(func.count())
            .select_from(Patient)
            .where(Patient.is_deleted.is_(False),
                   Patient.created_at >= start, Patient.created_at < end)
        )
        return int(self.session.execute(stmt).scalar_one())
