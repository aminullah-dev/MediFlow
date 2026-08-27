"""Book an appointment: pick a patient, choose doctor/department, date & time."""
from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.exceptions import MediFlowError
from mediflow.data.base import local_today
from mediflow.services.appointment_service import AppointmentBooking, AppointmentService
from mediflow.services.patient_service import PatientDTO, PatientService


class AppointmentDialog(QDialog):
    def __init__(self, patients: PatientService, appointments: AppointmentService,
                 default_date: date | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._patients = patients
        self._appointments = appointments
        self._selected: PatientDTO | None = None
        self.setModal(True)
        self.setMinimumWidth(560)
        self._build_ui(default_date or local_today())

    def _build_ui(self, default_date: date) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(12)

        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._search_patients)
        root.addWidget(self._search)

        self._results = QListWidget()
        self._results.setFixedHeight(120)
        self._results.itemClicked.connect(self._pick_patient)
        root.addWidget(self._results)

        self._selected_label = QLabel(objectName="Badge")
        self._selected_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._selected_label.setVisible(False)
        root.addWidget(self._selected_label)

        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self._date = QDateEdit()
        # LTR must precede setDisplayFormat so section order isn't RTL-mirrored.
        self._date.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("yyyy-MM-dd")
        self._date.setDate(QDate(default_date.year, default_date.month, default_date.day))
        self._time = QTimeEdit()
        self._time.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._time.setDisplayFormat("HH:mm")
        self._time.setTime(QTime(9, 0))

        self._doctor = QComboBox()
        self._doctor.addItem(self.tr("— None —"), None)
        for ref in self._appointments.list_doctors():
            self._doctor.addItem(ref.name, ref.id)

        self._department = QComboBox()
        self._department.addItem(self.tr("— None —"), None)
        for ref in self._appointments.list_departments():
            self._department.addItem(ref.name, ref.id)

        self._reason = QLineEdit()
        self._walk_in = QCheckBox(self.tr("Walk-in"))

        form.addRow(self.tr("Date"), self._date)
        form.addRow(self.tr("Time"), self._time)
        form.addRow(self.tr("Doctor"), self._doctor)
        form.addRow(self.tr("Department"), self._department)
        form.addRow(self.tr("Reason"), self._reason)
        form.addRow("", self._walk_in)
        root.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._cancel = QPushButton(self.tr("Cancel"))
        self._cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel.clicked.connect(self.reject)
        self._book = QPushButton(self.tr("Book"), objectName="Primary")
        self._book.setCursor(Qt.CursorShape.PointingHandCursor)
        self._book.clicked.connect(self._on_book)
        buttons.addWidget(self._cancel)
        buttons.addWidget(self._book)
        root.addLayout(buttons)

        self.setWindowTitle(self.tr("New appointment"))
        self._search.setPlaceholderText(self.tr("Search patient by name, MRN or phone"))
        self._search_patients("")

    def _search_patients(self, _text: str) -> None:
        term = self._search.text()
        results = self._patients.search(term, limit=25)
        self._results.clear()
        for p in results:
            item = QListWidgetItem(f"{p.full_name}  ·  {p.mrn}"
                                   + (f"  ·  {p.phone}" if p.phone else ""))
            item.setData(Qt.ItemDataRole.UserRole, p)
            self._results.addItem(item)

    def _pick_patient(self, item: QListWidgetItem) -> None:
        self._selected = item.data(Qt.ItemDataRole.UserRole)
        self._selected_label.setVisible(True)
        self._selected_label.setText(
            self.tr("Selected: {name}").format(name=self._selected.full_name))

    def _on_book(self) -> None:
        if self._selected is None:
            QMessageBox.warning(self, self.tr("New appointment"),
                                self.tr("Select a patient first."))
            return
        qd = self._date.date()
        qt = self._time.time()
        start = datetime(qd.year(), qd.month(), qd.day(), qt.hour(), qt.minute())  # noqa: DTZ001  (wall-clock domain — see mediflow/data/base.py)
        booking = AppointmentBooking(
            patient_id=self._selected.id,
            scheduled_start=start,
            doctor_id=self._doctor.currentData(),
            department_id=self._department.currentData(),
            reason=self._reason.text(),
            is_walk_in=self._walk_in.isChecked(),
        )
        try:
            self._appointments.book(booking)
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("New appointment"), str(exc))
            return
        self.accept()
