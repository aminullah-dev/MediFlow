"""Pharmacy module: medication inventory with stock and dispensing."""
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

from mediflow.services.pharmacy_service import MedicationDTO
from mediflow.ui.dialogs.medication_dialog import MedicationDialog
from mediflow.ui.dialogs.stock_dialog import DispenseDialog, StockDialog
from mediflow.ui import icons, widgets
from mediflow.ui.views.base_view import BaseView


def _ltr(text: str) -> str:
    return f"‎{text}‎" if text else text


class PharmacyView(BaseView):
    required_permission = "pharmacy.view"

    def build_ui(self) -> None:
        self._service = self.container.pharmacy
        self._rows: list[MedicationDTO] = []

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
        self._edit_btn = self._tool_button(self._edit_selected)
        self._stock_btn = self._tool_button(self._add_stock, primary=False)
        self._dispense_btn = self._tool_button(self._dispense)
        self._delete_btn = self._tool_button(self._delete_selected, danger=True)
        self._new_btn = self._tool_button(self._create, primary=True)
        for b in (self._edit_btn, self._stock_btn, self._dispense_btn,
                  self._delete_btn, self._new_btn):
            toolbar.addWidget(b)
        self._root.addLayout(toolbar)
        icons.apply_button_icon(self._edit_btn, "pencil")
        icons.apply_button_icon(self._stock_btn, "arrow-down")
        icons.apply_button_icon(self._dispense_btn, "arrow-up")
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
        self._area, self._empty_text = widgets.table_with_empty_state(self._table, "pharmacy")
        self._root.addWidget(self._area, stretch=1)

        self._count_label = QLabel(objectName="Muted")
        self._root.addWidget(self._count_label)

    def _tool_button(self, slot, *, primary: bool = False, danger: bool = False) -> QPushButton:
        name = "Primary" if primary else ("Danger" if danger else "")
        btn = QPushButton(objectName=name)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        return btn

    # -- data ---------------------------------------------------------------
    def on_activated(self) -> None:
        self._reload()

    def _reload(self, *_a) -> None:
        self._rows = self._service.list_medications(self._search.text())
        self._table.setRowCount(len(self._rows))
        for r, m in enumerate(self._rows):
            status, colour = self._status(m)
            values = [
                m.name,
                m.form or "",
                _ltr(m.strength or ""),
                str(m.stock_on_hand),
                str(m.reorder_level),
                status,
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c in (3, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 5 and colour is not None:
                    item.setForeground(QColor(colour))
                self._table.setItem(r, c, item)
        self._area.setCurrentIndex(0 if self._rows else 1)
        self._count_label.setText(self.tr("{count} medications").format(count=len(self._rows)))
        self._update_buttons()

    def _status(self, m: MedicationDTO) -> tuple[str, str | None]:
        if m.is_out:
            return self.tr("Out of stock"), "#dc2626"
        if m.is_expiring:
            return self.tr("Expiring"), "#d98324"
        if m.is_low:
            return self.tr("Low"), "#d98324"
        return self.tr("OK"), "#16a34a"

    def _selected(self) -> MedicationDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._rows[rows[0].row()]

    def _update_buttons(self) -> None:
        has = self._selected() is not None
        for b in (self._edit_btn, self._stock_btn, self._dispense_btn, self._delete_btn):
            b.setEnabled(has)

    # -- actions ------------------------------------------------------------
    def _create(self) -> None:
        if MedicationDialog(self._service, parent=self).exec():
            self._reload()

    def _edit_selected(self) -> None:
        m = self._selected()
        if m and MedicationDialog(self._service, m, parent=self).exec():
            self._reload()

    def _add_stock(self) -> None:
        m = self._selected()
        if m and StockDialog(self._service, m, parent=self).exec():
            self._reload()

    def _dispense(self) -> None:
        m = self._selected()
        if m and DispenseDialog(self._service, m, parent=self).exec():
            self._reload()

    def _delete_selected(self) -> None:
        m = self._selected()
        if m is None:
            return
        confirm = QMessageBox.question(
            self, self.tr("Delete medication?"),
            self.tr("Remove {name} from the catalogue?").format(name=m.name),
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._service.delete(m.id)
            self._reload()

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Pharmacy"))
        self._subtitle.setText(self.tr("Medication inventory"))
        self._search.setPlaceholderText(self.tr("Search by name, generic or barcode"))
        self._edit_btn.setText(self.tr("Edit"))
        self._stock_btn.setText(self.tr("Add stock"))
        self._dispense_btn.setText(self.tr("Dispense"))
        self._delete_btn.setText(self.tr("Delete"))
        self._new_btn.setText(self.tr("New medication"))
        self._table.setHorizontalHeaderLabels([
            self.tr("Medication"), self.tr("Form"), self.tr("Strength"),
            self.tr("Stock"), self.tr("Reorder"), self.tr("Status"),
        ])
        self._empty_text.setText(self.tr("No medications found"))
        self._count_label.setText(self.tr("{count} medications").format(count=len(self._rows)))
