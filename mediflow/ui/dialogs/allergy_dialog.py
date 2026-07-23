"""Add an allergy to a patient's record."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class AllergyDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(420)
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
        self._substance = QLineEdit()
        self._severity = QComboBox()
        self._severity.addItem(self.tr("— Not set —"), None)
        self._severity.addItem(self.tr("Mild"), "mild")
        self._severity.addItem(self.tr("Moderate"), "moderate")
        self._severity.addItem(self.tr("Severe"), "severe")
        self._reaction = QLineEdit()
        form.addRow(self.tr("Substance"), self._substance)
        form.addRow(self.tr("Severity"), self._severity)
        form.addRow(self.tr("Reaction"), self._reaction)
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

        self.setWindowTitle(self.tr("Add allergy"))
        self._substance.setFocus()

    def _on_save(self) -> None:
        if not self._substance.text().strip():
            QMessageBox.warning(self, self.tr("Invalid data"), self.tr("Substance"))
            return
        self.accept()

    def collected(self) -> tuple[str, str | None, str | None]:
        return (self._substance.text(), self._severity.currentData(), self._reaction.text())
