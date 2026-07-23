"""Settings module: clinic profile and application preferences."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.exceptions import ValidationError
from mediflow.services.settings_service import ClinicInfoDTO
from mediflow.ui import icons
from mediflow.ui.views.base_view import BaseView


class SettingsView(BaseView):
    required_permission = "settings.manage"

    def build_ui(self) -> None:
        self._service = self.container.settings
        self._settings = self.container.config.settings

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._root.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(16)

        # -- clinic profile ------------------------------------------------
        clinic_card, cform = self._section("hospital")
        self._clinic_heading, self._clinic_hint = clinic_card.heading, clinic_card.hint
        self._name = QLineEdit()
        self._name_pashto = QLineEdit()
        self._license = QLineEdit()
        self._phone = QLineEdit()
        self._email = QLineEdit()
        self._address = QLineEdit()
        self._city = QLineEdit()
        self._province = QLineEdit()
        self._currency = QLineEdit()
        self._currency.setMaximumWidth(130)
        self._currency.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._footer = QPlainTextEdit()
        self._footer.setFixedHeight(60)
        self._l_name = self._row(cform, self._name)
        self._l_name_pashto = self._row(cform, self._name_pashto)
        self._l_license = self._row(cform, self._license)
        self._l_phone = self._row(cform, self._phone)
        self._l_email = self._row(cform, self._email)
        self._l_address = self._row(cform, self._address)
        self._l_city = self._row(cform, self._city)
        self._l_province = self._row(cform, self._province)
        self._l_currency = self._row(cform, self._currency)
        self._l_footer = self._row(cform, self._footer)
        body.addWidget(clinic_card)

        # -- preferences ---------------------------------------------------
        pref_card, pform = self._section("sliders")
        self._pref_heading, self._pref_hint = pref_card.heading, pref_card.hint
        self._auto_backup = QCheckBox()
        self._interval = self._spin(1, 720)
        self._lock = self._spin(0, 240)
        self._fiscal = self._spin(1, 12)
        self._l_auto = self._row(pform, self._auto_backup)
        self._l_interval = self._row(pform, self._interval)
        self._l_lock = self._row(pform, self._lock)
        self._l_fiscal = self._row(pform, self._fiscal)
        body.addWidget(pref_card)
        body.addStretch(1)

        scroll.setWidget(content)
        self._root.addWidget(scroll, stretch=1)

        # -- sticky footer -------------------------------------------------
        footer = QFrame(objectName="FormFooter")
        frow = QHBoxLayout(footer)
        frow.setContentsMargins(18, 12, 18, 12)
        self._saved_note = QLabel(objectName="SavedNote")
        self._saved_note.setVisible(False)
        frow.addWidget(self._saved_note)
        frow.addStretch(1)
        self._reset = QPushButton(objectName="Ghost")
        self._reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset.clicked.connect(self.on_activated)
        self._save = QPushButton(objectName="Primary")
        self._save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save.setMinimumWidth(130)
        self._save.clicked.connect(self._on_save)
        frow.addWidget(self._reset)
        frow.addWidget(self._save)
        self._root.addWidget(footer)
        icons.apply_button_icon(self._reset, "refresh")
        icons.apply_button_icon(self._save, "check")

        self._saved_timer = QTimer(self)
        self._saved_timer.setSingleShot(True)
        self._saved_timer.timeout.connect(lambda: self._saved_note.setVisible(False))

    def _section(self, icon_name: str) -> tuple[QFrame, QFormLayout]:
        card = QFrame(objectName="Card")
        v = QVBoxLayout(card)
        v.setContentsMargins(24, 18, 24, 20)
        v.setSpacing(14)
        head = QHBoxLayout()
        head.setSpacing(12)
        icon = QFrame(objectName="SectionIcon")
        il = QVBoxLayout(icon)
        il.setContentsMargins(0, 0, 0, 0)
        glyph = QLabel(objectName="SectionEmoji")
        glyph.setPixmap(icons.pixmap(icon_name, 20, "#ffffff"))
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        il.addWidget(glyph)
        head.addWidget(icon)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        card.heading = QLabel(objectName="SectionTitle")
        card.hint = QLabel(objectName="SectionHint")
        titles.addWidget(card.heading)
        titles.addWidget(card.hint)
        head.addLayout(titles)
        head.addStretch(1)
        v.addLayout(head)
        divider = QFrame(objectName="Divider")
        v.addWidget(divider)
        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        v.addLayout(form)
        return card, form

    def _spin(self, low: int, high: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        spin.setRange(low, high)
        return spin

    def _row(self, form: QFormLayout, field: QWidget) -> QLabel:
        label = QLabel(objectName="Muted")
        form.addRow(label, field)
        return label

    # -- data ---------------------------------------------------------------
    def on_activated(self) -> None:
        clinic = self._service.get_clinic()
        self._name.setText(clinic.name)
        self._name_pashto.setText(clinic.name_pashto or "")
        self._license.setText(clinic.license_number or "")
        self._phone.setText(clinic.phone or "")
        self._email.setText(clinic.email or "")
        self._address.setText(clinic.address or "")
        self._city.setText(clinic.city or "")
        self._province.setText(clinic.province or "")
        self._currency.setText(clinic.default_currency)
        self._footer.setPlainText(clinic.receipt_footer or "")
        self._auto_backup.setChecked(self._settings.auto_backup_enabled)
        self._interval.setValue(self._settings.auto_backup_interval_hours)
        self._lock.setValue(self._settings.session_lock_minutes)
        self._fiscal.setValue(self._settings.fiscal_year_start_month)
        self._saved_note.setVisible(False)

    def _on_save(self) -> None:
        clinic = ClinicInfoDTO(
            name=self._name.text(), name_pashto=self._name_pashto.text(),
            license_number=self._license.text(), phone=self._phone.text(),
            email=self._email.text(), address=self._address.text(),
            city=self._city.text(), province=self._province.text(),
            default_currency=self._currency.text() or "AFN",
            receipt_footer=self._footer.toPlainText(),
        )
        try:
            self._service.save_clinic(clinic)
        except ValidationError as exc:
            QMessageBox.warning(self, self.tr("Invalid data"), str(exc))
            return
        self._settings.auto_backup_enabled = self._auto_backup.isChecked()
        self._settings.auto_backup_interval_hours = self._interval.value()
        self._settings.session_lock_minutes = self._lock.value()
        self._settings.fiscal_year_start_month = self._fiscal.value()
        self._settings.clinic_name = clinic.name
        self._settings.save()
        self._saved_note.setText("\U00002714  " + self.tr("Settings saved"))
        self._saved_note.setVisible(True)
        self._saved_timer.start(4000)

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Settings"))
        self._subtitle.setText(self.tr("Clinic profile and preferences"))
        self._clinic_heading.setText(self.tr("Clinic profile"))
        self._clinic_hint.setText(self.tr("Shown on printed documents and receipts"))
        self._pref_heading.setText(self.tr("Preferences"))
        self._pref_hint.setText(self.tr("Application behaviour and automatic backups"))
        self._save.setText(self.tr("Save"))
        self._reset.setText(self.tr("Reset"))
        self._l_name.setText(self.tr("Clinic name"))
        self._l_name_pashto.setText(self.tr("Name (Pashto)"))
        self._l_license.setText(self.tr("License number"))
        self._l_phone.setText(self.tr("Phone"))
        self._l_email.setText(self.tr("Email"))
        self._l_address.setText(self.tr("Address"))
        self._l_city.setText(self.tr("City"))
        self._l_province.setText(self.tr("Province"))
        self._l_currency.setText(self.tr("Currency"))
        self._l_footer.setText(self.tr("Receipt footer"))
        self._l_auto.setText(self.tr("Auto backup"))
        self._l_interval.setText(self.tr("Backup interval (hours)"))
        self._l_lock.setText(self.tr("Session lock (minutes)"))
        self._l_fiscal.setText(self.tr("Fiscal year start month"))
