"""Record a stock movement (in or out) for an inventory item."""
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
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.constants import StockMovementType
from mediflow.core.exceptions import MediFlowError
from mediflow.services.inventory_service import InventoryItemDTO, InventoryService

# Movement-type choices offered per direction: (source label, enum).
_IN_TYPES = [
    ("Purchase", StockMovementType.PURCHASE),
    ("Return", StockMovementType.RETURN),
    ("Adjustment", StockMovementType.ADJUSTMENT),
]
_OUT_TYPES = [
    ("Usage", StockMovementType.SALE),
    ("Expiry write-off", StockMovementType.EXPIRY_WRITEOFF),
    ("Transfer", StockMovementType.TRANSFER),
    ("Adjustment", StockMovementType.ADJUSTMENT),
]


class MovementDialog(QDialog):
    def __init__(self, service: InventoryService, item: InventoryItemDTO,
                 *, incoming: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._item = item
        self._incoming = incoming
        self.setModal(True)
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(12)

        root.addWidget(QLabel(self._item.name, objectName="PageTitle"))
        available = QLabel(objectName="Badge")
        available.setText(self.tr("Available: {count}").format(count=self._item.quantity))
        root.addWidget(available)

        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._type = QComboBox()
        for label, enum in (_IN_TYPES if self._incoming else _OUT_TYPES):
            self._type.addItem(self.tr(label), enum.value)
        self._quantity = QSpinBox()
        self._quantity.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        upper = 1_000_000 if self._incoming else max(1, self._item.quantity)
        self._quantity.setRange(1, upper)
        self._quantity.setValue(1)
        self._reason = QLineEdit()
        form.addRow(self.tr("Type"), self._type)
        form.addRow(self.tr("Quantity"), self._quantity)
        form.addRow(self.tr("Reason"), self._reason)
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

        self.setWindowTitle(self.tr("Stock in") if self._incoming else self.tr("Stock out"))
        self._quantity.setEnabled(self._incoming or self._item.quantity > 0)

    def _on_save(self) -> None:
        delta = self._quantity.value() if self._incoming else -self._quantity.value()
        movement = StockMovementType(self._type.currentData())
        try:
            self._service.record_movement(self._item.id, movement, delta,
                                          reason=self._reason.text())
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Invalid data"), str(exc))
            return
        self.accept()
