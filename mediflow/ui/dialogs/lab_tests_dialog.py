"""Manage the laboratory test catalogue: list, add and remove tests."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.exceptions import MediFlowError
from mediflow.services.lab_service import LabService, LabTestInput


class LabTestsDialog(QDialog):
    def __init__(self, lab: LabService, parent: QWidget | None = None):
        super().__init__(parent)
        self._lab = lab
        self.setModal(True)
        self.setMinimumWidth(520)
        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(12)

        self._title = QLabel(self.tr("Manage tests"), objectName="PageTitle")
        root.addWidget(self._title)

        self._list = QListWidget()
        self._list.setFixedHeight(180)
        root.addWidget(self._list)

        remove_row = QHBoxLayout()
        remove_row.addStretch(1)
        self._remove = QPushButton(self.tr("Remove"), objectName="Danger")
        self._remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove.clicked.connect(self._remove_selected)
        remove_row.addWidget(self._remove)
        root.addLayout(remove_row)

        form = QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._name = QLineEdit()
        self._code = QLineEdit()
        self._sample = QLineEdit()
        self._range = QLineEdit()
        self._unit = QLineEdit()
        form.addRow(self.tr("Name"), self._name)
        form.addRow(self.tr("Code"), self._code)
        form.addRow(self.tr("Sample type"), self._sample)
        form.addRow(self.tr("Reference range"), self._range)
        form.addRow(self.tr("Unit"), self._unit)
        root.addLayout(form)

        buttons = QHBoxLayout()
        self._add = QPushButton(self.tr("Add"), objectName="Primary")
        self._add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add.clicked.connect(self._add_test)
        buttons.addWidget(self._add)
        buttons.addStretch(1)
        self._close = QPushButton(self.tr("Close"))
        self._close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close.clicked.connect(self.accept)
        buttons.addWidget(self._close)
        root.addLayout(buttons)

        self.setWindowTitle(self.tr("Manage tests"))

    def _reload(self) -> None:
        self._list.clear()
        for t in self._lab.list_tests(active_only=False):
            parts = [t.name]
            if t.code:
                parts.append(f"({t.code})")
            if t.sample_type:
                parts.append(f"· {t.sample_type}")
            item = QListWidgetItem(" ".join(parts))
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            self._list.addItem(item)

    def _add_test(self) -> None:
        try:
            self._lab.create_test(LabTestInput(
                name=self._name.text(), code=self._code.text(),
                sample_type=self._sample.text(), reference_range=self._range.text(),
                unit=self._unit.text(),
            ))
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("Add test"), str(exc))
            return
        for field in (self._name, self._code, self._sample, self._range, self._unit):
            field.clear()
        self._reload()

    def _remove_selected(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        self._lab.delete_test(item.data(Qt.ItemDataRole.UserRole))
        self._reload()
