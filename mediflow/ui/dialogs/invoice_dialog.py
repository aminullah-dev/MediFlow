"""Create an invoice: pick a patient and add billable line items."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.exceptions import MediFlowError
from mediflow.services.billing_service import BillingService, InvoiceInput, LineInput
from mediflow.services.patient_service import PatientDTO, PatientService


class _LineRow(QWidget):
    def __init__(self, on_change, on_remove):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.description = QLineEdit()
        self.quantity = QSpinBox()
        self.quantity.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.quantity.setRange(1, 100000)
        self.quantity.setFixedWidth(70)
        self.price = QDoubleSpinBox()
        self.price.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.price.setRange(0, 1_000_000)
        self.price.setDecimals(2)
        self.price.setFixedWidth(110)
        remove = QPushButton("✕", objectName="Danger")
        remove.setFixedWidth(38)
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.clicked.connect(lambda: on_remove(self))
        layout.addWidget(self.description, stretch=1)
        layout.addWidget(self.quantity)
        layout.addWidget(self.price)
        layout.addWidget(remove)
        self.description.textChanged.connect(on_change)
        self.quantity.valueChanged.connect(on_change)
        self.price.valueChanged.connect(on_change)

    def to_input(self) -> LineInput | None:
        desc = self.description.text().strip()
        if not desc:
            return None
        return LineInput(desc, self.quantity.value(), self.price.value())

    def line_total(self) -> float:
        return self.quantity.value() * self.price.value()


class InvoiceDialog(QDialog):
    def __init__(self, patients: PatientService, billing: BillingService,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._patients = patients
        self._billing = billing
        self._selected: PatientDTO | None = None
        self._rows: list[_LineRow] = []
        self.setModal(True)
        self.setMinimumWidth(640)
        self._build_ui()
        self._add_line()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(12)

        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._search_patients)
        root.addWidget(self._search)
        self._results = QListWidget()
        self._results.setFixedHeight(96)
        self._results.itemClicked.connect(self._pick_patient)
        root.addWidget(self._results)
        self._selected_label = QLabel(objectName="Badge")
        self._selected_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._selected_label.setVisible(False)
        root.addWidget(self._selected_label)

        # line-item header
        head = QHBoxLayout()
        head.setSpacing(8)
        self._h_desc = QLabel(objectName="Muted")
        self._h_qty = QLabel(objectName="Muted")
        self._h_qty.setFixedWidth(70)
        self._h_price = QLabel(objectName="Muted")
        self._h_price.setFixedWidth(110)
        head.addWidget(self._h_desc, stretch=1)
        head.addWidget(self._h_qty)
        head.addWidget(self._h_price)
        head.addSpacing(46)
        root.addLayout(head)

        self._lines_layout = QVBoxLayout()
        self._lines_layout.setSpacing(6)
        root.addLayout(self._lines_layout)

        self._add_btn = QPushButton(objectName="Ghost")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.clicked.connect(self._add_line)
        add_row = QHBoxLayout()
        add_row.addWidget(self._add_btn)
        add_row.addStretch(1)
        root.addLayout(add_row)

        # totals
        totals = QGridLayout()
        totals.setHorizontalSpacing(12)
        self._l_subtotal = QLabel(objectName="Muted")
        self._l_discount = QLabel(objectName="Muted")
        self._l_tax = QLabel(objectName="Muted")
        self._l_total = QLabel(objectName="PageTitle")
        self._subtotal_val = QLabel("0.00")
        self._discount = QDoubleSpinBox()
        self._discount.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._discount.setRange(0, 1_000_000)
        self._discount.setDecimals(2)
        self._discount.valueChanged.connect(self._recompute)
        self._tax = QDoubleSpinBox()
        self._tax.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._tax.setRange(0, 1_000_000)
        self._tax.setDecimals(2)
        self._tax.valueChanged.connect(self._recompute)
        self._total_val = QLabel("0.00", objectName="PageTitle")
        totals.addWidget(self._l_subtotal, 0, 0)
        totals.addWidget(self._subtotal_val, 0, 1, Qt.AlignmentFlag.AlignRight)
        totals.addWidget(self._l_discount, 1, 0)
        totals.addWidget(self._discount, 1, 1)
        totals.addWidget(self._l_tax, 2, 0)
        totals.addWidget(self._tax, 2, 1)
        totals.addWidget(self._l_total, 3, 0)
        totals.addWidget(self._total_val, 3, 1, Qt.AlignmentFlag.AlignRight)
        totals.setColumnStretch(0, 1)
        root.addLayout(totals)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(self.tr("Cancel"))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        create = QPushButton(self.tr("Create"), objectName="Primary")
        create.setCursor(Qt.CursorShape.PointingHandCursor)
        create.clicked.connect(self._on_create)
        buttons.addWidget(cancel)
        buttons.addWidget(create)
        root.addLayout(buttons)

        self.setWindowTitle(self.tr("New invoice"))
        self._search.setPlaceholderText(self.tr("Search patient by name, MRN or phone"))
        self._h_desc.setText(self.tr("Description"))
        self._h_qty.setText(self.tr("Qty"))
        self._h_price.setText(self.tr("Unit price"))
        self._add_btn.setText(self.tr("Add line"))
        self._l_subtotal.setText(self.tr("Subtotal"))
        self._l_discount.setText(self.tr("Discount"))
        self._l_tax.setText(self.tr("Tax"))
        self._l_total.setText(self.tr("Total"))
        self._search_patients("")

    # -- patient ------------------------------------------------------------
    def _search_patients(self, _text: str) -> None:
        self._results.clear()
        for p in self._patients.search(self._search.text(), limit=20):
            item = QListWidgetItem(f"{p.full_name}  ·  {p.mrn}")
            item.setData(Qt.ItemDataRole.UserRole, p)
            self._results.addItem(item)

    def _pick_patient(self, item: QListWidgetItem) -> None:
        self._selected = item.data(Qt.ItemDataRole.UserRole)
        self._selected_label.setVisible(True)
        self._selected_label.setText(
            self.tr("Selected: {name}").format(name=self._selected.full_name))

    # -- lines --------------------------------------------------------------
    def _add_line(self) -> None:
        row = _LineRow(self._recompute, self._remove_line)
        self._rows.append(row)
        self._lines_layout.addWidget(row)
        self._recompute()

    def _remove_line(self, row: _LineRow) -> None:
        if row in self._rows:
            self._rows.remove(row)
            row.setParent(None)
            row.deleteLater()
            self._recompute()

    def _recompute(self, *_a) -> None:
        subtotal = sum(r.line_total() for r in self._rows)
        total = max(0.0, subtotal - self._discount.value() + self._tax.value())
        self._subtotal_val.setText(f"{subtotal:.2f}")
        self._total_val.setText(f"{total:.2f}")

    # -- create -------------------------------------------------------------
    def _on_create(self) -> None:
        if self._selected is None:
            QMessageBox.warning(self, self.tr("New invoice"), self.tr("Select a patient first."))
            return
        lines = [r.to_input() for r in self._rows]
        lines = [line for line in lines if line is not None]
        if not lines:
            QMessageBox.warning(self, self.tr("New invoice"), self.tr("Add at least one line."))
            return
        try:
            self._billing.create_invoice(InvoiceInput(
                patient_id=self._selected.id, lines=lines,
                discount=self._discount.value(), tax=self._tax.value(),
            ))
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("New invoice"), str(exc))
            return
        self.accept()
