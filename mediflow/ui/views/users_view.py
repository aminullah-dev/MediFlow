"""Users & Roles module: user administration and RBAC."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
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

from mediflow.core.exceptions import MediFlowError
from mediflow.services.user_service import UserDTO
from mediflow.ui.dialogs.roles_dialog import RolesDialog
from mediflow.ui.dialogs.user_dialog import UserDialog
from mediflow.ui import icons, widgets
from mediflow.ui.views.base_view import BaseView


class UsersView(BaseView):
    required_permission = "user.view"

    def build_ui(self) -> None:
        self._service = self.container.users
        self._rows: list[UserDTO] = []

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._reload)
        toolbar.addWidget(self._search, stretch=1)
        self._reset_btn = self._button(self._reset_password)
        self._toggle_btn = self._button(self._toggle_active)
        self._edit_btn = self._button(self._edit_selected)
        self._delete_btn = self._button(self._delete_selected, danger=True)
        self._roles_btn = self._button(self._manage_roles, ghost=True)
        self._new_btn = self._button(self._create, primary=True)
        for b in (self._reset_btn, self._toggle_btn, self._edit_btn,
                  self._delete_btn, self._roles_btn, self._new_btn):
            toolbar.addWidget(b)
        self._root.addLayout(toolbar)
        icons.apply_button_icon(self._reset_btn, "key")
        icons.apply_button_icon(self._toggle_btn, "power")
        icons.apply_button_icon(self._edit_btn, "pencil")
        icons.apply_button_icon(self._delete_btn, "trash")
        icons.apply_button_icon(self._roles_btn, "list")
        icons.apply_button_icon(self._new_btn, "plus")

        self._table = QTableWidget(0, 4)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.doubleClicked.connect(lambda _i: self._edit_selected())
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._area, self._empty_text = widgets.table_with_empty_state(self._table, "users")
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
        self._rows = self._service.list_users(self._search.text())
        self._table.setRowCount(len(self._rows))
        for r, u in enumerate(self._rows):
            status = self.tr("Active") if u.is_active else self.tr("Inactive")
            values = [u.username, u.full_name, "، ".join(u.role_names), status]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setForeground(QColor("#16a34a" if u.is_active else "#93a6ac"))
                self._table.setItem(r, c, item)
        self._area.setCurrentIndex(0 if self._rows else 1)
        self._count_label.setText(self.tr("{count} users").format(count=len(self._rows)))
        if not self._rows:
            self._count_label.setText(self.tr("No users found"))
        self._update_buttons()

    def _selected(self) -> UserDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._rows[rows[0].row()]

    def _update_buttons(self) -> None:
        u = self._selected()
        has = u is not None
        for b in (self._reset_btn, self._toggle_btn, self._edit_btn, self._delete_btn):
            b.setEnabled(has)
        self._toggle_btn.setText(
            self.tr("Deactivate") if (u and u.is_active) else self.tr("Activate"))

    # -- actions ------------------------------------------------------------
    def _create(self) -> None:
        dialog = UserDialog(self._service, parent=self)
        if dialog.exec() and dialog.temp_password:
            self._show_password(dialog._collect().full_name, dialog.temp_password)
        self._reload()

    def _edit_selected(self) -> None:
        u = self._selected()
        if u and UserDialog(self._service, u, parent=self).exec():
            self._reload()

    def _reset_password(self) -> None:
        u = self._selected()
        if u is None:
            return
        try:
            temp = self._service.reset_password(u.id)
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Reset password"), str(exc))
            return
        self._show_password(u.full_name, temp)

    def _toggle_active(self) -> None:
        u = self._selected()
        if u is None:
            return
        try:
            self._service.set_active(u.id, not u.is_active)
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Users & Roles"), str(exc))
            return
        self._reload()

    def _delete_selected(self) -> None:
        u = self._selected()
        if u is None:
            return
        confirm = QMessageBox.question(
            self, self.tr("Delete user?"),
            self.tr("Remove {name}?").format(name=u.full_name))
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.delete_user(u.id)
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Users & Roles"), str(exc))
            return
        self._reload()

    def _manage_roles(self) -> None:
        RolesDialog(self._service, parent=self).exec()
        self._reload()

    def _show_password(self, name: str, password: str) -> None:
        QMessageBox.information(
            self, self.tr("Temporary password"),
            self.tr("The temporary password for {name} is: {password}").format(
                name=name, password=password)
            + "\n\n" + self.tr("They must change it at first sign-in."))

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Users & Roles"))
        self._subtitle.setText(self.tr("Manage users and permissions"))
        self._search.setPlaceholderText(self.tr("Search by username or name"))
        self._reset_btn.setText(self.tr("Reset password"))
        self._edit_btn.setText(self.tr("Edit"))
        self._delete_btn.setText(self.tr("Delete"))
        self._roles_btn.setText(self.tr("Manage roles"))
        self._new_btn.setText(self.tr("New user"))
        self._table.setHorizontalHeaderLabels([
            self.tr("Username"), self.tr("Full name"), self.tr("Roles"), self.tr("Status")])
        self._empty_text.setText(self.tr("No users found"))
        self._update_buttons()
        if hasattr(self, "_rows"):
            self._count_label.setText(self.tr("{count} users").format(count=len(self._rows)))
