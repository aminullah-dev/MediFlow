"""Add / edit a user and assign roles."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.exceptions import MediFlowError
from mediflow.services.user_service import UserDTO, UserInput, UserService


class UserDialog(QDialog):
    def __init__(self, service: UserService, user: UserDTO | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._user = user
        self.temp_password: str | None = None
        self.setModal(True)
        self.setMinimumWidth(460)
        self._build_ui()
        if user is not None:
            self._load(user)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._username = QLineEdit()
        self._full_name = QLineEdit()
        self._email = QLineEdit()
        self._phone = QLineEdit()
        self._active = QCheckBox(self.tr("Active"))
        self._active.setChecked(True)
        form.addRow(self.tr("Username"), self._username)
        form.addRow(self.tr("Full name"), self._full_name)
        form.addRow(self.tr("Email"), self._email)
        form.addRow(self.tr("Phone"), self._phone)
        form.addRow("", self._active)
        root.addLayout(form)

        root.addWidget(QLabel(self.tr("Roles"), objectName="Muted"))
        self._roles = QListWidget()
        self._roles.setMaximumHeight(160)
        for role in self._service.list_roles():
            item = QListWidgetItem(role.name)
            item.setData(Qt.ItemDataRole.UserRole, role.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._roles.addItem(item)
        root.addWidget(self._roles)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(self.tr("Cancel"))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        save = QPushButton(self.tr("Save"), objectName="Primary")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self._on_save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

        self.setWindowTitle(self.tr("Edit user") if self._user else self.tr("New user"))
        self._username.setFocus()

    def _load(self, u: UserDTO) -> None:
        self._username.setText(u.username)
        self._username.setReadOnly(True)
        self._full_name.setText(u.full_name)
        self._email.setText(u.email or "")
        self._phone.setText(u.phone or "")
        self._active.setChecked(u.is_active)
        for i in range(self._roles.count()):
            item = self._roles.item(i)
            checked = item.data(Qt.ItemDataRole.UserRole) in u.role_ids
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def _collect(self) -> UserInput:
        role_ids = [
            self._roles.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._roles.count())
            if self._roles.item(i).checkState() == Qt.CheckState.Checked
        ]
        return UserInput(
            username=self._username.text(), full_name=self._full_name.text(),
            email=self._email.text(), phone=self._phone.text(),
            is_active=self._active.isChecked(), role_ids=role_ids,
        )

    def _on_save(self) -> None:
        data = self._collect()
        try:
            if self._user is None:
                self.temp_password = self._service.create_user(data)
            else:
                self._service.update_user(self._user.id, data)
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Invalid data"), str(exc))
            return
        self.accept()
