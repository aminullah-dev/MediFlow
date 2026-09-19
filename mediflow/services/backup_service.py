"""Backup service: create and restore SQLite database backups.

Uses SQLite's online backup API so backups are consistent even while the
application is running, and restore replaces the live database in place through
the existing connection (no restart required).

Integrity & authenticity: every backup is written with an HMAC sidecar
(``<name>.hmac``) keyed by the install's secret key. Restore refuses any file
that fails ``PRAGMA integrity_check``, lacks the expected schema, or whose HMAC
does not verify — closing the "drop in a crafted database" substitution vector.

Moving a backup to another machine
----------------------------------
A backup is only the database. The field-encryption key is sealed to the
machine that made it, so restoring on a second machine used to produce rows
that opened but columns that did not — and, before that, an HMAC failure,
because the signature was made with a key this install does not have.

Passing a passphrase to :meth:`BackupService.create_backup` writes a third
sidecar, ``<name>.key``, carrying that key wrapped against the passphrase (see
:mod:`mediflow.core.key_escrow`). Restore with the same passphrase then
verifies the HMAC with the key that signed it and adopts that key locally,
re-sealed to *this* machine.

The passphrase is not optional ceremony. A backup that simply contained the key
would hand over every encrypted column to whoever picks up the USB stick, which
is worse than one nobody can restore.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mediflow.core import key_escrow
from mediflow.core.exceptions import BackupError
from mediflow.core.logging_config import get_logger
from mediflow.core.security import FieldCipher, install_key
from mediflow.data.base import utcnow
from mediflow.data.database import Database
from mediflow.services.authz import require

log = get_logger("services.backup")

_BACKUP_PREFIX = "mediflow_backup_"
# Tables a genuine MediFlow database must contain.
_REQUIRED_TABLES = {"users", "roles", "permissions", "audit_log", "patients"}


@dataclass(slots=True)
class BackupDTO:
    name: str
    path: str
    size_bytes: int
    modified: datetime
    has_key: bool = False       # a .key sidecar travels with it


@dataclass(slots=True)
class RestoreResult:
    """What a restore did, beyond replacing the database."""

    safety: Path
    key_restored: bool = False

    @property
    def restart_required(self) -> bool:
        """True when the process must be restarted before the data is readable.

        Adopting a restored key leaves the running :class:`FieldCipher` and the
        audit hash chain bound to the old one. Swapping them underneath the
        services holding references would be the kind of fix that works in a
        test and corrupts an audit chain in a clinic.
        """
        return self.key_restored


class BackupService:
    def __init__(self, db: Database, backups_dir: Path,
                 cipher: FieldCipher | None = None,
                 secret_key_path: Path | None = None):
        self._db = db
        self._backups_dir = Path(backups_dir)
        self._cipher = cipher
        # Only needed to adopt a key from another machine's backup; without it
        # such a restore is refused rather than half-done.
        self._secret_key_path = Path(secret_key_path) if secret_key_path else None

    @property
    def backups_dir(self) -> Path:
        return self._backups_dir

    @require("backup.run")
    def create_backup(self, destination_dir: Path | None = None, *,
                      passphrase: str | None = None) -> Path:
        """Write a backup. With a passphrase, the encryption key travels too.

        Without one the backup is restorable only on this machine, which is the
        common case and stays the default: no passphrase to lose, and nothing
        on the USB stick that a thief can turn into patient records.
        """
        target_dir = Path(destination_dir) if destination_dir else self._backups_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = utcnow().strftime("%Y%m%d_%H%M%S")
        base = f"{_BACKUP_PREFIX}{stamp}"
        dest = target_dir / f"{base}.db"
        counter = 2
        while dest.exists():  # avoid clobbering a backup taken in the same second
            dest = target_dir / f"{base}-{counter}.db"
            counter += 1
        raw = self._db.engine.raw_connection()
        try:
            source: sqlite3.Connection = raw.driver_connection
            with closing(sqlite3.connect(str(dest))) as backup_conn:
                source.backup(backup_conn)
                backup_conn.commit()  # `closing` does not commit the way `with conn:` did
            log.info("Created backup %s", dest)
        except sqlite3.Error as exc:  # pragma: no cover - surfaced to the user
            raise BackupError(f"Backup failed: {exc}") from exc
        finally:
            raw.close()
        self._write_hmac(dest)
        self._write_key_envelope(dest, passphrase)
        return dest

    def list_backups(self) -> list[BackupDTO]:
        if not self._backups_dir.exists():
            return []
        rows: list[BackupDTO] = []
        for path in self._backups_dir.glob("*.db"):
            stat = path.stat()
            rows.append(BackupDTO(
                name=path.name, path=str(path), size_bytes=stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC).astimezone(),
                has_key=self._key_path(path).exists(),
            ))
        rows.sort(key=lambda b: b.modified, reverse=True)
        return rows

    @require("backup.run")
    def restore_backup(self, backup_path: Path, *,
                       passphrase: str | None = None) -> RestoreResult:
        """Restore from a backup, taking a safety copy of the current data first."""
        backup_path = Path(backup_path)
        if not backup_path.exists():
            raise BackupError("Backup file not found.")
        self._validate(backup_path)

        # Unwrap before anything else: the key decides whether the HMAC below
        # can verify at all, since a backup from another machine was signed
        # with a key this install has never held.
        incoming_key = self._unwrap_key(backup_path, passphrase)
        self._verify_hmac(backup_path, incoming_key)

        # The safety copy is encrypted with the key we are about to replace, so
        # it carries that key under the same passphrase. Skipping this would
        # make the "safety" copy the one thing nobody could ever restore.
        safety = self.create_backup(passphrase=passphrase)
        # Close ALL pooled connections first. Overwriting the live database file
        # via the backup API while other connections still hold the old WAL
        # state corrupts them ("database disk image is malformed"). dispose()
        # only closes *idle* pooled connections, so refuse to run while any
        # connection is checked out (e.g. a background worker mid-query).
        if self._db.engine.pool.checkedout():
            raise BackupError("The database is busy; finish open work and retry.")
        self._db.dispose()  # also removes the thread's scoped session
        try:
            with closing(sqlite3.connect(str(backup_path))) as source:
                raw = self._db.engine.raw_connection()
                try:
                    target: sqlite3.Connection = raw.driver_connection
                    source.backup(target)
                    target.commit()
                finally:
                    raw.close()
            self._db.dispose()  # drop the restore connection cleanly
            log.warning("Restored database from %s (safety copy: %s)", backup_path, safety)
        except sqlite3.Error as exc:  # pragma: no cover
            raise BackupError(f"Restore failed: {exc}") from exc
        return RestoreResult(safety=safety,
                             key_restored=self._adopt_key(incoming_key))

    @require("backup.run")
    def delete_backup(self, backup_path: Path) -> None:
        path = Path(backup_path)
        try:
            path.unlink(missing_ok=True)
            self._hmac_path(path).unlink(missing_ok=True)
            self._key_path(path).unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover
            raise BackupError(f"Could not delete backup: {exc}") from exc

    # -- integrity ----------------------------------------------------------
    @staticmethod
    def _validate(path: Path) -> None:
        try:
            with closing(sqlite3.connect(str(path))) as conn:
                check = conn.execute("PRAGMA integrity_check").fetchone()
                tables = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.Error as exc:
            raise BackupError("The selected file is not a valid database.") from exc
        if not check or check[0] != "ok":
            raise BackupError("The backup failed its integrity check (file is corrupt).")
        if not _REQUIRED_TABLES.issubset(tables):
            raise BackupError("The selected file does not look like a MediFlow backup.")

    def _write_hmac(self, dest: Path) -> None:
        if self._cipher is None:
            return
        try:
            self._hmac_path(dest).write_text(self._cipher.sign(dest.read_bytes()),
                                             encoding="ascii")
        except OSError:  # pragma: no cover
            log.warning("Could not write backup integrity signature for %s", dest)

    def _verify_hmac(self, backup_path: Path, incoming_key: bytes | None = None) -> None:
        """Check the signature, against the travelling key when one came along.

        The signature was made on the machine that wrote the backup, with that
        machine's key. Checking it against the local key is right for a backup
        from here and guaranteed to fail for one from anywhere else — which is
        why a cross-machine restore was impossible even before the encrypted
        columns became a problem. When a key envelope unwrapped, that key is
        the one that signed this file, so it is the one to verify with.
        """
        cipher = FieldCipher(incoming_key) if incoming_key else self._cipher
        if cipher is None:
            return  # headless/test context without a cipher
        sidecar = self._hmac_path(backup_path)
        if not sidecar.exists():
            raise BackupError(
                "This backup has no integrity signature and cannot be trusted."
            )
        import hmac as _hmac

        expected = sidecar.read_text(encoding="ascii").strip()
        actual = cipher.sign(backup_path.read_bytes())
        if not _hmac.compare_digest(expected, actual):
            raise BackupError(
                "The backup's integrity signature does not match — it may be "
                "tampered with, or created on a different installation. If it "
                "came from another machine, restore it with the passphrase its "
                "key file was made with."
            )

    @staticmethod
    def _hmac_path(backup_path: Path) -> Path:
        return backup_path.with_suffix(".hmac")

    # -- the travelling key -------------------------------------------------
    @staticmethod
    def _key_path(backup_path: Path) -> Path:
        return backup_path.with_suffix(".key")

    def _write_key_envelope(self, dest: Path, passphrase: str | None) -> None:
        if passphrase is None:
            return
        if self._cipher is None:
            raise BackupError(
                "This installation has no encryption key loaded, so there is "
                "nothing to travel with the backup."
            )
        # Deliberately not wrapped in try/except: a passphrase was asked for, so
        # a backup written without the key is not a lesser success, it is the
        # wrong file. Failing here leaves the .db and .hmac on disk, which is
        # exactly a plain local backup — still restorable here.
        self._key_path(dest).write_text(
            key_escrow.wrap(self._cipher.key, passphrase), encoding="ascii")
        log.info("Backup %s carries its encryption key", dest.name)

    def _unwrap_key(self, backup_path: Path, passphrase: str | None) -> bytes | None:
        """The key travelling with this backup, or None if none applies."""
        envelope = self._key_path(backup_path)
        if not envelope.exists():
            if passphrase:
                raise BackupError(
                    "A passphrase was given, but this backup has no key file "
                    "beside it. Copy the .key file along with the .db and "
                    ".hmac, or restore without a passphrase on the machine "
                    "that made it."
                )
            return None
        if not passphrase:
            # Not an error: a local restore does not need the envelope, and
            # demanding a passphrase for one would be theatre.
            return None
        return key_escrow.unwrap(envelope.read_text(encoding="ascii"), passphrase)

    def _adopt_key(self, incoming_key: bytes | None) -> bool:
        """Make a restored key this installation's own. True when it changed."""
        if incoming_key is None:
            return False
        if self._cipher is not None and incoming_key == self._cipher.key:
            return False            # same machine, nothing to adopt
        if self._secret_key_path is None:
            raise BackupError(
                "This backup was made on another machine and its data cannot "
                "be read without adopting its key, but this installation was "
                "started without a key file path."
            )
        install_key(self._secret_key_path, incoming_key)
        log.warning(
            "Adopted the encryption key that travelled with the restored "
            "backup. MediFlow must be restarted before the restored data can "
            "be read."
        )
        return True
