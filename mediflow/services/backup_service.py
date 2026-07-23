"""Backup service: create and restore SQLite database backups.

Uses SQLite's online backup API so backups are consistent even while the
application is running, and restore replaces the live database in place through
the existing connection (no restart required).

Integrity & authenticity: every backup is written with an HMAC sidecar
(``<name>.hmac``) keyed by the install's secret key. Restore refuses any file
that fails ``PRAGMA integrity_check``, lacks the expected schema, or whose HMAC
does not verify — closing the "drop in a crafted database" substitution vector.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mediflow.core.exceptions import BackupError
from mediflow.core.logging_config import get_logger
from mediflow.core.security import FieldCipher
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


class BackupService:
    def __init__(self, db: Database, backups_dir: Path, cipher: FieldCipher | None = None):
        self._db = db
        self._backups_dir = Path(backups_dir)
        self._cipher = cipher

    @property
    def backups_dir(self) -> Path:
        return self._backups_dir

    @require("backup.run")
    def create_backup(self, destination_dir: Path | None = None) -> Path:
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
            with sqlite3.connect(str(dest)) as backup_conn:
                source.backup(backup_conn)
            log.info("Created backup %s", dest)
        except sqlite3.Error as exc:  # pragma: no cover - surfaced to the user
            raise BackupError(f"Backup failed: {exc}") from exc
        finally:
            raw.close()
        self._write_hmac(dest)
        return dest

    def list_backups(self) -> list[BackupDTO]:
        if not self._backups_dir.exists():
            return []
        rows: list[BackupDTO] = []
        for path in self._backups_dir.glob("*.db"):
            stat = path.stat()
            rows.append(BackupDTO(
                name=path.name, path=str(path), size_bytes=stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime),
            ))
        rows.sort(key=lambda b: b.modified, reverse=True)
        return rows

    @require("backup.run")
    def restore_backup(self, backup_path: Path) -> Path:
        """Restore from a backup, returning the safety copy taken beforehand."""
        backup_path = Path(backup_path)
        if not backup_path.exists():
            raise BackupError("Backup file not found.")
        self._validate(backup_path)
        self._verify_hmac(backup_path)
        safety = self.create_backup()  # snapshot current state first
        # Close ALL pooled connections first. Overwriting the live database file
        # via the backup API while other connections still hold the old WAL
        # state corrupts them ("database disk image is malformed"). dispose()
        # only closes *idle* pooled connections, so refuse to run while any
        # connection is checked out (e.g. a background worker mid-query).
        if self._db.engine.pool.checkedout():
            raise BackupError("The database is busy; finish open work and retry.")
        self._db.dispose()  # also removes the thread's scoped session
        try:
            with sqlite3.connect(str(backup_path)) as source:
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
        return safety

    @require("backup.run")
    def delete_backup(self, backup_path: Path) -> None:
        path = Path(backup_path)
        try:
            path.unlink(missing_ok=True)
            self._hmac_path(path).unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover
            raise BackupError(f"Could not delete backup: {exc}") from exc

    # -- integrity ----------------------------------------------------------
    @staticmethod
    def _validate(path: Path) -> None:
        try:
            with sqlite3.connect(str(path)) as conn:
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

    def _verify_hmac(self, backup_path: Path) -> None:
        if self._cipher is None:
            return  # headless/test context without a cipher
        sidecar = self._hmac_path(backup_path)
        if not sidecar.exists():
            raise BackupError(
                "This backup has no integrity signature and cannot be trusted."
            )
        import hmac as _hmac

        expected = sidecar.read_text(encoding="ascii").strip()
        actual = self._cipher.sign(backup_path.read_bytes())
        if not _hmac.compare_digest(expected, actual):
            raise BackupError(
                "The backup's integrity signature does not match — it may be "
                "tampered with, or created on a different installation."
            )

    @staticmethod
    def _hmac_path(backup_path: Path) -> Path:
        return backup_path.with_suffix(".hmac")
