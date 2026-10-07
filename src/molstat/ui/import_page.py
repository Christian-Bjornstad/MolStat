from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QDate, QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QFileDialog, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QLayout, QLineEdit, QScrollArea,
    QVBoxLayout, QWidget,
)

from ..manual_import import ManualImportPlan
from ..modules import DEFAULT_UNITS, UnitRegistry
from .components import action_button, help_text, section_title, set_tone, status_tone


ROLE_LABELS = {
    "antall": "Antall",
    "resultater": "Resultater",
    "ekstraksjon": "Ekstraksjon",
    "backlog": "Full restanseliste",
    "current": "Prosess – valgt måned",
    "previous": "Prosess – forrige måned",
    "production_current": "Produksjon – valgt måned",
    "production_previous": "Produksjon – forrige måned",
    "macro_current": "Makro – valgt måned",
    "macro_previous": "Makro – forrige måned",
}


class ImportPage(QWidget):
    selection_changed = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("manual-import-page")
        self._busy = False
        self._displayed_context: tuple[str, str] | None = None
        self._drafts: dict[tuple[str, str], dict[str, str]] = {}
        self._roles: tuple[str, ...] = ()
        self._unit_names = {unit.key: unit.display_name for unit in DEFAULT_UNITS.active()}
        self._unit_profiles = {unit.key: unit.capability("statistics").processor_profile for unit in DEFAULT_UNITS.active()}
        today = QDate.currentDate()
        self._statistics_period = (QDate(today.year(), today.month(), 1), today)

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("manual-import-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("page-content")
        layout = QVBoxLayout(content)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        title = QLabel("Importer uttrekk")
        title.setObjectName("page-title")
        intro = help_text("Hent rapportene fra LVMS, og velg filene her. MolStat validerer uttrekkene og behandler dem med samme database og rapportoppsett som automatisk kjøring.")
        intro.setObjectName("page-intro")
        layout.addWidget(title)
        layout.addWidget(intro)

        self.form_container = QWidget()
        form_layout = QVBoxLayout(self.form_container)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(16)
        selection = QGroupBox("1. Velg enhet og periode")
        selection_form = QFormLayout(selection)
        selection_form.setSpacing(12)
        self.unit_combo = QComboBox()
        self.unit_combo.setObjectName("import-unit")
        self.unit_combo.setAccessibleName("Enhet for manuell import")
        self.unit_combo.setMinimumHeight(44)
        for unit in DEFAULT_UNITS.active():
            self.unit_combo.addItem(self._unit_names[unit.key], unit.key)
        self.job_combo = QComboBox()
        self.job_combo.setObjectName("import-job")
        self.job_combo.setAccessibleName("Rapporttype for manuell import")
        self.job_combo.setMinimumHeight(44)
        self.job_combo.addItem("Statistikk", "statistics")
        selection_form.addRow("Enhet", self.unit_combo)
        selection_form.addRow("Rapporttype", self.job_combo)
        dates = QHBoxLayout()
        self.from_date = _date_field("import-from", "Fra dato i LVMS-uttrekket", self._statistics_period[0])
        self.to_date = _date_field("import-to", "Til dato i LVMS-uttrekket", today)
        from_label = QLabel("Fra")
        from_label.setBuddy(self.from_date)
        to_label = QLabel("Til")
        to_label.setBuddy(self.to_date)
        dates.addWidget(from_label)
        dates.addWidget(self.from_date, 1)
        dates.addSpacing(12)
        dates.addWidget(to_label)
        dates.addWidget(self.to_date, 1)
        selection_form.addRow("Uttrekksperiode", dates)
        self.period_hint = help_text("")
        selection_form.addRow(self.period_hint)
        form_layout.addWidget(selection)

        files = QGroupBox("2. Velg rapportfiler")
        files_layout = QVBoxLayout(files)
        files_layout.setSpacing(12)
        files_layout.addWidget(help_text("Alle rapportrollene må ha en fil. Velg originale CSV-uttrekk med kolonneoverskrifter."))
        self.files_container = QWidget()
        self.file_form = QFormLayout(self.files_container)
        self.file_form.setContentsMargins(0, 0, 0, 0)
        self.file_form.setSpacing(12)
        self.file_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.file_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.file_fields: dict[str, QLineEdit] = {}
        files_layout.addWidget(self.files_container)
        form_layout.addWidget(files)
        form_layout.addWidget(help_text("Originalfilene beholdes. Validerte filer lagres i K-sensitiv før behandling."))
        layout.addWidget(self.form_container)
        self.feedback = help_text("Velg enhet, periode og alle rapportfilene før du starter.", name="import-feedback")
        self.feedback.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.import_button = action_button("Valider og importer", "start-manual-import",
                                           accessible_name="Valider og importer valgte LVMS-uttrekk", primary=True)
        layout.addStretch(1)
        scroll.setWidget(content)
        page_layout.addWidget(scroll, 1)
        footer = QWidget()
        footer.setObjectName("import-footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(28, 12, 28, 16)
        footer_layout.setSpacing(16)
        footer_layout.addWidget(self.feedback, 1)
        footer_layout.addWidget(self.import_button)
        page_layout.addWidget(footer)
        self.unit_combo.currentIndexChanged.connect(self._selection_updated)
        self.job_combo.currentIndexChanged.connect(self._selection_updated)
        self.from_date.dateChanged.connect(self._update_period_hint)
        self.to_date.dateChanged.connect(self._update_period_hint)
        self.set_roles(())
        self._configure_period()

    def set_enabled_units(self, keys: set[str]) -> None:
        self._remember_files()
        selected = self.unit_combo.currentData()
        blocker = QSignalBlocker(self.unit_combo)
        self.unit_combo.clear()
        for unit in DEFAULT_UNITS.active():
            if unit.key in keys:
                self.unit_combo.addItem(self._unit_names[unit.key], unit.key)
        index = self.unit_combo.findData(selected)
        self.unit_combo.setCurrentIndex(index if index >= 0 else 0)
        del blocker
        self._selection_updated()

    def set_definitions(self, units: UnitRegistry) -> None:
        for unit in units:
            self._unit_names[unit.key] = unit.display_name
            if unit.status == "active":
                self._unit_profiles[unit.key] = unit.capability("statistics").processor_profile
            index = self.unit_combo.findData(unit.key)
            if index >= 0:
                self.unit_combo.setItemText(index, unit.display_name)
        self._update_period_hint()

    def set_available_jobs(self, jobs: tuple[str, ...]) -> None:
        selected = self.job_combo.currentData()
        blocker = QSignalBlocker(self.job_combo)
        self.job_combo.clear()
        for kind in jobs:
            self.job_combo.addItem({"statistics": "Statistikk", "backlog": "Restanse"}.get(kind, kind), kind)
        index = self.job_combo.findData(selected)
        self.job_combo.setCurrentIndex(index if index >= 0 else 0)
        del blocker
        self._configure_period()
        self._refresh_controls()

    def set_roles(self, roles: tuple[str, ...]) -> None:
        context = self._context()
        if roles == self._roles and context == self._displayed_context:
            return
        self._remember_files()
        while self.file_form.rowCount():
            self.file_form.removeRow(0)
        self.file_fields = {}
        self._roles = roles
        self._displayed_context = context
        draft = self._drafts.get(context, {})
        for role in roles:
            name = ROLE_LABELS.get(role, role)
            field = QLineEdit()
            field.setObjectName(f"import-file-{role}")
            field.setAccessibleName(f"CSV-fil for {name}")
            field.setPlaceholderText("Velg CSV-uttrekk …")
            field.setMinimumHeight(44)
            field.setText(draft.get(role, ""))
            field.textChanged.connect(lambda _text="", target=field: set_tone(target, "neutral"))
            browse = action_button("Velg fil …", f"browse-import-{role}",
                                   accessible_name=f"Velg CSV-fil for {name}")
            browse.clicked.connect(lambda _checked=False, target=field, label=name: self._choose_file(target, label))
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            row_layout.addWidget(field, 1)
            row_layout.addWidget(browse)
            self.file_fields[role] = field
            self.file_form.addRow(name, row)
        if not roles:
            self.file_form.addRow(help_text("Velg en aktiv enhet med et gyldig rapportoppsett."))
        self._refresh_controls()

    def get_plan(self) -> ManualImportPlan:
        unit_key, job_kind = self._context()
        if not unit_key or not job_kind or not self._roles:
            raise ValueError("Velg en aktiv enhet og rapporttype før import.")
        date_from = self.from_date.date().toPyDate()
        date_to = self.to_date.date().toPyDate()
        if date_from > date_to:
            raise ValueError("Fra-dato kan ikke være etter til-dato.")
        missing = [role for role, field in self.file_fields.items() if not field.text().strip()]
        if missing:
            for role in missing:
                set_tone(self.file_fields[role], "danger")
            first = self.file_fields[missing[0]]
            first.setFocus()
            raise ValueError("Velg fil for: " + ", ".join(ROLE_LABELS.get(role, role) for role in missing) + ".")
        paths = {role: Path(field.text().strip()) for role, field in self.file_fields.items()}
        for role, path in paths.items():
            if not path.is_file():
                set_tone(self.file_fields[role], "danger")
                self.file_fields[role].setFocus()
                raise ValueError(f"Filen for «{ROLE_LABELS.get(role, role)}» finnes ikke eller kan ikke leses.")
        self._remember_files()
        return ManualImportPlan(unit_key, job_kind, date_from, date_to, paths)

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.form_container.setEnabled(not busy)
        self.import_button.setText("Importerer …" if busy else "Valider og importer")
        if busy:
            self.set_result("Pågår", "Validerer rapportfiler og behandler data …")
        self._refresh_controls()

    def set_result(self, state: str, text: str) -> None:
        self.feedback.setText(f"{state}: {text}" if state else text)
        set_tone(self.feedback, status_tone(state))

    def set_feedback(self, state: str, text: str) -> None:
        self.set_result(state, text)

    def _context(self) -> tuple[str, str]:
        return self.unit_combo.currentData() or "", self.job_combo.currentData() or ""

    def _remember_files(self) -> None:
        if self._displayed_context is not None:
            self._drafts[self._displayed_context] = {role: field.text() for role, field in self.file_fields.items()}

    def _selection_updated(self) -> None:
        self._remember_files()
        self._configure_period()
        self.selection_changed.emit(*self._context())
        self._refresh_controls()

    def _configure_period(self) -> None:
        backlog = self.job_combo.currentData() == "backlog"
        if backlog:
            if self.from_date.isEnabled():
                self._statistics_period = self.from_date.date(), self.to_date.date()
            self.from_date.setDate(QDate(2024, 1, 1))
            self.to_date.setDate(QDate.currentDate())
        elif not self.from_date.isEnabled():
            self.from_date.setDate(self._statistics_period[0])
            self.to_date.setDate(self._statistics_period[1])
        self.from_date.setEnabled(not backlog)
        self.to_date.setEnabled(not backlog)
        self._update_period_hint()

    def _update_period_hint(self) -> None:
        if self.job_combo.currentData() == "backlog":
            self.period_hint.setText("Restanse krever en komplett liste fra 01.01.2024 til i dag. Perioden er låst for å unngå at et deluttrekk erstatter restansestatus.")
        elif self._unit_profiles.get(self.unit_combo.currentData()) == "lege":
            previous = self.from_date.date().addMonths(-1)
            start = QDate(previous.year(), previous.month(), 1)
            end = QDate(previous.year(), previous.month(), previous.daysInMonth())
            self.period_hint.setText(
                "Velg perioden fra første dag innen én måned. Rapportene merket «forrige måned» skal dekke "
                f"{start.toString('dd.MM.yyyy')}–{end.toString('dd.MM.yyyy')}."
            )
        else:
            self.period_hint.setText("Datoene skal være de samme som perioden du valgte i LVMS. Historiske perioder kan også importeres.")

    def _refresh_controls(self) -> None:
        self.import_button.setEnabled(bool(self._roles and all(self._context())) and not self._busy)

    def _choose_file(self, field: QLineEdit, role: str) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, f"Velg uttrekk: {role}", field.text(), "CSV-uttrekk (*.csv);;Alle filer (*)")
        if selected:
            field.setText(selected)


def _date_field(name: str, accessible_name: str, value: QDate) -> QDateEdit:
    field = QDateEdit(value)
    field.setObjectName(name)
    field.setAccessibleName(accessible_name)
    field.setMinimumHeight(44)
    field.setCalendarPopup(True)
    field.setDisplayFormat("dd.MM.yyyy")
    field.setMaximumDate(QDate.currentDate())
    return field
