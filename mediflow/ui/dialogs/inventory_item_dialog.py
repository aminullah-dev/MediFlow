"""Add / edit an inventory item."""
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
from mediflow.services.inventory_service import InventoryItemDTO, InventoryService, ItemInput


class InventoryItemDialog(QDialog):
    def __init__(self, service: InventoryService, item: InventoryItemDTO | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._item = item
        self.setModal(True)
        self.setMinimumWidth(460)
        self._build_ui()
        if item is not None:
            self._load(item)

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
        self._category = QLineEdit()
        self._code = QLineEdit()
        self._unit = QLineEdit()
        self._unit.setText("unit")
        self._reorder = QSpinBox()
        self._reorder.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._reorder.setRange(0, 1_000_000)
        self._cost = QDoubleSpinBox()
        self._cost.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._cost.setRange(0, 1_000_000)
        self._cost.setDecimals(2)
        self._notes = QPlainTextEdit()
        self._notes.setFixedHeight(60)

        form.addRow(self.tr("Name"), self._name)
        form.addRow(self.tr("Category"), self._category)
        form.addRow(self.tr("Code"), self._code)
        form.addRow(self.tr("Unit"), self._unit)
        form.addRow(self.tr("Reorder level"), self._reorder)
        form.addRow(self.tr("Unit cost"), self._cost)
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

        self.setWindowTitle(self.tr("Edit item") if self._item else self.tr("New item"))
        self._name.setFocus()

    def _load(self, i: InventoryItemDTO) -> None:
        self._name.setText(i.name)
        self._category.setText(i.category or "")
        self._code.setText(i.code or "")
        self._unit.setText(i.unit or "unit")
        self._reorder.setValue(i.reorder_level)
        self._cost.setValue(i.unit_cost)
        self._notes.setPlainText(i.notes or "")

    def _collect(self) -> ItemInput:
        return ItemInput(
            name=self._name.text(), category=self._category.text(), code=self._code.text(),
            unit=self._unit.text(), reorder_level=self._reorder.value(),
            unit_cost=self._cost.value(), notes=self._notes.toPlainText(),
        )

    def _on_save(self) -> None:
        try:
            if self._item is None:
                self._service.create(self._collect())
            else:
                self._service.update(self._item.id, self._collect())
        except ValidationError as exc:
            QMessageBox.warning(self, self.tr("Invalid data"), str(exc))
            return
        self.accept()
