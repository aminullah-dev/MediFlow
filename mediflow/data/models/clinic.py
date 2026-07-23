"""Clinic configuration: organisation profile, departments, services, taxes."""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediflow.data.base import Base
from mediflow.data.mixins import AuditMixin


class ClinicInfo(Base, AuditMixin):
    """Singleton-ish organisation profile shown on every printed document."""

    __tablename__ = "clinic_info"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    name_pashto: Mapped[str | None] = mapped_column(String(150))
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(80))
    province: Mapped[str | None] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(60))
    email: Mapped[str | None] = mapped_column(String(120))
    license_number: Mapped[str | None] = mapped_column(String(80))
    logo_path: Mapped[str | None] = mapped_column(String(255))
    receipt_footer: Mapped[str | None] = mapped_column(Text)
    default_currency: Mapped[str] = mapped_column(String(10), default="AFN", nullable=False)


class Department(Base, AuditMixin):
    __tablename__ = "departments"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    code: Mapped[str | None] = mapped_column(String(20), unique=True)
    description: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    services: Mapped[list["Service"]] = relationship(back_populates="department")


class Service(Base, AuditMixin):
    """A billable clinical service (consultation, procedure, package)."""

    __tablename__ = "services"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str | None] = mapped_column(String(30), unique=True, index=True)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    tax_id: Mapped[int | None] = mapped_column(ForeignKey("taxes.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    department: Mapped[Department | None] = relationship(back_populates="services")
    tax: Mapped["Tax | None"] = relationship()


class Tax(Base, AuditMixin):
    __tablename__ = "taxes"

    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    rate_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
