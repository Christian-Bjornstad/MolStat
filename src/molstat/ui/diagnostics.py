from __future__ import annotations

from PyQt6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QVBoxLayout, QWidget,
)

from ..modules import DEFAULT_UNITS
from .components import action_button, help_text


class DiagnosticsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("diagnostics-page")
        self._messages: tuple[str, ...] = ()
        self._configuration_error: str | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)
        title = QLabel("Diagnostikk")
        title.setObjectName("page-title")
        intro = help_text("Driftslogg uten prøve- eller pasientidentifikatorer. Filtrer på enheten du vil undersøke.")
        intro.setObjectName("page-intro")
        layout.addWidget(title)
        layout.addWidget(intro)

        filters = QHBoxLayout()
        self.unit_filter = QComboBox()
        self.unit_filter.setObjectName("diagnostic-unit-filter")
        self.unit_filter.setAccessibleName("Filtrer driftslogg etter enhet")
        self.unit_filter.setMinimumHeight(44)
        self.unit_filter.addItem("Alle enheter", "")
        for unit in DEFAULT_UNITS.active():
            self.unit_filter.addItem(unit.display_name, unit.key)
        self.search_field = QLineEdit()
        self.search_field.setObjectName("diagnostic-search")
        self.search_field.setAccessibleName("Søk i driftsloggen")
        self.search_field.setPlaceholderText("Søk etter hendelse eller feilkode")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.setMinimumHeight(44)
        self.copy_button = action_button("Kopier logg", "copy-diagnostics",
                                         accessible_name="Kopier synlig driftslogg")
        self.copy_button.clicked.connect(self._copy_log)
        filters.addWidget(self.unit_filter)
        filters.addWidget(self.search_field, 1)
        filters.addWidget(self.copy_button)
        layout.addLayout(filters)
        self.summary = help_text("", name="diagnostic-summary")
        layout.addWidget(self.summary)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setAccessibleName("Personvernsikker driftslogg")
        self.log.setMaximumBlockCount(2000)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.log, 1)
        self.unit_filter.currentIndexChanged.connect(self._render_messages)
        self.search_field.textChanged.connect(self._render_messages)
        self._render_messages()

    def set_configuration_error(self, error: str | None) -> None:
        self._configuration_error = error
        self._render_messages()

    def set_messages(self, messages: tuple[str, ...]) -> None:
        self._messages = messages
        self._render_messages()

    def _render_messages(self) -> None:
        messages = self._messages
        if self._configuration_error:
            messages = (f"Oppsettet kunne ikke lastes:\n{self._configuration_error}", *messages)
        unit = self.unit_filter.currentData()
        query = self.search_field.text().strip().casefold()
        visible = tuple(
            message for message in messages
            if (not unit or unit.casefold() in message.casefold())
            and (not query or query in message.casefold())
        )
        self.summary.setText(f"{len(messages)} hendelser · {len(visible)} vist")
        empty = "Ingen hendelser passer til filteret." if messages else "Ingen hendelser registrert."
        self.log.setPlainText("\n\n".join(visible) if visible else empty)
        self.copy_button.setEnabled(bool(visible))

    def _copy_log(self) -> None:
        QApplication.clipboard().setText(self.log.toPlainText())
