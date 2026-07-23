"""Reports module: aggregate analytics with Excel export."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mediflow.services.report_service import REPORTS, ReportResult, export_excel
from mediflow.ui import icons
from mediflow.ui.views.base_view import BaseView


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"‎{value:.2f}‎"
    return f"‎{value}‎"


class _Metric(QFrame):
    def __init__(self, caption: str, value: str):
        super().__init__(objectName="StatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)
        v = QLabel(value, objectName="StatValue")
        c = QLabel(caption, objectName="StatCaption")
        layout.addWidget(v)
        layout.addWidget(c)


class ReportsView(BaseView):
    required_permission = "report.view"

    def build_ui(self) -> None:
        self._service = self.container.reports
        self._result: ReportResult | None = None

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(16)

        self._list = QListWidget()
        self._list.setFixedWidth(240)
        self._list.currentRowChanged.connect(self._on_select)
        body.addWidget(self._list)

        right = QVBoxLayout()
        right.setSpacing(12)
        self._report_title = QLabel(objectName="PageTitle")
        right.addWidget(self._report_title)

        self._metrics_host = QWidget()
        self._metrics_layout = QGridLayout(self._metrics_host)
        self._metrics_layout.setContentsMargins(0, 0, 0, 0)
        self._metrics_layout.setSpacing(12)
        right.addWidget(self._metrics_host)

        self._table = QTableWidget(0, 0)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        right.addWidget(self._table, stretch=1)

        export_row = QHBoxLayout()
        export_row.addStretch(1)
        self._export_btn = QPushButton(objectName="Primary")
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.clicked.connect(self._export)
        icons.apply_button_icon(self._export_btn, "download")
        export_row.addWidget(self._export_btn)
        right.addLayout(export_row)

        body.addLayout(right, stretch=1)
        self._root.addLayout(body, stretch=1)

    # -- data ---------------------------------------------------------------
    def on_activated(self) -> None:
        if self._list.count() and self._list.currentRow() >= 0:
            self._on_select(self._list.currentRow())

    def _populate_list(self) -> None:
        current = self._list.currentRow()
        self._list.blockSignals(True)
        self._list.clear()
        for key, title in REPORTS:
            item = QListWidgetItem(self.tr(title))
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._list.addItem(item)
        self._list.setCurrentRow(current if current >= 0 else 0)
        self._list.blockSignals(False)

    def _on_select(self, row: int) -> None:
        if row < 0 or row >= self._list.count():
            return
        key = self._list.item(row).data(Qt.ItemDataRole.UserRole)
        self._result = self._service.generate(key)
        self._render()

    def _render(self) -> None:
        r = self._result
        if r is None:
            return
        self._report_title.setText(self.tr(r.title))

        while self._metrics_layout.count():
            item = self._metrics_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, (label, value) in enumerate(r.summary):
            self._metrics_layout.addWidget(_Metric(self.tr(label), _fmt(value)), i // 4, i % 4)

        self._table.setVisible(bool(r.columns))
        if r.columns:
            self._table.setColumnCount(len(r.columns))
            self._table.setHorizontalHeaderLabels([self.tr(c) for c in r.columns])
            self._table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Stretch)
            self._table.setRowCount(len(r.rows))
            for ri, row in enumerate(r.rows):
                for ci, value in enumerate(row):
                    item = QTableWidgetItem(value)
                    if ci > 0:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._table.setItem(ri, ci, item)

    # -- export -------------------------------------------------------------
    def _export(self) -> None:
        if self._result is None:
            return
        r = self._result
        summary_labels = {label: self.tr(label) for label, _v in r.summary}
        column_labels = {c: self.tr(c) for c in r.columns}
        try:
            path = export_excel(
                r, self.container.config.paths.documents,
                title=self.tr(r.title), summary_labels=summary_labels,
                column_labels=column_labels,
            )
        except Exception as exc:  # pragma: no cover - surfaced to the user
            QMessageBox.warning(self, self.tr("Export"), str(exc))
            return
        QMessageBox.information(self, self.tr("Export"),
                                self.tr("Exported to {path}").format(path=str(path)))

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Reports"))
        self._subtitle.setText(self.tr("Analytics and exports"))
        self._export_btn.setText(self.tr("Export to Excel"))
        self._populate_list()
        if self._result is not None:
            self._render()
