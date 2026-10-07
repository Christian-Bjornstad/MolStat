from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout,
    QLineEdit, QScrollArea, QVBoxLayout, QWidget,
)

from ..modules import DEFAULT_UNITS, UnitDefinition, UnitRegistry
from .components import action_button, help_text, section_title, set_tone, status_tone


class StatusCard(QFrame):
    def __init__(self, title: str, state: str, detail: str) -> None:
        super().__init__()
        self.title = title
        self.setObjectName("status-card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setProperty("cardTitle", True)
        self.state_label = QLabel()
        self.state_label.setProperty("cardState", True)
        self.state_label.setWordWrap(True)
        self.detail_label = help_text("")
        layout.addWidget(title_label)
        layout.addWidget(self.state_label)
        layout.addWidget(self.detail_label)
        layout.addStretch(1)
        self.set_status(state, detail)

    def set_status(self, state: str, detail: str) -> None:
        self.state_label.setText(state)
        self.detail_label.setText(detail)
        set_tone(self.state_label, status_tone(state))
        self.setAccessibleName(f"{self.title}: {state}. {detail}")


class UnitCard(QFrame):
    status_changed = pyqtSignal()

    def __init__(self, unit: UnitDefinition) -> None:
        super().__init__()
        self.unit = unit
        self.enabled = unit.status == "active"
        self.tone = "neutral"
        self.setObjectName(f"unit-card-{unit.key}")
        self.setProperty("unitStatus", unit.status)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        heading = QHBoxLayout()
        self.title_label = QLabel(unit.display_name)
        self.title_label.setProperty("unitTitle", True)
        self.badge = QLabel()
        self.badge.setProperty("badge", True)
        heading.addWidget(self.title_label)
        heading.addStretch(1)
        heading.addWidget(self.badge)
        layout.addLayout(heading)

        names = {"statistics": "Statistikk", "backlog": "restanse"}
        capabilities = " + ".join(names[item.job_kind] for item in unit.capabilities)
        self.capability_label = help_text(capabilities or "Enheten er under utvikling")
        self.capability_label.setObjectName(f"capabilities-{unit.key}")
        layout.addWidget(self.capability_label)

        self.status_label = QLabel("Klar for kjøring" if self.enabled else "Ikke tilgjengelig ennå")
        self.status_label.setProperty("unitRunState", True)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.capability_status_labels: dict[str, QLabel] = {}
        self.capability_status_layout = QVBoxLayout()
        self.capability_status_layout.setSpacing(6)
        for capability in unit.capabilities:
            label = QLabel()
            label.setObjectName(f"status-{unit.key}-{capability.job_kind}")
            label.setProperty("capabilityStatus", True)
            label.setWordWrap(True)
            label.hide()
            self.capability_status_labels[capability.job_kind] = label
            self.capability_status_layout.addWidget(label)
        layout.addLayout(self.capability_status_layout)
        layout.addStretch(1)

        actions = QHBoxLayout()
        self.settings_button = action_button(
            "Oppsett", f"settings-{unit.key}",
            accessible_name=f"Åpne innstillinger for {unit.display_name}",
        )
        self.settings_button.setProperty("quiet", True)
        self.settings_button.setVisible(unit.status == "active")
        text = f"Kjør {unit.display_name}" if self.enabled else "Kommer"
        self.run_button = action_button(
            text, f"run-{unit.key}",
            accessible_name=(f"Kjør alle funksjoner for {unit.display_name}"
                             if self.enabled else f"{unit.display_name} kommer senere"),
        )
        self.run_button.setEnabled(self.enabled)
        actions.addWidget(self.settings_button)
        actions.addStretch(1)
        actions.addWidget(self.run_button)
        layout.addLayout(actions)
        self.set_enabled(self.enabled)

    def set_definition(self, unit: UnitDefinition) -> None:
        if unit.key != self.unit.key:
            raise ValueError("Enhetskortet kan bare oppdateres med samme enhetsnøkkel.")
        self.unit = unit
        self.setProperty("unitStatus", unit.status)
        self.title_label.setText(unit.display_name)
        names = {"statistics": "Statistikk", "backlog": "restanse"}
        self.capability_label.setText(" + ".join(names[item.job_kind] for item in unit.capabilities)
                                      or "Enheten er under utvikling")
        kinds = {item.job_kind for item in unit.capabilities}
        for kind in tuple(self.capability_status_labels):
            if kind not in kinds:
                label = self.capability_status_labels.pop(kind)
                self.capability_status_layout.removeWidget(label)
                label.deleteLater()
        for capability in unit.capabilities:
            if capability.job_kind in self.capability_status_labels:
                continue
            label = QLabel()
            label.setObjectName(f"status-{unit.key}-{capability.job_kind}")
            label.setProperty("capabilityStatus", True)
            label.setWordWrap(True)
            label.hide()
            self.capability_status_labels[capability.job_kind] = label
            self.capability_status_layout.addWidget(label)
        self.run_button.setText(f"Kjør {unit.display_name}" if unit.status == "active" else "Kommer")
        self.run_button.setAccessibleName(f"Kjør alle funksjoner for {unit.display_name}")
        self.settings_button.setAccessibleName(f"Åpne innstillinger for {unit.display_name}")
        self.settings_button.setVisible(unit.status == "active")
        self.set_enabled(self.enabled)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled and self.unit.status == "active"
        self.badge.setText("Aktiv" if self.enabled else "Deaktivert" if self.unit.status == "active" else "Kommer")
        set_tone(self.badge, "success" if self.enabled else "neutral")
        self._refresh_accessible_name()
        self.status_changed.emit()

    def set_status(self, state: str, detail: str) -> None:
        self.status_label.setText(f"{state}: {detail}" if detail else state)
        self.tone = status_tone(state)
        set_tone(self.status_label, self.tone)
        self._refresh_accessible_name()
        self.status_changed.emit()

    def set_capability_status(self, job_kind: str, state: str, detail: str) -> None:
        label = self.capability_status_labels.get(job_kind)
        if label is None:
            return
        name = {"statistics": "Statistikk", "backlog": "Restanse"}.get(job_kind, job_kind)
        label.setText(f"{name} · {state}" + (f" — {detail}" if detail else ""))
        label.setToolTip(detail)
        set_tone(label, status_tone(state))
        label.show()
        self._refresh_accessible_name()

    def _refresh_accessible_name(self) -> None:
        outcomes = ". ".join(label.text() for label in self.capability_status_labels.values() if label.text())
        self.setAccessibleName(
            f"{self.unit.display_name}. {self.badge.text()}. {self.capability_label.text()}. "
            f"{self.status_label.text()}. {outcomes}"
        )


class OverviewPage(QWidget):
    settings_requested = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("overview-page")
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("overview-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("page-content")
        layout = QVBoxLayout(content)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Driftsoversikt")
        title.setObjectName("page-title")
        layout.addWidget(title)
        intro = help_text("Hver enhet har eget oppsett og egen kjørestatus. Velg en enhet, eller kjør alle aktive enheter.")
        intro.setObjectName("page-intro")
        layout.addWidget(intro)

        actions = QHBoxLayout()
        self.run_all = action_button("Kjør aktive enheter", "run-all", primary=True,
                                     accessible_name="Kjør alle funksjoner for aktive enheter")
        self.import_button = action_button("Importer uttrekk …", "open-manual-import",
                                          accessible_name="Importer manuelt hentede LVMS-uttrekk")
        actions.addWidget(self.run_all)
        actions.addWidget(self.import_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("unit-summary")
        self.summary_label.setProperty("sectionTitle", True)
        layout.addWidget(self.summary_label)
        filters = QHBoxLayout()
        self.unit_search = QLineEdit()
        self.unit_search.setObjectName("unit-search")
        self.unit_search.setAccessibleName("Søk etter enhet")
        self.unit_search.setPlaceholderText("Søk etter enhet")
        self.unit_search.setClearButtonEnabled(True)
        self.unit_search.setMinimumHeight(44)
        self.unit_filter = QComboBox()
        self.unit_filter.setObjectName("unit-filter")
        self.unit_filter.setAccessibleName("Filtrer enheter")
        self.unit_filter.setMinimumHeight(44)
        for label, key in (("Alle enheter", "all"), ("Aktive enheter", "active"),
                           ("Deaktiverte", "disabled"), ("Trenger oppfølging", "attention")):
            self.unit_filter.addItem(label, key)
        self.unit_filter.setCurrentIndex(self.unit_filter.findData("active"))
        filters.addWidget(self.unit_search, 1)
        filters.addWidget(self.unit_filter)
        layout.addLayout(filters)

        self.unit_grid = QGridLayout()
        self.unit_grid.setHorizontalSpacing(12)
        self.unit_grid.setVerticalSpacing(12)
        self.unit_grid.setColumnStretch(0, 1)
        self.unit_grid.setColumnStretch(1, 1)
        self.unit_cards = {unit.key: UnitCard(unit) for unit in DEFAULT_UNITS}
        for key, card in self.unit_cards.items():
            card.status_changed.connect(self.refresh_summary)
            card.settings_button.clicked.connect(lambda _checked=False, selected=key: self.settings_requested.emit(selected))
        layout.addLayout(self.unit_grid)
        self.empty_label = help_text("Ingen enheter passer til søket. Prøv et annet søk eller filter.", name="no-units")
        layout.addWidget(self.empty_label)

        self.future_units = QWidget()
        future_layout = QVBoxLayout(self.future_units)
        future_layout.setContentsMargins(0, 0, 0, 0)
        for card in self.unit_cards.values():
            if card.unit.status != "active":
                future_layout.addWidget(card)
        self.future_units.hide()
        self.show_future = action_button("Vis kommende enheter", "show-future-units")
        self.show_future.setProperty("quiet", True)
        self.show_future.setCheckable(True)
        self.show_future.toggled.connect(self._toggle_future)
        layout.addWidget(self.show_future, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.future_units)

        layout.addWidget(section_title("Felles tjenester"))
        system_grid = QGridLayout()
        system_grid.setHorizontalSpacing(12)
        self.cards = {
            "database": StatusCard("Database", "Ikke kontrollert", "Status kontrolleres når appen starter"),
            "sharepoint": StatusCard("Publisering", "Ikke satt opp", "Velg SharePoint-mappe i Innstillinger"),
            "excel": StatusCard("Excel-søk", "Ikke kontrollert", "Søkefil fra databasen"),
        }
        for column, card in enumerate(self.cards.values()):
            system_grid.addWidget(card, 0, column)
            system_grid.setColumnStretch(column, 1)
        layout.addLayout(system_grid)
        service_actions = QHBoxLayout()
        self.refresh_excel = action_button("Oppdater Excel-søk", "refresh-excel")
        self.retry_publish = action_button("Prøv publisering igjen", "retry-publish")
        service_actions.addWidget(self.refresh_excel)
        service_actions.addWidget(self.retry_publish)
        service_actions.addStretch(1)
        layout.addLayout(service_actions)
        layout.addStretch(1)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        self.unit_search.textChanged.connect(self._filter_units)
        self.unit_filter.currentIndexChanged.connect(self._filter_units)
        self.refresh_summary()

    def set_enabled_units(self, keys: set[str]) -> None:
        for key, card in self.unit_cards.items():
            card.set_enabled(key in keys)
        self.refresh_summary()

    def set_definitions(self, units: UnitRegistry) -> None:
        for unit in units:
            card = self.unit_cards.get(unit.key)
            if card is not None:
                card.set_definition(unit)
        self.refresh_summary()

    def refresh_summary(self) -> None:
        active = [card for card in self.unit_cards.values() if card.unit.status == "active"]
        enabled = sum(card.enabled for card in active)
        attention = sum(card.enabled and card.tone in {"danger", "warning"} for card in active)
        text = f"{enabled} aktive enheter · {len(active) - enabled} deaktiverte"
        if attention:
            text += f" · {attention} trenger oppfølging"
        self.summary_label.setText(text)
        self._filter_units()

    def _filter_units(self) -> None:
        query = self.unit_search.text().strip().casefold()
        selected = self.unit_filter.currentData()
        while self.unit_grid.count():
            self.unit_grid.takeAt(0)
        visible = 0
        for card in self.unit_cards.values():
            if card.unit.status != "active":
                continue
            matches = not query or query in f"{card.unit.key} {card.unit.display_name}".casefold()
            matches &= selected == "all" or (selected == "active" and card.enabled) or (selected == "disabled" and not card.enabled) or (selected == "attention" and card.enabled and card.tone in {"danger", "warning"})
            card.setVisible(matches)
            if matches:
                self.unit_grid.addWidget(card, visible // 2, visible % 2)
                visible += 1
        self.empty_label.setVisible(visible == 0)

    def _toggle_future(self, visible: bool) -> None:
        self.future_units.setVisible(visible)
        self.show_future.setText("Skjul kommende enheter" if visible else "Vis kommende enheter")
