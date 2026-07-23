"""Manage roles: list with permission counts, add / edit / remove."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.exceptions import MediFlowError
from mediflow.services.user_service import RoleDTO, UserService
from mediflow.ui.dialogs.role_dialog import RoleDialog


class RolesDialog(QDialog):
    def __init__(self, service: UserService, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._rows: list[RoleDTO] = []
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

        root.addWidget(QLabel(self.tr("Manage roles"), objectName="PageTitle"))

        self._table = QTableWidget(0, 3)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setHorizontalHeaderLabels([
            self.tr("Role"), self.tr("Permissions"), self.tr("System")])
        self._table.doubleClicked.connect(lambda _i: self._edit())
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._table.setMaximumHeight(300)
        root.addWidget(self._table)

        buttons = QHBoxLayout()
        self._new = QPushButton(self.tr("New role"), objectName="Primary")
        self._new.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new.clicked.connect(self._create)
        self._edit_btn = QPushButton(self.tr("Edit"))
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.clicked.connect(self._edit)
        self._remove = QPushButton(self.tr("Remove"), objectName="Danger")
        self._remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove.clicked.connect(self._remove_selected)
        buttons.addWidget(self._new)
        buttons.addWidget(self._edit_btn)
        buttons.addWidget(self._remove)
        buttons.addStretch(1)
        close = QPushButton(self.tr("Close"))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)

        self.setWindowTitle(self.tr("Manage roles"))

    def _reload(self) -> None:
        self._rows = self._service.list_roles()
        self._table.setRowCount(len(self._rows))
        for r, role in enumerate(self._rows):
            cells = [role.name, f"‎{role.permission_count}‎",
                     self.tr("System") if role.is_system else ""]
            for c, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if c in (1, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, c, item)
        self._update_buttons()

    def _selected(self) -> RoleDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._rows[rows[0].row()]

    def _update_buttons(self) -> None:
        role = self._selected()
        self._edit_btn.setEnabled(role is not None)
        self._remove.setEnabled(role is not None and not role.is_system)

    def _create(self) -> None:
        if RoleDialog(self._service, parent=self).exec():
            self._reload()

    def _edit(self) -> None:
        role = self._selected()
        if role and RoleDialog(self._service, role, parent=self).exec():
            self._reload()

    def _remove_selected(self) -> None:
        role = self._selected()
        if role is None:
            return
        try:
            self._service.delete_role(role.id)
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Manage roles"), str(exc))
            return
        self._reload()
