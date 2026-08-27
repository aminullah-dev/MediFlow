"""Reception module: the live daily patient queue and check-in flow."""
from __future__ import annotations

from datetime import datetime

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

from mediflow.core.constants import AppointmentStatus
from mediflow.services.appointment_service import AppointmentDTO
from mediflow.ui import icons
from mediflow.ui.views.base_view import BaseView
from mediflow.data.base import local_today

_STATUS_LABELS = {
    AppointmentStatus.BOOKED.value: "Booked",
    AppointmentStatus.CHECKED_IN.value: "Checked in",
    AppointmentStatus.IN_CONSULTATION.value: "In consultation",
    AppointmentStatus.COMPLETED.value: "Completed",
    AppointmentStatus.CANCELLED.value: "Cancelled",
    AppointmentStatus.NO_SHOW.value: "No show",
    AppointmentStatus.WAITLISTED.value: "Waitlisted",
}
_WAITING = {AppointmentStatus.CHECKED_IN.value, AppointmentStatus.WAITLISTED.value}


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


class ReceptionView(BaseView):
    required_permission = "reception.checkin"

    def build_ui(self) -> None:
        self._service = self.container.appointments
        self._rows: list[AppointmentDTO] = []

        top = QHBoxLayout()
        head = QVBoxLayout()
        head.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        head.addWidget(self._title)
        head.addWidget(self._subtitle)
        top.addLayout(head)
        top.addStretch(1)
        self._serving = QLabel(objectName="Badge")
        self._serving.setVisible(False)
        top.addWidget(self._serving, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._root.addLayout(top)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self._waiting_stat = _Stat()
        self._consult_stat = _Stat()
        self._done_stat = _Stat()
        for s in (self._waiting_stat, self._consult_stat, self._done_stat):
            stats.addWidget(s)
        stats.addStretch(1)
        self._root.addLayout(stats)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._checkin_btn = QPushButton()
        self._checkin_btn.clicked.connect(self._check_in)
        self._call_btn = QPushButton(objectName="Primary")
        self._call_btn.clicked.connect(self._call)
        self._complete_btn = QPushButton()
        self._complete_btn.clicked.connect(self._complete)
        for b in (self._checkin_btn, self._call_btn, self._complete_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        self._refresh_btn = QPushButton(objectName="Ghost")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self._reload)
        toolbar.addWidget(self._refresh_btn)
        self._root.addLayout(toolbar)
        icons.apply_button_icon(self._checkin_btn, "log-in")
        icons.apply_button_icon(self._call_btn, "reception")
        icons.apply_button_icon(self._complete_btn, "check")
        icons.apply_button_icon(self._refresh_btn, "refresh")

        self._table = QTableWidget(0, 6)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._root.addWidget(self._table, stretch=1)

        self._empty = QLabel(objectName="Muted")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._root.addWidget(self._empty)

    # -- data ---------------------------------------------------------------
    def on_activated(self) -> None:
        self._reload()

    def _reload(self) -> None:
        today = datetime.combine(local_today(), datetime.min.time())
        allrows = self._service.list_for_day(today)
        # Show everything except cancelled; active first, then by time.
        order = {AppointmentStatus.IN_CONSULTATION.value: 0,
                 AppointmentStatus.CHECKED_IN.value: 1,
                 AppointmentStatus.WAITLISTED.value: 1,
                 AppointmentStatus.BOOKED.value: 2,
                 AppointmentStatus.COMPLETED.value: 3}
        self._rows = sorted(
            [a for a in allrows if a.status != AppointmentStatus.CANCELLED.value],
            key=lambda a: (order.get(a.status, 4), a.scheduled_start),
        )
        self._table.setRowCount(len(self._rows))
        for r, a in enumerate(self._rows):
            values = [
                a.token_label or "",
                a.scheduled_start.strftime("%H:%M"),
                a.patient_name,
                a.doctor_name or "",
                self.tr(_STATUS_LABELS.get(a.status, a.status)),
                a.reason or "",
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c in (0, 1, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, c, item)

        waiting = sum(1 for a in allrows if a.status in _WAITING)
        consulting = [a for a in allrows
                      if a.status == AppointmentStatus.IN_CONSULTATION.value]
        done = sum(1 for a in allrows
                   if a.status == AppointmentStatus.COMPLETED.value)
        self._waiting_stat.value.setText(str(waiting))
        self._consult_stat.value.setText(str(len(consulting)))
        self._done_stat.value.setText(str(done))

        tokens = ", ".join(a.token_label for a in consulting if a.token_label)
        self._serving.setVisible(bool(tokens))
        if tokens:
            self._serving.setText(self.tr("Now serving: {token}").format(token=tokens))
        self._empty.setText("" if self._rows else self.tr("Nothing in the queue right now"))
        self._update_buttons()

    def _selected(self) -> AppointmentDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._rows[rows[0].row()]

    def _update_buttons(self) -> None:
        appt = self._selected()
        status = appt.status if appt else None
        self._checkin_btn.setEnabled(status == AppointmentStatus.BOOKED.value)
        self._call_btn.setEnabled(status in _WAITING)
        self._complete_btn.setEnabled(status == AppointmentStatus.IN_CONSULTATION.value)

    # -- actions ------------------------------------------------------------
    def _check_in(self) -> None:
        appt = self._selected()
        if appt is not None:
            self._service.check_in(appt.id)
            self._reload()

    def _call(self) -> None:
        appt = self._selected()
        if appt is not None:
            self._service.call(appt.id)
            self._reload()

    def _complete(self) -> None:
        appt = self._selected()
        if appt is not None:
            self._service.complete(appt.id)
            self._reload()

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Reception"))
        self._subtitle.setText(self.tr("Live patient queue"))
        self._waiting_stat.caption.setText(self.tr("Waiting"))
        self._consult_stat.caption.setText(self.tr("In consultation"))
        self._done_stat.caption.setText(self.tr("Completed today"))
        self._checkin_btn.setText(self.tr("Check in"))
        self._call_btn.setText(self.tr("Call"))
        self._complete_btn.setText(self.tr("Complete"))
        self._refresh_btn.setText(self.tr("Refresh"))
        self._table.setHorizontalHeaderLabels([
            self.tr("Token"), self.tr("Time"), self.tr("Patient"),
            self.tr("Doctor"), self.tr("Status"), self.tr("Reason"),
        ])
