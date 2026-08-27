"""Medical Records module: a patient's allergies, problem list and history."""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mediflow.core.constants import AppointmentStatus
from mediflow.services.patient_service import PatientDTO
from mediflow.ui import icons
from mediflow.ui.dialogs.allergy_dialog import AllergyDialog
from mediflow.ui.dialogs.condition_dialog import ConditionDialog
from mediflow.ui.views.base_view import BaseView

_GENDER_LABELS = {"male": "Male", "female": "Female", "other": "Other"}
_STATUS_LABELS = {
    AppointmentStatus.BOOKED.value: "Booked",
    AppointmentStatus.CHECKED_IN.value: "Checked in",
    AppointmentStatus.IN_CONSULTATION.value: "In consultation",
    AppointmentStatus.COMPLETED.value: "Completed",
    AppointmentStatus.CANCELLED.value: "Cancelled",
    AppointmentStatus.NO_SHOW.value: "No show",
    AppointmentStatus.WAITLISTED.value: "Waitlisted",
}


def _ltr(text: str) -> str:
    """Wrap codes/numbers in Left-to-Right marks so RTL doesn't reorder them."""
    return f"‎{text}‎" if text else text


class MedicalRecordsView(BaseView):
    required_permission = "emr.view"

    def build_ui(self) -> None:
        self._records = self.container.medical_records
        self._patients = self.container.patients
        self._appointments = self.container.appointments
        self._patient: PatientDTO | None = None

        head = QVBoxLayout()
        head.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        head.addWidget(self._title)
        head.addWidget(self._subtitle)
        self._root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(16)

        # -- left: patient picker ------------------------------------------
        left = QVBoxLayout()
        left.setSpacing(10)
        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._search_patients)
        left.addWidget(self._search)
        self._patient_list = QListWidget()
        self._patient_list.itemClicked.connect(self._pick_patient)
        left.addWidget(self._patient_list, stretch=1)
        left_container = QWidget()
        left_container.setFixedWidth(300)
        left_container.setLayout(left)
        body.addWidget(left_container)

        # -- right: empty-state or record detail ---------------------------
        self._right = QStackedWidget()

        empty_page = QWidget()
        ep = QVBoxLayout(empty_page)
        ep.addStretch(1)
        self._empty = QLabel(objectName="Muted")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ep.addWidget(self._empty)
        ep.addStretch(2)
        self._right.addWidget(empty_page)

        self._detail = self._build_detail()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self._detail)
        self._right.addWidget(scroll)

        body.addWidget(self._right, stretch=1)
        self._root.addLayout(body, stretch=1)

    def _build_detail(self) -> QWidget:
        detail = QWidget()
        layout = QVBoxLayout(detail)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # summary card
        self._summary_card = QFrame(objectName="Card")
        sc = QVBoxLayout(self._summary_card)
        sc.setContentsMargins(20, 16, 20, 16)
        sc.setSpacing(6)
        self._name_label = QLabel(objectName="PageTitle")
        self._facts_label = QLabel(objectName="Muted")
        self._facts_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        sc.addWidget(self._name_label)
        sc.addWidget(self._facts_label)
        layout.addWidget(self._summary_card)

        self._allergy_list = QListWidget()
        self._allergy_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._allergy_section, self._allergy_add, self._allergy_del, self._allergy_title = \
            self._section(self._allergy_list)
        self._allergy_add.clicked.connect(self._add_allergy)
        self._allergy_del.clicked.connect(self._remove_allergy)
        icons.apply_button_icon(self._allergy_add, "plus")
        icons.apply_button_icon(self._allergy_del, "trash")
        layout.addWidget(self._allergy_section)

        self._condition_list = QListWidget()
        self._condition_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._condition_section, self._condition_add, self._condition_del, self._condition_title = \
            self._section(self._condition_list)
        self._condition_add.clicked.connect(self._add_condition)
        self._condition_del.clicked.connect(self._remove_condition)
        icons.apply_button_icon(self._condition_add, "plus")
        icons.apply_button_icon(self._condition_del, "trash")
        layout.addWidget(self._condition_section)

        # recent appointments
        self._history_card = QFrame(objectName="Card")
        hc = QVBoxLayout(self._history_card)
        hc.setContentsMargins(18, 14, 18, 16)
        hc.setSpacing(10)
        self._history_title = QLabel(objectName="Subtitle")
        hc.addWidget(self._history_title)
        self._history = QTableWidget(0, 3)
        self._history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._history.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._history.verticalHeader().setVisible(False)
        self._history.horizontalHeader().setStretchLastSection(True)
        self._history.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._history.setMaximumHeight(220)
        hc.addWidget(self._history)
        layout.addWidget(self._history_card)
        layout.addStretch(1)
        return detail

    def _section(self, list_widget: QListWidget):
        card = QFrame(objectName="Card")
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel(objectName="Subtitle")
        header.addWidget(title)
        header.addStretch(1)
        add_btn = QPushButton(objectName="Ghost")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn = QPushButton(objectName="Danger")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        header.addWidget(add_btn)
        header.addWidget(del_btn)
        v.addLayout(header)
        list_widget.setMaximumHeight(150)
        v.addWidget(list_widget)
        return card, add_btn, del_btn, title

    # -- patient selection --------------------------------------------------
    def on_activated(self) -> None:
        self._search_patients("")
        if self._patient is None:
            self._show_empty()

    def _search_patients(self, _text: str) -> None:
        results = self._patients.search(self._search.text(), limit=50)
        self._patient_list.clear()
        for p in results:
            item = QListWidgetItem(f"{p.full_name}  ·  {p.mrn}")
            item.setData(Qt.ItemDataRole.UserRole, p)
            self._patient_list.addItem(item)

    def _pick_patient(self, item: QListWidgetItem) -> None:
        self._patient = item.data(Qt.ItemDataRole.UserRole)
        self._right.setCurrentIndex(1)
        self._load_record()

    def _show_empty(self) -> None:
        self._right.setCurrentIndex(0)

    # -- record loading -----------------------------------------------------
    def _load_record(self) -> None:
        p = self._patient
        if p is None:
            return
        self._name_label.setText(p.full_name)
        gender = QCoreApplication.translate("PatientDialog", _GENDER_LABELS.get(p.gender, "Other"))
        age = "" if p.age_years is None else str(p.age_years)
        blood = "" if p.blood_group == "unknown" else p.blood_group
        facts = [
            f"MRN {_ltr(p.mrn)}",
            f"{self.tr('Age')} {age}" if age else "",
            gender,
            _ltr(blood),
            _ltr(p.phone or ""),
        ]
        self._facts_label.setText("   ·   ".join(f for f in facts if f))
        self._reload_allergies()
        self._reload_conditions()
        self._reload_history()

    def _reload_allergies(self) -> None:
        self._allergy_list.clear()
        rows = self._records.list_allergies(self._patient.id)
        for a in rows:
            parts = [a.substance]
            if a.severity:
                parts.append(f"({a.severity})")
            if a.reaction:
                parts.append(f"— {a.reaction}")
            item = QListWidgetItem(" ".join(parts))
            item.setData(Qt.ItemDataRole.UserRole, a.id)
            self._allergy_list.addItem(item)
        if not rows:
            self._allergy_list.addItem(self.tr("None recorded"))

    def _reload_conditions(self) -> None:
        self._condition_list.clear()
        rows = self._records.list_conditions(self._patient.id)
        for c in rows:
            parts = [c.name]
            if c.icd10_code:
                parts.append(f"[{_ltr(c.icd10_code)}]")
            if c.is_chronic:
                parts.append(f"· {self.tr('Chronic')}")
            item = QListWidgetItem(" ".join(parts))
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            self._condition_list.addItem(item)
        if not rows:
            self._condition_list.addItem(self.tr("None recorded"))

    def _reload_history(self) -> None:
        rows = self._appointments.list_for_patient(self._patient.id, limit=25)
        self._history.setRowCount(len(rows))
        for r, a in enumerate(rows):
            values = [
                _ltr(a.scheduled_start.strftime("%Y-%m-%d")),
                a.reason or "",
                self.tr(_STATUS_LABELS.get(a.status, a.status)),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c in (0, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._history.setItem(r, c, item)

    # -- actions ------------------------------------------------------------
    def _add_allergy(self) -> None:
        if self._patient is None:
            return
        dialog = AllergyDialog(self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            substance, severity, reaction = dialog.collected()
            self._records.add_allergy(self._patient.id, substance, severity, reaction)
            self._reload_allergies()

    def _remove_allergy(self) -> None:
        item = self._allergy_list.currentItem()
        if item is None:
            return
        allergy_id = item.data(Qt.ItemDataRole.UserRole)
        if allergy_id is not None:
            self._records.delete_allergy(allergy_id)
            self._reload_allergies()

    def _add_condition(self) -> None:
        if self._patient is None:
            return
        dialog = ConditionDialog(self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._records.add_condition(self._patient.id, **dialog.collected())
            self._reload_conditions()

    def _remove_condition(self) -> None:
        item = self._condition_list.currentItem()
        if item is None:
            return
        condition_id = item.data(Qt.ItemDataRole.UserRole)
        if condition_id is not None:
            self._records.delete_condition(condition_id)
            self._reload_conditions()

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Medical Records"))
        self._subtitle.setText(self.tr("Patient clinical history"))
        self._search.setPlaceholderText(self.tr("Search patient by name, MRN or phone"))
        self._empty.setText(self.tr("Select a patient to view their record."))
        self._allergy_title.setText(self.tr("Allergies"))
        self._condition_title.setText(self.tr("Conditions"))
        self._history_title.setText(self.tr("Recent appointments"))
        for btn in (self._allergy_add, self._condition_add):
            btn.setText(self.tr("Add"))
        for btn in (self._allergy_del, self._condition_del):
            btn.setText(self.tr("Remove"))
        self._history.setHorizontalHeaderLabels([
            self.tr("Date"), self.tr("Reason"), self.tr("Status"),
        ])
        if self._patient is not None:
            self._load_record()
