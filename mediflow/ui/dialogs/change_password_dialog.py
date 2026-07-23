"""Force / allow a signed-in user to set a new password."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.exceptions import MediFlowError
from mediflow.core.security import MIN_PASSWORD_LENGTH
from mediflow.services.auth_service import AuthService


class ChangePasswordDialog(QDialog):
    def __init__(self, auth: AuthService, user_id: int, *, forced: bool = False,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._auth = auth
        self._user_id = user_id
        self._forced = forced
        self.setModal(True)
        self.setMinimumWidth(420)
        if forced:
            # A forced change must not be dismissible via the window close button.
            self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel(self.tr("Change password"), objectName="PageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)
        if self._forced:
            hint = QLabel(self.tr("You must set a new password before continuing."),
                          objectName="Subtitle")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            root.addWidget(hint)
        root.addSpacing(6)

        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._current = self._password_field()
        self._new = self._password_field()
        self._confirm = self._password_field()
        form.addRow(self.tr("Current password"), self._current)
        form.addRow(self.tr("New password"), self._new)
        form.addRow(self.tr("Confirm password"), self._confirm)
        root.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        if not self._forced:
            cancel = QPushButton(self.tr("Cancel"))
            cancel.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel.clicked.connect(self.reject)
            buttons.addWidget(cancel)
        self._save = QPushButton(self.tr("Change"), objectName="Primary")
        self._save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save.setMinimumHeight(40)
        self._save.clicked.connect(self._on_change)
        buttons.addWidget(self._save)
        root.addLayout(buttons)

        self.setWindowTitle(self.tr("Change password"))
        self._current.setFocus()

    def _password_field(self) -> QLineEdit:
        field = QLineEdit()
        field.setEchoMode(QLineEdit.EchoMode.Password)
        return field

    def reject(self) -> None:
        # A forced change is mandatory: Esc / Alt+F4 must not dismiss it
        # (QDialog maps Esc to reject() even without a close button).
        if self._forced:
            return
        super().reject()

    def _on_change(self) -> None:
        new = self._new.text()
        if new != self._confirm.text():
            QMessageBox.warning(self, self.tr("Change password"),
                                self.tr("Passwords do not match."))
            return
        if len(new) < MIN_PASSWORD_LENGTH:
            QMessageBox.warning(self, self.tr("Change password"),
                                self.tr("Password must be at least 8 characters."))
            return
        try:
            self._auth.change_password(self._user_id, self._current.text(), new)
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Change password"), str(exc))
            return
        self.accept()
