"""Appointments module: day view with booking, check-in and status actions."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from mediflow.core.constants import AppointmentStatus
from mediflow.services.appointment_service import AppointmentDTO
from mediflow.ui.dialogs.appointment_dialog import AppointmentDialog
from mediflow.ui import icons, widgets
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


class AppointmentsView(BaseView):
    required_permission = "appointment.view"

    def build_ui(self) -> None:
        self._service = self.container.appointments
        self._date = local_today()
        self._rows: list[AppointmentDTO] = []

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._prev_btn = QPushButton()
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.clicked.connect(lambda: self._shift(-1))
        self._today_btn = QPushButton()
        self._today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._today_btn.clicked.connect(self._go_today)
        self._next_btn = QPushButton()
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(lambda: self._shift(1))
        self._date_edit = QDateEdit()
        # LTR must precede setDisplayFormat so section order isn't RTL-mirrored.
        self._date_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setDate(QDate(self._date.year, self._date.month, self._date.day))
        self._date_edit.dateChanged.connect(self._on_date_changed)
        toolbar.addWidget(self._prev_btn)
        toolbar.addWidget(self._date_edit)
        toolbar.addWidget(self._next_btn)
        toolbar.addWidget(self._today_btn)
        toolbar.addStretch(1)

        self._checkin_btn = QPushButton()
        self._checkin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checkin_btn.clicked.connect(self._check_in)
        self._complete_btn = QPushButton()
        self._complete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._complete_btn.clicked.connect(self._complete)
        self._cancel_btn = QPushButton(objectName="Danger")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self._cancel)
        self._new_btn = QPushButton(objectName="Primary")
        self._new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_btn.clicked.connect(self._create)
        toolbar.addWidget(self._checkin_btn)
        toolbar.addWidget(self._complete_btn)
        toolbar.addWidget(self._cancel_btn)
        toolbar.addWidget(self._new_btn)
        self._root.addLayout(toolbar)
        icons.apply_button_icon(self._prev_btn, "chevron-left")
        icons.apply_button_icon(self._next_btn, "chevron-right")
        icons.apply_button_icon(self._today_btn, "calendar-check")
        icons.apply_button_icon(self._checkin_btn, "log-in")
        icons.apply_button_icon(self._complete_btn, "check")
        icons.apply_button_icon(self._cancel_btn, "x")
        icons.apply_button_icon(self._new_btn, "plus")

        self._table = QTableWidget(0, 8)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._area, self._empty_text = widgets.table_with_empty_state(self._table, "appointments")
        self._root.addWidget(self._area, stretch=1)

        self._count_label = QLabel(objectName="Muted")
        self._root.addWidget(self._count_label)

    # -- data ---------------------------------------------------------------
    def on_activated(self) -> None:
        self._reload()

    def _reload(self) -> None:
        from datetime import datetime
        day = datetime(self._date.year, self._date.month, self._date.day)  # noqa: DTZ001  (wall-clock domain — see mediflow/data/base.py)
        self._rows = self._service.list_for_day(day)
        self._table.setRowCount(len(self._rows))
        for r, a in enumerate(self._rows):
            status = self.tr(_STATUS_LABELS.get(a.status, a.status))
            values = [
                a.scheduled_start.strftime("%H:%M"),
                a.token_label or "",
                a.patient_name,
                a.mrn,
                a.doctor_name or "",
                a.department_name or "",
                status,
                a.reason or "",
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c in (0, 1, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, c, item)
        self._area.setCurrentIndex(0 if self._rows else 1)
        self._count_label.setText(
            self.tr("{count} appointments").format(count=len(self._rows)))
        self._update_buttons()

    def _selected(self) -> AppointmentDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._rows[rows[0].row()]

    def _update_buttons(self) -> None:
        appt = self._selected()
        active = appt is not None and appt.is_active
        self._checkin_btn.setEnabled(active)
        self._complete_btn.setEnabled(active)
        self._cancel_btn.setEnabled(active)

    # -- date navigation ----------------------------------------------------
    def _shift(self, days: int) -> None:
        self._set_date(self._date + timedelta(days=days))

    def _go_today(self) -> None:
        self._set_date(local_today())

    def _set_date(self, new_date: date) -> None:
        self._date = new_date
        self._date_edit.blockSignals(True)
        self._date_edit.setDate(QDate(new_date.year, new_date.month, new_date.day))
        self._date_edit.blockSignals(False)
        self._reload()

    def _on_date_changed(self, qd: QDate) -> None:
        self._date = date(qd.year(), qd.month(), qd.day())
        self._reload()

    # -- actions ------------------------------------------------------------
    def _create(self) -> None:
        dialog = AppointmentDialog(self.container.patients, self._service,
                                   default_date=self._date, parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._reload()

    def _check_in(self) -> None:
        appt = self._selected()
        if appt is not None:
            self._service.check_in(appt.id)
            self._reload()

    def _complete(self) -> None:
        appt = self._selected()
        if appt is not None:
            self._service.complete(appt.id)
            self._reload()

    def _cancel(self) -> None:
        appt = self._selected()
        if appt is None:
            return
        confirm = QMessageBox.question(
            self, self.tr("Cancel appointment"),
            self.tr("Cancel appointment") + " — " + appt.patient_name + "?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._service.cancel(appt.id)
            self._reload()

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Appointments"))
        self._subtitle.setText(self.tr("Schedule and manage visits"))
        self._prev_btn.setText(self.tr("Previous"))
        self._today_btn.setText(self.tr("Today"))
        self._next_btn.setText(self.tr("Next"))
        self._checkin_btn.setText(self.tr("Check in"))
        self._complete_btn.setText(self.tr("Complete"))
        self._cancel_btn.setText(self.tr("Cancel appointment"))
        self._new_btn.setText(self.tr("New appointment"))
        self._table.setHorizontalHeaderLabels([
            self.tr("Time"), self.tr("Token"), self.tr("Patient"), self.tr("MRN"),
            self.tr("Doctor"), self.tr("Department"), self.tr("Status"), self.tr("Reason"),
        ])
        self._empty_text.setText(self.tr("No appointments for this day"))
        if hasattr(self, "_rows"):
            self._count_label.setText(
                self.tr("{count} appointments").format(count=len(self._rows)))
