"""Patients module: searchable roster with add / edit / delete."""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mediflow.services.patient_service import PatientDTO
from mediflow.ui import icons
from mediflow.ui.dialogs.patient_dialog import PatientDialog
from mediflow.ui.views.base_view import BaseView

_GENDER_LABELS = {"male": "Male", "female": "Female", "other": "Other"}


class PatientsView(BaseView):
    required_permission = "patient.view"

    def build_ui(self) -> None:
        self._service = self.container.patients
        self._rows: list[PatientDTO] = []

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._reload)
        self._search.setMinimumWidth(280)
        toolbar.addWidget(self._search, stretch=1)

        self._edit_btn = QPushButton()
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.clicked.connect(self._edit_selected)
        self._delete_btn = QPushButton(objectName="Danger")
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.clicked.connect(self._delete_selected)
        self._new_btn = QPushButton(objectName="Primary")
        self._new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_btn.clicked.connect(self._create)
        toolbar.addWidget(self._edit_btn)
        toolbar.addWidget(self._delete_btn)
        toolbar.addWidget(self._new_btn)
        self._root.addLayout(toolbar)
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
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 150)
        self._table.doubleClicked.connect(lambda _i: self._edit_selected())
        self._table.itemSelectionChanged.connect(self._update_buttons)

        # Table and empty-state placeholder share the content area.
        self._area = QStackedWidget()
        self._area.addWidget(self._table)                 # index 0
        empty = QWidget()
        ev = QVBoxLayout(empty)
        ev.addStretch(1)
        self._empty_icon = QLabel()
        self._empty_icon.setPixmap(icons.pixmap("patients", 56, "#93a6ac"))
        self._empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_text = QLabel(objectName="Subtitle")
        self._empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ev.addWidget(self._empty_icon)
        ev.addSpacing(10)
        ev.addWidget(self._empty_text)
        ev.addStretch(2)
        self._area.addWidget(empty)                       # index 1
        self._root.addWidget(self._area, stretch=1)

        self._count_label = QLabel(objectName="Muted")
        self._root.addWidget(self._count_label)

    # -- data ---------------------------------------------------------------
    def on_activated(self) -> None:
        self._reload()

    def _reload(self, *_a) -> None:
        self._rows = self._service.search(self._search.text())
        self._table.setRowCount(len(self._rows))
        for r, p in enumerate(self._rows):
            gender = QCoreApplication.translate("PatientDialog",
                                                _GENDER_LABELS.get(p.gender, "Other"))
            age = "" if p.age_years is None else str(p.age_years)
            values = [p.mrn, p.full_name, gender, age, p.phone or "", p.province or ""]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c in (0, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, c, item)
        self._area.setCurrentIndex(0 if self._rows else 1)
        self._count_label.setText(self.tr("{count} patients").format(count=len(self._rows)))
        self._update_buttons()

    def _selected(self) -> PatientDTO | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._rows[rows[0].row()]

    def _update_buttons(self) -> None:
        has = self._selected() is not None
        self._edit_btn.setEnabled(has)
        self._delete_btn.setEnabled(has)

    # -- actions ------------------------------------------------------------
    def _create(self) -> None:
        dialog = PatientDialog(self._service, parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._reload()

    def _edit_selected(self) -> None:
        selected = self._selected()
        if selected is None:
            return
        detail = self._service.get(selected.id)  # includes decrypted national id
        dialog = PatientDialog(self._service, detail, parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._reload()

    def _delete_selected(self) -> None:
        selected = self._selected()
        if selected is None:
            return
        confirm = QMessageBox.question(
            self, self.tr("Delete patient?"),
            self.tr("Remove {name} from active records?").format(name=selected.full_name),
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._service.delete(selected.id)
            self._reload()

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Patients"))
        self._subtitle.setText(self.tr("Manage patient records"))
        self._search.setPlaceholderText(self.tr("Search by name, MRN or phone"))
        self._edit_btn.setText(self.tr("Edit"))
        self._delete_btn.setText(self.tr("Delete"))
        self._new_btn.setText(self.tr("New patient"))
        self._table.setHorizontalHeaderLabels([
            self.tr("MRN"), self.tr("Name"), self.tr("Gender"),
            self.tr("Age"), self.tr("Phone"), self.tr("Province"),
        ])
        self._empty_text.setText(self.tr("No patients found"))
        self._count_label.setText(self.tr("{count} patients").format(count=len(self._rows)))
