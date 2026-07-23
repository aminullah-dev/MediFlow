"""Canonical permission catalogue and the default role -> permission matrix.

Permission codes follow ``<module>.<action>``. This catalogue is the single
source of truth: seeding inserts any missing permissions and never deletes,
so upgrades that add permissions are safe and additive.
"""
from __future__ import annotations

from mediflow.core.constants import (
    ROLE_ACCOUNTANT,
    ROLE_ADMIN,
    ROLE_CASHIER,
    ROLE_DOCTOR,
    ROLE_LAB_TECH,
    ROLE_NURSE,
    ROLE_PHARMACIST,
    ROLE_RECEPTIONIST,
)

# module -> list of (action, description)
PERMISSION_CATALOG: dict[str, list[tuple[str, str]]] = {
    "dashboard": [("view", "View dashboard")],
    "patient": [
        ("view", "View patients"),
        ("create", "Register patients"),
        ("update", "Edit patient records"),
        ("delete", "Remove patient records"),
    ],
    "appointment": [
        ("view", "View appointments"),
        ("create", "Book appointments"),
        ("update", "Reschedule appointments"),
        ("cancel", "Cancel appointments"),
    ],
    "reception": [("checkin", "Check in patients"), ("queue", "Manage the queue")],
    "emr": [("view", "View medical records"), ("write", "Author medical records")],
    "prescription": [("write", "Write prescriptions")],
    "pharmacy": [
        ("view", "View pharmacy"),
        ("sell", "Dispense/sell medicine"),
        ("purchase", "Record purchases"),
        ("manage", "Manage inventory"),
    ],
    "lab": [("view", "View lab"), ("request", "Request tests"), ("result", "Enter results")],
    "inventory": [("view", "View inventory"), ("manage", "Manage inventory")],
    "billing": [
        ("view", "View invoices"),
        ("create", "Create invoices"),
        ("payment", "Take payments"),
        ("refund", "Issue refunds"),
    ],
    "accounting": [("view", "View accounting"), ("post", "Post journal entries")],
    "hr": [("view", "View HR"), ("manage", "Manage employees/payroll")],
    "report": [("view", "View reports"), ("export", "Export reports")],
    "user": [("view", "View users"), ("manage", "Manage users & roles")],
    "audit": [("view", "View audit logs")],
    "backup": [("run", "Run backup/restore")],
    "settings": [("manage", "Manage settings")],
}


def all_permission_rows() -> list[tuple[str, str, str]]:
    """Flatten the catalogue to (code, module, description) tuples."""
    rows: list[tuple[str, str, str]] = []
    for module, actions in PERMISSION_CATALOG.items():
        for action, description in actions:
            rows.append((f"{module}.{action}", module, description))
    return rows


def _codes(*modules_or_codes: str) -> set[str]:
    """Expand ``"patient"`` to all patient.* codes, or pass explicit codes."""
    result: set[str] = set()
    catalog_codes = {c for c, _, _ in all_permission_rows()}
    for item in modules_or_codes:
        if "." in item:
            result.add(item)
        else:
            result |= {c for c in catalog_codes if c.startswith(f"{item}.")}
    return result


# Default role -> permission-code assignment. Administrator implicitly gets all.
ROLE_MATRIX: dict[str, set[str]] = {
    ROLE_ADMIN: {c for c, _, _ in all_permission_rows()},
    ROLE_DOCTOR: _codes(
        "dashboard.view", "patient.view", "appointment", "emr", "prescription.write",
        "lab.view", "lab.request", "report.view",
    ),
    ROLE_NURSE: _codes(
        "dashboard.view", "patient.view", "appointment.view", "emr.view",
        "reception.checkin", "reception.queue",
    ),
    ROLE_RECEPTIONIST: _codes(
        "dashboard.view", "patient.view", "patient.create", "patient.update",
        "appointment", "reception",
    ),
    ROLE_PHARMACIST: _codes("dashboard.view", "pharmacy", "inventory.view", "report.view"),
    ROLE_LAB_TECH: _codes("dashboard.view", "lab", "patient.view"),
    ROLE_ACCOUNTANT: _codes("dashboard.view", "accounting", "billing.view", "report"),
    ROLE_CASHIER: _codes("dashboard.view", "billing.view", "billing.create", "billing.payment"),
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    ROLE_ADMIN: "Full system administrator",
    ROLE_DOCTOR: "Physician: consultations, EMR, prescriptions",
    ROLE_NURSE: "Nursing and triage",
    ROLE_RECEPTIONIST: "Front desk registration and scheduling",
    ROLE_PHARMACIST: "Pharmacy dispensing and stock",
    ROLE_LAB_TECH: "Laboratory testing",
    ROLE_ACCOUNTANT: "Accounting and financial reporting",
    ROLE_CASHIER: "Billing and cash collection",
}
