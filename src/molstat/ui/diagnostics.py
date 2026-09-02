from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget


class DiagnosticsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("diagnostics-page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        title = QLabel("Diagnostikk")
        title.setObjectName("page-title")
        intro = QLabel("Teknisk driftslogg uten prøve- eller pasientidentifikatorer.")
        intro.setObjectName("page-intro")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setAccessibleName("Personvernsikker driftslogg")
        self.log.setPlainText("Ingen hendelser registrert.")
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(self.log, 1)
