from __future__ import annotations

from PyQt6.QtWidgets import (
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


class SettingsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("settings-page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)
        title = QLabel("Innstillinger")
        title.setObjectName("page-title")
        intro = QLabel(
            "Produksjonsstier lagres lokalt. Sensitive data publiseres aldri til SharePoint."
        )
        intro.setObjectName("page-intro")
        intro.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(intro)

        storage = QGroupBox("Lagring og publisering")
        form = QFormLayout(storage)
        form.setSpacing(14)
        self.sensitive_root = _field("sensitive-root", "K-sensitiv mappe")
        self.sharepoint_root = _field("sharepoint-root", "SharePoint-mappe")
        self.lvms_url = _field("lvms-url", "LVMS-adresse")
        self.lookup_hemato = _field("lookup-hemato", "Lookup-fil for Hemato")
        self.lookup_solide = _field("lookup-solide", "Lookup-fil for Solide")
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
        form.addRow(
            "Lookup Hemato",
            self._file_row(
                self.lookup_hemato,
                "browse-lookup-hemato",
                "Velg lookup-fil for Hemato",
            ),
        )
        form.addRow(
            "Lookup Solide",
            self._file_row(
                self.lookup_solide,
                "browse-lookup-solide",
                "Velg lookup-fil for Solide",
            ),
        )
        layout.addWidget(storage)
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
    button = QPushButton("Bla gjennom …")
    button.setObjectName(name)
    button.setAccessibleName(accessible_name)
    button.setMinimumHeight(44)
    return button


def _path_row(field: QLineEdit, button: QPushButton) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(field, 1)
    layout.addWidget(button)
    return container
