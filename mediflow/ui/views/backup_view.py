"""Backup module: create, restore and manage database backups."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from mediflow.core.exceptions import MediFlowError
from mediflow.services.backup_service import BackupDTO
from mediflow.ui import icons
from mediflow.ui.views.base_view import BaseView


def _ltr(text: str) -> str:
    return f"‎{text}‎" if text else text


def _human_size(num: int) -> str:
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class BackupView(BaseView):
    required_permission = "backup.run"

    def build_ui(self) -> None:
        self._service = self.container.backup
        self._rows: list[BackupDTO] = []

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._create_btn = self._button(self._create, primary=True)
        self._create_to_btn = self._button(self._create_to)
        toolbar.addWidget(self._create_btn)
        toolbar.addWidget(self._create_to_btn)
        toolbar.addStretch(1)
        self._restore_btn = self._button(self._restore)
        self._delete_btn = self._button(self._delete, danger=True)
        self._open_btn = self._button(self._open_folder, ghost=True)
        toolbar.addWidget(self._restore_btn)
        toolbar.addWidget(self._delete_btn)
        toolbar.addWidget(self._open_btn)
        self._root.addLayout(toolbar)
        icons.apply_button_icon(self._create_btn, "download")
        icons.apply_button_icon(self._create_to_btn, "folder")
        icons.apply_button_icon(self._restore_btn, "upload")
        icons.apply_button_icon(self._delete_btn, "trash")
        icons.apply_button_icon(self._open_btn, "folder")

        self._table = QTableWidget(0, 3)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._root.addWidget(self._table, stretch=1)

        self._count_label = QLabel(objectName="Muted")
        self._root.addWidget(self._count_label)

    def _button(self, slot, *, primary=False, danger=False, ghost=False) -> QPushButton:
        name = "Primary" if primary else ("Danger" if danger else ("Ghost" if ghost else ""))
        btn = QPushButton(objectName=name)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        return btn

    # -- data ---------------------------------------------------------------
    def on_activated(self) -> None:
        self._reload()

    def _reload(self) -> None:
        self._rows = self._service.list_backups()
        self._table.setRowCount(len(self._rows))
        for r, b in enumerate(self._rows):
            values = [b.name, _ltr(_human_size(b.size_bytes)),
                      _ltr(b.modified.strftime("%Y-%m-%d %H:%M"))]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c in (1, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, c, item)
        self._count_label.setText(
            self.tr("{count} backups").format(count=len(self._rows))
            if self._rows else self.tr("No backups yet"))
        self._update_buttons()

    def _selected(self) -> BackupDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._rows[rows[0].row()]

    def _update_buttons(self) -> None:
        has = self._selected() is not None
        self._restore_btn.setEnabled(has)
        self._delete_btn.setEnabled(has)

    # -- actions ------------------------------------------------------------
    def _create(self) -> None:
        try:
            path = self._service.create_backup()
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Error"), str(exc))
            return
        self._reload()
        QMessageBox.information(self, self.tr("Backup created"),
                               self.tr("Backup saved to {path}").format(path=str(path)))

    def _create_to(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, self.tr("Select backup folder"))
        if not directory:
            return
        try:
            path = self._service.create_backup(Path(directory))
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Error"), str(exc))
            return
        self._reload()
        QMessageBox.information(self, self.tr("Backup created"),
                               self.tr("Backup saved to {path}").format(path=str(path)))

    def _restore(self) -> None:
        b = self._selected()
        if b is None:
            return
        confirm = QMessageBox.question(
            self, self.tr("Restore database?"),
            self.tr("This replaces all current data with the backup. "
                    "A safety copy is made first. Continue?"))
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.restore_backup(Path(b.path))
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Error"), str(exc))
            return
        self._reload()
        QMessageBox.information(
            self, self.tr("Restore complete"),
            self.tr("Restored. A safety copy of the previous data was saved."))

    def _delete(self) -> None:
        b = self._selected()
        if b is None:
            return
        confirm = QMessageBox.question(self, self.tr("Delete backup?"), b.name)
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.delete_backup(Path(b.path))
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Error"), str(exc))
            return
        self._reload()

    def _open_folder(self) -> None:
        self._service.backups_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._service.backups_dir)))

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Backup"))
        self._subtitle.setText(self.tr("Database backup and restore"))
        self._create_btn.setText(self.tr("Create backup"))
        self._create_to_btn.setText(self.tr("Backup to…"))
        self._restore_btn.setText(self.tr("Restore"))
        self._delete_btn.setText(self.tr("Delete"))
        self._open_btn.setText(self.tr("Open folder"))
        self._table.setHorizontalHeaderLabels([
            self.tr("File name"), self.tr("Size"), self.tr("Date")])
        if hasattr(self, "_rows"):
            self._count_label.setText(
                self.tr("{count} backups").format(count=len(self._rows))
                if self._rows else self.tr("No backups yet"))
