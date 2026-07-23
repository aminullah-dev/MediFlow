"""Medical records: a patient's allergies, problem list and documents.

Built on the Phase-1 clinical sub-entities (``PatientAllergy``,
``PatientCondition``, ``PatientDocument``) owned by :class:`Patient`. Returns
detached DTOs so callers can use the data after the session closes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from mediflow.core.exceptions import ValidationError
from mediflow.core.logging_config import get_logger
from mediflow.data.database import Database
from mediflow.data.models.patient import PatientAllergy, PatientCondition, PatientDocument
from mediflow.services.authz import require

log = get_logger("services.medical_record")


@dataclass(slots=True)
class AllergyDTO:
    id: int
    substance: str
    severity: str | None
    reaction: str | None


@dataclass(slots=True)
class ConditionDTO:
    id: int
    name: str
    icd10_code: str | None
    is_chronic: bool
    diagnosed_on: date | None
    notes: str | None


@dataclass(slots=True)
class DocumentDTO:
    id: int
    title: str
    category: str | None
    file_path: str
    mime_type: str | None


class MedicalRecordService:
    def __init__(self, db: Database):
        self._db = db

    # -- allergies ----------------------------------------------------------
    def list_allergies(self, patient_id: int) -> list[AllergyDTO]:
        with self._db.unit_of_work() as session:
            stmt = (
                select(PatientAllergy)
                .where(PatientAllergy.patient_id == patient_id,
                       PatientAllergy.is_deleted.is_(False))
                .order_by(PatientAllergy.substance)
            )
            return [AllergyDTO(a.id, a.substance, a.severity, a.reaction)
                    for a in session.execute(stmt).scalars().all()]

    @require("emr.write")
    def add_allergy(self, patient_id: int, substance: str,
                    severity: str | None = None, reaction: str | None = None) -> int:
        substance = (substance or "").strip()
        if not substance:
            raise ValidationError("Substance is required.", field="substance")
        with self._db.unit_of_work() as session:
            allergy = PatientAllergy(
                patient_id=patient_id,
                substance=substance,
                severity=(severity or "").strip() or None,
                reaction=(reaction or "").strip() or None,
            )
            session.add(allergy)
            session.flush()
            return allergy.id

    @require("emr.write")
    def delete_allergy(self, allergy_id: int) -> None:
        with self._db.unit_of_work() as session:
            allergy = session.get(PatientAllergy, allergy_id)
            if allergy is not None:
                allergy.soft_delete()

    # -- conditions ---------------------------------------------------------
    def list_conditions(self, patient_id: int) -> list[ConditionDTO]:
        with self._db.unit_of_work() as session:
            stmt = (
                select(PatientCondition)
                .where(PatientCondition.patient_id == patient_id,
                       PatientCondition.is_deleted.is_(False))
                .order_by(PatientCondition.is_chronic.desc(), PatientCondition.name)
            )
            return [ConditionDTO(c.id, c.name, c.icd10_code, c.is_chronic,
                                 c.diagnosed_on, c.notes)
                    for c in session.execute(stmt).scalars().all()]

    @require("emr.write")
    def add_condition(self, patient_id: int, name: str, *, icd10_code: str | None = None,
                      is_chronic: bool = True, diagnosed_on: date | None = None,
                      notes: str | None = None) -> int:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Condition name is required.", field="name")
        with self._db.unit_of_work() as session:
            condition = PatientCondition(
                patient_id=patient_id,
                name=name,
                icd10_code=(icd10_code or "").strip() or None,
                is_chronic=is_chronic,
                diagnosed_on=diagnosed_on,
                notes=(notes or "").strip() or None,
            )
            session.add(condition)
            session.flush()
            return condition.id

    @require("emr.write")
    def delete_condition(self, condition_id: int) -> None:
        with self._db.unit_of_work() as session:
            condition = session.get(PatientCondition, condition_id)
            if condition is not None:
                condition.soft_delete()

    # -- documents ----------------------------------------------------------
    def list_documents(self, patient_id: int) -> list[DocumentDTO]:
        with self._db.unit_of_work() as session:
            stmt = (
                select(PatientDocument)
                .where(PatientDocument.patient_id == patient_id,
                       PatientDocument.is_deleted.is_(False))
                .order_by(PatientDocument.created_at.desc())
            )
            return [DocumentDTO(d.id, d.title, d.category, d.file_path, d.mime_type)
                    for d in session.execute(stmt).scalars().all()]
