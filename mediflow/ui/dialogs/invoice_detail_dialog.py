"""Read-only view of an invoice: line items, totals and payments."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mediflow.services.billing_service import BillingService, InvoiceDetailDTO


def _ltr(text: str) -> str:
    return f"‎{text}‎" if text else text


class InvoiceDetailDialog(QDialog):
    def __init__(self, billing: BillingService, invoice_id: int,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._detail: InvoiceDetailDTO = billing.get_detail(invoice_id)
        self.setModal(True)
        self.setMinimumWidth(560)
        self._build_ui()

    def _build_ui(self) -> None:
        d = self._detail
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(12)

        root.addWidget(QLabel(f"{self.tr('Invoice')} ‎{d.invoice.invoice_number}‎",
                              objectName="PageTitle"))
        root.addWidget(QLabel(f"{d.invoice.patient_name} · ‎{d.invoice.mrn}‎", objectName="Muted"))

        table = QTableWidget(len(d.lines), 4)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.setHorizontalHeaderLabels([
            self.tr("Description"), self.tr("Qty"), self.tr("Unit price"), self.tr("Total")])
        for r, line in enumerate(d.lines):
            cells = [line.description, str(line.quantity),
                     _ltr(f"{line.unit_price:.2f}"), _ltr(f"{line.line_total:.2f}")]
            for c, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if c in (1, 2, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(r, c, item)
        table.setMaximumHeight(220)
        root.addWidget(table)

        totals = QGridLayout()
        totals.setColumnStretch(0, 1)
        rows = [
            (self.tr("Subtotal"), d.subtotal),
            (self.tr("Discount"), d.discount),
            (self.tr("Tax"), d.tax),
            (self.tr("Total"), d.invoice.total),
            (self.tr("Paid"), d.invoice.paid_amount),
            (self.tr("Balance"), d.invoice.balance),
        ]
        for i, (label, value) in enumerate(rows):
            name = QLabel(label, objectName="PageTitle" if label in
                          (self.tr("Total"), self.tr("Balance")) else "Muted")
            val = QLabel(_ltr(f"{value:.2f}"))
            totals.addWidget(name, i, 0)
            totals.addWidget(val, i, 1, Qt.AlignmentFlag.AlignRight)
        root.addLayout(totals)

        if d.payments:
            root.addWidget(QLabel(self.tr("Payments"), objectName="Subtitle"))
            payments = QListWidget()
            payments.setMaximumHeight(110)
            for p in d.payments:
                payments.addItem(
                    f"‎{p.amount:.2f}‎ · {p.method} · ‎{p.paid_at.strftime('%Y-%m-%d')}‎")
            root.addWidget(payments)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton(self.tr("Close"), objectName="Primary")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)

        self.setWindowTitle(f"{self.tr('Invoice')} {d.invoice.invoice_number}")
