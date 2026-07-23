"""Regression tests for the Persian-keyboard-layout login failure.

Background: clinic machines carry both a US (0409) and a Persian (0429) Windows
layout. With the Persian one active the operator types ``Amin2026`` but the
masked password field receives ``َئهد2026``, so every sign-in fails and every
password reset produces another unenterable string. These tests pin the
recovery behaviour so the bug cannot silently return.
"""
from __future__ import annotations

import pytest

from mediflow.core.exceptions import AuthenticationError
from mediflow.core.keyboard import (
    from_persian_layout,
    has_persian_layout_chars,
    normalize_digits,
)
from mediflow.data.database import Database, current_user_id
from mediflow.data.models.user import LoginHistory
from mediflow.data.repositories.user_repository import UserRepository
from mediflow.data.schema import create_all
from mediflow.seeds.seed_data import DEFAULT_ADMIN_USERNAME, seed_database
from mediflow.services.auth_service import AuthService


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


# What the field actually receives for a few real passwords when the Persian
# layout is active. Captured from the Windows layout tables themselves.
AS_TYPED_ON_PERSIAN = {
    "Amin2026": "َئهد2026",
    "mediflow2026": "ئثیهبمخص2026",
    "Clinic99": "ژمهدهز99",
    "aB3dEf7h": "شإ3یٍب7ا",
}


@pytest.mark.parametrize("intended,typed", AS_TYPED_ON_PERSIAN.items())
def test_layout_remap_recovers_the_intended_password(intended, typed):
    assert from_persian_layout(typed) == intended
    assert has_persian_layout_chars(typed)


@pytest.mark.parametrize("password", ["Amin2026", "p@ss[word]", "a,b\\c", "Zz9!", "12345678"])
def test_correctly_typed_passwords_are_never_altered(password):
    """The remap must be a no-op for ASCII, or it would break working logins."""
    assert from_persian_layout(password) == password
    assert not has_persian_layout_chars(password)


def test_persian_digits_fold_to_ascii():
    assert normalize_digits("۲۰۲۶") == "2026"      # Extended Arabic-Indic
    assert normalize_digits("٢٠٢٦") == "2026"      # Arabic-Indic
    assert normalize_digits("2026") == "2026"      # already ASCII


def test_remap_is_idempotent_on_its_own_output():
    once = from_persian_layout("َئهد2026")
    assert from_persian_layout(once) == once


def test_rial_sign_is_not_decomposed():
    """Shift+R emits the 4-char Rial sign; decomposing it would forge bogus
    single-char entries that collide with the unshifted map."""
    assert from_persian_layout("ريال") == "R"


def test_sign_in_succeeds_with_password_typed_on_persian_layout(db, admin_password):
    """The headline fix: a layout slip must still let the operator in."""
    from mediflow.core.security import hash_password

    auth = AuthService(db)
    with db.unit_of_work() as session:
        user = UserRepository(session).get_by_username(DEFAULT_ADMIN_USERNAME)
        user.password_hash = hash_password("Amin2026")
        user.must_change_password = False

    signed_in = auth.authenticate(
        DEFAULT_ADMIN_USERNAME, AS_TYPED_ON_PERSIAN["Amin2026"])
    assert signed_in.username == DEFAULT_ADMIN_USERNAME


def test_layout_slip_does_not_count_as_a_failed_attempt(db, admin_password):
    """A forgiven slip must not push the account toward lockout."""
    auth = AuthService(db)
    from mediflow.core.security import hash_password

    with db.unit_of_work() as session:
        user = UserRepository(session).get_by_username(DEFAULT_ADMIN_USERNAME)
        user.password_hash = hash_password("Amin2026")
        user.must_change_password = False

    for _ in range(6):
        auth.authenticate(DEFAULT_ADMIN_USERNAME, AS_TYPED_ON_PERSIAN["Amin2026"])

    with db.unit_of_work() as session:
        user = UserRepository(session).get_by_username(DEFAULT_ADMIN_USERNAME)
        assert user.failed_login_count == 0
        assert user.locked_until is None


def test_layout_recovery_is_recorded_in_login_history(db, admin_password):
    """The audit trail must show the sign-in needed layout correction."""
    auth = AuthService(db)
    from mediflow.core.security import hash_password

    with db.unit_of_work() as session:
        user = UserRepository(session).get_by_username(DEFAULT_ADMIN_USERNAME)
        user.password_hash = hash_password("Amin2026")
        user.must_change_password = False

    auth.authenticate(DEFAULT_ADMIN_USERNAME, AS_TYPED_ON_PERSIAN["Amin2026"])

    with db.unit_of_work() as session:
        last = (
            session.query(LoginHistory)
            .order_by(LoginHistory.id.desc())
            .first()
        )
        assert last.success is True
        assert last.reason == "layout_recovered"


def test_a_genuinely_wrong_password_still_fails(db, admin_password):
    """Recovery must not become a way in for an actually wrong password."""
    auth = AuthService(db)
    with pytest.raises(AuthenticationError):
        auth.authenticate(DEFAULT_ADMIN_USERNAME, "totally-wrong-password")

    # A Persian string that maps to something still wrong must also fail.
    with pytest.raises(AuthenticationError):
        auth.authenticate(DEFAULT_ADMIN_USERNAME, "ضضضضضضضض")


def test_correct_password_still_authenticates(db, admin_password):
    auth = AuthService(db)
    user = auth.authenticate(DEFAULT_ADMIN_USERNAME, admin_password)
    assert user.username == DEFAULT_ADMIN_USERNAME


def test_change_password_accepts_layout_slipped_current_password(db, admin_password):
    """Even the change-password flow must forgive the slip on the old password."""
    auth = AuthService(db)
    from mediflow.core.security import hash_password, verify_password

    with db.unit_of_work() as session:
        user = UserRepository(session).get_by_username(DEFAULT_ADMIN_USERNAME)
        user.password_hash = hash_password("Amin2026")
        user_id = user.id

    auth.change_password(user_id, AS_TYPED_ON_PERSIAN["Amin2026"], "Kabul2026")

    with db.unit_of_work() as session:
        user = UserRepository(session).get_by_username(DEFAULT_ADMIN_USERNAME)
        assert verify_password("Kabul2026", user.password_hash)
