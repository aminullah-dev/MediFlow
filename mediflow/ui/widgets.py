"""Small reusable UI building blocks shared across module views."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

from mediflow.ui import icons


def table_with_empty_state(table, icon_name: str, color: str = "#93a6ac"):
    """Wrap a table in a stack whose second page is a centered empty state.

    Returns ``(stack, empty_text_label)``. The caller shows the placeholder
    with ``stack.setCurrentIndex(1)`` when there are no rows (0 for the table),
    and sets the label text in ``retranslate_ui`` (e.g. "No patients found").
    """
    stack = QStackedWidget()
    stack.addWidget(table)  # index 0 — the table

    page = QWidget()
    layout = QVBoxLayout(page)
    layout.addStretch(1)
    icon = QLabel()
    icon.setPixmap(icons.pixmap(icon_name, 56, color))
    icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    text = QLabel(objectName="Subtitle")
    text.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(icon)
    layout.addSpacing(10)
    layout.addWidget(text)
    layout.addStretch(2)
    stack.addWidget(page)  # index 1 — the empty state

    return stack, text
