"""Patient master record and closely-owned clinical sub-entities."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediflow.core.constants import BloodGroup, Gender
from mediflow.data.base import Base
from mediflow.data.mixins import AuditMixin


class Patient(Base, AuditMixin):
    __tablename__ = "patients"

    # Human-friendly, printable identifier (e.g. MRN "P-2026-000123"), assigned
    # by the patient service; distinct from the surrogate integer PK.
    mrn: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)

    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    father_name: Mapped[str | None] = mapped_column(String(80))
    gender: Mapped[str] = mapped_column(String(10), default=Gender.MALE.value, nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    # Afghan patients frequently know only an age; store it as a fallback.
    approximate_age_years: Mapped[int | None] = mapped_column()
    blood_group: Mapped[str] = mapped_column(
        String(10), default=BloodGroup.UNKNOWN.value, nullable=False
    )

    phone: Mapped[str | None] = mapped_column(String(30), index=True)
    # National ID (Tazkira) is sensitive — stored encrypted via the service layer.
    national_id_encrypted: Mapped[str | None] = mapped_column(String(255))

    province: Mapped[str | None] = mapped_column(String(80))
    district: Mapped[str | None] = mapped_column(String(80))
    address: Mapped[str | None] = mapped_column(String(255))
    photo_path: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    allergies: Mapped[list[PatientAllergy]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    conditions: Mapped[list[PatientCondition]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    documents: Mapped[list[PatientDocument]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class PatientAllergy(Base, AuditMixin):
    __tablename__ = "patient_allergies"

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    substance: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(30))  # mild/moderate/severe
    reaction: Mapped[str | None] = mapped_column(String(255))

    patient: Mapped[Patient] = relationship(back_populates="allergies")


class PatientCondition(Base, AuditMixin):
    """A chronic disease / ongoing diagnosis on the patient's problem list."""

    __tablename__ = "patient_conditions"

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    icd10_code: Mapped[str | None] = mapped_column(String(15))
    diagnosed_on: Mapped[date | None] = mapped_column(Date)
    is_chronic: Mapped[bool] = mapped_column(default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    patient: Mapped[Patient] = relationship(back_populates="conditions")


class PatientDocument(Base, AuditMixin):
    __tablename__ = "patient_documents"

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str | None] = mapped_column(String(60))
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(80))

    patient: Mapped[Patient] = relationship(back_populates="documents")
