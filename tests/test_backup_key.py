"""Backups that can be restored on a different machine, safely.

The field-encryption key is sealed to the machine that made it, so a backup
carried to a second machine used to fail twice: the HMAC could not verify,
because it was signed with a key this install has never held, and even past
that the encrypted columns would not open.

These tests cover the fix and, just as importantly, what it must NOT become: a
backup that simply contains the key would hand every Tazkira to whoever picks
up the USB stick, which is worse than a backup nobody can restore.

"Another machine" is simulated the way it actually differs — a separate data
directory with its own generated key — rather than by mocking the escrow.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from mediflow.core import key_escrow
from mediflow.core.exceptions import BackupError
from mediflow.core.security import FieldCipher
from mediflow.data.database import current_permissions
from mediflow.data.schema import create_all
from mediflow.services.backup_service import BackupService

PASSPHRASE = "a-passphrase-long-enough"


@pytest.fixture(autouse=True)
def _allowed():
    """Every method here is behind @require("backup.run")."""
    token = current_permissions.set({"backup.run"})
    yield
    current_permissions.reset(token)


def _install(tmp_path, name: str) -> tuple[BackupService, FieldCipher]:
    """A self-contained MediFlow install: own database, own key, own backups."""
    from mediflow.data.database import Database

    root = tmp_path / name
    root.mkdir()
    database = Database(f"sqlite:///{root / 'mediflow.db'}")
    create_all(database)
    cipher = FieldCipher.from_key_file(root / ".secret_key")
    service = BackupService(database, root / "backups", cipher,
                            secret_key_path=root / ".secret_key")
    return service, cipher


# ── the escrow envelope ──────────────────────────────────────────────────────

def test_the_key_never_appears_in_the_clear():
    key = Fernet.generate_key()
    envelope = key_escrow.wrap(key, PASSPHRASE)

    assert key not in envelope.encode()
    assert key_escrow.unwrap(envelope, PASSPHRASE) == key


def test_a_short_passphrase_is_refused_with_the_reason():
    with pytest.raises(BackupError, match="at least"):
        key_escrow.wrap(Fernet.generate_key(), "short")


def test_the_wrong_passphrase_and_the_wrong_file_say_different_things():
    envelope = key_escrow.wrap(Fernet.generate_key(), PASSPHRASE)

    with pytest.raises(BackupError, match="Wrong passphrase"):
        key_escrow.unwrap(envelope, "a-different-passphrase")
    with pytest.raises(BackupError, match="not a MediFlow backup key file"):
        key_escrow.unwrap("just some text", PASSPHRASE)


def test_a_tampered_envelope_does_not_open():
    envelope = key_escrow.wrap(Fernet.generate_key(), PASSPHRASE)
    corrupted = envelope.replace("key=gAAAA", "key=gBBBB")

    with pytest.raises(BackupError):
        key_escrow.unwrap(corrupted, PASSPHRASE)


# ── what lands on disk ───────────────────────────────────────────────────────

def test_no_passphrase_means_no_key_leaves_the_machine(tmp_path):
    service, cipher = _install(tmp_path, "clinic")

    backup = service.create_backup()

    assert not backup.with_suffix(".key").exists()
    assert cipher.key not in backup.read_bytes()      # nor hidden in the db


def test_a_passphrase_writes_a_key_sidecar_that_is_not_the_key(tmp_path):
    service, cipher = _install(tmp_path, "clinic")

    backup = service.create_backup(passphrase=PASSPHRASE)
    sidecar = backup.with_suffix(".key")

    assert sidecar.exists()
    assert cipher.key not in sidecar.read_bytes()     # wrapped, not copied
    assert key_escrow.unwrap(sidecar.read_text(), PASSPHRASE) == cipher.key


def test_backups_report_whether_a_key_travels_with_them(tmp_path):
    service, _ = _install(tmp_path, "clinic")
    service.create_backup()
    service.create_backup(passphrase=PASSPHRASE)

    assert sorted(b.has_key for b in service.list_backups()) == [False, True]


def test_deleting_a_backup_takes_its_key_with_it(tmp_path):
    service, _ = _install(tmp_path, "clinic")
    backup = service.create_backup(passphrase=PASSPHRASE)

    service.delete_backup(backup)

    assert not backup.exists()
    assert not backup.with_suffix(".key").exists()
    assert not backup.with_suffix(".hmac").exists()


# ── the case this exists for ─────────────────────────────────────────────────

def test_a_backup_from_another_machine_restores_and_adopts_its_key(tmp_path):
    source, source_cipher = _install(tmp_path, "old-clinic-pc")
    backup = source.create_backup(passphrase=PASSPHRASE)

    target, target_cipher = _install(tmp_path, "new-clinic-mac")
    assert target_cipher.key != source_cipher.key      # genuinely a second install
    for suffix in (".db", ".hmac", ".key"):
        carried = target.backups_dir / backup.with_suffix(suffix).name
        carried.parent.mkdir(parents=True, exist_ok=True)
        carried.write_bytes(backup.with_suffix(suffix).read_bytes())

    result = target.restore_backup(target.backups_dir / backup.name,
                                   passphrase=PASSPHRASE)

    assert result.key_restored
    assert result.restart_required                     # the live cipher is stale
    assert FieldCipher.from_key_file(tmp_path / "new-clinic-mac" / ".secret_key").key \
        == source_cipher.key


def test_without_the_passphrase_that_backup_is_refused_not_half_restored(tmp_path):
    source, _ = _install(tmp_path, "old-clinic-pc")
    backup = source.create_backup(passphrase=PASSPHRASE)

    target, target_cipher = _install(tmp_path, "new-clinic-mac")
    for suffix in (".db", ".hmac", ".key"):
        carried = target.backups_dir / backup.with_suffix(suffix).name
        carried.parent.mkdir(parents=True, exist_ok=True)
        carried.write_bytes(backup.with_suffix(suffix).read_bytes())

    # The HMAC was signed with the source key, so it cannot verify here — and
    # the error has to point at the passphrase rather than cry tampering.
    with pytest.raises(BackupError, match="another machine"):
        target.restore_backup(target.backups_dir / backup.name)
    assert FieldCipher.from_key_file(
        tmp_path / "new-clinic-mac" / ".secret_key").key == target_cipher.key


def test_the_wrong_passphrase_changes_nothing(tmp_path):
    source, _ = _install(tmp_path, "old-clinic-pc")
    backup = source.create_backup(passphrase=PASSPHRASE)

    target, target_cipher = _install(tmp_path, "new-clinic-mac")
    for suffix in (".db", ".hmac", ".key"):
        carried = target.backups_dir / backup.with_suffix(suffix).name
        carried.parent.mkdir(parents=True, exist_ok=True)
        carried.write_bytes(backup.with_suffix(suffix).read_bytes())

    with pytest.raises(BackupError, match="Wrong passphrase"):
        target.restore_backup(target.backups_dir / backup.name,
                              passphrase="the-wrong-passphrase")
    assert FieldCipher.from_key_file(
        tmp_path / "new-clinic-mac" / ".secret_key").key == target_cipher.key


# ── the ordinary local case must not have grown a ceremony ──────────────────

def test_a_local_restore_still_needs_no_passphrase(tmp_path):
    service, cipher = _install(tmp_path, "clinic")
    backup = service.create_backup()

    result = service.restore_backup(backup)

    assert not result.key_restored
    assert not result.restart_required
    assert result.safety.exists()
    assert FieldCipher.from_key_file(tmp_path / "clinic" / ".secret_key").key == cipher.key


def test_restoring_the_machines_own_key_is_not_treated_as_a_change(tmp_path):
    service, _cipher = _install(tmp_path, "clinic")
    backup = service.create_backup(passphrase=PASSPHRASE)

    result = service.restore_backup(backup, passphrase=PASSPHRASE)

    assert not result.key_restored          # same key; nothing to adopt
    assert not result.restart_required


def test_the_safety_copy_carries_the_key_it_was_made_with(tmp_path):
    """Otherwise the 'safety' copy is the one thing nobody could restore."""
    source, _ = _install(tmp_path, "old-clinic-pc")
    backup = source.create_backup(passphrase=PASSPHRASE)

    target, target_cipher = _install(tmp_path, "new-clinic-mac")
    for suffix in (".db", ".hmac", ".key"):
        carried = target.backups_dir / backup.with_suffix(suffix).name
        carried.parent.mkdir(parents=True, exist_ok=True)
        carried.write_bytes(backup.with_suffix(suffix).read_bytes())

    result = target.restore_backup(target.backups_dir / backup.name,
                                   passphrase=PASSPHRASE)

    escrowed = result.safety.with_suffix(".key")
    assert escrowed.exists()
    assert key_escrow.unwrap(escrowed.read_text(), PASSPHRASE) == target_cipher.key


def test_a_passphrase_with_no_key_file_beside_the_backup_is_an_error(tmp_path):
    service, _ = _install(tmp_path, "clinic")
    backup = service.create_backup()          # no key sidecar written

    with pytest.raises(BackupError, match="no key file"):
        service.restore_backup(backup, passphrase=PASSPHRASE)
