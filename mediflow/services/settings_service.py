"""Settings service: the clinic organisation profile (single row)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from mediflow.core.exceptions import ValidationError
from mediflow.core.logging_config import get_logger
from mediflow.data.database import Database
from mediflow.data.models.clinic import ClinicInfo
from mediflow.services.authz import require

log = get_logger("services.settings")


@dataclass(slots=True)
class ClinicInfoDTO:
    name: str = ""
    name_pashto: str | None = None
    license_number: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    province: str | None = None
    default_currency: str = "AFN"
    receipt_footer: str | None = None


class SettingsService:
    def __init__(self, db: Database):
        self._db = db

    def get_clinic(self) -> ClinicInfoDTO:
        with self._db.unit_of_work() as session:
            clinic = self._load(session)
            if clinic is None:
                return ClinicInfoDTO()
            return ClinicInfoDTO(
                name=clinic.name or "",
                name_pashto=clinic.name_pashto,
                license_number=clinic.license_number,
                phone=clinic.phone,
                email=clinic.email,
                address=clinic.address,
                city=clinic.city,
                province=clinic.province,
                default_currency=clinic.default_currency or "AFN",
                receipt_footer=clinic.receipt_footer,
            )

    @require("settings.manage")
    def save_clinic(self, data: ClinicInfoDTO) -> None:
        if not (data.name or "").strip():
            raise ValidationError("Clinic name is required.", field="name")
        with self._db.unit_of_work() as session:
            clinic = self._load(session)
            if clinic is None:
                clinic = ClinicInfo(name=data.name.strip())
                session.add(clinic)
            clinic.name = data.name.strip()
            clinic.name_pashto = (data.name_pashto or "").strip() or None
            clinic.license_number = (data.license_number or "").strip() or None
            clinic.phone = (data.phone or "").strip() or None
            clinic.email = (data.email or "").strip() or None
            clinic.address = (data.address or "").strip() or None
            clinic.city = (data.city or "").strip() or None
            clinic.province = (data.province or "").strip() or None
            clinic.default_currency = (data.default_currency or "AFN").strip() or "AFN"
            clinic.receipt_footer = (data.receipt_footer or "").strip() or None
            log.info("Saved clinic profile '%s'", clinic.name)

    @staticmethod
    def _load(session) -> ClinicInfo | None:
        return session.execute(
            select(ClinicInfo).where(ClinicInfo.is_deleted.is_(False)).order_by(ClinicInfo.id)
        ).scalars().first()
