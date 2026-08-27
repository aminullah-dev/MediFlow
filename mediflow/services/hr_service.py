"""Human resources service: employees, attendance and payroll."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select

from mediflow.core.constants import AttendanceStatus, Gender, PayslipStatus
from mediflow.core.exceptions import ValidationError
from mediflow.core.logging_config import get_logger
from mediflow.data.base import utcnow
from mediflow.data.database import Database
from mediflow.data.models.hr import Attendance, Employee, Payslip
from mediflow.services.authz import require

log = get_logger("services.hr")


@dataclass(slots=True)
class EmployeeInput:
    first_name: str
    last_name: str
    father_name: str | None = None
    position: str | None = None
    department: str | None = None
    gender: str = Gender.MALE.value
    phone: str | None = None
    hire_date: date | None = None
    base_salary: float = 0.0
    notes: str | None = None


@dataclass(slots=True)
class EmployeeDTO:
    id: int
    employee_code: str
    first_name: str
    last_name: str
    father_name: str | None
    position: str | None
    department: str | None
    gender: str
    phone: str | None
    hire_date: date | None
    base_salary: float
    is_active: bool
    notes: str | None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


@dataclass(slots=True)
class AttendanceDTO:
    id: int
    work_date: date
    status: str
    note: str | None


@dataclass(slots=True)
class PayslipDTO:
    id: int
    period_year: int
    period_month: int
    base_salary: float
    allowances: float
    deductions: float
    net: float
    status: str

    @property
    def is_pending(self) -> bool:
        return self.status == PayslipStatus.PENDING.value


class HRService:
    def __init__(self, db: Database):
        self._db = db

    # -- employees ----------------------------------------------------------
    def list_employees(self, term: str = "") -> list[EmployeeDTO]:
        term = (term or "").strip()
        with self._db.unit_of_work() as session:
            stmt = select(Employee).where(Employee.is_deleted.is_(False))
            if term:
                like = f"%{term}%"
                stmt = stmt.where(
                    Employee.first_name.ilike(like)
                    | Employee.last_name.ilike(like)
                    | Employee.employee_code.ilike(like)
                    | Employee.position.ilike(like)
                    | Employee.phone.ilike(like)
                )
            stmt = stmt.order_by(Employee.first_name, Employee.last_name)
            return [self._to_dto(e) for e in session.execute(stmt).scalars().all()]

    def get(self, employee_id: int) -> EmployeeDTO:
        with self._db.unit_of_work() as session:
            employee = session.get(Employee, employee_id)
            if employee is None:
                raise ValidationError("Employee not found.")
            return self._to_dto(employee)

    @require("hr.manage")
    def create(self, data: EmployeeInput) -> int:
        self._validate(data)
        with self._db.unit_of_work() as session:
            year = utcnow().year
            prefix = f"EMP-{year}-"
            count = session.execute(
                select(func.count()).select_from(Employee).where(
                    Employee.employee_code.like(f"{prefix}%"))
            ).scalar_one()
            employee = Employee(employee_code=f"{prefix}{count + 1:06d}", **self._fields(data))
            session.add(employee)
            session.flush()
            log.info("Created employee %s (id=%s)", employee.employee_code, employee.id)
            return employee.id

    @require("hr.manage")
    def update(self, employee_id: int, data: EmployeeInput) -> None:
        self._validate(data)
        with self._db.unit_of_work() as session:
            employee = session.get(Employee, employee_id)
            if employee is None:
                raise ValidationError("Employee not found.")
            for key, value in self._fields(data).items():
                setattr(employee, key, value)

    @require("hr.manage")
    def delete(self, employee_id: int) -> None:
        with self._db.unit_of_work() as session:
            employee = session.get(Employee, employee_id)
            if employee is not None:
                employee.soft_delete()

    def summary(self) -> tuple[int, int, float]:
        """Return (total employees, active employees, monthly base payroll)."""
        with self._db.unit_of_work() as session:
            total = session.execute(
                select(func.count()).select_from(Employee).where(
                    Employee.is_deleted.is_(False))
            ).scalar_one()
            active = session.execute(
                select(func.count()).select_from(Employee).where(
                    Employee.is_deleted.is_(False), Employee.is_active.is_(True))
            ).scalar_one()
            payroll = session.execute(
                select(func.coalesce(func.sum(Employee.base_salary), 0)).where(
                    Employee.is_deleted.is_(False), Employee.is_active.is_(True))
            ).scalar_one()
            return int(total), int(active), round(float(payroll), 2)

    # -- attendance ---------------------------------------------------------
    @require("hr.manage")
    def mark_attendance(self, employee_id: int, work_date: date,
                        status: AttendanceStatus, note: str | None = None) -> None:
        with self._db.unit_of_work() as session:
            existing = session.execute(
                select(Attendance).where(Attendance.employee_id == employee_id,
                                         Attendance.work_date == work_date,
                                         Attendance.is_deleted.is_(False))
            ).scalars().first()
            if existing is not None:
                existing.status = status.value
                existing.note = (note or "").strip() or None
            else:
                session.add(Attendance(employee_id=employee_id, work_date=work_date,
                                       status=status.value,
                                       note=(note or "").strip() or None))

    def list_attendance(self, employee_id: int, *, limit: int = 60) -> list[AttendanceDTO]:
        with self._db.unit_of_work() as session:
            stmt = (
                select(Attendance)
                .where(Attendance.employee_id == employee_id,
                       Attendance.is_deleted.is_(False))
                .order_by(Attendance.work_date.desc())
                .limit(limit)
            )
            return [AttendanceDTO(a.id, a.work_date, a.status, a.note)
                    for a in session.execute(stmt).scalars().all()]

    # -- payroll ------------------------------------------------------------
    @require("hr.manage")
    def create_payslip(self, employee_id: int, year: int, month: int,
                       base_salary: float, allowances: float = 0.0,
                       deductions: float = 0.0) -> int:
        net = round(float(base_salary or 0) + float(allowances or 0) - float(deductions or 0), 2)
        if net < 0:
            raise ValidationError("Deductions exceed salary plus allowances.", field="deductions")
        with self._db.unit_of_work() as session:
            if session.get(Employee, employee_id) is None:
                raise ValidationError("Employee not found.")
            payslip = Payslip(
                employee_id=employee_id, period_year=year, period_month=month,
                base_salary=round(float(base_salary or 0), 2),
                allowances=round(float(allowances or 0), 2),
                deductions=round(float(deductions or 0), 2), net=net,
                status=PayslipStatus.PENDING.value,
            )
            session.add(payslip)
            session.flush()
            return payslip.id

    @require("hr.manage")
    def mark_paid(self, payslip_id: int, method: str | None = None) -> None:
        with self._db.unit_of_work() as session:
            payslip = session.get(Payslip, payslip_id)
            if payslip is None:
                raise ValidationError("Payslip not found.")
            payslip.status = PayslipStatus.PAID.value
            payslip.paid_at = utcnow()
            payslip.method = (method or "").strip() or None

    def list_payslips(self, employee_id: int, *, limit: int = 36) -> list[PayslipDTO]:
        with self._db.unit_of_work() as session:
            stmt = (
                select(Payslip)
                .where(Payslip.employee_id == employee_id, Payslip.is_deleted.is_(False))
                .order_by(Payslip.period_year.desc(), Payslip.period_month.desc())
                .limit(limit)
            )
            return [PayslipDTO(p.id, p.period_year, p.period_month, float(p.base_salary or 0),
                               float(p.allowances or 0), float(p.deductions or 0),
                               float(p.net or 0), p.status)
                    for p in session.execute(stmt).scalars().all()]

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _to_dto(e: Employee) -> EmployeeDTO:
        return EmployeeDTO(
            id=e.id, employee_code=e.employee_code, first_name=e.first_name,
            last_name=e.last_name, father_name=e.father_name, position=e.position,
            department=e.department, gender=e.gender, phone=e.phone, hire_date=e.hire_date,
            base_salary=float(e.base_salary or 0), is_active=e.is_active, notes=e.notes,
        )

    @staticmethod
    def _fields(data: EmployeeInput) -> dict:
        return {
            "first_name": data.first_name.strip(),
            "last_name": data.last_name.strip(),
            "father_name": (data.father_name or "").strip() or None,
            "position": (data.position or "").strip() or None,
            "department": (data.department or "").strip() or None,
            "gender": data.gender,
            "phone": (data.phone or "").strip() or None,
            "hire_date": data.hire_date,
            "base_salary": float(data.base_salary or 0),
            "notes": (data.notes or "").strip() or None,
        }

    @staticmethod
    def _validate(data: EmployeeInput) -> None:
        if not data.first_name or not data.first_name.strip():
            raise ValidationError("First name is required.", field="first_name")
        if not data.last_name or not data.last_name.strip():
            raise ValidationError("Last name is required.", field="last_name")
        if data.gender not in {g.value for g in Gender}:
            raise ValidationError("Invalid gender.", field="gender")
