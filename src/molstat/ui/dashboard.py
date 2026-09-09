from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..modules import DEFAULT_UNITS, UnitDefinition


class StatusCard(QFrame):
    def __init__(self, title: str, state: str, detail: str) -> None:
        super().__init__()
        self.title = title
        self.setObjectName("status-card")
        self._set_accessible_status(state, detail)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(7)
        title_label = QLabel(title)
        title_label.setProperty("cardTitle", True)
        self.state_label = QLabel(state)
        self.state_label.setProperty("cardState", True)
        self.detail_label = QLabel(detail)
        self.detail_label.setProperty("cardDetail", True)
        self.detail_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(self.state_label)
        layout.addWidget(self.detail_label)

    def set_status(self, state: str, detail: str) -> None:
        self.state_label.setText(state)
        self.detail_label.setText(detail)
        self._set_accessible_status(state, detail)

    def _set_accessible_status(self, state: str, detail: str) -> None:
        self.setAccessibleName(f"{self.title}: {state}. {detail}")


class UnitCard(QFrame):
    def __init__(self, unit: UnitDefinition) -> None:
        super().__init__()
        self.unit = unit
        self.setObjectName(f"unit-card-{unit.key}")
        self.setProperty("unitStatus", unit.status)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)

        heading = QHBoxLayout()
        title = QLabel(unit.display_name)
        title.setProperty("unitTitle", True)
        state = QLabel("Aktiv" if unit.status == "active" else "Kommer")
        state.setProperty("unitBadge", unit.status)
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(state)
        layout.addLayout(heading)

        capability_names = {
            "statistics": "Statistikk",
            "backlog": "restanse",
        }
        capabilities = " + ".join(
            capability_names[item.job_kind]
            for item in unit.capabilities
        )
        self.capability_label = QLabel(capabilities or "Flere funksjoner kommer")
        self.capability_label.setObjectName(f"capabilities-{unit.key}")
        self.capability_label.setProperty("cardDetail", True)
        self.capability_label.setWordWrap(True)
        layout.addWidget(self.capability_label)

        self.status_label = QLabel(
            "Klar for kjøring" if unit.status == "active" else "Ikke tilgjengelig ennå"
        )
        self.status_label.setProperty("unitRunState", True)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        text = f"Kjør {unit.display_name}" if unit.status == "active" else "Kommer"
        self.run_button = _button(text, f"run-{unit.key}")
        self.run_button.setEnabled(unit.status == "active")
        self.run_button.setAccessibleName(
            f"Kjør alle funksjoner for {unit.display_name}"
            if unit.status == "active"
            else f"{unit.display_name} kommer senere"
        )
        layout.addWidget(self.run_button)
        self._refresh_accessible_name()

    def set_status(self, state: str, detail: str) -> None:
        self.status_label.setText(f"{state}: {detail}")
        self._refresh_accessible_name()

    def _refresh_accessible_name(self) -> None:
        self.setAccessibleName(
            f"{self.unit.display_name}. {self.capability_label.text()}. "
            f"{self.status_label.text()}"
        )


class OverviewPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("overview-page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        title = QLabel("Driftsoversikt")
        title.setObjectName("page-title")
        intro = QLabel(
            "Kjør hele MolStat eller én hovedenhet om gangen."
        )
        intro.setObjectName("page-intro")
        intro.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(intro)

        self.run_all = _button("Kjør alt", "run-all", primary=True)
        self.run_all.setAccessibleName("Kjør alle funksjoner for aktive enheter")
        layout.addWidget(self.run_all, 0, Qt.AlignmentFlag.AlignLeft)

        unit_grid = QGridLayout()
        unit_grid.setHorizontalSpacing(16)
        unit_grid.setVerticalSpacing(16)
        self.unit_cards = {
            unit.key: UnitCard(unit) for unit in DEFAULT_UNITS
        }
        for index, card in enumerate(self.unit_cards.values()):
            unit_grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(unit_grid)

        system_grid = QGridLayout()
        system_grid.setHorizontalSpacing(16)
        self.cards = {
            "database": StatusCard(
                "Database", "Beskyttet", "Én aktiv skriver på K-sensitiv"
            ),
            "sharepoint": StatusCard(
                "SharePoint", "Ikke satt opp", "Velg mappe i Innstillinger"
            ),
        }
        system_grid.addWidget(self.cards["database"], 0, 0)
        system_grid.addWidget(self.cards["sharepoint"], 0, 1)
        layout.addLayout(system_grid)
        layout.addStretch(1)


def _button(text: str, name: str, *, primary: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.setAccessibleName(text)
    button.setMinimumHeight(44)
    if primary:
        button.setProperty("primary", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button
