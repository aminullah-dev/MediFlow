"""Read-only view of an audit entry's field-level changes."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mediflow.services.audit_service import AuditService


class AuditDetailDialog(QDialog):
    def __init__(self, service: AuditService, audit_id: int, header: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._changes = service.get_changes(audit_id)
        self._header = header
        self.setModal(True)
        self.setMinimumWidth(520)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(12)

        root.addWidget(QLabel(self.tr("Change detail"), objectName="PageTitle"))
        root.addWidget(QLabel(self._header, objectName="Muted"))

        table = QTableWidget(len(self._changes), 3)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.setHorizontalHeaderLabels([self.tr("Field"), self.tr("Old"), self.tr("New")])
        for r, ch in enumerate(self._changes):
            table.setItem(r, 0, QTableWidgetItem(ch.field))
            table.setItem(r, 1, QTableWidgetItem(ch.old))
            table.setItem(r, 2, QTableWidgetItem(ch.new))
        table.setMaximumHeight(320)
        root.addWidget(table)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton(self.tr("Close"), objectName="Primary")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)

        self.setWindowTitle(self.tr("Change detail"))
