"""Read-only view of a journal entry's lines."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mediflow.services.accounting_service import AccountingService


def _ltr(text: str) -> str:
    return f"‎{text}‎" if text else text


class EntryDetailDialog(QDialog):
    def __init__(self, service: AccountingService, entry_id: int,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._detail = service.get_entry_detail(entry_id)
        self.setModal(True)
        self.setMinimumWidth(520)
        self._build_ui()

    def _build_ui(self) -> None:
        d = self._detail
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(10)

        root.addWidget(QLabel(f"{self.tr('Entry')} · ‎{d.entry.entry_date.strftime('%Y-%m-%d')}‎",
                              objectName="PageTitle"))
        root.addWidget(QLabel(d.entry.description, objectName="Muted"))

        table = QTableWidget(len(d.lines), 3)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.setHorizontalHeaderLabels([self.tr("Account"), self.tr("Debit"), self.tr("Credit")])
        for r, line in enumerate(d.lines):
            cells = [
                f"‎{line.account_code}‎ — {line.account_name}",
                _ltr(f"{line.debit:.2f}") if line.debit else "",
                _ltr(f"{line.credit:.2f}") if line.credit else "",
            ]
            for c, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if c in (1, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(r, c, item)
        table.setMaximumHeight(260)
        root.addWidget(table)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton(self.tr("Close"), objectName="Primary")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)

        self.setWindowTitle(self.tr("Entry"))
