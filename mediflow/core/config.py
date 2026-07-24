"""Runtime configuration and filesystem layout.

All mutable data lives outside the source tree in a per-user application data
directory (``%APPDATA%\\MediFlow`` on Windows). This keeps the installation
read-only and makes backup/restore a matter of copying one folder.

The active application settings (language, theme, backup schedule, clinic id)
are persisted as a small JSON file so they survive restarts without needing the
database — the UI reads them before the database is even opened.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from mediflow.core.constants import Language, Theme

APP_DIR_NAME = "MediFlow"


def _base_data_dir() -> Path:
    """Return the OS-appropriate writable base directory for application data.

    ``MEDIFLOW_DATA_DIR`` overrides everything. That escape hatch exists for a
    concrete reason: when the interpreter is a Microsoft Store (MSIX) build,
    Windows silently redirects writes to ``%APPDATA%`` into a per-package
    ``LocalCache`` folder, so a script and the installed app can each believe
    they are using "the" database while touching two different files. Setting
    this variable pins both to one path.
    """
    override = os.environ.get("MEDIFLOW_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform.startswith("win"):
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
        return Path(root) / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_DIR_NAME


@dataclass(slots=True)
class Paths:
    """Resolved, guaranteed-to-exist runtime paths."""

    base: Path
    database: Path
    backups: Path
    logs: Path
    documents: Path      # scanned patient documents, attachments
    photos: Path         # patient / employee photos
    secret_key: Path     # encryption key for sensitive fields

    @classmethod
    def resolve(cls, base: Path | None = None) -> "Paths":
        base = base or _base_data_dir()
        paths = cls(
            base=base,
            database=base / "mediflow.db",
            backups=base / "backups",
            logs=base / "logs",
            documents=base / "documents",
            photos=base / "photos",
            secret_key=base / ".secret_key",
        )
        for directory in (base, paths.backups, paths.logs, paths.documents, paths.photos):
            directory.mkdir(parents=True, exist_ok=True)
        return paths


@dataclass(slots=True)
class AppSettings:
    """User-facing preferences persisted to ``settings.json``."""

    language: str = Language.DARI.value
    theme: str = Theme.LIGHT.value
    auto_backup_enabled: bool = True
    auto_backup_interval_hours: int = 24
    session_lock_minutes: int = 10          # 0 disables auto-lock
    last_username: str = ""                  # pre-filled on the next sign-in
    clinic_name: str = ""
    fiscal_year_start_month: int = 1        # Hijri/Gregorian configurable later
    _path: Path | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, paths: Paths) -> "AppSettings":
        settings_file = paths.base / "settings.json"
        if settings_file.exists():
            try:
                raw = json.loads(settings_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                raw = {}
        else:
            raw = {}
        allowed = {f for f in cls.__dataclass_fields__ if not f.startswith("_")}
        clean = {k: v for k, v in raw.items() if k in allowed}
        instance = cls(**clean)
        instance._path = settings_file
        return instance

    def save(self) -> None:
        if self._path is None:
            raise RuntimeError("AppSettings was not loaded from disk; cannot save.")
        data = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


@dataclass(slots=True)
class Config:
    """Top-level container assembled once at startup and passed via DI."""

    paths: Paths
    settings: AppSettings
    debug: bool = False

    @classmethod
    def bootstrap(cls, base: Path | None = None, *, debug: bool = False) -> "Config":
        paths = Paths.resolve(base)
        settings = AppSettings.load(paths)
        return cls(paths=paths, settings=settings, debug=debug)

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.paths.database}"
