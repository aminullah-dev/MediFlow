"""Create a laboratory test request for a patient."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
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
from mediflow.data.database import current_user_id
from mediflow.services.lab_service import LabService
from mediflow.services.patient_service import PatientDTO, PatientService


class LabRequestDialog(QDialog):
    def __init__(self, patients: PatientService, lab: LabService,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._patients = patients
        self._lab = lab
        self._selected: PatientDTO | None = None
        self.setModal(True)
        self.setMinimumWidth(520)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame(objectName="Card")
        outer.addWidget(card)
        root = QVBoxLayout(card)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(12)

        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._search_patients)
        root.addWidget(self._search)
        self._results = QListWidget()
        self._results.setFixedHeight(120)
        self._results.itemClicked.connect(self._pick_patient)
        root.addWidget(self._results)
        self._selected_label = QLabel(objectName="Badge")
        self._selected_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._selected_label.setVisible(False)
        root.addWidget(self._selected_label)

        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._test = QComboBox()
        for t in self._lab.list_tests():
            label = t.name if not t.code else f"{t.name} ({t.code})"
            self._test.addItem(label, t.id)
        form.addRow(self.tr("Test"), self._test)
        root.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(self.tr("Cancel"))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        create = QPushButton(self.tr("Create"), objectName="Primary")
        create.setCursor(Qt.CursorShape.PointingHandCursor)
        create.clicked.connect(self._on_create)
        buttons.addWidget(cancel)
        buttons.addWidget(create)
        root.addLayout(buttons)

        self.setWindowTitle(self.tr("New request"))
        self._search.setPlaceholderText(self.tr("Search patient by name, MRN or phone"))
        self._search_patients("")

    def _search_patients(self, _text: str) -> None:
        self._results.clear()
        for p in self._patients.search(self._search.text(), limit=25):
            item = QListWidgetItem(f"{p.full_name}  ·  {p.mrn}")
            item.setData(Qt.ItemDataRole.UserRole, p)
            self._results.addItem(item)

    def _pick_patient(self, item: QListWidgetItem) -> None:
        self._selected = item.data(Qt.ItemDataRole.UserRole)
        self._selected_label.setVisible(True)
        self._selected_label.setText(
            self.tr("Selected: {name}").format(name=self._selected.full_name))

    def _on_create(self) -> None:
        if self._selected is None:
            QMessageBox.warning(self, self.tr("New request"), self.tr("Select a patient first."))
            return
        if self._test.currentData() is None:
            return
        try:
            self._lab.create_request(self._selected.id, self._test.currentData(),
                                     requested_by_id=current_user_id.get())
        except MediFlowError as exc:
            QMessageBox.warning(self, self.tr("New request"), str(exc))
            return
        self.accept()
