"""Laboratory module: test-request worklist and result entry."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from mediflow.core.constants import LabRequestStatus
from mediflow.services.lab_service import LabRequestDTO
from mediflow.ui.dialogs.lab_request_dialog import LabRequestDialog
from mediflow.ui.dialogs.lab_result_dialog import LabResultDialog
from mediflow.ui.dialogs.lab_tests_dialog import LabTestsDialog
from mediflow.ui import icons, widgets
from mediflow.ui.views.base_view import BaseView

_STATUS_LABELS = {
    LabRequestStatus.REQUESTED.value: "Requested",
    LabRequestStatus.SAMPLE_COLLECTED.value: "Sample collected",
    LabRequestStatus.IN_PROGRESS.value: "In progress",
    LabRequestStatus.COMPLETED.value: "Completed",
    LabRequestStatus.CANCELLED.value: "Cancelled",
}


def _ltr(text: str) -> str:
    return f"‎{text}‎" if text else text


class LaboratoryView(BaseView):
    required_permission = "lab.view"

    def build_ui(self) -> None:
        self._service = self.container.lab
        self._rows: list[LabRequestDTO] = []

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._pending_only = QCheckBox()
        self._pending_only.toggled.connect(self._reload)
        toolbar.addWidget(self._pending_only)
        toolbar.addStretch(1)
        self._collect_btn = self._button(self._collect)
        self._start_btn = self._button(self._start)
        self._result_btn = self._button(self._enter_result, primary=True)
        self._cancel_btn = self._button(self._cancel, danger=True)
        self._tests_btn = self._button(self._manage_tests, ghost=True)
        self._new_btn = self._button(self._create, primary=True)
        for b in (self._collect_btn, self._start_btn, self._result_btn,
                  self._cancel_btn, self._tests_btn, self._new_btn):
            toolbar.addWidget(b)
        self._root.addLayout(toolbar)
        icons.apply_button_icon(self._collect_btn, "laboratory")
        icons.apply_button_icon(self._start_btn, "play")
        icons.apply_button_icon(self._result_btn, "pencil")
        icons.apply_button_icon(self._cancel_btn, "x")
        icons.apply_button_icon(self._tests_btn, "list")
        icons.apply_button_icon(self._new_btn, "plus")

        self._table = QTableWidget(0, 6)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._area, self._empty_text = widgets.table_with_empty_state(self._table, "laboratory")
        self._root.addWidget(self._area, stretch=1)

        self._count_label = QLabel(objectName="Muted")
        self._root.addWidget(self._count_label)

    def _button(self, slot, *, primary=False, danger=False, ghost=False) -> QPushButton:
        name = "Primary" if primary else ("Danger" if danger else ("Ghost" if ghost else ""))
        btn = QPushButton(objectName=name)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        return btn

    # -- data ---------------------------------------------------------------
    def on_activated(self) -> None:
        self._reload()

    def _reload(self, *_a) -> None:
        self._rows = self._service.list_requests(open_only=self._pending_only.isChecked())
        self._table.setRowCount(len(self._rows))
        for r, req in enumerate(self._rows):
            result = req.result_value or ""
            if result and req.unit:
                result = f"{result} {req.unit}"
            values = [
                req.patient_name,
                req.mrn,
                req.test_name,
                self.tr(_STATUS_LABELS.get(req.status, req.status)),
                _ltr(result),
                _ltr(req.requested_at.strftime("%Y-%m-%d")),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c in (3, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, c, item)
        self._area.setCurrentIndex(0 if self._rows else 1)
        self._count_label.setText(self.tr("{count} requests").format(count=len(self._rows)))
        if not self._rows:
            self._count_label.setText(self.tr("No test requests"))
        self._update_buttons()

    def _selected(self) -> LabRequestDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._rows[rows[0].row()]

    def _update_buttons(self) -> None:
        req = self._selected()
        s = req.status if req else None
        self._collect_btn.setEnabled(s == LabRequestStatus.REQUESTED.value)
        self._start_btn.setEnabled(s == LabRequestStatus.SAMPLE_COLLECTED.value)
        self._result_btn.setEnabled(req is not None and req.is_open)
        self._cancel_btn.setEnabled(req is not None and req.is_open)

    # -- actions ------------------------------------------------------------
    def _create(self) -> None:
        if LabRequestDialog(self.container.patients, self._service, parent=self).exec():
            self._reload()

    def _collect(self) -> None:
        req = self._selected()
        if req is not None:
            self._service.collect_sample(req.id)
            self._reload()

    def _start(self) -> None:
        req = self._selected()
        if req is not None:
            self._service.start(req.id)
            self._reload()

    def _enter_result(self) -> None:
        req = self._selected()
        if req is not None and LabResultDialog(self._service, req, parent=self).exec():
            self._reload()

    def _cancel(self) -> None:
        req = self._selected()
        if req is not None:
            self._service.cancel(req.id)
            self._reload()

    def _manage_tests(self) -> None:
        LabTestsDialog(self._service, parent=self).exec()

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Laboratory"))
        self._subtitle.setText(self.tr("Test requests and results"))
        self._pending_only.setText(self.tr("Only pending"))
        self._collect_btn.setText(self.tr("Collect sample"))
        self._start_btn.setText(self.tr("Start"))
        self._result_btn.setText(self.tr("Enter result"))
        self._cancel_btn.setText(self.tr("Cancel request"))
        self._tests_btn.setText(self.tr("Manage tests"))
        self._new_btn.setText(self.tr("New request"))
        self._table.setHorizontalHeaderLabels([
            self.tr("Patient"), self.tr("MRN"), self.tr("Test"),
            self.tr("Status"), self.tr("Result"), self.tr("Requested on"),
        ])
        self._empty_text.setText(self.tr("No test requests"))
        if hasattr(self, "_rows"):
            self._count_label.setText(self.tr("{count} requests").format(count=len(self._rows)))
