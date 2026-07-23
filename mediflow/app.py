"""Application composition root.

Wires together configuration, logging, database, security, services, and the Qt
presentation layer. This is the single place where concrete implementations are
constructed and injected — everything else depends on abstractions/parameters,
keeping the codebase testable and SOLID (Dependency Inversion).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

from mediflow.core.config import Config
from mediflow.core.constants import Language, Theme
from mediflow.core.logging_config import configure_logging, get_logger
from mediflow.core.security import FieldCipher
from mediflow.data.database import Database
from mediflow.data.schema import create_all
from mediflow.seeds.seed_data import seed_database
from mediflow.services.accounting_service import AccountingService
from mediflow.services.appointment_service import AppointmentService
from mediflow.services.audit_service import AuditService
from mediflow.services.auth_service import AuthService
from mediflow.services.backup_service import BackupService
from mediflow.services.billing_service import BillingService
from mediflow.services.hr_service import HRService
from mediflow.services.inventory_service import InventoryService
from mediflow.services.lab_service import LabService
from mediflow.services.medical_record_service import MedicalRecordService
from mediflow.services.patient_service import PatientService
from mediflow.services.pharmacy_service import PharmacyService
from mediflow.services.report_service import ReportService
from mediflow.services.settings_service import SettingsService
from mediflow.services.user_service import UserService

log = get_logger("app")


@dataclass
class ServiceContainer:
    """Constructed services, injected into the UI. Extend as modules land."""

    config: Config
    database: Database
    cipher: FieldCipher
    auth: AuthService
    patients: PatientService
    appointments: AppointmentService
    medical_records: MedicalRecordService
    pharmacy: PharmacyService
    lab: LabService
    inventory: InventoryService
    billing: BillingService
    accounting: AccountingService
    reports: ReportService
    hr: HRService
    users: UserService
    audit: AuditService
    settings: SettingsService
    backup: BackupService


def _persist_first_run_password(config: Config, password: str) -> None:
    """Write the initial admin credential to a restricted one-time file.

    Normally the password is never logged (logs are retained and may be shipped
    for support). ONE deliberate exception below: if the credential file cannot
    be written, the password is emitted to the log and stderr as a last resort —
    otherwise the freshly-created admin account would be unrecoverable. After
    using it, change the password and rotate/delete the log.
    """
    import os
    import stat

    path = config.paths.secret_key.parent / "INITIAL_ADMIN_PASSWORD.txt"
    try:
        path.write_text(
            "MediFlow — initial administrator account\n"
            "  username: admin\n"
            f"  temporary password: {password}\n\n"
            "Sign in, change this password immediately, then DELETE this file.\n",
            encoding="utf-8",
        )
    except OSError:
        # Deliberate policy exception (see docstring): without this the only
        # credential is lost. stderr too, in case the log handler shares the
        # same failing volume as the credential file.
        message = (
            "INITIAL ADMIN CREATED but the credential file could not be "
            f"written. Emergency recovery — username 'admin', password: {password}"
        )
        log.critical(message)
        print(message, file=sys.stderr)
        return
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # best-effort owner-only
    except OSError:  # pragma: no cover
        pass
    log.warning(
        "INITIAL ADMIN CREATED — credentials written to %s "
        "(read it, sign in, change the password, then delete the file).",
        path,
    )


def build_container(config: Config) -> ServiceContainer:
    database = Database(config.database_url, echo=config.debug)
    try:
        return _build_container_with(config, database)
    except Exception:
        database.dispose()  # never leak the engine on a failed startup
        raise


def _build_container_with(config: Config, database: Database) -> ServiceContainer:
    # First-run schema creation. In an installed product Alembic owns the
    # schema; create_all is a safe no-op once tables already exist.
    create_all(database)

    # Load the secret key and bind the audit hash chain BEFORE seeding, so the
    # rows seeding generates are chained with the real key (not the fallback).
    cipher = FieldCipher.from_key_file(config.paths.secret_key)
    from mediflow.data import audit as audit_hooks
    audit_hooks.set_audit_key(cipher.key)

    first_run_password = seed_database(database)
    if first_run_password:
        _persist_first_run_password(config, first_run_password)

    return ServiceContainer(
        config=config,
        database=database,
        cipher=cipher,
        auth=AuthService(database),
        patients=PatientService(database, cipher=cipher),
        appointments=AppointmentService(database),
        medical_records=MedicalRecordService(database),
        pharmacy=PharmacyService(database),
        lab=LabService(database),
        inventory=InventoryService(database),
        billing=BillingService(database),
        accounting=AccountingService(database),
        reports=ReportService(database),
        hr=HRService(database),
        users=UserService(database),
        audit=AuditService(database),
        settings=SettingsService(database),
        backup=BackupService(database, config.paths.backups, cipher),
    )


def _fail_early(message: str) -> int:
    """Show a startup error in a dialog (no logging/config prerequisites)."""
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("MediFlow")
    QMessageBox.critical(None, "MediFlow", message)
    return 1


def run() -> int:
    """Launch the desktop application. Returns the process exit code."""
    try:
        config = Config.bootstrap(debug="--debug" in sys.argv)
        configure_logging(config.paths.logs, debug=config.debug)
    except Exception as exc:  # unwritable APPDATA, bad settings.json, …
        return _fail_early(f"MediFlow cannot start:\n{type(exc).__name__}: {exc}")
    log.info("Starting MediFlow…")

    try:
        container = build_container(config)
    except Exception as exc:
        # A startup failure (unreadable key, corrupt database, …) must surface
        # as a clear message, not a console traceback the operator never sees.
        log.exception("Startup failed")
        detail = str(exc) or type(exc).__name__
        return _fail_early(f"{detail}\n\nLog folder: {config.paths.logs}")

    # Qt imports are deferred so headless tooling (tests, migrations, seeding)
    # never requires a display or PySide6 to be installed.
    from PySide6.QtWidgets import QApplication, QMessageBox

    from mediflow.core.exceptions import MediFlowError
    from mediflow.i18n.translator import TranslationManager
    from mediflow.ui.main_window import MainWindow
    from mediflow.ui.theme import ThemeManager

    # -- global UI error guard ---------------------------------------------
    # PySide6 delivers exceptions from signal/slot handlers to sys.excepthook
    # (NOT through QApplication.notify — verified empirically on 6.11.1), while
    # exceptions from overridden virtual event handlers surface via notify().
    # Both hooks funnel into one reporter so a PermissionDeniedError (or any
    # bug) becomes a dialog instead of a silent no-op or a lost traceback.
    _reporting = False

    def _report_ui_error(exc: BaseException) -> None:
        nonlocal _reporting
        if _reporting:  # re-entrancy guard: never stack error dialogs
            log.error("Suppressed nested UI error: %r", exc)
            return
        _reporting = True
        try:
            parent = QApplication.activeWindow()
            if isinstance(exc, MediFlowError):
                QMessageBox.warning(parent, "MediFlow", str(exc))
            else:
                log.error("Unhandled UI error", exc_info=exc)
                QMessageBox.critical(
                    parent, "MediFlow",
                    "An unexpected error occurred. It has been recorded in the log.",
                )
        finally:
            _reporting = False

    def _excepthook(exc_type, value, tb):  # slot exceptions land here
        _report_ui_error(value)

    sys.excepthook = _excepthook

    class _Application(QApplication):
        """Catches exceptions raised in overridden virtual event handlers."""

        def notify(self, receiver, event):
            try:
                return super().notify(receiver, event)
            except Exception as exc:  # pragma: no cover - safety net
                _report_ui_error(exc)
                return False

    qt_app = _Application(sys.argv)
    qt_app.setApplicationName("MediFlow")
    qt_app.setOrganizationName("MediFlow")

    translator = TranslationManager(qt_app)
    translator.install(Language(config.settings.language))

    theme = ThemeManager(qt_app)
    theme.apply(Theme(config.settings.theme))

    window = MainWindow(container, translator, theme)
    if not window.authenticate_and_show():
        log.info("Login cancelled; exiting.")
        container.database.dispose()
        return 0

    exit_code = qt_app.exec()
    container.database.dispose()
    log.info("MediFlow exited with code %s.", exit_code)
    return exit_code
