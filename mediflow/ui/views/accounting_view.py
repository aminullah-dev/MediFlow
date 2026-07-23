"""Accounting module: journal entries with a P&L summary."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from mediflow.services.accounting_service import EntryDTO
from mediflow.ui.dialogs.accounts_dialog import AccountsDialog
from mediflow.ui.dialogs.entry_detail_dialog import EntryDetailDialog
from mediflow.ui.dialogs.journal_entry_dialog import JournalEntryDialog
from mediflow.ui import icons
from mediflow.ui.views.base_view import BaseView


def _ltr(text: str) -> str:
    return f"‎{text}‎" if text else text


class _Stat(QFrame):
    def __init__(self, colour: str | None = None):
        super().__init__(objectName="StatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(2)
        self.value = QLabel("0.00", objectName="StatValue")
        if colour:
            self.value.setStyleSheet(f"color: {colour};")
        self.caption = QLabel("", objectName="StatCaption")
        layout.addWidget(self.value)
        layout.addWidget(self.caption)


class AccountingView(BaseView):
    required_permission = "accounting.view"

    def build_ui(self) -> None:
        self._service = self.container.accounting
        self._rows: list[EntryDTO] = []

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._root.addLayout(header)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self._income_stat = _Stat("#16a34a")
        self._expense_stat = _Stat("#dc2626")
        self._net_stat = _Stat()
        for s in (self._income_stat, self._expense_stat, self._net_stat):
            stats.addWidget(s)
        stats.addStretch(1)
        self._root.addLayout(stats)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addStretch(1)
        self._view_btn = self._button(self._view_selected)
        self._accounts_btn = self._button(self._manage_accounts, ghost=True)
        self._new_btn = self._button(self._create, primary=True)
        for b in (self._view_btn, self._accounts_btn, self._new_btn):
            toolbar.addWidget(b)
        self._root.addLayout(toolbar)
        icons.apply_button_icon(self._view_btn, "eye")
        icons.apply_button_icon(self._accounts_btn, "book")
        icons.apply_button_icon(self._new_btn, "plus")

        self._table = QTableWidget(0, 4)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.doubleClicked.connect(lambda _i: self._view_selected())
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._root.addWidget(self._table, stretch=1)

        self._count_label = QLabel(objectName="Muted")
        self._root.addWidget(self._count_label)

    def _button(self, slot, *, primary=False, ghost=False) -> QPushButton:
        name = "Primary" if primary else ("Ghost" if ghost else "")
        btn = QPushButton(objectName=name)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        return btn

    # -- data ---------------------------------------------------------------
    def on_activated(self) -> None:
        self._reload()

    def _reload(self) -> None:
        summary = self._service.summary()
        self._income_stat.value.setText(f"{summary.income:.2f}")
        self._expense_stat.value.setText(f"{summary.expense:.2f}")
        self._net_stat.value.setText(f"{summary.net:.2f}")

        self._rows = self._service.list_entries()
        self._table.setRowCount(len(self._rows))
        for r, e in enumerate(self._rows):
            values = [
                _ltr(e.entry_date.strftime("%Y-%m-%d")),
                e.description,
                e.reference or "",
                _ltr(f"{e.amount:.2f}"),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c in (0, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, c, item)
        self._count_label.setText(self.tr("{count} entries").format(count=len(self._rows)))
        if not self._rows:
            self._count_label.setText(self.tr("No journal entries"))
        self._update_buttons()

    def _selected(self) -> EntryDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._rows[rows[0].row()]

    def _update_buttons(self) -> None:
        self._view_btn.setEnabled(self._selected() is not None)

    # -- actions ------------------------------------------------------------
    def _create(self) -> None:
        if JournalEntryDialog(self._service, parent=self).exec():
            self._reload()

    def _view_selected(self) -> None:
        e = self._selected()
        if e is not None:
            EntryDetailDialog(self._service, e.id, parent=self).exec()

    def _manage_accounts(self) -> None:
        AccountsDialog(self._service, parent=self).exec()
        self._reload()

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Accounting"))
        self._subtitle.setText(self.tr("General ledger"))
        self._income_stat.caption.setText(self.tr("Income"))
        self._expense_stat.caption.setText(self.tr("Expense"))
        self._net_stat.caption.setText(self.tr("Net"))
        self._view_btn.setText(self.tr("View"))
        self._accounts_btn.setText(self.tr("Chart of accounts"))
        self._new_btn.setText(self.tr("New entry"))
        self._table.setHorizontalHeaderLabels([
            self.tr("Date"), self.tr("Description"), self.tr("Reference"), self.tr("Amount")])
        if hasattr(self, "_rows"):
            self._count_label.setText(self.tr("{count} entries").format(count=len(self._rows)))
