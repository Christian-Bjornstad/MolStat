from __future__ import annotations

from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
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
        form.addRow("K-sensitiv mappe", self.sensitive_root)
        form.addRow("SharePoint-mappe", self.sharepoint_root)
        form.addRow("LVMS-adresse", self.lvms_url)
        layout.addWidget(storage)
        self.save_button = QPushButton("Valider og lagre")
        self.save_button.setAccessibleName("Valider og lagre innstillinger")
        self.save_button.setMinimumHeight(44)
        self.save_button.setProperty("primary", True)
        layout.addWidget(self.save_button, 0)
        layout.addStretch(1)


def _field(name: str, accessible_name: str) -> QLineEdit:
    field = QLineEdit()
    field.setObjectName(name)
    field.setAccessibleName(accessible_name)
    field.setMinimumHeight(44)
    return field
