"""Patient registration and management service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from mediflow.core.constants import BloodGroup, Gender
from mediflow.core.exceptions import ValidationError
from mediflow.core.logging_config import get_logger
from mediflow.core.security import FieldCipher
from mediflow.data.database import Database
from mediflow.data.models.patient import Patient
from mediflow.data.repositories.patient_repository import PatientRepository
from mediflow.services.authz import require
from mediflow.data.base import local_today

log = get_logger("services.patient")


@dataclass(slots=True)
class PatientRegistration:
    first_name: str
    last_name: str
    gender: str = Gender.MALE.value
    father_name: str | None = None
    date_of_birth: date | None = None
    approximate_age_years: int | None = None
    blood_group: str = BloodGroup.UNKNOWN.value
    phone: str | None = None
    national_id: str | None = None
    province: str | None = None
    district: str | None = None
    address: str | None = None
    notes: str | None = None


@dataclass(slots=True)
class PatientDTO:
    """Detached snapshot of a patient, safe to use after the session closes."""

    id: int
    mrn: str
    first_name: str
    last_name: str
    father_name: str | None
    gender: str
    date_of_birth: date | None
    approximate_age_years: int | None
    blood_group: str
    phone: str | None
    national_id: str | None
    province: str | None
    district: str | None
    address: str | None
    notes: str | None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def age_years(self) -> int | None:
        if self.date_of_birth is not None:
            today = local_today()
            years = today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
            return max(years, 0)
        return self.approximate_age_years


class PatientService:
    def __init__(self, db: Database, cipher: FieldCipher | None = None):
        self._db = db
        self._cipher = cipher

    # -- commands -----------------------------------------------------------
    @require("patient.create")
    def register(self, data: PatientRegistration) -> int:
        self._validate(data)
        with self._db.unit_of_work() as session:
            repo = PatientRepository(session)
            year = local_today().year  # MRN year follows the local calendar
            sequence = repo.next_mrn_sequence(year)
            mrn = f"P-{year}-{sequence:06d}"

            patient = Patient(
                mrn=mrn,
                first_name=data.first_name.strip(),
                last_name=data.last_name.strip(),
                father_name=(data.father_name or "").strip() or None,
                gender=data.gender,
                date_of_birth=data.date_of_birth,
                approximate_age_years=data.approximate_age_years,
                blood_group=data.blood_group,
                phone=(data.phone or "").strip() or None,
                national_id_encrypted=self._encrypt(data.national_id),
                province=(data.province or "").strip() or None,
                district=(data.district or "").strip() or None,
                address=(data.address or "").strip() or None,
                notes=(data.notes or "").strip() or None,
            )
            repo.add(patient)
            session.flush()  # assign patient.id within the transaction
            patient_id = patient.id
            log.info("Registered patient %s (id=%s)", mrn, patient_id)
        return patient_id

    @require("patient.update")
    def update(self, patient_id: int, data: PatientRegistration) -> None:
        self._validate(data)
        with self._db.unit_of_work() as session:
            repo = PatientRepository(session)
            patient = repo.get_or_raise(patient_id)
            patient.first_name = data.first_name.strip()
            patient.last_name = data.last_name.strip()
            patient.father_name = (data.father_name or "").strip() or None
            patient.gender = data.gender
            patient.date_of_birth = data.date_of_birth
            patient.approximate_age_years = data.approximate_age_years
            patient.blood_group = data.blood_group
            patient.phone = (data.phone or "").strip() or None
            patient.national_id_encrypted = self._encrypt(data.national_id)
            patient.province = (data.province or "").strip() or None
            patient.district = (data.district or "").strip() or None
            patient.address = (data.address or "").strip() or None
            patient.notes = (data.notes or "").strip() or None
            log.info("Updated patient %s (id=%s)", patient.mrn, patient_id)

    @require("patient.delete")
    def delete(self, patient_id: int) -> None:
        with self._db.unit_of_work() as session:
            repo = PatientRepository(session)
            patient = repo.get_or_raise(patient_id)
            repo.soft_delete(patient)
            log.info("Soft-deleted patient id=%s", patient_id)

    # -- queries ------------------------------------------------------------
    def list_recent(self, *, limit: int = 200) -> list[PatientDTO]:
        with self._db.unit_of_work() as session:
            repo = PatientRepository(session)
            rows = repo.list(order_by=Patient.created_at.desc(), limit=limit)
            return [self._to_dto(p) for p in rows]

    def search(self, term: str, *, limit: int = 100) -> list[PatientDTO]:
        term = (term or "").strip()
        if not term:
            return self.list_recent(limit=limit)
        with self._db.unit_of_work() as session:
            repo = PatientRepository(session)
            return [self._to_dto(p) for p in repo.search(term, limit=limit)]

    def get(self, patient_id: int) -> PatientDTO:
        with self._db.unit_of_work() as session:
            repo = PatientRepository(session)
            patient = repo.get_or_raise(patient_id)
            return self._to_dto(patient, reveal=True)

    def count(self) -> int:
        with self._db.unit_of_work() as session:
            return PatientRepository(session).count()

    # -- helpers ------------------------------------------------------------
    def _to_dto(self, patient: Patient, *, reveal: bool = False) -> PatientDTO:
        national_id = self.reveal_national_id(patient) if reveal else None
        return PatientDTO(
            id=patient.id,
            mrn=patient.mrn,
            first_name=patient.first_name,
            last_name=patient.last_name,
            father_name=patient.father_name,
            gender=patient.gender,
            date_of_birth=patient.date_of_birth,
            approximate_age_years=patient.approximate_age_years,
            blood_group=patient.blood_group,
            phone=patient.phone,
            national_id=national_id,
            province=patient.province,
            district=patient.district,
            address=patient.address,
            notes=patient.notes,
        )

    def reveal_national_id(self, patient: Patient) -> str | None:
        if patient.national_id_encrypted is None or self._cipher is None:
            return None
        return self._cipher.decrypt(patient.national_id_encrypted)

    def _encrypt(self, value: str | None) -> str | None:
        value = (value or "").strip() or None
        if value is None:
            return None
        if self._cipher is None:
            # No cipher configured — refuse to store sensitive data in the clear.
            raise ValidationError(
                "Encryption is not configured; cannot store national id.",
                field="national_id",
            )
        return self._cipher.encrypt(value)

    @staticmethod
    def _validate(data: PatientRegistration) -> None:
        if not data.first_name or not data.first_name.strip():
            raise ValidationError("First name is required.", field="first_name")
        if not data.last_name or not data.last_name.strip():
            raise ValidationError("Last name is required.", field="last_name")
        if data.gender not in {g.value for g in Gender}:
            raise ValidationError("Invalid gender.", field="gender")
        if data.date_of_birth is None and data.approximate_age_years is None:
            raise ValidationError(
                "Provide a date of birth or an approximate age.", field="date_of_birth"
            )
