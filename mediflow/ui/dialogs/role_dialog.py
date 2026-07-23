"""Add / edit a role and its permissions (grouped by module)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.exceptions import MediFlowError
from mediflow.services.user_service import RoleDTO, UserService

_MODULE_LABELS = {
    "dashboard": "Dashboard", "patient": "Patients", "appointment": "Appointments",
    "reception": "Reception", "emr": "Medical Records", "prescription": "Prescriptions",
    "pharmacy": "Pharmacy", "lab": "Laboratory", "inventory": "Inventory",
    "billing": "Billing", "accounting": "Accounting", "hr": "Human Resources",
    "report": "Reports", "user": "Users & Roles", "audit": "Audit Log",
    "backup": "Backup", "settings": "Settings",
}


class RoleDialog(QDialog):
    def __init__(self, service: UserService, role: RoleDTO | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._role = role
        self._checks: dict[str, QCheckBox] = {}
        self.setModal(True)
        self.setMinimumSize(560, 560)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._name = QLineEdit()
        self._description = QLineEdit()
        if self._role is not None:
            self._name.setText(self._role.name)
            self._description.setText(self._role.description or "")
            if self._role.is_system:
                self._name.setReadOnly(True)
        form.addRow(self.tr("Name"), self._name)
        form.addRow(self.tr("Description"), self._description)
        root.addLayout(form)

        root.addWidget(QLabel(self.tr("Permissions"), objectName="Subtitle"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        grid = QVBoxLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)

        checked = self._role.permission_codes if self._role else set()
        for module, perms in self._service.list_permission_groups():
            box = QFrame(objectName="Card")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(14, 10, 14, 12)
            box_layout.setSpacing(6)
            box_layout.addWidget(QLabel(self.tr(_MODULE_LABELS.get(module, module)),
                                        objectName="Muted"))
            actions = QGridLayout()
            actions.setHorizontalSpacing(12)
            for i, perm in enumerate(perms):
                action = perm.code.split(".")[-1]
                cb = QCheckBox(self.tr(action))
                cb.setToolTip(perm.description or perm.code)
                cb.setChecked(perm.code in checked)
                self._checks[perm.code] = cb
                actions.addWidget(cb, i // 3, i % 3)
            box_layout.addLayout(actions)
            grid.addWidget(box)
        grid.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

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

        self.setWindowTitle(self.tr("Edit role") if self._role else self.tr("New role"))

    def _selected_codes(self) -> set[str]:
        return {code for code, cb in self._checks.items() if cb.isChecked()}

    def _on_save(self) -> None:
        try:
            if self._role is None:
                self._service.create_role(self._name.text(), self._description.text(),
                                          self._selected_codes())
            else:
                self._service.update_role(self._role.id, self._description.text(),
                                          self._selected_codes())
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Invalid data"), str(exc))
            return
        self.accept()
