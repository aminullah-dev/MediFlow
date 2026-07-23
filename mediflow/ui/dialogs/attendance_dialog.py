"""Record and review an employee's attendance."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.constants import AttendanceStatus
from mediflow.services.hr_service import EmployeeDTO, HRService

_STATUS_LABELS = {
    AttendanceStatus.PRESENT.value: "Present",
    AttendanceStatus.ABSENT.value: "Absent",
    AttendanceStatus.LEAVE.value: "Leave",
    AttendanceStatus.HALF_DAY.value: "Half day",
    AttendanceStatus.HOLIDAY.value: "Holiday",
}


def _ltr(text: str) -> str:
    return f"‎{text}‎" if text else text


class AttendanceDialog(QDialog):
    def __init__(self, service: HRService, employee: EmployeeDTO,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._employee = employee
        self.setModal(True)
        self.setMinimumWidth(520)
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

        root.addWidget(QLabel(f"{self.tr('Attendance')} · {self._employee.full_name}",
                              objectName="PageTitle"))

        entry = QHBoxLayout()
        entry.setSpacing(8)
        self._date = QDateEdit()
        self._date.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("yyyy-MM-dd")
        self._date.setDate(QDate.currentDate())
        self._status = QComboBox()
        for st in AttendanceStatus:
            self._status.addItem(self.tr(_STATUS_LABELS[st.value]), st.value)
        self._note = QLineEdit()
        self._note.setPlaceholderText(self.tr("Note"))
        self._mark = QPushButton(self.tr("Mark"), objectName="Primary")
        self._mark.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mark.clicked.connect(self._mark_attendance)
        entry.addWidget(self._date)
        entry.addWidget(self._status)
        entry.addWidget(self._note, stretch=1)
        entry.addWidget(self._mark)
        root.addLayout(entry)

        self._table = QTableWidget(0, 3)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setHorizontalHeaderLabels([
            self.tr("Date"), self.tr("Status"), self.tr("Note")])
        self._table.setMaximumHeight(280)
        root.addWidget(self._table)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton(self.tr("Close"))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)

        self.setWindowTitle(self.tr("Attendance"))

    def _reload(self) -> None:
        rows = self._service.list_attendance(self._employee.id)
        self._table.setRowCount(len(rows))
        for r, a in enumerate(rows):
            cells = [_ltr(a.work_date.strftime("%Y-%m-%d")),
                     self.tr(_STATUS_LABELS.get(a.status, a.status)), a.note or ""]
            for c, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if c in (0, 1):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, c, item)

    def _mark_attendance(self) -> None:
        self._service.mark_attendance(
            self._employee.id, self._date.date().toPython(),
            AttendanceStatus(self._status.currentData()), self._note.text())
        self._note.clear()
        self._reload()
