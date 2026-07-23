"""Record a payment against an invoice."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.constants import PaymentMethod
from mediflow.core.exceptions import MediFlowError
from mediflow.services.billing_service import BillingService, InvoiceDTO


class PaymentDialog(QDialog):
    def __init__(self, billing: BillingService, invoice: InvoiceDTO,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._billing = billing
        self._invoice = invoice
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

        root.addWidget(QLabel(f"‎{self._invoice.invoice_number}‎", objectName="PageTitle"))
        balance = QLabel(objectName="Badge")
        balance.setText(self.tr("Balance: {amount}").format(amount=f"{self._invoice.balance:.2f}"))
        root.addWidget(balance)

        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._amount = QDoubleSpinBox()
        self._amount.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._amount.setRange(0, 1_000_000)
        self._amount.setDecimals(2)
        self._amount.setValue(self._invoice.balance)
        self._method = QComboBox()
        self._method.addItem(self.tr("Cash"), PaymentMethod.CASH.value)
        self._method.addItem(self.tr("Card"), PaymentMethod.CARD.value)
        self._method.addItem(self.tr("Bank transfer"), PaymentMethod.BANK_TRANSFER.value)
        self._method.addItem(self.tr("Mobile money"), PaymentMethod.MOBILE_MONEY.value)
        self._reference = QLineEdit()
        form.addRow(self.tr("Amount"), self._amount)
        form.addRow(self.tr("Method"), self._method)
        form.addRow(self.tr("Reference"), self._reference)
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

        self.setWindowTitle(self.tr("Record payment"))

    def _on_save(self) -> None:
        try:
            self._billing.add_payment(self._invoice.id, self._amount.value(),
                                      PaymentMethod(self._method.currentData()),
                                      reference=self._reference.text())
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Invalid data"), str(exc))
            return
        self.accept()
