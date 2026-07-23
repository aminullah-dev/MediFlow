"""Idempotent seeding entry point.

Safe to run on every startup: it inserts only what is missing. Returns the
generated initial-admin password *once* (on first creation) so the installer/
first-run wizard can display it; subsequent runs return ``None``.
"""
from __future__ import annotations

from sqlalchemy import select

from mediflow.core.constants import ROLE_ADMIN, AccountType
from mediflow.core.logging_config import get_logger
from mediflow.core.security import generate_temporary_password, hash_password
from mediflow.data.database import Database
from mediflow.data.models.accounting import Account
from mediflow.data.models.inventory import InventoryItem
from mediflow.data.models.laboratory import LabTest
from mediflow.data.models.pharmacy import Medication
from mediflow.data.models.user import Permission, Role, User
from mediflow.data.repositories.user_repository import (
    PermissionRepository,
    RoleRepository,
    UserRepository,
)
from mediflow.seeds.permissions import (
    ROLE_DESCRIPTIONS,
    ROLE_MATRIX,
    all_permission_rows,
)

log = get_logger("seeds")

DEFAULT_ADMIN_USERNAME = "admin"

# (name, code, sample_type, reference_range, unit)
DEFAULT_LAB_TESTS = [
    ("Complete Blood Count", "CBC", "Blood", None, None),
    ("Blood Glucose (Fasting)", "FBS", "Blood", "70–110", "mg/dL"),
    ("Hemoglobin", "HGB", "Blood", "12–16", "g/dL"),
    ("Urinalysis", "UA", "Urine", None, None),
    ("Malaria RDT", "MAL", "Blood", "Negative", None),
    ("Liver Function Test", "LFT", "Blood", None, None),
    ("Renal Function Test", "RFT", "Blood", None, None),
]

# (name, generic_name, form, strength, unit, reorder_level)
DEFAULT_MEDICATIONS = [
    ("Paracetamol", "Acetaminophen", "Tablet", "500 mg", "tablet", 50),
    ("Amoxicillin", "Amoxicillin", "Capsule", "500 mg", "capsule", 40),
    ("Ibuprofen", "Ibuprofen", "Tablet", "400 mg", "tablet", 40),
    ("Metronidazole", "Metronidazole", "Tablet", "400 mg", "tablet", 30),
    ("Oral Rehydration Salts", "ORS", "Sachet", None, "sachet", 30),
    ("Omeprazole", "Omeprazole", "Capsule", "20 mg", "capsule", 30),
]

# (name, category, unit, reorder_level)
DEFAULT_INVENTORY = [
    ("Examination Gloves", "Consumables", "box", 20),
    ("Syringe 5ml", "Consumables", "piece", 100),
    ("Gauze Pads", "Consumables", "pack", 30),
    ("Face Masks", "Consumables", "box", 20),
    ("Alcohol Swabs", "Consumables", "box", 25),
    ("Cotton Rolls", "Consumables", "roll", 20),
]

# (code, name, account_type)
DEFAULT_ACCOUNTS = [
    ("1000", "Cash", AccountType.ASSET),
    ("1100", "Bank", AccountType.ASSET),
    ("1200", "Accounts Receivable", AccountType.ASSET),
    ("2000", "Accounts Payable", AccountType.LIABILITY),
    ("3000", "Owner Equity", AccountType.EQUITY),
    ("4000", "Consultation Income", AccountType.INCOME),
    ("4100", "Pharmacy Sales", AccountType.INCOME),
    ("4200", "Laboratory Income", AccountType.INCOME),
    ("5000", "Salaries Expense", AccountType.EXPENSE),
    ("5100", "Rent Expense", AccountType.EXPENSE),
    ("5200", "Utilities Expense", AccountType.EXPENSE),
    ("5300", "Supplies Expense", AccountType.EXPENSE),
]


def seed_database(db: Database) -> str | None:
    generated_password: str | None = None

    with db.unit_of_work() as session:
        perm_repo = PermissionRepository(session)
        role_repo = RoleRepository(session)
        user_repo = UserRepository(session)

        _seed_permissions(perm_repo)
        session.flush()  # ensure permission ids exist for role linking
        _seed_roles(role_repo, perm_repo)
        session.flush()
        generated_password = _seed_admin(user_repo, role_repo)
        _seed_lab_tests(session)
        _seed_medications(session)
        _seed_inventory(session)
        _seed_accounts(session)

    return generated_password


def _seed_lab_tests(session) -> None:
    existing = set(session.execute(select(LabTest.name)).scalars().all())
    for name, code, sample_type, ref, unit in DEFAULT_LAB_TESTS:
        if name not in existing:
            session.add(LabTest(name=name, code=code, sample_type=sample_type,
                                reference_range=ref, unit=unit))
            log.info("Seeded lab test %s", name)


def _seed_medications(session) -> None:
    existing = set(session.execute(select(Medication.name)).scalars().all())
    for name, generic, form, strength, unit, reorder in DEFAULT_MEDICATIONS:
        if name not in existing:
            session.add(Medication(name=name, generic_name=generic, form=form,
                                   strength=strength, unit=unit, reorder_level=reorder))
            log.info("Seeded medication %s", name)


def _seed_inventory(session) -> None:
    existing = set(session.execute(select(InventoryItem.name)).scalars().all())
    for name, category, unit, reorder in DEFAULT_INVENTORY:
        if name not in existing:
            session.add(InventoryItem(name=name, category=category, unit=unit,
                                      reorder_level=reorder))
            log.info("Seeded inventory item %s", name)


def _seed_accounts(session) -> None:
    existing = set(session.execute(select(Account.code)).scalars().all())
    for code, name, account_type in DEFAULT_ACCOUNTS:
        if code not in existing:
            session.add(Account(code=code, name=name, account_type=account_type.value))
            log.info("Seeded account %s %s", code, name)


def _seed_permissions(perm_repo: PermissionRepository) -> None:
    existing = perm_repo.all_codes()
    for code, module, description in all_permission_rows():
        if code not in existing:
            perm_repo.add(Permission(code=code, module=module, description=description))
            log.info("Seeded permission %s", code)


def _seed_roles(role_repo: RoleRepository, perm_repo: PermissionRepository) -> None:
    code_to_perm = {p.code: p for p in perm_repo.list(limit=10_000)}
    for role_name, perm_codes in ROLE_MATRIX.items():
        role = role_repo.get_by_name(role_name)
        if role is None:
            role = Role(
                name=role_name,
                description=ROLE_DESCRIPTIONS.get(role_name),
                is_system=True,
            )
            role_repo.add(role)
        desired = {code_to_perm[c] for c in perm_codes if c in code_to_perm}
        current = set(role.permissions)
        for perm in desired - current:
            role.permissions.append(perm)


def _seed_admin(user_repo: UserRepository, role_repo: RoleRepository) -> str | None:
    # include_deleted=True: the username UNIQUE constraint spans soft-deleted
    # rows, so a deactivated 'admin' must still suppress re-creation (otherwise
    # the insert raises IntegrityError and crashes startup on every launch).
    if user_repo.get_by_username(DEFAULT_ADMIN_USERNAME, include_deleted=True) is not None:
        return None
    password = generate_temporary_password()
    admin_role = role_repo.get_by_name(ROLE_ADMIN)
    admin = User(
        username=DEFAULT_ADMIN_USERNAME,
        password_hash=hash_password(password),
        full_name="System Administrator",
        is_active=True,
        must_change_password=True,
    )
    if admin_role is not None:
        admin.roles.append(admin_role)
    user_repo.add(admin)
    log.warning("Created initial admin account '%s'.", DEFAULT_ADMIN_USERNAME)
    return password
