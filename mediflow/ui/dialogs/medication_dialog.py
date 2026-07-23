"""Add / edit a medication catalogue entry."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
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

from mediflow.core.exceptions import ValidationError
from mediflow.services.pharmacy_service import MedicationDTO, MedicationInput, PharmacyService


class MedicationDialog(QDialog):
    def __init__(self, service: PharmacyService, medication: MedicationDTO | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._medication = medication
        self.setModal(True)
        self.setMinimumWidth(480)
        self._build_ui()
        if medication is not None:
            self._load(medication)

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

        self._name = QLineEdit()
        self._generic = QLineEdit()
        self._form = QLineEdit()
        self._strength = QLineEdit()
        self._barcode = QLineEdit()
        self._unit = QLineEdit()
        self._unit.setText("unit")
        self._reorder = QSpinBox()
        self._reorder.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._reorder.setRange(0, 1_000_000)
        self._price = QDoubleSpinBox()
        self._price.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._price.setRange(0, 1_000_000)
        self._price.setDecimals(2)
        self._notes = QPlainTextEdit()
        self._notes.setFixedHeight(60)

        form.addRow(self.tr("Name"), self._name)
        form.addRow(self.tr("Generic name"), self._generic)
        form.addRow(self.tr("Form"), self._form)
        form.addRow(self.tr("Strength"), self._strength)
        form.addRow(self.tr("Barcode"), self._barcode)
        form.addRow(self.tr("Unit"), self._unit)
        form.addRow(self.tr("Reorder level"), self._reorder)
        form.addRow(self.tr("Sale price"), self._price)
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

        self.setWindowTitle(self.tr("Edit medication") if self._medication else self.tr("New medication"))
        self._name.setFocus()

    def _load(self, m: MedicationDTO) -> None:
        self._name.setText(m.name)
        self._generic.setText(m.generic_name or "")
        self._form.setText(m.form or "")
        self._strength.setText(m.strength or "")
        self._barcode.setText(m.barcode or "")
        self._unit.setText(m.unit or "unit")
        self._reorder.setValue(m.reorder_level)
        self._price.setValue(m.sale_price)
        self._notes.setPlainText(m.notes or "")

    def _collect(self) -> MedicationInput:
        return MedicationInput(
            name=self._name.text(),
            generic_name=self._generic.text(),
            form=self._form.text(),
            strength=self._strength.text(),
            barcode=self._barcode.text(),
            unit=self._unit.text(),
            reorder_level=self._reorder.value(),
            sale_price=self._price.value(),
            notes=self._notes.toPlainText(),
        )

    def _on_save(self) -> None:
        try:
            if self._medication is None:
                self._service.create(self._collect())
            else:
                self._service.update(self._medication.id, self._collect())
        except ValidationError as exc:
            QMessageBox.warning(self, self.tr("Invalid data"), str(exc))
            return
        self.accept()
