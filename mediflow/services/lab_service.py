"""Laboratory service: test catalogue and patient test requests/results."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from mediflow.core.constants import LabRequestStatus
from mediflow.core.exceptions import ValidationError
from mediflow.core.logging_config import get_logger
from mediflow.data.base import utcnow
from mediflow.data.database import Database
from mediflow.data.models.laboratory import LabRequest, LabTest
from mediflow.data.repositories.patient_repository import PatientRepository
from mediflow.services.authz import require, require_any

log = get_logger("services.lab")

_OPEN_STATUSES = (
    LabRequestStatus.REQUESTED.value,
    LabRequestStatus.SAMPLE_COLLECTED.value,
    LabRequestStatus.IN_PROGRESS.value,
)


@dataclass(slots=True)
class LabTestDTO:
    id: int
    name: str
    code: str | None
    sample_type: str | None
    price: float
    reference_range: str | None
    unit: str | None


@dataclass(slots=True)
class LabTestInput:
    name: str
    code: str | None = None
    sample_type: str | None = None
    price: float = 0.0
    reference_range: str | None = None
    unit: str | None = None


@dataclass(slots=True)
class LabRequestDTO:
    id: int
    patient_id: int
    patient_name: str
    mrn: str
    test_name: str
    reference_range: str | None
    unit: str | None
    status: str
    result_value: str | None
    result_flag: str | None
    requested_at: datetime

    @property
    def is_open(self) -> bool:
        return self.status in _OPEN_STATUSES


class LabService:
    def __init__(self, db: Database):
        self._db = db

    # -- test catalogue -----------------------------------------------------
    def list_tests(self, *, active_only: bool = True) -> list[LabTestDTO]:
        with self._db.unit_of_work() as session:
            stmt = select(LabTest).where(LabTest.is_deleted.is_(False))
            if active_only:
                stmt = stmt.where(LabTest.is_active.is_(True))
            stmt = stmt.order_by(LabTest.name)
            return [self._test_dto(t) for t in session.execute(stmt).scalars().all()]

    @require_any("lab.result", "lab.request")
    def create_test(self, data: LabTestInput) -> int:
        if not data.name or not data.name.strip():
            raise ValidationError("Test name is required.", field="name")
        with self._db.unit_of_work() as session:
            test = LabTest(
                name=data.name.strip(),
                code=(data.code or "").strip() or None,
                sample_type=(data.sample_type or "").strip() or None,
                price=float(data.price or 0),
                reference_range=(data.reference_range or "").strip() or None,
                unit=(data.unit or "").strip() or None,
            )
            session.add(test)
            session.flush()
            return test.id

    @require_any("lab.result", "lab.request")
    def delete_test(self, test_id: int) -> None:
        with self._db.unit_of_work() as session:
            test = session.get(LabTest, test_id)
            if test is not None:
                test.soft_delete()

    # -- requests -----------------------------------------------------------
    @require("lab.request")
    def create_request(self, patient_id: int, lab_test_id: int,
                        requested_by_id: int | None = None) -> int:
        with self._db.unit_of_work() as session:
            PatientRepository(session).get_or_raise(patient_id)
            if session.get(LabTest, lab_test_id) is None:
                raise ValidationError("Test not found.", field="lab_test_id")
            request = LabRequest(
                patient_id=patient_id,
                lab_test_id=lab_test_id,
                requested_by_id=requested_by_id,
                status=LabRequestStatus.REQUESTED.value,
                requested_at=utcnow(),
            )
            session.add(request)
            session.flush()
            log.info("Created lab request id=%s", request.id)
            return request.id

    def set_status(self, request_id: int, status: LabRequestStatus) -> None:
        with self._db.unit_of_work() as session:
            request = session.get(LabRequest, request_id)
            if request is None:
                raise ValidationError("Request not found.")
            request.status = status.value
            if status is LabRequestStatus.COMPLETED and request.completed_at is None:
                request.completed_at = utcnow()

    @require("lab.result")
    def collect_sample(self, request_id: int) -> None:
        self.set_status(request_id, LabRequestStatus.SAMPLE_COLLECTED)

    @require("lab.result")
    def start(self, request_id: int) -> None:
        self.set_status(request_id, LabRequestStatus.IN_PROGRESS)

    @require("lab.result")
    def cancel(self, request_id: int) -> None:
        self.set_status(request_id, LabRequestStatus.CANCELLED)

    @require("lab.result")
    def set_result(self, request_id: int, value: str, *, flag: str | None = None,
                   notes: str | None = None) -> None:
        if not value or not value.strip():
            raise ValidationError("A result value is required.", field="result_value")
        with self._db.unit_of_work() as session:
            request = session.get(LabRequest, request_id)
            if request is None:
                raise ValidationError("Request not found.")
            request.result_value = value.strip()
            request.result_flag = (flag or "").strip() or None
            request.result_notes = (notes or "").strip() or None
            request.status = LabRequestStatus.COMPLETED.value
            request.completed_at = utcnow()
            log.info("Recorded result for lab request id=%s", request_id)

    def list_requests(self, *, open_only: bool = False, limit: int = 200) -> list[LabRequestDTO]:
        with self._db.unit_of_work() as session:
            stmt = select(LabRequest).where(LabRequest.is_deleted.is_(False))
            if open_only:
                stmt = stmt.where(LabRequest.status.in_(_OPEN_STATUSES))
            stmt = stmt.order_by(LabRequest.requested_at.desc()).limit(limit)
            return [self._request_dto(r) for r in session.execute(stmt).scalars().all()]

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _test_dto(t: LabTest) -> LabTestDTO:
        return LabTestDTO(t.id, t.name, t.code, t.sample_type, float(t.price or 0),
                          t.reference_range, t.unit)

    @staticmethod
    def _request_dto(r: LabRequest) -> LabRequestDTO:
        patient = r.patient
        test = r.lab_test
        return LabRequestDTO(
            id=r.id,
            patient_id=r.patient_id,
            patient_name=patient.full_name if patient else "—",
            mrn=patient.mrn if patient else "",
            test_name=test.name if test else "—",
            reference_range=test.reference_range if test else None,
            unit=test.unit if test else None,
            status=r.status,
            result_value=r.result_value,
            result_flag=r.result_flag,
            requested_at=r.requested_at,
        )
