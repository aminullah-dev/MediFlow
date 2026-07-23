"""Billing module: invoice list with payment recording."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from mediflow.core.constants import InvoiceStatus
from mediflow.services.billing_service import InvoiceDTO
from mediflow.ui.dialogs.invoice_detail_dialog import InvoiceDetailDialog
from mediflow.ui.dialogs.invoice_dialog import InvoiceDialog
from mediflow.ui.dialogs.payment_dialog import PaymentDialog
from mediflow.ui import icons, widgets
from mediflow.ui.views.base_view import BaseView

_STATUS_LABELS = {
    InvoiceStatus.DRAFT.value: "Draft",
    InvoiceStatus.UNPAID.value: "Unpaid",
    InvoiceStatus.PARTIALLY_PAID.value: "Partially paid",
    InvoiceStatus.PAID.value: "Paid",
    InvoiceStatus.REFUNDED.value: "Refunded",
    InvoiceStatus.CANCELLED.value: "Cancelled",
}
_STATUS_COLOURS = {
    InvoiceStatus.UNPAID.value: "#dc2626",
    InvoiceStatus.PARTIALLY_PAID.value: "#d98324",
    InvoiceStatus.PAID.value: "#16a34a",
    InvoiceStatus.CANCELLED.value: "#93a6ac",
}


def _ltr(text: str) -> str:
    return f"‎{text}‎" if text else text


class BillingView(BaseView):
    required_permission = "billing.view"

    def build_ui(self) -> None:
        self._service = self.container.billing
        self._rows: list[InvoiceDTO] = []

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._reload)
        toolbar.addWidget(self._search, stretch=1)
        self._view_btn = self._button(self._view_selected)
        self._pay_btn = self._button(self._record_payment, primary=True)
        self._cancel_btn = self._button(self._cancel_selected, danger=True)
        self._new_btn = self._button(self._create, primary=True)
        for b in (self._view_btn, self._pay_btn, self._cancel_btn, self._new_btn):
            toolbar.addWidget(b)
        self._root.addLayout(toolbar)
        icons.apply_button_icon(self._view_btn, "eye")
        icons.apply_button_icon(self._pay_btn, "credit-card")
        icons.apply_button_icon(self._cancel_btn, "x")
        icons.apply_button_icon(self._new_btn, "plus")

        self._table = QTableWidget(0, 6)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.doubleClicked.connect(lambda _i: self._view_selected())
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._area, self._empty_text = widgets.table_with_empty_state(self._table, "billing")
        self._root.addWidget(self._area, stretch=1)

        self._count_label = QLabel(objectName="Muted")
        self._root.addWidget(self._count_label)

    def _button(self, slot, *, primary=False, danger=False) -> QPushButton:
        name = "Primary" if primary else ("Danger" if danger else "")
        btn = QPushButton(objectName=name)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        return btn

    # -- data ---------------------------------------------------------------
    def on_activated(self) -> None:
        self._reload()

    def _reload(self, *_a) -> None:
        self._rows = self._service.list_invoices(self._search.text())
        self._table.setRowCount(len(self._rows))
        for r, inv in enumerate(self._rows):
            status = self.tr(_STATUS_LABELS.get(inv.status, inv.status))
            values = [
                _ltr(inv.invoice_number),
                inv.patient_name,
                _ltr(inv.issued_at.strftime("%Y-%m-%d")),
                _ltr(f"{inv.total:.2f}"),
                _ltr(f"{inv.paid_amount:.2f}"),
                status,
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c in (2, 3, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 5:
                    colour = _STATUS_COLOURS.get(inv.status)
                    if colour:
                        item.setForeground(QColor(colour))
                self._table.setItem(r, c, item)
        self._area.setCurrentIndex(0 if self._rows else 1)
        self._count_label.setText(self.tr("{count} invoices").format(count=len(self._rows)))
        if not self._rows:
            self._count_label.setText(self.tr("No invoices"))
        self._update_buttons()

    def _selected(self) -> InvoiceDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._rows[rows[0].row()]

    def _update_buttons(self) -> None:
        inv = self._selected()
        self._view_btn.setEnabled(inv is not None)
        self._pay_btn.setEnabled(inv is not None and inv.is_open)
        self._cancel_btn.setEnabled(inv is not None and inv.is_open)

    # -- actions ------------------------------------------------------------
    def _create(self) -> None:
        if InvoiceDialog(self.container.patients, self._service, parent=self).exec():
            self._reload()

    def _view_selected(self) -> None:
        inv = self._selected()
        if inv is not None:
            InvoiceDetailDialog(self._service, inv.id, parent=self).exec()

    def _record_payment(self) -> None:
        inv = self._selected()
        if inv is not None and PaymentDialog(self._service, inv, parent=self).exec():
            self._reload()

    def _cancel_selected(self) -> None:
        inv = self._selected()
        if inv is None:
            return
        confirm = QMessageBox.question(
            self, self.tr("Cancel invoice"),
            self.tr("Cancel invoice") + f" — ‎{inv.invoice_number}‎?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._service.cancel_invoice(inv.id)
            self._reload()

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Billing"))
        self._subtitle.setText(self.tr("Invoices and payments"))
        self._search.setPlaceholderText(self.tr("Search by invoice, patient or MRN"))
        self._view_btn.setText(self.tr("View"))
        self._pay_btn.setText(self.tr("Record payment"))
        self._cancel_btn.setText(self.tr("Cancel invoice"))
        self._new_btn.setText(self.tr("New invoice"))
        self._table.setHorizontalHeaderLabels([
            self.tr("Invoice"), self.tr("Patient"), self.tr("Date"),
            self.tr("Total"), self.tr("Paid"), self.tr("Status"),
        ])
        self._empty_text.setText(self.tr("No invoices"))
        if hasattr(self, "_rows"):
            self._count_label.setText(self.tr("{count} invoices").format(count=len(self._rows)))
