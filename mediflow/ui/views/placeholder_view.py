"""Placeholder view for modules whose UI is scheduled in a later phase.

Keeps navigation complete and honest: the entry appears, opens, and clearly
states the module is not yet implemented, rather than being hidden or crashing.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from mediflow.app import ServiceContainer
from mediflow.ui.views.base_view import BaseView


class PlaceholderView(BaseView):
    def __init__(self, container: ServiceContainer, title_key: str,
                 parent: QWidget | None = None):
        self._title_key = title_key
        super().__init__(container, parent)

    def build_ui(self) -> None:
        center = QVBoxLayout()
        center.setSpacing(10)
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._glyph = QLabel("\U0001F6E0", objectName="EmptyGlyph")
        self._glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title = QLabel(objectName="PageTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge = QLabel(objectName="Badge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body = QLabel(objectName="Muted")
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)

        center.addWidget(self._glyph, alignment=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self._title, alignment=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self._badge, alignment=Qt.AlignmentFlag.AlignCenter)
        center.addSpacing(4)
        center.addWidget(self._body, alignment=Qt.AlignmentFlag.AlignCenter)

        self._root.addStretch(1)
        self._root.addLayout(center)
        self._root.addStretch(2)

    def retranslate_ui(self) -> None:
        self._title.setText(self.tr(self._title_key))
        self._badge.setText(self.tr("Coming soon"))
        self._body.setText(self.tr("This module is coming in an upcoming release."))
