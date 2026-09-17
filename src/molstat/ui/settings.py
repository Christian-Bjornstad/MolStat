from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..modules import DEFAULT_UNITS
from ..unit_settings import load_unit_file
from pathlib import Path
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices


class SettingsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("settings-page")
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("settings-scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("page-content")
        layout = QVBoxLayout(content)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        title = QLabel("Innstillinger")
        title.setObjectName("page-title")
        intro = QLabel(
            "Globale mapper og enhetsoppsett lagres lokalt. "
            "Fritekst publiseres ordrett og må ikke inneholde identifikatorer."
        )
        intro.setObjectName("page-intro")
        intro.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(intro)

        storage = QGroupBox("Lagring og LVMS")
        form = QFormLayout(storage)
        form.setSpacing(12)
        self.sensitive_root = _field("sensitive-root", "K-sensitiv mappe")
        self.sharepoint_root = _field("sharepoint-root", "SharePoint-mappe")
        self.lvms_url = _field("lvms-url", "LVMS-adresse")
        form.addRow(
            "K-sensitiv mappe",
            self._directory_row(
                self.sensitive_root,
                "browse-sensitive-root",
                "Velg K-sensitiv mappe",
            ),
        )
        form.addRow(
            "SharePoint-mappe",
            self._directory_row(
                self.sharepoint_root,
                "browse-sharepoint-root",
                "Velg SharePoint-mappe",
            ),
        )
        form.addRow("LVMS-adresse", self.lvms_url)
        layout.addWidget(storage)

        self.lookup_fields: dict[str, QLineEdit] = {}
        self.config_fields: dict[str, QLineEdit] = {}
        self.enabled_fields: dict[str, QCheckBox] = {}
        for unit in DEFAULT_UNITS.active():
            group = QGroupBox(unit.display_name)
            unit_form = QFormLayout(group)
            unit_form.setSpacing(12)
            enabled = QCheckBox(f"Aktiver {unit.display_name}")
            enabled.setObjectName(f"enabled-{unit.key}")
            enabled.setAccessibleName(f"Aktiver enheten {unit.display_name}")
            enabled.setMinimumHeight(44)
            enabled.setChecked(True)
            self.enabled_fields[unit.key] = enabled
            unit_form.addRow("Enhet", enabled)
            config_field = _field(f"config-{unit.key}", f"Enhetsfil for {unit.display_name}")
            config_field.setPlaceholderText("Standardoppsett opprettes ved første lagring")
            self.config_fields[unit.key] = config_field
            browse = _browse_button(f"browse-config-{unit.key}", f"Velg enhetsfil for {unit.display_name}")
            browse.clicked.connect(lambda _=False, target=config_field: self._choose_config(target))
            unit_form.addRow("Analyser og rapporter", _path_row(config_field, browse))
            preview = QLabel("Velg en JSON-fil. Endringene aktiveres med «Valider og lagre».")
            preview.setWordWrap(True)
            preview.setProperty("cardDetail", True)
            validate = _action_button("Valider fil", f"validate-config-{unit.key}", f"Valider enhetsfil for {unit.display_name}")
            validate.clicked.connect(lambda _=False, field=config_field, label=preview, key=unit.key: self._validate_config(field, label, key))
            unit_form.addRow(validate, preview)
            open_folder = _action_button("Åpne filmappe", f"open-config-{unit.key}", f"Åpne mappen med enhetsfil for {unit.display_name}")
            open_folder.clicked.connect(lambda _=False, field=config_field: self._open_config_folder(field))
            unit_form.addRow("Rediger oppsett", open_folder)

            capability = unit.capability("statistics")
            del capability
            accessible_name = f"Lookup-fil for {unit.display_name}"
            field = _field(f"lookup-{unit.key}", accessible_name)
            self.lookup_fields[unit.key] = field
            setattr(self, f"lookup_{unit.key}", field)
            unit_form.addRow(
                "Lookup-fil",
                self._file_row(
                    field,
                    f"browse-lookup-{unit.key}",
                    f"Velg lookup-fil for {unit.display_name}",
                ),
            )
            layout.addWidget(group)

        schedule = QGroupBox("Automatisk kjøring")
        schedule_form = QFormLayout(schedule)
        self.schedule_fields = {}
        for key, label, default in (("statistics_hour", "Statistikk – klokkeslett", 5),
                                    ("backlog_first_hour", "Restanse – første time", 6),
                                    ("backlog_last_hour", "Restanse – siste time", 18)):
            field = QSpinBox()
            field.setRange(0, 23)
            field.setValue(default)
            field.setAccessibleName(label)
            field.setSuffix(":00")
            field.setMinimumHeight(44)
            self.schedule_fields[key] = field
            schedule_form.addRow(label, field)
        hint = QLabel("Installer Windows-oppgavene på nytt etter endring av tidsplanen.")
        hint.setWordWrap(True)
        schedule_form.addRow(hint)
        layout.addWidget(schedule)

        transfer = QGroupBox("Flytt innstillinger")
        transfer_layout = QHBoxLayout(transfer)
        self.import_button = _action_button(
            "Importer …", "import-settings", "Importer MolStat-innstillinger"
        )
        self.export_button = _action_button(
            "Eksporter …", "export-settings", "Eksporter MolStat-innstillinger"
        )
        transfer_layout.addWidget(self.import_button)
        transfer_layout.addWidget(self.export_button)
        transfer_layout.addStretch(1)
        layout.addWidget(transfer)

        self.save_button = QPushButton("Valider og lagre")
        self.save_button.setAccessibleName("Valider og lagre innstillinger")
        self.save_button.setMinimumHeight(44)
        self.save_button.setProperty("primary", True)
        layout.addWidget(self.save_button, 0)
        layout.addStretch(1)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)

    def _choose_config(self, field: QLineEdit) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "Velg enhetsfil", field.text(), "JSON-filer (*.json)")
        if selected:
            field.setText(selected)

    def _open_config_folder(self, field: QLineEdit) -> None:
        if field.text() and Path(field.text()).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(field.text()).resolve().parent)))

    def _validate_config(self, field: QLineEdit, label: QLabel, key: str) -> None:
        try:
            definition = load_unit_file(Path(field.text()), key)
            counts = ", ".join(f"{name}: {len(report['analysis_codes'])}" for name, report in definition.payload["statistics"].items())
            backlog = definition.payload.get("backlog")
            label.setText(f"Gyldig · {counts}" + (f" · restanse: {len(backlog['report']['analysis_codes'])}" if backlog else ""))
        except ValueError as exc:
            label.setText(str(exc))

    def _directory_row(
        self, field: QLineEdit, button_name: str, accessible_name: str
    ) -> QWidget:
        button = _browse_button(button_name, accessible_name)
        button.clicked.connect(lambda: self._choose_directory(field, accessible_name))
        return _path_row(field, button)

    def _file_row(
        self, field: QLineEdit, button_name: str, accessible_name: str
    ) -> QWidget:
        button = _browse_button(button_name, accessible_name)
        button.clicked.connect(lambda: self._choose_lookup(field, accessible_name))
        return _path_row(field, button)

    def _choose_directory(self, field: QLineEdit, title: str) -> None:
        selected = QFileDialog.getExistingDirectory(self, title, field.text())
        if selected:
            field.setText(selected)

    def _choose_lookup(self, field: QLineEdit, title: str) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            title,
            field.text(),
            "Excel-filer (*.xlsx *.xlsm *.xls);;Alle filer (*)",
        )
        if selected:
            field.setText(selected)


def _field(name: str, accessible_name: str) -> QLineEdit:
    field = QLineEdit()
    field.setObjectName(name)
    field.setAccessibleName(accessible_name)
    field.setMinimumHeight(44)
    return field


def _browse_button(name: str, accessible_name: str) -> QPushButton:
    return _action_button("Bla gjennom …", name, accessible_name)


def _action_button(text: str, name: str, accessible_name: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.setAccessibleName(accessible_name)
    button.setMinimumHeight(44)
    return button


def _path_row(field: QLineEdit, button: QPushButton) -> QWidget:
    container = QWidget()
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    row.addWidget(field, 1)
    row.addWidget(button)
    return container
