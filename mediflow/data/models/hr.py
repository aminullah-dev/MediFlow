"""Human resources: employees, daily attendance and monthly payslips."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediflow.core.constants import AttendanceStatus, Gender, PayslipStatus
from mediflow.data.base import Base
from mediflow.data.mixins import AuditMixin


class Employee(Base, AuditMixin):
    __tablename__ = "employees"

    employee_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    father_name: Mapped[str | None] = mapped_column(String(80))
    position: Mapped[str | None] = mapped_column(String(100))
    department: Mapped[str | None] = mapped_column(String(100))
    gender: Mapped[str] = mapped_column(String(10), default=Gender.MALE.value, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), index=True)
    hire_date: Mapped[date | None] = mapped_column(Date)
    base_salary: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    attendance: Mapped[list[Attendance]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    payslips: Mapped[list[Payslip]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Attendance(Base, AuditMixin):
    __tablename__ = "attendance"

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=AttendanceStatus.PRESENT.value, nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(255))

    employee: Mapped[Employee] = relationship(back_populates="attendance")


class Payslip(Base, AuditMixin):
    __tablename__ = "payslips"

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    base_salary: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    allowances: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    deductions: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    net: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=PayslipStatus.PENDING.value, nullable=False, index=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)
    method: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)

    employee: Mapped[Employee] = relationship(back_populates="payslips")
