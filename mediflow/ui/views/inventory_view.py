"""Inventory module: supplies and consumables with stock movements."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from mediflow.services.inventory_service import InventoryItemDTO
from mediflow.ui import icons, widgets
from mediflow.ui.dialogs.inventory_item_dialog import InventoryItemDialog
from mediflow.ui.dialogs.movement_dialog import MovementDialog
from mediflow.ui.views.base_view import BaseView


class InventoryView(BaseView):
    required_permission = "inventory.view"

    def build_ui(self) -> None:
        self._service = self.container.inventory
        self._rows: list[InventoryItemDTO] = []

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._reload)
        toolbar.addWidget(self._search, stretch=1)
        self._in_btn = self._button(self._stock_in, primary=True)
        self._out_btn = self._button(self._stock_out)
        self._edit_btn = self._button(self._edit_selected)
        self._delete_btn = self._button(self._delete_selected, danger=True)
        self._new_btn = self._button(self._create, primary=True)
        for b in (self._in_btn, self._out_btn, self._edit_btn, self._delete_btn, self._new_btn):
            toolbar.addWidget(b)
        self._root.addLayout(toolbar)
        icons.apply_button_icon(self._in_btn, "arrow-down")
        icons.apply_button_icon(self._out_btn, "arrow-up")
        icons.apply_button_icon(self._edit_btn, "pencil")
        icons.apply_button_icon(self._delete_btn, "trash")
        icons.apply_button_icon(self._new_btn, "plus")

        self._table = QTableWidget(0, 6)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.doubleClicked.connect(lambda _i: self._edit_selected())
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._area, self._empty_text = widgets.table_with_empty_state(self._table, "inventory")
        self._root.addWidget(self._area, stretch=1)

        self._count_label = QLabel(objectName="Muted")
        self._root.addWidget(self._count_label)

    def _button(self, slot, *, primary=False, danger=False) -> QPushButton:
        name = "Primary" if primary else ("Danger" if danger else "")
        btn = QPushButton(objectName=name)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        return btn

    # -- data ---------------------------------------------------------------
    def on_activated(self) -> None:
        self._reload()

    def _reload(self, *_a) -> None:
        self._rows = self._service.list_items(self._search.text())
        self._table.setRowCount(len(self._rows))
        for r, i in enumerate(self._rows):
            status, colour = self._status(i)
            values = [i.name, i.category or "", i.unit, str(i.quantity),
                      str(i.reorder_level), status]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c in (3, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 5 and colour:
                    item.setForeground(QColor(colour))
                self._table.setItem(r, c, item)
        self._area.setCurrentIndex(0 if self._rows else 1)
        self._count_label.setText(self.tr("{count} items").format(count=len(self._rows)))
        self._update_buttons()

    def _status(self, i: InventoryItemDTO) -> tuple[str, str | None]:
        if i.is_out:
            return self.tr("Out of stock"), "#dc2626"
        if i.is_low:
            return self.tr("Low"), "#d98324"
        return self.tr("OK"), "#16a34a"

    def _selected(self) -> InventoryItemDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._rows[rows[0].row()]

    def _update_buttons(self) -> None:
        has = self._selected() is not None
        for b in (self._in_btn, self._out_btn, self._edit_btn, self._delete_btn):
            b.setEnabled(has)

    # -- actions ------------------------------------------------------------
    def _create(self) -> None:
        if InventoryItemDialog(self._service, parent=self).exec():
            self._reload()

    def _edit_selected(self) -> None:
        i = self._selected()
        if i and InventoryItemDialog(self._service, i, parent=self).exec():
            self._reload()

    def _stock_in(self) -> None:
        i = self._selected()
        if i and MovementDialog(self._service, i, incoming=True, parent=self).exec():
            self._reload()

    def _stock_out(self) -> None:
        i = self._selected()
        if i and MovementDialog(self._service, i, incoming=False, parent=self).exec():
            self._reload()

    def _delete_selected(self) -> None:
        i = self._selected()
        if i is None:
            return
        confirm = QMessageBox.question(
            self, self.tr("Delete item?"),
            self.tr("Remove {name} from inventory?").format(name=i.name),
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._service.delete(i.id)
            self._reload()

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Inventory"))
        self._subtitle.setText(self.tr("Supplies and consumables"))
        self._search.setPlaceholderText(self.tr("Search by name, category or code"))
        self._in_btn.setText(self.tr("Stock in"))
        self._out_btn.setText(self.tr("Stock out"))
        self._edit_btn.setText(self.tr("Edit"))
        self._delete_btn.setText(self.tr("Delete"))
        self._new_btn.setText(self.tr("New item"))
        self._table.setHorizontalHeaderLabels([
            self.tr("Item"), self.tr("Category"), self.tr("Unit"),
            self.tr("Quantity"), self.tr("Reorder"), self.tr("Status"),
        ])
        self._empty_text.setText(self.tr("No items found"))
        self._count_label.setText(self.tr("{count} items").format(count=len(self._rows)))
