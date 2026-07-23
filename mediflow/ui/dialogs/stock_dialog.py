"""Add a dated stock batch to a medication, and dispense from stock."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
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

from mediflow.core.exceptions import MediFlowError
from mediflow.services.pharmacy_service import MedicationDTO, PharmacyService


class StockDialog(QDialog):
    """Receive stock into a medication as a dated batch."""

    def __init__(self, service: PharmacyService, medication: MedicationDTO,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._medication = medication
        self.setModal(True)
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(14)

        heading = QLabel(f"{self._medication.name}", objectName="PageTitle")
        root.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._quantity = QSpinBox()
        self._quantity.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._quantity.setRange(1, 1_000_000)
        self._quantity.setValue(1)
        self._batch = QLineEdit()
        self._has_expiry = QCheckBox(self.tr("Has expiry date"))
        self._has_expiry.setChecked(True)
        self._expiry = QDateEdit()
        self._expiry.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._expiry.setCalendarPopup(True)
        self._expiry.setDisplayFormat("yyyy-MM-dd")
        self._expiry.setDate(QDate.currentDate().addYears(1))
        self._has_expiry.toggled.connect(self._expiry.setEnabled)
        expiry_row = QHBoxLayout()
        expiry_row.setContentsMargins(0, 0, 0, 0)
        expiry_row.addWidget(self._has_expiry)
        expiry_row.addWidget(self._expiry, stretch=1)
        expiry_widget = QWidget()
        expiry_widget.setLayout(expiry_row)
        self._cost = QDoubleSpinBox()
        self._cost.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._cost.setRange(0, 1_000_000)
        self._cost.setDecimals(2)

        form.addRow(self.tr("Quantity"), self._quantity)
        form.addRow(self.tr("Batch number"), self._batch)
        form.addRow(self.tr("Expiry date"), expiry_widget)
        form.addRow(self.tr("Cost price"), self._cost)
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

        self.setWindowTitle(self.tr("Add stock"))

    def _on_save(self) -> None:
        expiry: date | None = self._expiry.date().toPython() if self._has_expiry.isChecked() else None
        try:
            self._service.add_stock(
                self._medication.id, self._quantity.value(),
                batch_number=self._batch.text(), expiry_date=expiry,
                cost_price=self._cost.value(),
            )
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Invalid data"), str(exc))
            return
        self.accept()


class DispenseDialog(QDialog):
    def __init__(self, service: PharmacyService, medication: MedicationDTO,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._medication = medication
        self.setModal(True)
        self.setMinimumWidth(380)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(12)

        root.addWidget(QLabel(self._medication.name, objectName="PageTitle"))
        self._available = QLabel(objectName="Badge")
        self._available.setText(
            self.tr("Available: {count}").format(count=self._medication.stock_on_hand))
        root.addWidget(self._available)

        form = QFormLayout()
        form.setSpacing(12)
        self._quantity = QSpinBox()
        self._quantity.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._quantity.setRange(1, max(1, self._medication.stock_on_hand))
        self._quantity.setValue(1)
        form.addRow(self.tr("Quantity"), self._quantity)
        root.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(self.tr("Cancel"))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        dispense = QPushButton(self.tr("Dispense"), objectName="Primary")
        dispense.setCursor(Qt.CursorShape.PointingHandCursor)
        dispense.clicked.connect(self._on_dispense)
        buttons.addWidget(cancel)
        buttons.addWidget(dispense)
        root.addLayout(buttons)

        self.setWindowTitle(self.tr("Dispense"))
        self._quantity.setEnabled(self._medication.stock_on_hand > 0)

    def _on_dispense(self) -> None:
        try:
            self._service.dispense(self._medication.id, self._quantity.value())
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Cannot dispense"), str(exc))
            return
        self.accept()
