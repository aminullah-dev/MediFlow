"""Human Resources module: employee roster, attendance and payroll."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
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
)

from mediflow.services.hr_service import EmployeeDTO
from mediflow.ui import icons
from mediflow.ui.dialogs.attendance_dialog import AttendanceDialog
from mediflow.ui.dialogs.employee_dialog import EmployeeDialog
from mediflow.ui.dialogs.payroll_dialog import PayrollDialog
from mediflow.ui.views.base_view import BaseView


def _ltr(text: str) -> str:
    return f"‎{text}‎" if text else text


class _Stat(QFrame):
    def __init__(self):
        super().__init__(objectName="StatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(2)
        self.value = QLabel("0", objectName="StatValue")
        self.caption = QLabel("", objectName="StatCaption")
        layout.addWidget(self.value)
        layout.addWidget(self.caption)


class HRView(BaseView):
    required_permission = "hr.view"

    def build_ui(self) -> None:
        self._service = self.container.hr
        self._rows: list[EmployeeDTO] = []

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._root.addLayout(header)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self._total_stat = _Stat()
        self._active_stat = _Stat()
        self._payroll_stat = _Stat()
        for s in (self._total_stat, self._active_stat, self._payroll_stat):
            stats.addWidget(s)
        stats.addStretch(1)
        self._root.addLayout(stats)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._reload)
        toolbar.addWidget(self._search, stretch=1)
        self._attend_btn = self._button(self._attendance)
        self._payroll_btn = self._button(self._payroll)
        self._edit_btn = self._button(self._edit_selected)
        self._delete_btn = self._button(self._delete_selected, danger=True)
        self._new_btn = self._button(self._create, primary=True)
        for b in (self._attend_btn, self._payroll_btn, self._edit_btn,
                  self._delete_btn, self._new_btn):
            toolbar.addWidget(b)
        self._root.addLayout(toolbar)
        icons.apply_button_icon(self._attend_btn, "calendar-check")
        icons.apply_button_icon(self._payroll_btn, "credit-card")
        icons.apply_button_icon(self._edit_btn, "pencil")
        icons.apply_button_icon(self._delete_btn, "trash")
        icons.apply_button_icon(self._new_btn, "plus")

        self._table = QTableWidget(0, 7)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.doubleClicked.connect(lambda _i: self._edit_selected())
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._root.addWidget(self._table, stretch=1)

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
        total, active, payroll = self._service.summary()
        self._total_stat.value.setText(str(total))
        self._active_stat.value.setText(str(active))
        self._payroll_stat.value.setText(f"{payroll:.2f}")

        self._rows = self._service.list_employees(self._search.text())
        self._table.setRowCount(len(self._rows))
        for r, e in enumerate(self._rows):
            status = self.tr("Active") if e.is_active else self.tr("Inactive")
            values = [
                _ltr(e.employee_code), e.full_name, e.position or "", e.department or "",
                _ltr(e.phone or ""), _ltr(f"{e.base_salary:.2f}"), status,
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c in (0, 5, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 6:
                    item.setForeground(QColor("#16a34a" if e.is_active else "#93a6ac"))
                self._table.setItem(r, c, item)
        self._count_label.setText(self.tr("{count} employees").format(count=len(self._rows)))
        if not self._rows:
            self._count_label.setText(self.tr("No employees found"))
        self._update_buttons()

    def _selected(self) -> EmployeeDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._rows[rows[0].row()]

    def _update_buttons(self) -> None:
        has = self._selected() is not None
        for b in (self._attend_btn, self._payroll_btn, self._edit_btn, self._delete_btn):
            b.setEnabled(has)

    # -- actions ------------------------------------------------------------
    def _create(self) -> None:
        if EmployeeDialog(self._service, parent=self).exec():
            self._reload()

    def _edit_selected(self) -> None:
        e = self._selected()
        if e and EmployeeDialog(self._service, e, parent=self).exec():
            self._reload()

    def _attendance(self) -> None:
        e = self._selected()
        if e:
            AttendanceDialog(self._service, e, parent=self).exec()

    def _payroll(self) -> None:
        e = self._selected()
        if e:
            PayrollDialog(self._service, e, parent=self).exec()
            self._reload()

    def _delete_selected(self) -> None:
        e = self._selected()
        if e is None:
            return
        confirm = QMessageBox.question(
            self, self.tr("Delete employee?"),
            self.tr("Remove {name} from records?").format(name=e.full_name),
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._service.delete(e.id)
            self._reload()

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Human Resources"))
        self._subtitle.setText(self.tr("Employees and payroll"))
        self._total_stat.caption.setText(self.tr("Employees"))
        self._active_stat.caption.setText(self.tr("Active"))
        self._payroll_stat.caption.setText(self.tr("Monthly payroll"))
        self._search.setPlaceholderText(self.tr("Search by name, code or position"))
        self._attend_btn.setText(self.tr("Attendance"))
        self._payroll_btn.setText(self.tr("Payroll"))
        self._edit_btn.setText(self.tr("Edit"))
        self._delete_btn.setText(self.tr("Delete"))
        self._new_btn.setText(self.tr("New employee"))
        self._table.setHorizontalHeaderLabels([
            self.tr("Code"), self.tr("Name"), self.tr("Position"), self.tr("Department"),
            self.tr("Phone"), self.tr("Salary"), self.tr("Status"),
        ])
        self._count_label.setText(self.tr("{count} employees").format(count=len(self._rows)))
