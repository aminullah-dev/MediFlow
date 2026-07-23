"""Dashboard: at-a-glance daily statistics."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from mediflow.services.dashboard_service import DashboardService
from mediflow.ui import icons
from mediflow.ui.views.base_view import BaseView


class _StatCard(QFrame):
    def __init__(self, icon: str):
        super().__init__(objectName="StatCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        self.icon_label = QLabel(objectName="StatIcon")
        self.icon_label.setPixmap(icons.pixmap(icon, 22, "#ffffff"))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)
        self.value_label = QLabel("0", objectName="StatValue")
        self.caption_label = QLabel("", objectName="StatCaption")
        text_box.addWidget(self.value_label)
        text_box.addWidget(self.caption_label)
        layout.addLayout(text_box)
        layout.addStretch(1)

    def set_value(self, value: int) -> None:
        self.value_label.setText(str(value))

    def set_caption(self, caption: str) -> None:
        self.caption_label.setText(caption)


class DashboardView(BaseView):
    required_permission = "dashboard.view"

    # (stats attribute, caption source string, icon name)
    _SPECS = [
        ("total_patients", "Total patients", "patients"),
        ("patients_today", "Registered today", "user-plus"),
        ("appointments_today", "Appointments today", "appointments"),
        ("waiting_now", "Waiting now", "clock"),
        ("completed_today", "Completed today", "check-circle"),
    ]

    def build_ui(self) -> None:
        self._service = DashboardService(self.container.database)

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._root.addLayout(header)
        self._root.addSpacing(6)

        grid = QGridLayout()
        grid.setSpacing(16)
        self._cards: dict[str, _StatCard] = {}
        for index, (key, _caption, icon) in enumerate(self._SPECS):
            card = _StatCard(icon)
            self._cards[key] = card
            grid.addWidget(card, index // 3, index % 3)
        self._root.addLayout(grid)
        self._root.addStretch(1)

    def on_activated(self) -> None:
        stats = self._service.snapshot()
        for key, card in self._cards.items():
            card.set_value(getattr(stats, key))

    def retranslate_ui(self) -> None:
        if hasattr(self, "_title"):
            self._title.setText(self.tr("Dashboard"))
            self._subtitle.setText(self.tr("Today at a glance"))
            for key, caption, _icon in self._SPECS:
                self._cards[key].set_caption(self.tr(caption))
