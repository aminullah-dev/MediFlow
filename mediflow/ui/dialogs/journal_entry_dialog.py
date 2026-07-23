"""Post a balanced double-entry journal entry."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
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
    QVBoxLayout,
    QWidget,
)

from mediflow.core.exceptions import MediFlowError
from mediflow.services.accounting_service import (
    AccountingService,
    AccountDTO,
    EntryInput,
    LineInput,
)


class _EntryLine(QWidget):
    def __init__(self, accounts: list[AccountDTO], on_change, on_remove):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.account = QComboBox()
        for a in accounts:
            self.account.addItem(f"‎{a.code}‎ — {a.name}", a.id)
        self.debit = QDoubleSpinBox()
        self.debit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.debit.setRange(0, 100_000_000)
        self.debit.setDecimals(2)
        self.debit.setFixedWidth(110)
        self.credit = QDoubleSpinBox()
        self.credit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.credit.setRange(0, 100_000_000)
        self.credit.setDecimals(2)
        self.credit.setFixedWidth(110)
        remove = QPushButton("✕", objectName="Danger")
        remove.setFixedWidth(38)
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.clicked.connect(lambda: on_remove(self))
        layout.addWidget(self.account, stretch=1)
        layout.addWidget(self.debit)
        layout.addWidget(self.credit)
        layout.addWidget(remove)
        self.debit.valueChanged.connect(on_change)
        self.credit.valueChanged.connect(on_change)

    def to_input(self) -> LineInput | None:
        if self.debit.value() <= 0 and self.credit.value() <= 0:
            return None
        return LineInput(self.account.currentData(), self.debit.value(), self.credit.value())


class JournalEntryDialog(QDialog):
    def __init__(self, service: AccountingService, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._accounts = service.list_accounts(active_only=True)
        self._rows: list[_EntryLine] = []
        self.setModal(True)
        self.setMinimumWidth(600)
        self._build_ui()
        self._add_line()
        self._add_line()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._date = QDateEdit()
        self._date.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("yyyy-MM-dd")
        self._date.setDate(QDate.currentDate())
        self._description = QLineEdit()
        self._reference = QLineEdit()
        form.addRow(self.tr("Date"), self._date)
        form.addRow(self.tr("Description"), self._description)
        form.addRow(self.tr("Reference"), self._reference)
        root.addLayout(form)

        head = QHBoxLayout()
        head.setSpacing(8)
        self._h_account = QLabel(objectName="Muted")
        self._h_debit = QLabel(objectName="Muted")
        self._h_debit.setFixedWidth(110)
        self._h_debit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._h_credit = QLabel(objectName="Muted")
        self._h_credit.setFixedWidth(110)
        self._h_credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.addWidget(self._h_account, stretch=1)
        head.addWidget(self._h_debit)
        head.addWidget(self._h_credit)
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

        totals = QHBoxLayout()
        self._totals_label = QLabel(objectName="Muted")
        self._balance_badge = QLabel(objectName="Badge")
        totals.addWidget(self._totals_label)
        totals.addStretch(1)
        totals.addWidget(self._balance_badge)
        root.addLayout(totals)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(self.tr("Cancel"))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        self._save = QPushButton(self.tr("Save"), objectName="Primary")
        self._save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save.clicked.connect(self._on_save)
        buttons.addWidget(cancel)
        buttons.addWidget(self._save)
        root.addLayout(buttons)

        self.setWindowTitle(self.tr("New entry"))
        self._h_account.setText(self.tr("Account"))
        self._h_debit.setText(self.tr("Debit"))
        self._h_credit.setText(self.tr("Credit"))
        self._add_btn.setText(self.tr("Add line"))
        self._recompute()

    def _add_line(self) -> None:
        row = _EntryLine(self._accounts, self._recompute, self._remove_line)
        self._rows.append(row)
        self._lines_layout.addWidget(row)
        self._recompute()

    def _remove_line(self, row: _EntryLine) -> None:
        if row in self._rows and len(self._rows) > 1:
            self._rows.remove(row)
            row.setParent(None)
            row.deleteLater()
            self._recompute()

    def _recompute(self, *_a) -> None:
        total_debit = sum(r.debit.value() for r in self._rows)
        total_credit = sum(r.credit.value() for r in self._rows)
        self._totals_label.setText(
            f"{self.tr('Total debit')}: ‎{total_debit:.2f}‎    "
            f"{self.tr('Total credit')}: ‎{total_credit:.2f}‎")
        balanced = total_debit > 0 and abs(total_debit - total_credit) < 0.005
        self._balance_badge.setText(self.tr("Balanced") if balanced else self.tr("Not balanced"))
        self._save.setEnabled(balanced)

    def _on_save(self) -> None:
        lines = [r.to_input() for r in self._rows]
        lines = [line for line in lines if line is not None]
        try:
            self._service.create_entry(EntryInput(
                entry_date=self._date.date().toPython(),
                description=self._description.text(),
                reference=self._reference.text(),
                lines=lines,
            ))
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Invalid data"), str(exc))
            return
        self.accept()
