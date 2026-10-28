from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QUrl, QTime
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QLayout, QLineEdit, QListWidget, QListWidgetItem, QScrollArea,
    QStackedWidget, QTabWidget, QTimeEdit, QVBoxLayout, QWidget,
)

from ..modules import DEFAULT_UNITS, UnitDefinition, UnitRegistry
from ..unit_settings import load_unit_file, load_backlog_file
from .components import action_button, help_text, section_title, set_tone


class UnitSettingsPanel(QWidget):
    """One unit's draft. Changing the selection does not discard its fields."""

    def __init__(self, unit: UnitDefinition) -> None:
        super().__init__()
        self.unit = unit
        self.setObjectName(f"unit-settings-{unit.key}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        self.heading_label = section_title(unit.display_name)
        layout.addWidget(self.heading_label)
        kinds = {"statistics": "statistikk", "backlog": "restanse"}
        capabilities = " og ".join(kinds[item.job_kind] for item in unit.capabilities)
        self.capability_hint = help_text(f"Oppsett for {capabilities}. Innstillinger og feil gjelder bare denne enheten.")
        layout.addWidget(self.capability_hint)

        self.enabled = QCheckBox(f"Aktiver {unit.display_name}")
        self.enabled.setObjectName(f"enabled-{unit.key}")
        self.enabled.setAccessibleName(f"Aktiver enheten {unit.display_name}")
        self.enabled.setMinimumHeight(44)
        self.enabled.setChecked(True)
        layout.addWidget(self.enabled)
        layout.addWidget(help_text("Deaktiverte enheter blir ikke med i automatisk kjøring eller «Kjør aktive enheter»."))

        config = QGroupBox("Analyser og rapporter")
        config_form = QFormLayout(config)
        config_form.setSpacing(12)
        config_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        config_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.config_field = _field(f"config-{unit.key}", f"Enhetsfil for {unit.display_name}")
        self.config_field.setPlaceholderText("Velg din egen enhetsfil (JSON)")
        browse = action_button("Velg fil …", f"browse-config-{unit.key}",
                               accessible_name=f"Velg enhetsfil for {unit.display_name}")
        browse.clicked.connect(self._choose_config)
        config_form.addRow("Enhetsfil (JSON)", _path_row(self.config_field, browse))
        config_form.addRow(help_text("JSON-filen bestemmer rapporter, analysekoder og eventuell restanse. Valider filen etter redigering."))
        config_actions = QHBoxLayout()
        self.validate_button = action_button("Valider JSON", f"validate-config-{unit.key}",
                                            accessible_name=f"Valider enhetsfil for {unit.display_name}")
        self.validate_button.clicked.connect(self.validate_config)
        open_folder = action_button("Åpne filmappe", f"open-config-{unit.key}",
                                    accessible_name=f"Åpne mappen med enhetsfil for {unit.display_name}")
        open_folder.clicked.connect(self._open_config_folder)
        config_actions.addWidget(self.validate_button)
        config_actions.addWidget(open_folder)
        config_actions.addStretch(1)
        config_form.addRow(config_actions)
        self.preview = help_text("Velg din egen enhetsfil (JSON).",
                                 name=f"config-feedback-{unit.key}")
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        config_form.addRow(self.preview)
        layout.addWidget(config)
        self.config_field.textChanged.connect(self._config_changed)

        self.backlog_group = QGroupBox("Restanse")
        backlog_form = QFormLayout(self.backlog_group)
        backlog_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        backlog_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.backlog_field = _field(f"backlog-config-{unit.key}", f"Restansefil for {unit.display_name}")
        self.backlog_field.setPlaceholderText("Valgfri: bruker ellers restanse i enhetsfilen")
        backlog_browse = action_button("Velg fil …", f"browse-backlog-{unit.key}",
            accessible_name=f"Velg restansefil for {unit.display_name}")
        backlog_browse.clicked.connect(self._choose_backlog)
        backlog_form.addRow("Restansefil (JSON)", _path_row(self.backlog_field, backlog_browse))
        backlog_form.addRow(help_text("Egen fil for rapport, grupper, analyser, frister og CSV-kolonner. Endringer leses ved neste kjøring. Statistikkoppsettet endres separat i enhetsfilen."))
        backlog_actions = QHBoxLayout()
        backlog_validate = action_button("Valider JSON", f"validate-backlog-{unit.key}",
            accessible_name=f"Valider restansefil for {unit.display_name}")
        backlog_validate.clicked.connect(self.validate_backlog)
        backlog_open = action_button("Åpne mappe", f"open-backlog-{unit.key}",
            accessible_name=f"Åpne mappen med restansefil for {unit.display_name}")
        backlog_open.clicked.connect(self._open_backlog_folder)
        backlog_actions.addWidget(backlog_validate)
        backlog_actions.addWidget(backlog_open)
        backlog_actions.addStretch(1)
        backlog_form.addRow(backlog_actions)
        self.backlog_preview = help_text("Bruker restanse i enhetsfilen hvis egen fil ikke er valgt.")
        backlog_form.addRow(self.backlog_preview)
        self.backlog_field.textChanged.connect(self._backlog_changed)
        self.backlog_group.setVisible(unit.key in {"hemato", "solide"})
        layout.addWidget(self.backlog_group)

        capability = unit.capability("statistics")
        is_lege = unit.key == "lege"
        self.workflow_hint = help_text("Uttrekk: PAT-TID-STØP-SNITT-OU. Henter én kalendermåned om gangen fra januar 2024 til dagens dato. Ingen andre patolograpporter hentes.")
        self.workflow_hint.setVisible(is_lege)
        layout.addWidget(self.workflow_hint)
        layout.addStretch(1)

    def set_definition(self, unit: UnitDefinition) -> None:
        if unit.key != self.unit.key:
            raise ValueError("Enhetseditoren kan bare oppdateres med samme enhetsnøkkel.")
        self.unit = unit
        self.heading_label.setText(unit.display_name)
        names = {"statistics": "statistikk", "backlog": "restanse"}
        kinds = " og ".join(names[item.job_kind] for item in unit.capabilities)
        self.capability_hint.setText(f"Oppsett for {kinds}. Innstillinger og feil gjelder bare denne enheten.")
        self.enabled.setText(f"Aktiver {unit.display_name}")
        self.enabled.setAccessibleName(f"Aktiver enheten {unit.display_name}")
        self.config_field.setAccessibleName(f"Enhetsfil for {unit.display_name}")
        self.workflow_hint.setVisible(unit.key == "lege")
        self.validate_button.setAccessibleName(f"Valider enhetsfil for {unit.display_name}")

    def _config_changed(self) -> None:
        self.preview.setText("Filen er ikke validert etter siste endring. Bruk «Valider JSON».")
        set_tone(self.preview, "neutral")
        set_tone(self.config_field, "neutral")

    def _choose_config(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "Velg enhetsfil", self.config_field.text(), "JSON-filer (*.json)"
        )
        if selected:
            self.config_field.setText(selected)
            self.validate_config()

    def _open_config_folder(self) -> None:
        path = Path(self.config_field.text().strip())
        if self.config_field.text().strip() and path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve().parent)))
        else:
            self.preview.setText("Velg en eksisterende enhetsfil før du åpner mappen.")
            set_tone(self.preview, "warning")

    def validate_config(self) -> None:
        if not self.config_field.text().strip():
            self.preview.setText("Velg din egen JSON-fil først.")
            set_tone(self.preview, "warning")
            return
        try:
            text = self.backlog_field.text().strip() if self.unit.key in {"hemato", "solide"} else ""
            definition = load_unit_file(Path(self.config_field.text().strip()), self.unit.key,
                backlog_path=Path(text) if text else None)
        except ValueError as error:
            self.preview.setText(str(error))
            set_tone(self.preview, "danger")
            set_tone(self.config_field, "danger")
            return
        statistics = definition.payload["statistics"]
        if definition.unit.profile == "lege":
            detail = f"{len(statistics)} rapporter. Ingen legeregisterfil er nødvendig."
        else:
            counts = ", ".join(f"{name}: {len(report['analysis_codes'])} koder" for name, report in statistics.items())
            backlog = definition.payload.get("backlog")
            detail = counts + (f" · Restanse: {len(backlog['report']['analysis_codes'])} koder" if backlog else "")
        self.preview.setText(f"Gyldig oppsett · {detail}")
        set_tone(self.preview, "success")
        set_tone(self.config_field, "neutral")

    def _choose_backlog(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "Velg restansefil",
            self.backlog_field.text(), "JSON-filer (*.json)")
        if selected:
            self.backlog_field.setText(selected)
            self.validate_backlog()

    def _backlog_changed(self) -> None:
        self.backlog_preview.setText("Filen er ikke validert etter siste endring. Bruk «Valider JSON».")
        set_tone(self.backlog_preview, "neutral")

    def validate_backlog(self) -> None:
        if not self.backlog_field.text().strip():
            self.backlog_preview.setText("Bruker restanse i enhetsfilen hvis egen fil ikke er valgt.")
            return
        try:
            payload = load_backlog_file(Path(self.backlog_field.text().strip()), self.unit.key)
        except ValueError as exc:
            self.backlog_preview.setText(str(exc))
            set_tone(self.backlog_preview, "danger")
            return
        self.backlog_preview.setText(f"Gyldig restanseoppsett · {len(payload['analyses']['analyses'])} analyser · {len(payload['report']['report_groups'])} rapportgrupper")
        set_tone(self.backlog_preview, "success")

    def _open_backlog_folder(self) -> None:
        path = Path(self.backlog_field.text().strip())
        if self.backlog_field.text().strip() and path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve().parent)))
        else:
            self.backlog_preview.setText("Lagre innstillingene eller velg en eksisterende restansefil først.")



class SettingsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("settings-page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)
        title = QLabel("Innstillinger")
        title.setObjectName("page-title")
        layout.addWidget(title)
        intro = help_text("Velg én enhet om gangen. Felles mapper og tidsplaner har egne faner.")
        intro.setObjectName("page-intro")
        layout.addWidget(intro)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("settings-tabs")
        self.tabs.setAccessibleName("Innstillingsområder")
        self.tabs.addTab(self._units_tab(), "Enheter")
        self.tabs.addTab(self._storage_tab(), "Mapper og tilkobling")
        self.tabs.addTab(self._schedule_tab(), "Automatikk")
        self.tabs.addTab(self._transfer_tab(), "Overføring")
        layout.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        footer.addWidget(help_text("Endringene tas i bruk når du validerer og lagrer."), 1)
        self.save_button = action_button("Valider og lagre", "save-settings",
                                        accessible_name="Valider og lagre innstillinger", primary=True)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)

    def _units_tab(self) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(12, 12, 12, 12)
        row.setSpacing(12)
        navigation = QWidget()
        navigation.setFixedWidth(176)
        nav_layout = QVBoxLayout(navigation)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(8)
        nav_layout.addWidget(section_title("Enheter"))
        self.unit_list = QListWidget()
        self.unit_list.setObjectName("settings-unit-list")
        self.unit_list.setAccessibleName("Velg enhet å redigere")
        self.unit_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.unit_list.setSpacing(4)
        nav_layout.addWidget(self.unit_list, 1)
        nav_layout.addWidget(help_text("Aktivering gjelder først etter lagring."))
        row.addWidget(navigation)

        self.unit_stack = QStackedWidget()
        self.unit_stack.setObjectName("unit-settings-stack")
        self.unit_panels: dict[str, UnitSettingsPanel] = {}
        self.config_fields: dict[str, QLineEdit] = {}
        self.backlog_fields: dict[str, QLineEdit] = {}
        self.enabled_fields: dict[str, QCheckBox] = {}
        for unit in DEFAULT_UNITS.active():
            panel = UnitSettingsPanel(unit)
            self.unit_panels[unit.key] = panel
            self.unit_stack.addWidget(panel)
            self.config_fields[unit.key] = panel.config_field
            if unit.key in {"hemato", "solide"}:
                self.backlog_fields[unit.key] = panel.backlog_field
            self.enabled_fields[unit.key] = panel.enabled
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, unit.key)
            item.setSizeHint(QSize(0, 64))
            self.unit_list.addItem(item)
            panel.enabled.toggled.connect(lambda _checked=False, key=unit.key: self._update_unit_label(key))
            self._update_unit_label(unit.key)

        scroll = QScrollArea()
        scroll.setObjectName("settings-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.unit_stack)
        row.addWidget(scroll, 1)
        self.unit_list.currentRowChanged.connect(self.unit_stack.setCurrentIndex)
        self.unit_list.setCurrentRow(0)
        return container

    def _storage_tab(self) -> QWidget:
        content, layout = _tab_content()
        layout.addWidget(section_title("Lagring og LVMS"))
        layout.addWidget(help_text("Rådata, databasen og oppsettet lagres i K-sensitiv. SharePoint mottar bare rapportfiler."))
        storage = QGroupBox("Felles mapper")
        form = QFormLayout(storage)
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.sensitive_root = _field("sensitive-root", "K-sensitiv mappe")
        self.sharepoint_root = _field("sharepoint-root", "SharePoint-mappe")
        self.lvms_url = _field("lvms-url", "LVMS-adresse")
        form.addRow("K-sensitiv mappe", self._directory_row(self.sensitive_root, "browse-sensitive-root", "Velg K-sensitiv mappe"))
        form.addRow("SharePoint-mappe", self._directory_row(self.sharepoint_root, "browse-sharepoint-root", "Velg SharePoint-mappe"))
        layout.addWidget(storage)
        connection = QGroupBox("Automatisk uttrekk")
        connection_form = QFormLayout(connection)
        connection_form.setSpacing(12)
        connection_form.addRow("LVMS-adresse", self.lvms_url)
        connection_form.addRow(help_text("Ved problemer med automatisk uttrekk kan du hente rapportene selv og bruke «Importer uttrekk» på oversikten."))
        layout.addWidget(connection)
        layout.addStretch(1)
        return _tab_scroll(content, "storage-settings-scroll")

    def _schedule_tab(self) -> QWidget:
        content, layout = _tab_content()
        layout.addWidget(section_title("Automatisk kjøring"))
        layout.addWidget(help_text("Velg når MolStat skal oppdatere alle lagrede, aktive enheter hver dag mens programmet er åpent. Klokkeslett bruker PC-ens lokale tid."))
        schedule = QGroupBox("Tidsplan")
        form = QFormLayout(schedule)
        form.setSpacing(12)
        self.daily_time = QTimeEdit(QTime(7, 0))
        self.daily_time.setDisplayFormat("HH:mm")
        self.daily_time.setObjectName("daily-run-time")
        self.daily_time.setAccessibleName("Klokkeslett for daglig automatisk oppdatering")
        self.daily_time.setMinimumHeight(44)
        self.daily_time.setMaximumWidth(180)
        form.addRow("Daglig kl.", self.daily_time)
        form.addRow(help_text("Trykk «Valider og lagre» for å ta i bruk tidspunktet. Standard er 07:00. Et nytt tidspunkt starter en ny kjøring selv om programmet allerede har kjørt tidligere samme dag."))
        form.addRow(help_text("Statistikk og restanse kjøres samlet, med behandling, publisering og oppdatering av Excel-søk."))
        layout.addWidget(schedule)
        layout.addWidget(help_text("La MolStat være åpent, gjerne minimert. PC-en må være våken og ha tilgang til LVMS, datarot og SharePoint. En forsinket kjøring tas igjen når programmet er tilgjengelig etter valgt tidspunkt."))
        layout.addWidget(help_text("Tidsstyringen krever ingen Windows-oppgave eller ekstra program. Gamle tidsplaner brukes ikke lenger. Ved feil: se Diagnostikk, velg et nytt tidspunkt eller bruk «Kjør aktive enheter»."))
        layout.addStretch(1)
        return _tab_scroll(content, "schedule-settings-scroll")

    def _transfer_tab(self) -> QWidget:
        content, layout = _tab_content()
        layout.addWidget(section_title("Flytt innstillinger"))
        layout.addWidget(help_text("Eksporter oppsettet for å bruke det på en annen PC. Ved import kontrolleres filen før innstillingene lagres."))
        transfer = QGroupBox("Innstillingsfil (JSON)")
        transfer_layout = QVBoxLayout(transfer)
        transfer_layout.setSpacing(12)
        transfer_layout.addWidget(help_text("Mapper og oppslagsfiler kan ha andre plasseringer på den nye PC-en. Kontroller dem etter import."))
        actions = QHBoxLayout()
        self.import_button = action_button("Importer innstillinger …", "import-settings",
                                          accessible_name="Importer MolStat-innstillinger")
        self.export_button = action_button("Eksporter innstillinger …", "export-settings",
                                          accessible_name="Eksporter MolStat-innstillinger")
        actions.addWidget(self.import_button)
        actions.addWidget(self.export_button)
        actions.addStretch(1)
        transfer_layout.addLayout(actions)
        layout.addWidget(transfer)
        layout.addWidget(help_text("Fritekst i oppsettet publiseres ordrett. Bruk bare rapportnavn og faglige beskrivelser."))
        layout.addStretch(1)
        return _tab_scroll(content, "transfer-settings-scroll")

    def select_unit(self, key: str) -> None:
        for index in range(self.unit_list.count()):
            if self.unit_list.item(index).data(Qt.ItemDataRole.UserRole) == key:
                self.tabs.setCurrentIndex(0)
                self.unit_list.setCurrentRow(index)
                return

    def set_definitions(self, units: UnitRegistry) -> None:
        for unit in units:
            if unit.key in self.unit_panels:
                self.unit_panels[unit.key].set_definition(unit)
                self._update_unit_label(unit.key)

    def _update_unit_label(self, key: str) -> None:
        unit = self.unit_panels[key].unit
        enabled = self.enabled_fields[key].isChecked()
        for index in range(self.unit_list.count()):
            item = self.unit_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == key:
                item.setText(f"{unit.display_name}\n{'Aktiv' if enabled else 'Deaktivert'}")
                item.setToolTip(f"{unit.display_name}: {'Aktiv' if enabled else 'Deaktivert'} i oppsettet")
                return

    def _directory_row(self, field: QLineEdit, name: str, title: str) -> QWidget:
        browse = action_button("Velg mappe …", name, accessible_name=title)
        browse.clicked.connect(lambda: self._choose_directory(field, title))
        return _path_row(field, browse)

    def _choose_directory(self, field: QLineEdit, title: str) -> None:
        selected = QFileDialog.getExistingDirectory(self, title, field.text())
        if selected:
            field.setText(selected)


def _field(name: str, accessible_name: str) -> QLineEdit:
    field = QLineEdit()
    field.setObjectName(name)
    field.setAccessibleName(accessible_name)
    field.setMinimumHeight(44)
    field.setMinimumWidth(80)
    return field


def _path_row(field: QLineEdit, button: QWidget) -> QWidget:
    container = QWidget()
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    row.addWidget(field, 1)
    row.addWidget(button)
    return container


def _tab_content() -> tuple[QWidget, QVBoxLayout]:
    content = QWidget()
    content.setObjectName("settings-tab-content")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(16)
    layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
    return content, layout


def _tab_scroll(content: QWidget, name: str) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName(name)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(content)
    return scroll
