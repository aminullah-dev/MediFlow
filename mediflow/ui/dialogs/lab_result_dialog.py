"""Record the result for a laboratory request."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.exceptions import MediFlowError
from mediflow.services.lab_service import LabRequestDTO, LabService


class LabResultDialog(QDialog):
    def __init__(self, lab: LabService, request: LabRequestDTO,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._lab = lab
        self._request = request
        self.setModal(True)
        self.setMinimumWidth(440)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(12)

        root.addWidget(QLabel(f"{self._request.test_name} — {self._request.patient_name}",
                              objectName="PageTitle"))
        if self._request.reference_range:
            ref = QLabel(objectName="Muted")
            ref.setText(self.tr("Reference range: {range}").format(
                range=f"‎{self._request.reference_range}‎"
                + (f" {self._request.unit}" if self._request.unit else "")))
            root.addWidget(ref)

        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._value = QLineEdit()
        self._flag = QComboBox()
        self._flag.addItem(self.tr("— None —"), None)
        self._flag.addItem(self.tr("Normal"), "normal")
        self._flag.addItem(self.tr("High"), "high")
        self._flag.addItem(self.tr("Low"), "low")
        self._flag.addItem(self.tr("Abnormal"), "abnormal")
        self._notes = QPlainTextEdit()
        self._notes.setFixedHeight(64)
        form.addRow(self.tr("Result"), self._value)
        form.addRow(self.tr("Flag"), self._flag)
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

        self.setWindowTitle(self.tr("Enter result"))
        self._value.setFocus()

    def _on_save(self) -> None:
        try:
            self._lab.set_result(self._request.id, self._value.text(),
                                 flag=self._flag.currentData(),
                                 notes=self._notes.toPlainText())
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Invalid data"), str(exc))
            return
        self.accept()
