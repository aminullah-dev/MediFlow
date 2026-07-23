"""End-to-end foundation tests: schema, seeding, auth, patients, audit trail.

These exercise the full core stack against a real (temporary) SQLite database —
no GUI required — proving the data, security, repository, service, and audit
layers work together.
"""
from __future__ import annotations

import json

import pytest

from mediflow.core.exceptions import AccountLockedError, AuthenticationError
from mediflow.core.security import FieldCipher
from mediflow.data.database import Database, current_user_id
from mediflow.data.models.audit import AuditLog
from mediflow.data.repositories.patient_repository import PatientRepository
from mediflow.data.repositories.user_repository import UserRepository
from mediflow.data.schema import create_all
from mediflow.seeds.seed_data import DEFAULT_ADMIN_USERNAME, seed_database
from mediflow.services.auth_service import MAX_FAILED_ATTEMPTS, AuthService
from mediflow.services.patient_service import PatientRegistration, PatientService


@pytest.fixture()
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path/'test.db'}")
    create_all(database)
    current_user_id.set(None)
    yield database
    database.dispose()


@pytest.fixture()
def admin_password(db):
    return seed_database(db)


@pytest.fixture()
def cipher():
    from cryptography.fernet import Fernet

    return FieldCipher(Fernet.generate_key())


def test_seeding_is_idempotent(db):
    first = seed_database(db)
    assert first is not None  # admin created, password returned once
    second = seed_database(db)
    assert second is None     # nothing new the second time

    with db.unit_of_work() as session:
        users = UserRepository(session)
        admin = users.get_by_username(DEFAULT_ADMIN_USERNAME)
        assert admin is not None
        assert admin.has_permission("patient.create")
        assert admin.has_permission("settings.manage")


def test_authenticate_success_and_permissions(db, admin_password):
    auth = AuthService(db)
    user = auth.authenticate(DEFAULT_ADMIN_USERNAME, admin_password)
    assert user.username == DEFAULT_ADMIN_USERNAME
    assert user.can("patient.create")
    assert user.must_change_password is True


def test_authenticate_wrong_password_rejected(db, admin_password):
    auth = AuthService(db)
    with pytest.raises(AuthenticationError):
        auth.authenticate(DEFAULT_ADMIN_USERNAME, "definitely-wrong")


def test_account_locks_after_repeated_failures(db, admin_password):
    auth = AuthService(db)
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(AuthenticationError):
            auth.authenticate(DEFAULT_ADMIN_USERNAME, "wrong")
    with pytest.raises(AccountLockedError):
        auth.authenticate(DEFAULT_ADMIN_USERNAME, "wrong")


def test_patient_registration_generates_mrn_and_encrypts_id(db, admin_password, cipher):
    auth = AuthService(db)
    auth.authenticate(DEFAULT_ADMIN_USERNAME, admin_password)  # sets current user

    service = PatientService(db, cipher=cipher)
    patient_id = service.register(
        PatientRegistration(
            first_name="Ahmad",
            last_name="Zadran",
            approximate_age_years=34,
            national_id="1401-1234567",
            phone="0700000000",
        )
    )

    with db.unit_of_work() as session:
        patient = PatientRepository(session).get_or_raise(patient_id)
        assert patient.mrn.startswith("P-")
        assert patient.national_id_encrypted != "1401-1234567"  # not plaintext
        assert cipher.decrypt(patient.national_id_encrypted) == "1401-1234567"
        assert patient.created_by_id is not None  # attribution stamped


def test_audit_trail_records_create_and_update(db, admin_password):
    auth = AuthService(db)
    actor = auth.authenticate(DEFAULT_ADMIN_USERNAME, admin_password)

    service = PatientService(db, cipher=None)
    patient_id = service.register(
        PatientRegistration(first_name="Sara", last_name="Noori", approximate_age_years=20)
    )

    # Update the patient and confirm a diffed audit row is written.
    with db.unit_of_work() as session:
        patient = PatientRepository(session).get_or_raise(patient_id)
        patient.phone = "0788888888"

    with db.unit_of_work() as session:
        logs = (
            session.query(AuditLog)
            .filter(AuditLog.entity_type == "Patient", AuditLog.entity_id == patient_id)
            .order_by(AuditLog.id)
            .all()
        )
        actions = [row.action for row in logs]
        assert "create" in actions
        assert "update" in actions
        assert all(row.user_id == actor.id for row in logs)

        update_row = next(r for r in logs if r.action == "update")
        changes = json.loads(update_row.changes)
        assert "phone" in changes
        assert changes["phone"][1] == "0788888888"


def test_soft_delete_hides_but_retains(db, admin_password):
    auth = AuthService(db)
    auth.authenticate(DEFAULT_ADMIN_USERNAME, admin_password)
    service = PatientService(db, cipher=None)
    patient_id = service.register(
        PatientRegistration(first_name="Gul", last_name="Rahman", approximate_age_years=50)
    )

    with db.unit_of_work() as session:
        repo = PatientRepository(session)
        repo.soft_delete(repo.get_or_raise(patient_id))

    with db.unit_of_work() as session:
        repo = PatientRepository(session)
        assert repo.get(patient_id) is None                      # hidden by default
        assert repo.get(patient_id, include_deleted=True) is not None  # still there
        assert repo.count() == 0
