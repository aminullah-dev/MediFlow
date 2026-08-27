"""Audit Log module: change history and sign-in history (read-only)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from mediflow.services.audit_service import AuditEntryDTO, LoginEntryDTO
from mediflow.ui import icons
from mediflow.ui.dialogs.audit_detail_dialog import AuditDetailDialog
from mediflow.ui.views.base_view import BaseView


def _ltr(text: str) -> str:
    return f"‎{text}‎" if text else text


class AuditView(BaseView):
    required_permission = "audit.view"

    def build_ui(self) -> None:
        self._service = self.container.audit
        self._mode = "changes"
        self._events: list[AuditEntryDTO] = []
        self._logins: list[LoginEntryDTO] = []

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._changes_btn = QPushButton(objectName="Segment")
        self._changes_btn.setCheckable(True)
        self._changes_btn.setChecked(True)
        self._signins_btn = QPushButton(objectName="Segment")
        self._signins_btn.setCheckable(True)
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self._changes_btn)
        group.addButton(self._signins_btn)
        for b in (self._changes_btn, self._signins_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self._changes_btn.clicked.connect(lambda: self._set_mode("changes"))
        self._signins_btn.clicked.connect(lambda: self._set_mode("signins"))
        toolbar.addWidget(self._changes_btn)
        toolbar.addWidget(self._signins_btn)
        toolbar.addSpacing(12)

        self._entity_combo = QComboBox()
        self._entity_combo.setMinimumWidth(150)
        self._entity_combo.currentIndexChanged.connect(lambda _i: self._reload())
        self._action_combo = QComboBox()
        self._action_combo.setMinimumWidth(140)
        self._action_combo.currentIndexChanged.connect(lambda _i: self._reload())
        toolbar.addWidget(self._entity_combo)
        toolbar.addWidget(self._action_combo)
        toolbar.addStretch(1)
        self._view_btn = QPushButton(objectName="")
        self._view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view_btn.clicked.connect(self._view_selected)
        self._verify_btn = QPushButton(objectName="Ghost")
        self._verify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._verify_btn.clicked.connect(self._verify_integrity)
        self._refresh_btn = QPushButton(objectName="Ghost")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self._reload_all)
        toolbar.addWidget(self._view_btn)
        toolbar.addWidget(self._verify_btn)
        toolbar.addWidget(self._refresh_btn)
        self._root.addLayout(toolbar)
        icons.apply_button_icon(self._changes_btn, "list")
        icons.apply_button_icon(self._signins_btn, "log-in")
        icons.apply_button_icon(self._verify_btn, "users")
        icons.apply_button_icon(self._view_btn, "eye")
        icons.apply_button_icon(self._refresh_btn, "refresh")

        self._table = QTableWidget(0, 5)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.doubleClicked.connect(lambda _i: self._view_selected())
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._root.addWidget(self._table, stretch=1)

        self._count_label = QLabel(objectName="Muted")
        self._root.addWidget(self._count_label)

    # -- lifecycle ----------------------------------------------------------
    def on_activated(self) -> None:
        self._populate_filters()
        self._reload()

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        is_changes = mode == "changes"
        self._entity_combo.setVisible(is_changes)
        self._action_combo.setVisible(is_changes)
        self._view_btn.setVisible(is_changes)
        self._apply_headers()
        self._reload()

    def _reload_all(self) -> None:
        self._populate_filters()
        self._reload()

    def _populate_filters(self) -> None:
        self._entity_combo.blockSignals(True)
        self._action_combo.blockSignals(True)
        self._entity_combo.clear()
        self._entity_combo.addItem(self.tr("All"), None)
        for et in self._service.entity_types():
            self._entity_combo.addItem(et, et)
        self._action_combo.clear()
        self._action_combo.addItem(self.tr("All"), None)
        for ac in self._service.actions():
            self._action_combo.addItem(self.tr(ac), ac)
        self._entity_combo.blockSignals(False)
        self._action_combo.blockSignals(False)

    # -- data ---------------------------------------------------------------
    def _reload(self, *_a) -> None:
        if self._mode == "changes":
            self._events = self._service.list_events(
                entity_type=self._entity_combo.currentData(),
                action=self._action_combo.currentData())
            self._fill_changes()
        else:
            self._logins = self._service.list_logins()
            self._fill_logins()
        self._update_buttons()

    def _fill_changes(self) -> None:
        self._table.setColumnCount(5)
        self._table.setRowCount(len(self._events))
        for r, e in enumerate(self._events):
            values = [
                _ltr(e.occurred_at.strftime("%Y-%m-%d %H:%M")),
                e.user_name,
                self.tr(e.action),
                f"{e.entity_type}" + (f" #{e.entity_id}" if e.entity_id else ""),
                e.summary or "",
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c in (0, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, c, item)
        self._count_label.setText(
            self.tr("{count} events").format(count=len(self._events))
            if self._events else self.tr("No records"))

    def _fill_logins(self) -> None:
        self._table.setColumnCount(4)
        self._apply_headers()
        self._table.setRowCount(len(self._logins))
        for r, e in enumerate(self._logins):
            result = self.tr("Success") if e.success else self.tr("Failed")
            reason = self.tr(e.reason) if e.reason else ""
            values = [_ltr(e.occurred_at.strftime("%Y-%m-%d %H:%M")), e.username, result, reason]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c in (0, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 2:
                    item.setForeground(QColor("#16a34a" if e.success else "#dc2626"))
                self._table.setItem(r, c, item)
        self._count_label.setText(
            self.tr("{count} sign-ins").format(count=len(self._logins))
            if self._logins else self.tr("No records"))

    def _selected_event(self) -> AuditEntryDTO | None:
        if self._mode != "changes":
            return None
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._events[rows[0].row()]

    def _update_buttons(self) -> None:
        e = self._selected_event()
        self._view_btn.setEnabled(e is not None and e.has_changes)

    def _view_selected(self) -> None:
        e = self._selected_event()
        if e is not None and e.has_changes:
            header = f"{self.tr(e.action)} · {e.entity_type}" + (f" #{e.entity_id}" if e.entity_id else "")
            AuditDetailDialog(self._service, e.id, header, parent=self).exec()

    def _verify_integrity(self) -> None:
        ok, broken_id, total = self._service.verify_chain()
        if ok:
            QMessageBox.information(
                self, self.tr("Integrity check"),
                self.tr("Audit trail is intact — {count} records verified.").format(count=total))
        else:
            QMessageBox.warning(
                self, self.tr("Integrity check"),
                self.tr("Tampering detected: record #{id} was altered or removed.").format(
                    id=broken_id))

    # -- i18n ---------------------------------------------------------------
    def _apply_headers(self) -> None:
        if self._mode == "changes":
            self._table.setColumnCount(5)
            self._table.setHorizontalHeaderLabels([
                self.tr("Time"), self.tr("User"), self.tr("Action"),
                self.tr("Entity"), self.tr("Summary")])
            self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        else:
            self._table.setColumnCount(4)
            self._table.setHorizontalHeaderLabels([
                self.tr("Time"), self.tr("Username"), self.tr("Result"), self.tr("Reason")])
            self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Audit Log"))
        self._subtitle.setText(self.tr("Change history and sign-ins"))
        self._changes_btn.setText(self.tr("Changes"))
        self._signins_btn.setText(self.tr("Sign-ins"))
        self._view_btn.setText(self.tr("View"))
        self._verify_btn.setText(self.tr("Verify integrity"))
        self._refresh_btn.setText(self.tr("Refresh"))
        self._apply_headers()
