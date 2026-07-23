"""Manage the chart of accounts: list with balances, add and remove."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.constants import AccountType
from mediflow.core.exceptions import MediFlowError
from mediflow.services.accounting_service import AccountingService

_TYPE_LABELS = {
    AccountType.ASSET.value: "Asset",
    AccountType.LIABILITY.value: "Liability",
    AccountType.EQUITY.value: "Equity",
    AccountType.INCOME.value: "Income",
    AccountType.EXPENSE.value: "Expense",
}


def _ltr(text: str) -> str:
    return f"‎{text}‎" if text else text


class AccountsDialog(QDialog):
    def __init__(self, service: AccountingService, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self.setModal(True)
        self.setMinimumWidth(560)
        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(12)

        root.addWidget(QLabel(self.tr("Chart of accounts"), objectName="PageTitle"))

        self._table = QTableWidget(0, 4)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setMaximumHeight(240)
        root.addWidget(self._table)

        remove_row = QHBoxLayout()
        remove_row.addStretch(1)
        self._remove = QPushButton(self.tr("Remove"), objectName="Danger")
        self._remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove.clicked.connect(self._remove_selected)
        remove_row.addWidget(self._remove)
        root.addLayout(remove_row)

        form = QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._code = QLineEdit()
        self._name = QLineEdit()
        self._type = QComboBox()
        for atype in AccountType:
            self._type.addItem(self.tr(_TYPE_LABELS[atype.value]), atype.value)
        form.addRow(self.tr("Code"), self._code)
        form.addRow(self.tr("Name"), self._name)
        form.addRow(self.tr("Type"), self._type)
        root.addLayout(form)

        buttons = QHBoxLayout()
        self._add = QPushButton(self.tr("Add"), objectName="Primary")
        self._add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add.clicked.connect(self._add_account)
        buttons.addWidget(self._add)
        buttons.addStretch(1)
        close = QPushButton(self.tr("Close"))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)

        self._table.setHorizontalHeaderLabels([
            self.tr("Code"), self.tr("Name"), self.tr("Type"), self.tr("Balance")])
        self.setWindowTitle(self.tr("Chart of accounts"))

    def _reload(self) -> None:
        accounts = self._service.list_accounts()
        self._table.setRowCount(len(accounts))
        for r, a in enumerate(accounts):
            cells = [_ltr(a.code), a.name, self.tr(_TYPE_LABELS.get(a.account_type,
                     a.account_type)), _ltr(f"{a.balance:.2f}")]
            for c, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, a.id)
                if c in (0, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, c, item)

    def _add_account(self) -> None:
        try:
            self._service.create_account(self._code.text(), self._name.text(),
                                         AccountType(self._type.currentData()))
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Add account"), str(exc))
            return
        self._code.clear()
        self._name.clear()
        self._reload()

    def _remove_selected(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        account_id = self._table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        try:
            self._service.delete_account(account_id)
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Chart of accounts"), str(exc))
            return
        self._reload()
