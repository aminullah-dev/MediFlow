"""Application-wide constants and enumerations.

Enumerations are stored in the database as their string ``value`` so the data
remains human-readable and language-independent. UI labels for each value come
from the translation layer, never from these names.
"""
from __future__ import annotations

import enum


class Language(str, enum.Enum):
    """Supported UI languages. English is scaffolded for future activation."""

    DARI = "fa_AF"      # دری
    PASHTO = "ps_AF"    # پښتو
    ENGLISH = "en"      # future

    @property
    def is_rtl(self) -> bool:
        return self in (Language.DARI, Language.PASHTO)


class Theme(str, enum.Enum):
    LIGHT = "light"
    DARK = "dark"


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class BloodGroup(str, enum.Enum):
    A_POS = "A+"
    A_NEG = "A-"
    B_POS = "B+"
    B_NEG = "B-"
    AB_POS = "AB+"
    AB_NEG = "AB-"
    O_POS = "O+"
    O_NEG = "O-"
    UNKNOWN = "unknown"


class AppointmentStatus(str, enum.Enum):
    BOOKED = "booked"
    CHECKED_IN = "checked_in"
    IN_CONSULTATION = "in_consultation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    WAITLISTED = "waitlisted"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    MOBILE_MONEY = "mobile_money"


class LabRequestStatus(str, enum.Enum):
    REQUESTED = "requested"
    SAMPLE_COLLECTED = "sample_collected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StockMovementType(str, enum.Enum):
    PURCHASE = "purchase"
    SALE = "sale"
    ADJUSTMENT = "adjustment"
    RETURN = "return"
    EXPIRY_WRITEOFF = "expiry_writeoff"
    TRANSFER = "transfer"


class AccountType(str, enum.Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    INCOME = "income"
    EXPENSE = "expense"


class AttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LEAVE = "leave"
    HALF_DAY = "half_day"
    HOLIDAY = "holiday"


class PayslipStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"


class AuditAction(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PRINT = "print"
    EXPORT = "export"
    BACKUP = "backup"
    RESTORE = "restore"


# Default seeded roles.
ROLE_ADMIN = "administrator"
ROLE_DOCTOR = "doctor"
ROLE_NURSE = "nurse"
ROLE_RECEPTIONIST = "receptionist"
ROLE_PHARMACIST = "pharmacist"
ROLE_LAB_TECH = "lab_technician"
ROLE_ACCOUNTANT = "accountant"
ROLE_CASHIER = "cashier"
