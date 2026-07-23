"""Main application window: sidebar navigation + stacked module content.

Responsibilities
* Gate entry behind login (``authenticate_and_show``).
* Present only the modules the signed-in user is permitted to open (RBAC).
* Lazily construct each module view on first navigation and refresh it via
  ``on_activated`` whenever it is shown.
* Switch language and theme at runtime, re-translating the whole widget tree.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mediflow.app import ServiceContainer
from mediflow.core.constants import Language, Theme
from mediflow.i18n.translator import TranslationManager, retranslate_tree
from mediflow.services.auth_service import AuthenticatedUser
from mediflow.ui import icons
from mediflow.ui import theme as theme_colors
from mediflow.ui.dialogs.change_password_dialog import ChangePasswordDialog
from mediflow.ui.dialogs.login_dialog import LoginDialog
from mediflow.ui.theme import ThemeManager
from mediflow.ui.views.accounting_view import AccountingView
from mediflow.ui.views.appointments_view import AppointmentsView
from mediflow.ui.views.audit_view import AuditView
from mediflow.ui.views.backup_view import BackupView
from mediflow.ui.views.base_view import BaseView
from mediflow.ui.views.billing_view import BillingView
from mediflow.ui.views.dashboard_view import DashboardView
from mediflow.ui.views.hr_view import HRView
from mediflow.ui.views.inventory_view import InventoryView
from mediflow.ui.views.laboratory_view import LaboratoryView
from mediflow.ui.views.medical_records_view import MedicalRecordsView
from mediflow.ui.views.patients_view import PatientsView
from mediflow.ui.views.pharmacy_view import PharmacyView
from mediflow.ui.views.reception_view import ReceptionView
from mediflow.ui.views.reports_view import ReportsView
from mediflow.ui.views.settings_view import SettingsView
from mediflow.ui.views.users_view import UsersView


@dataclass(frozen=True)
class NavEntry:
    key: str
    title_key: str          # untranslated source string, translated at display
    icon: str               # icon name in mediflow.ui.icons
    factory: Callable[[ServiceContainer], BaseView]
    permission: str | None


# Light icon colour for the dark-teal sidebar (constant across both themes).
_NAV_ICON = "#d7e7ea"

# The full module map — every module now has a real view.
NAV_ENTRIES: list[NavEntry] = [
    NavEntry("dashboard", "Dashboard", "dashboard", DashboardView, "dashboard.view"),
    NavEntry("patients", "Patients", "patients", PatientsView, "patient.view"),
    NavEntry("appointments", "Appointments", "appointments", AppointmentsView, "appointment.view"),
    NavEntry("reception", "Reception", "reception", ReceptionView, "reception.checkin"),
    NavEntry("emr", "Medical Records", "emr", MedicalRecordsView, "emr.view"),
    NavEntry("pharmacy", "Pharmacy", "pharmacy", PharmacyView, "pharmacy.view"),
    NavEntry("laboratory", "Laboratory", "laboratory", LaboratoryView, "lab.view"),
    NavEntry("inventory", "Inventory", "inventory", InventoryView, "inventory.view"),
    NavEntry("billing", "Billing", "billing", BillingView, "billing.view"),
    NavEntry("accounting", "Accounting", "accounting", AccountingView, "accounting.view"),
    NavEntry("hr", "Human Resources", "hr", HRView, "hr.view"),
    NavEntry("reports", "Reports", "reports", ReportsView, "report.view"),
    NavEntry("users", "Users & Roles", "users", UsersView, "user.view"),
    NavEntry("audit", "Audit Log", "audit", AuditView, "audit.view"),
    NavEntry("backup", "Backup", "backup", BackupView, "backup.run"),
    NavEntry("settings", "Settings", "settings", SettingsView, "settings.manage"),
]


class MainWindow(QMainWindow):
    def __init__(self, container: ServiceContainer, translator: TranslationManager,
                 theme: ThemeManager):
        super().__init__()
        self._container = container
        self._translator = translator
        self._theme = theme
        self._user: AuthenticatedUser | None = None
        self._views: dict[str, BaseView] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._visible_entries: list[NavEntry] = []
        self.setMinimumSize(1160, 740)

    # -- lifecycle ----------------------------------------------------------
    def authenticate_and_show(self) -> bool:
        dialog = LoginDialog(self._container.auth, config=self._container.config)
        if dialog.exec() != dialog.DialogCode.Accepted or dialog.user is None:
            return False
        self._user = dialog.user
        if self._user.must_change_password:
            change = ChangePasswordDialog(self._container.auth, self._user.id, forced=True)
            if change.exec() != change.DialogCode.Accepted:
                self._container.auth.logout()  # they declined the mandatory change
                return False
        self._build_ui()
        self._translator.language_changed.connect(lambda _l: retranslate_tree(self))
        self.showMaximized()
        return True

    # -- construction -------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._build_header())
        self._stack = QStackedWidget()
        content_layout.addWidget(self._stack, stretch=1)
        outer.addWidget(content, stretch=1)

        assert self._user is not None
        self._visible_entries = [
            e for e in NAV_ENTRIES
            if e.permission is None or self._user.can(e.permission)
        ]
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for entry in self._visible_entries:
            button = QPushButton(objectName="NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(icons.icon(entry.icon, 18, _NAV_ICON))
            button.setIconSize(QSize(18, 18))
            button.clicked.connect(lambda _c=False, k=entry.key: self._navigate(k))
            self._nav_layout.addWidget(button)
            self._nav_group.addButton(button)
            self._nav_buttons[entry.key] = button
        self._nav_layout.addStretch(1)

        self.retranslate_ui()
        if self._visible_entries:
            self._navigate(self._visible_entries[0].key)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame(objectName="Sidebar")
        sidebar.setFixedWidth(248)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 22, 16, 16)
        layout.setSpacing(4)

        self._brand = QLabel(objectName="Brand")
        self._brand_tag = QLabel(objectName="BrandTag")
        layout.addWidget(self._brand)
        layout.addWidget(self._brand_tag)
        layout.addSpacing(14)
        rule = QFrame(objectName="SidebarRule")
        rule.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(rule)
        layout.addSpacing(12)

        self._nav_layout = layout
        return sidebar

    def _build_header(self) -> QWidget:
        header = QFrame(objectName="Header")
        header.setFixedHeight(72)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(12)

        avatar = QFrame(objectName="Avatar")
        avatar_layout = QVBoxLayout(avatar)
        avatar_layout.setContentsMargins(0, 0, 0, 0)
        self._avatar_text = QLabel(objectName="AvatarText")
        self._avatar_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar_text.setText(self._initials())
        avatar_layout.addWidget(self._avatar_text)
        layout.addWidget(avatar)

        user_box = QVBoxLayout()
        user_box.setContentsMargins(0, 0, 0, 0)
        user_box.setSpacing(0)
        self._user_name = QLabel(objectName="HeaderTitle")
        assert self._user is not None
        self._user_name.setText(self._user.full_name)
        self._user_label = QLabel(objectName="HeaderUser")
        user_box.addWidget(self._user_name)
        user_box.addWidget(self._user_label)
        layout.addLayout(user_box)

        layout.addStretch(1)

        self._language_combo = QComboBox()
        self._language_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._language_combo.setMinimumWidth(130)
        self._language_combo.addItem("دری", Language.DARI.value)
        self._language_combo.addItem("پښتو", Language.PASHTO.value)
        self._language_combo.addItem("English", Language.ENGLISH.value)
        current_index = self._language_combo.findData(self._translator.current.value)
        self._language_combo.setCurrentIndex(max(0, current_index))
        self._language_combo.currentIndexChanged.connect(self._on_language_changed)
        layout.addWidget(self._language_combo)

        self._theme_button = QPushButton(objectName="Ghost")
        self._theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_button.clicked.connect(self._on_theme_toggle)
        layout.addWidget(self._theme_button)

        # Voluntary password change — the only in-app place to set a password of
        # one's own choosing (the Users module can only issue random temporaries).
        self._change_pw_button = QPushButton(objectName="Ghost")
        self._change_pw_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._change_pw_button.clicked.connect(self._on_change_password)
        layout.addWidget(self._change_pw_button)

        self._logout_button = QPushButton(objectName="Danger")
        self._logout_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._logout_button.clicked.connect(self._on_logout)
        layout.addWidget(self._logout_button)
        return header

    def _initials(self) -> str:
        assert self._user is not None
        parts = [p for p in self._user.full_name.split() if p]
        if not parts:
            return (self._user.username[:1] or "?").upper()
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][:1] + parts[-1][:1]).upper()

    # -- navigation ---------------------------------------------------------
    def _navigate(self, key: str) -> None:
        view = self._views.get(key)
        if view is None:
            entry = next(e for e in self._visible_entries if e.key == key)
            view = entry.factory(self._container)
            self._views[key] = view
            self._stack.addWidget(view)
        self._stack.setCurrentWidget(view)
        self._nav_buttons[key].setChecked(True)
        view.on_activated()

    # -- actions ------------------------------------------------------------
    def _on_language_changed(self, _index: int) -> None:
        language = Language(self._language_combo.currentData())
        self._translator.install(language)
        self._container.config.settings.language = language.value
        self._container.config.settings.save()

    def _on_theme_toggle(self) -> None:
        self._theme.toggle()
        self._container.config.settings.theme = self._theme.current.value
        self._container.config.settings.save()
        self.retranslate_ui()

    def _on_change_password(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        assert self._user is not None
        dialog = ChangePasswordDialog(self._container.auth, self._user.id, forced=False,
                                      parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            QMessageBox.information(
                self, self.tr("Change password"),
                self.tr("Your password has been changed."),
            )

    def _on_logout(self) -> None:
        self._container.auth.logout()
        self.close()

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.tr("MediFlow — Clinic & Hospital Management"))
        if hasattr(self, "_brand"):
            self._brand.setText(self.tr("MediFlow"))
            self._brand_tag.setText(self.tr("Clinic Management System"))
        if self._user is not None and hasattr(self, "_user_label"):
            self._user_label.setText(self.tr("Signed in as {name}").format(name=self._user.username))
        for entry in self._visible_entries:
            # Double any '&' so Qt renders it literally instead of as a mnemonic.
            label = self.tr(entry.title_key).replace("&", "&&")
            self._nav_buttons[entry.key].setText(f"  {label}")
        if hasattr(self, "_theme_button"):
            muted = theme_colors.CURRENT["text_muted"]
            if self._theme.current is Theme.DARK:
                self._theme_button.setIcon(icons.icon("sun", 16, muted))
                self._theme_button.setText(self.tr("Light mode"))
            else:
                self._theme_button.setIcon(icons.icon("moon", 16, muted))
                self._theme_button.setText(self.tr("Dark mode"))
            self._theme_button.setIconSize(QSize(16, 16))
        if hasattr(self, "_change_pw_button"):
            self._change_pw_button.setIcon(icons.icon("key", 16, theme_colors.CURRENT["text_muted"]))
            self._change_pw_button.setIconSize(QSize(16, 16))
            self._change_pw_button.setText(self.tr("Change password"))
        if hasattr(self, "_logout_button"):
            self._logout_button.setText(self.tr("Sign out"))
