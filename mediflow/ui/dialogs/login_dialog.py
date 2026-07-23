"""Login dialog — authenticates against :class:`AuthService`.

Presentation only: all credential logic lives in the service. Domain errors are
mapped to translated, non-revealing messages (never disclose whether it was the
username or the password that was wrong).

The redesign targets the one failure operators actually hit — mistyping a hard
password until the account locks — with four remedies:
    * a show/hide (eye) toggle so the typed password can be verified;
    * a pre-filled username (the last one used), so only the password is typed;
    * a Caps Lock warning, the usual silent cause of "the password won't work";
    * inline, non-blocking feedback: attempts remaining, and a live unlock
      countdown while the account is locked (replacing the modal popups that
      forced a click between every attempt).
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.exceptions import AccountLockedError, AuthenticationError, MediFlowError
from mediflow.services.auth_service import AuthenticatedUser, AuthService
from mediflow.ui import icons
from mediflow.ui import theme as theme_colors

# Amber warning colour (Caps Lock hint). Legible on both light and dark cards;
# the palette has no amber token, so it is fixed here rather than themed.
_WARN = "#d97706"


class LoginDialog(QDialog):
    def __init__(self, auth: AuthService, config=None, parent: QWidget | None = None):
        super().__init__(parent)
        self._auth = auth
        self._config = config
        self.user: AuthenticatedUser | None = None
        self._muted = theme_colors.CURRENT["text_muted"]

        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(1000)
        self._lock_timer.timeout.connect(self._tick_lock)
        self._lock_seconds = 0

        self.setModal(True)
        self.setFixedWidth(430)
        self._build_ui()
        self.retranslate_ui()
        self._prefill_username()

    # -- construction -------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)

        card = QFrame(objectName="Card")
        root = QVBoxLayout(card)
        root.setContentsMargins(34, 34, 34, 34)
        root.setSpacing(6)

        self._logo = QLabel(objectName="Brand")
        self._logo.setPixmap(icons.pixmap("stethoscope", 46, theme_colors.CURRENT["primary"]))
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._logo)

        self._title = QLabel(objectName="PageTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._title)

        self._subtitle = QLabel(objectName="Subtitle")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setWordWrap(True)
        root.addWidget(self._subtitle)
        root.addSpacing(20)

        self._username_label = QLabel(objectName="Muted")
        self._username = QLineEdit()
        self._username.setClearButtonEnabled(True)
        self._username.setMinimumHeight(40)
        self._username.installEventFilter(self)
        self._username.returnPressed.connect(self._password_focus)
        root.addWidget(self._username_label)
        root.addWidget(self._username)
        root.addSpacing(10)

        self._password_label = QLabel(objectName="Muted")
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setMinimumHeight(40)
        self._password.installEventFilter(self)
        self._password.returnPressed.connect(self._attempt_login)
        # Eye toggle lives inside the field; TrailingPosition is RTL-aware.
        self._reveal = self._password.addAction(
            icons.icon("eye", 18, self._muted),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self._reveal.setCheckable(True)
        self._reveal.triggered.connect(self._toggle_reveal)
        root.addWidget(self._password_label)
        root.addWidget(self._password)

        # Caps Lock hint — hidden until Caps Lock is actually on.
        self._caps = self._make_banner("CapsHint", _WARN, _WARN)
        root.addSpacing(8)
        root.addWidget(self._caps["frame"])

        # Status banner — errors and the lockout countdown, inline (no popups).
        danger = theme_colors.CURRENT["danger"]
        self._status = self._make_banner(
            "LoginStatus", danger, danger, soft=theme_colors.CURRENT["danger_soft"]
        )
        root.addWidget(self._status["frame"])
        root.addSpacing(14)

        self._login_button = QPushButton(objectName="Primary")
        self._login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_button.setMinimumHeight(44)
        self._login_button.clicked.connect(self._attempt_login)
        root.addWidget(self._login_button)

        outer.addWidget(card)

    def _make_banner(self, name: str, icon_color: str, text_color: str,
                     soft: str | None = None) -> dict:
        """A hideable icon+text row used for the Caps hint and status messages."""
        frame = QFrame(objectName=name)
        if soft:
            frame.setStyleSheet(
                f"QFrame#{name} {{ background-color:{soft}; border:1px solid {text_color};"
                f" border-radius:10px; }}"
            )
        row = QHBoxLayout(frame)
        if soft:                              # filled banner (status) vs. bare hint
            row.setContentsMargins(12, 9, 12, 9)
        else:
            row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(8)
        glyph = QLabel()
        glyph.setFixedWidth(18)
        text = QLabel()
        text.setWordWrap(True)
        text.setStyleSheet(f"color:{text_color}; background:transparent; font-weight:600;")
        row.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(text, 1)
        frame.setVisible(False)
        return {"frame": frame, "glyph": glyph, "text": text,
                "icon_color": icon_color}

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.tr("Sign in to MediFlow"))
        self._title.setText(self.tr("MediFlow"))
        self._subtitle.setText(self.tr("Sign in to your account"))
        self._username_label.setText(self.tr("Username"))
        self._password_label.setText(self.tr("Password"))
        self._login_button.setText(self.tr("Sign in"))
        checked = self._reveal.isChecked()
        self._reveal.setToolTip(
            self.tr("Hide password") if checked else self.tr("Show password"))
        self._caps["text"].setText(self.tr("Caps Lock is on"))

    # -- behaviour ----------------------------------------------------------
    def _prefill_username(self) -> None:
        remembered = ""
        if self._config is not None:
            remembered = (self._config.settings.last_username or "").strip()
        self._username.setText(remembered)
        if remembered:
            self._password.setFocus()
        else:
            self._username.setFocus()

    def _password_focus(self) -> None:
        self._password.setFocus()

    def _toggle_reveal(self, checked: bool) -> None:
        self._password.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
        self._reveal.setIcon(icons.icon("eye-off" if checked else "eye", 18, self._muted))
        self._reveal.setToolTip(
            self.tr("Hide password") if checked else self.tr("Show password"))

    def eventFilter(self, obj, event) -> bool:
        if event.type() in (
            QEvent.Type.KeyPress, QEvent.Type.KeyRelease, QEvent.Type.FocusIn,
        ):
            self._update_caps_hint()
        return super().eventFilter(obj, event)

    def _update_caps_hint(self) -> None:
        on = _caps_lock_on()
        if on and not self._caps["frame"].isVisible():
            self._caps["glyph"].setPixmap(
                icons.pixmap("alert-triangle", 16, self._caps["icon_color"]))
        self._caps["frame"].setVisible(on)

    # -- status banner ------------------------------------------------------
    def _set_status(self, icon_name: str, text: str) -> None:
        self._status["glyph"].setPixmap(
            icons.pixmap(icon_name, 16, self._status["icon_color"]))
        self._status["text"].setText(text)
        self._status["frame"].setVisible(True)

    def _clear_status(self) -> None:
        self._status["frame"].setVisible(False)

    # -- lockout countdown --------------------------------------------------
    def _begin_lockout(self, seconds: int) -> None:
        self._lock_seconds = max(seconds, 1)
        self._login_button.setEnabled(False)
        self._password.setEnabled(False)
        self._render_lock()
        self._lock_timer.start()

    def _tick_lock(self) -> None:
        self._lock_seconds -= 1
        if self._lock_seconds <= 0:
            self._lock_timer.stop()
            self._end_lockout()
        else:
            self._render_lock()

    def _render_lock(self) -> None:
        minutes, seconds = divmod(self._lock_seconds, 60)
        self._set_status(
            "lock",
            self.tr("Account locked. Try again in {time}.").format(
                time=f"{minutes:02d}:{seconds:02d}"),
        )

    def _end_lockout(self) -> None:
        self._login_button.setEnabled(True)
        self._password.setEnabled(True)
        self._clear_status()
        self._password.clear()
        self._password.setFocus()

    # -- authentication -----------------------------------------------------
    def _attempt_login(self) -> None:
        username = self._username.text().strip()
        password = self._password.text()
        if not username or not password:
            self._set_status(
                "alert-triangle",
                self.tr("Please enter your username and password."))
            return
        try:
            self.user = self._auth.authenticate(username, password)
        except AccountLockedError as exc:
            self._begin_lockout(exc.retry_after_seconds or 60)
            self._password.clear()
        except AuthenticationError as exc:
            self._show_bad_credentials(exc.attempts_remaining)
            self._password.clear()
            self._password.setFocus()
        except MediFlowError:
            self._set_status(
                "alert-triangle", self.tr("Invalid username or password."))
            self._password.clear()
            self._password.setFocus()
        else:
            self._remember_username(username)
            self.accept()

    def _show_bad_credentials(self, remaining: int | None) -> None:
        if remaining is not None and 0 < remaining <= 3:
            text = self.tr(
                "Invalid username or password. {n} tries left before lock."
            ).format(n=remaining)
        else:
            text = self.tr("Invalid username or password.")
        self._set_status("alert-triangle", text)

    def _remember_username(self, username: str) -> None:
        if self._config is None:
            return
        try:
            self._config.settings.last_username = username
            self._config.settings.save()
        except Exception:  # a settings-write failure must never block sign-in
            pass


def _caps_lock_on() -> bool:
    """Best-effort Caps Lock state. Windows-native; silently False elsewhere."""
    if sys.platform.startswith("win"):
        try:
            import ctypes

            return bool(ctypes.WinDLL("user32").GetKeyState(0x14) & 0x0001)
        except Exception:
            return False
    return False
