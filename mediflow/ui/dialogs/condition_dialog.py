"""Add a condition / problem-list entry to a patient's record."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
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


class ConditionDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(440)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self._name = QLineEdit()
        self._icd10 = QLineEdit()
        self._chronic = QCheckBox(self.tr("Chronic condition"))
        self._chronic.setChecked(True)

        self._date_known = QCheckBox(self.tr("Date known"))
        self._diagnosed = QDateEdit()
        self._diagnosed.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._diagnosed.setCalendarPopup(True)
        self._diagnosed.setDisplayFormat("yyyy-MM-dd")
        self._diagnosed.setMaximumDate(QDate.currentDate())
        self._diagnosed.setDate(QDate.currentDate())
        self._diagnosed.setEnabled(False)
        self._date_known.toggled.connect(self._diagnosed.setEnabled)
        date_row = QHBoxLayout()
        date_row.setContentsMargins(0, 0, 0, 0)
        date_row.addWidget(self._date_known)
        date_row.addWidget(self._diagnosed, stretch=1)
        date_widget = QWidget()
        date_widget.setLayout(date_row)

        self._notes = QPlainTextEdit()
        self._notes.setFixedHeight(64)

        form.addRow(self.tr("Name"), self._name)
        form.addRow(self.tr("ICD-10 code"), self._icd10)
        form.addRow("", self._chronic)
        form.addRow(self.tr("Diagnosed on"), date_widget)
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

        self.setWindowTitle(self.tr("Add condition"))
        self._name.setFocus()

    def _on_save(self) -> None:
        if not self._name.text().strip():
            QMessageBox.warning(self, self.tr("Invalid data"), self.tr("Name"))
            return
        self.accept()

    def collected(self) -> dict:
        diagnosed: date | None = (
            self._diagnosed.date().toPython() if self._date_known.isChecked() else None
        )
        return {
            "name": self._name.text(),
            "icd10_code": self._icd10.text(),
            "is_chronic": self._chronic.isChecked(),
            "diagnosed_on": diagnosed,
            "notes": self._notes.toPlainText(),
        }
