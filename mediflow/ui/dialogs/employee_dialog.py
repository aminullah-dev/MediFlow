"""Add / edit an employee."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.constants import Gender
from mediflow.core.exceptions import ValidationError
from mediflow.services.hr_service import EmployeeDTO, EmployeeInput, HRService


class EmployeeDialog(QDialog):
    def __init__(self, service: HRService, employee: EmployeeDTO | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._employee = employee
        self.setModal(True)
        self.setMinimumWidth(500)
        self._build_ui()
        if employee is not None:
            self._load(employee)

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
        self._position = QLineEdit()
        self._department = QLineEdit()
        self._gender = QComboBox()
        self._gender.addItem(self.tr("Male"), Gender.MALE.value)
        self._gender.addItem(self.tr("Female"), Gender.FEMALE.value)
        self._gender.addItem(self.tr("Other"), Gender.OTHER.value)
        self._phone = QLineEdit()

        self._date_known = QCheckBox(self.tr("Date known"))
        self._hire_date = QDateEdit()
        self._hire_date.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._hire_date.setCalendarPopup(True)
        self._hire_date.setDisplayFormat("yyyy-MM-dd")
        self._hire_date.setMaximumDate(QDate.currentDate())
        self._hire_date.setDate(QDate.currentDate())
        self._hire_date.setEnabled(False)
        self._date_known.toggled.connect(self._hire_date.setEnabled)
        date_row = QHBoxLayout()
        date_row.setContentsMargins(0, 0, 0, 0)
        date_row.addWidget(self._date_known)
        date_row.addWidget(self._hire_date, stretch=1)
        date_widget = QWidget()
        date_widget.setLayout(date_row)

        self._salary = QDoubleSpinBox()
        self._salary.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._salary.setRange(0, 100_000_000)
        self._salary.setDecimals(2)
        self._notes = QPlainTextEdit()
        self._notes.setFixedHeight(60)

        form.addRow(self.tr("First name"), self._first_name)
        form.addRow(self.tr("Last name"), self._last_name)
        form.addRow(self.tr("Father's name"), self._father_name)
        form.addRow(self.tr("Position"), self._position)
        form.addRow(self.tr("Department"), self._department)
        form.addRow(self.tr("Gender"), self._gender)
        form.addRow(self.tr("Phone"), self._phone)
        form.addRow(self.tr("Hire date"), date_widget)
        form.addRow(self.tr("Base salary"), self._salary)
        form.addRow(self.tr("Notes"), self._notes)
        root.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(self.tr("Cancel"))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        save = QPushButton(self.tr("Save"), objectName="Primary")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self._on_save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

        self.setWindowTitle(
            self.tr("Edit employee") if self._employee else self.tr("New employee"))
        self._first_name.setFocus()

    def _load(self, e: EmployeeDTO) -> None:
        self._first_name.setText(e.first_name)
        self._last_name.setText(e.last_name)
        self._father_name.setText(e.father_name or "")
        self._position.setText(e.position or "")
        self._department.setText(e.department or "")
        gi = self._gender.findData(e.gender)
        if gi >= 0:
            self._gender.setCurrentIndex(gi)
        self._phone.setText(e.phone or "")
        if e.hire_date is not None:
            self._date_known.setChecked(True)
            self._hire_date.setDate(QDate(e.hire_date.year, e.hire_date.month, e.hire_date.day))
        self._salary.setValue(e.base_salary)
        self._notes.setPlainText(e.notes or "")

    def _collect(self) -> EmployeeInput:
        known = self._date_known.isChecked()
        return EmployeeInput(
            first_name=self._first_name.text(), last_name=self._last_name.text(),
            father_name=self._father_name.text(), position=self._position.text(),
            department=self._department.text(), gender=self._gender.currentData(),
            phone=self._phone.text(),
            hire_date=self._hire_date.date().toPython() if known else None,
            base_salary=self._salary.value(), notes=self._notes.toPlainText(),
        )

    def _on_save(self) -> None:
        try:
            if self._employee is None:
                self._service.create(self._collect())
            else:
                self._service.update(self._employee.id, self._collect())
        except ValidationError as exc:
            QMessageBox.warning(self, self.tr("Invalid data"), str(exc))
            return
        self.accept()
