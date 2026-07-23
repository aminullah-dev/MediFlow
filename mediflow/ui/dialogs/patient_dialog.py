"""Add / edit a patient record."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.constants import BloodGroup, Gender
from mediflow.core.exceptions import ValidationError
from mediflow.services.patient_service import PatientDTO, PatientRegistration, PatientService


class PatientDialog(QDialog):
    def __init__(self, service: PatientService, patient: PatientDTO | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._patient = patient
        self.setModal(True)
        self.setMinimumWidth(520)
        self._build_ui()
        if patient is not None:
            self._load(patient)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self._first_name = QLineEdit()
        self._last_name = QLineEdit()
        self._father_name = QLineEdit()

        self._gender = QComboBox()
        self._gender.addItem(self.tr("Male"), Gender.MALE.value)
        self._gender.addItem(self.tr("Female"), Gender.FEMALE.value)
        self._gender.addItem(self.tr("Other"), Gender.OTHER.value)

        self._dob_known = QCheckBox(self.tr("Date of birth known"))
        self._dob = QDateEdit()
        # LTR must be set BEFORE the display format: QDateTimeEdit fixes its
        # section order at setDisplayFormat time from the current direction.
        # Without this, an RTL app mirrors "2000-01-01" into "01-01-2000".
        self._dob.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._dob.setCalendarPopup(True)
        self._dob.setDisplayFormat("yyyy-MM-dd")
        self._dob.setMaximumDate(QDate.currentDate())
        self._dob.setDate(QDate(2000, 1, 1))
        self._age = QSpinBox()
        self._age.setRange(0, 130)
        self._age.setValue(25)
        self._age.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._dob_known.toggled.connect(self._sync_age_dob)

        dob_row = QHBoxLayout()
        dob_row.setContentsMargins(0, 0, 0, 0)
        dob_row.addWidget(self._dob_known)
        dob_row.addWidget(self._dob, stretch=1)
        dob_widget = QWidget()
        dob_widget.setLayout(dob_row)

        self._blood = QComboBox()
        for bg in BloodGroup:
            # Wrap codes like "A+"/"B-" in Left-to-Right marks so RTL bidi does
            # not reorder them to "+A"/"-B". The stored data value is untouched.
            label = self.tr("Unknown") if bg is BloodGroup.UNKNOWN else f"‎{bg.value}‎"
            self._blood.addItem(label, bg.value)

        self._phone = QLineEdit()
        self._national_id = QLineEdit()
        self._province = QLineEdit()
        self._district = QLineEdit()
        self._address = QLineEdit()
        self._notes = QPlainTextEdit()
        self._notes.setFixedHeight(70)

        form.addRow(self.tr("First name"), self._first_name)
        form.addRow(self.tr("Last name"), self._last_name)
        form.addRow(self.tr("Father's name"), self._father_name)
        form.addRow(self.tr("Gender"), self._gender)
        form.addRow(self.tr("Date of birth"), dob_widget)
        form.addRow(self.tr("Approximate age (years)"), self._age)
        form.addRow(self.tr("Blood group"), self._blood)
        form.addRow(self.tr("Phone"), self._phone)
        form.addRow(self.tr("National ID (Tazkira)"), self._national_id)
        form.addRow(self.tr("Province"), self._province)
        form.addRow(self.tr("District"), self._district)
        form.addRow(self.tr("Address"), self._address)
        form.addRow(self.tr("Notes"), self._notes)
        root.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._cancel = QPushButton(self.tr("Cancel"))
        self._cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel.clicked.connect(self.reject)
        self._save = QPushButton(self.tr("Save"), objectName="Primary")
        self._save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save.clicked.connect(self._on_save)
        buttons.addWidget(self._cancel)
        buttons.addWidget(self._save)
        root.addLayout(buttons)

        title = self.tr("Edit patient") if self._patient else self.tr("New patient")
        self.setWindowTitle(title)
        self._dob_known.setChecked(False)
        self._sync_age_dob(False)

    def _sync_age_dob(self, known: bool) -> None:
        self._dob.setEnabled(known)
        self._age.setEnabled(not known)

    def _load(self, p: PatientDTO) -> None:
        self._first_name.setText(p.first_name)
        self._last_name.setText(p.last_name)
        self._father_name.setText(p.father_name or "")
        gi = self._gender.findData(p.gender)
        if gi >= 0:
            self._gender.setCurrentIndex(gi)
        bi = self._blood.findData(p.blood_group)
        if bi >= 0:
            self._blood.setCurrentIndex(bi)
        if p.date_of_birth is not None:
            self._dob_known.setChecked(True)
            self._dob.setDate(QDate(p.date_of_birth.year, p.date_of_birth.month,
                                    p.date_of_birth.day))
        else:
            self._dob_known.setChecked(False)
            self._age.setValue(p.approximate_age_years or 0)
        self._phone.setText(p.phone or "")
        self._national_id.setText(p.national_id or "")
        self._province.setText(p.province or "")
        self._district.setText(p.district or "")
        self._address.setText(p.address or "")
        self._notes.setPlainText(p.notes or "")

    def _collect(self) -> PatientRegistration:
        known = self._dob_known.isChecked()
        return PatientRegistration(
            first_name=self._first_name.text(),
            last_name=self._last_name.text(),
            father_name=self._father_name.text(),
            gender=self._gender.currentData(),
            date_of_birth=self._dob.date().toPython() if known else None,
            approximate_age_years=None if known else self._age.value(),
            blood_group=self._blood.currentData(),
            phone=self._phone.text(),
            national_id=self._national_id.text(),
            province=self._province.text(),
            district=self._district.text(),
            address=self._address.text(),
            notes=self._notes.toPlainText(),
        )

    def _on_save(self) -> None:
        data = self._collect()
        try:
            if self._patient is None:
                self._service.register(data)
            else:
                self._service.update(self._patient.id, data)
        except ValidationError as exc:
            QMessageBox.warning(self, self.tr("Invalid data"), str(exc))
            return
        self.accept()
