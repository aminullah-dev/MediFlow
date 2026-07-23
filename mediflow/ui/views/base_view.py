"""Base class for module views.

Each module (Patients, Pharmacy, Billing …) subclasses :class:`BaseView`. The
view is lazily constructed the first time its navigation entry is opened, and
``on_activated`` is called every time it becomes visible so it can refresh data.
Subclasses implement ``retranslate_ui`` for live language switching.
"""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from mediflow.app import ServiceContainer


class BaseView(QWidget):
    #: Permission required to open this view (None = always available).
    required_permission: str | None = None

    def __init__(self, container: ServiceContainer, parent: QWidget | None = None):
        super().__init__(parent)
        self.container = container
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(24, 24, 24, 24)
        self._root.setSpacing(16)
        self.build_ui()
        self.retranslate_ui()

    def build_ui(self) -> None:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError

    def retranslate_ui(self) -> None:
        """Refresh translated strings. Override in subclasses."""

    def on_activated(self) -> None:
        """Called each time the view becomes the active page. Override to refresh."""
