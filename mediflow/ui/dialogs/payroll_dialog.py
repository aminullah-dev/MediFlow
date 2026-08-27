"""Create and pay employee payslips."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


from mediflow.core.constants import PayslipStatus
from mediflow.core.exceptions import MediFlowError
from mediflow.services.hr_service import EmployeeDTO, HRService, PayslipDTO
from mediflow.data.base import local_today

_STATUS_LABELS = {PayslipStatus.PENDING.value: "Pending", PayslipStatus.PAID.value: "Paid"}


def _ltr(text: str) -> str:
    return f"‎{text}‎" if text else text


class PayrollDialog(QDialog):
    def __init__(self, service: HRService, employee: EmployeeDTO,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._employee = employee
        self._rows: list[PayslipDTO] = []
        self.setModal(True)
        self.setMinimumWidth(600)
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

        root.addWidget(QLabel(f"{self.tr('Payroll')} · {self._employee.full_name}",
                              objectName="PageTitle"))

        now = local_today()  # payroll period defaults follow the local calendar
        entry = QHBoxLayout()
        entry.setSpacing(8)
        self._year = QSpinBox()
        self._year.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._year.setRange(2000, 2100)
        self._year.setValue(now.year)
        self._month = QSpinBox()
        self._month.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._month.setRange(1, 12)
        self._month.setValue(now.month)
        self._base = self._money(self._employee.base_salary)
        self._allow = self._money(0)
        self._deduct = self._money(0)
        self._net = QLabel("0.00", objectName="Badge")
        for w in (self._base, self._allow, self._deduct):
            w.valueChanged.connect(self._recompute)
        self._l_year = QLabel(self.tr("Year"), objectName="Muted")
        self._l_month = QLabel(self.tr("Month"), objectName="Muted")
        self._l_base = QLabel(self.tr("Base"), objectName="Muted")
        self._l_allow = QLabel(self.tr("Allowances"), objectName="Muted")
        self._l_deduct = QLabel(self.tr("Deductions"), objectName="Muted")
        self._l_net = QLabel(self.tr("Net"), objectName="Muted")
        for label, widget in ((self._l_year, self._year), (self._l_month, self._month),
                              (self._l_base, self._base), (self._l_allow, self._allow),
                              (self._l_deduct, self._deduct), (self._l_net, self._net)):
            box = QVBoxLayout()
            box.setSpacing(2)
            box.addWidget(label)
            box.addWidget(widget)
            entry.addLayout(box)
        root.addLayout(entry)

        create_row = QHBoxLayout()
        self._create = QPushButton(self.tr("Create payslip"), objectName="Primary")
        self._create.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create.clicked.connect(self._create_payslip)
        create_row.addWidget(self._create)
        create_row.addStretch(1)
        self._paid_btn = QPushButton(self.tr("Mark paid"))
        self._paid_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._paid_btn.clicked.connect(self._mark_paid)
        create_row.addWidget(self._paid_btn)
        root.addLayout(create_row)

        self._table = QTableWidget(0, 6)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setHorizontalHeaderLabels([
            self.tr("Period"), self.tr("Base"), self.tr("Allowances"),
            self.tr("Deductions"), self.tr("Net"), self.tr("Status")])
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._table.setMaximumHeight(240)
        root.addWidget(self._table)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton(self.tr("Close"))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)

        self.setWindowTitle(self.tr("Payroll"))
        self._recompute()

    def _money(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        spin.setRange(0, 100_000_000)
        spin.setDecimals(2)
        spin.setValue(value)
        spin.setFixedWidth(110)
        return spin

    def _recompute(self, *_a) -> None:
        net = self._base.value() + self._allow.value() - self._deduct.value()
        self._net.setText(f"‎{max(0.0, net):.2f}‎")

    def _reload(self) -> None:
        self._rows = self._service.list_payslips(self._employee.id)
        self._table.setRowCount(len(self._rows))
        for r, p in enumerate(self._rows):
            status = self.tr(_STATUS_LABELS.get(p.status, p.status))
            cells = [_ltr(f"{p.period_year}-{p.period_month:02d}"), _ltr(f"{p.base_salary:.2f}"),
                     _ltr(f"{p.allowances:.2f}"), _ltr(f"{p.deductions:.2f}"),
                     _ltr(f"{p.net:.2f}"), status]
            for c, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 5:
                    item.setForeground(QColor("#16a34a" if p.status == PayslipStatus.PAID.value
                                              else "#d98324"))
                self._table.setItem(r, c, item)
        self._update_buttons()

    def _selected(self) -> PayslipDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._rows[rows[0].row()]

    def _update_buttons(self) -> None:
        p = self._selected()
        self._paid_btn.setEnabled(p is not None and p.is_pending)

    def _create_payslip(self) -> None:
        try:
            self._service.create_payslip(
                self._employee.id, self._year.value(), self._month.value(),
                self._base.value(), self._allow.value(), self._deduct.value())
        except MediFlowError as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, self.tr("Invalid data"), str(exc))
            return
        self._reload()

    def _mark_paid(self) -> None:
        p = self._selected()
        if p is not None:
            self._service.mark_paid(p.id)
            self._reload()
