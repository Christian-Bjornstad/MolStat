from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..modules import DEFAULT_UNITS


class SettingsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("settings-page")
        layout = QVBoxLayout(self)
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
