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


class OverviewPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("overview-page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(22)

        title = QLabel("Driftsoversikt")
        title.setObjectName("page-title")
        intro = QLabel(
            "Én trygg dataflyt fra LVMS til K-sensitiv, SharePoint og restansetavlen."
        )
        intro.setObjectName("page-intro")
        intro.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(intro)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        self.cards = {
            "statistics": StatusCard("Statistikk", "Klar", "Neste kjøring kl. 05:00"),
            "backlog": StatusCard("Restanse", "Klar", "Kjører hver time kl. 06–18"),
            "database": StatusCard("Database", "Beskyttet", "Én aktiv skriver på K-sensitiv"),
            "sharepoint": StatusCard("SharePoint", "Ikke satt opp", "Velg mappe i Innstillinger"),
        }
        for index, card in enumerate(self.cards.values()):
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)
        self.run_statistics = _button(
            "Kjør statistikk nå", "run-statistics", primary=True
        )
        self.run_backlog = _button("Hent restanse nå", "run-backlog")
        self.open_board = _button("Åpne restansetavle", "open-board")
        action_row.addWidget(self.run_statistics)
        action_row.addWidget(self.run_backlog)
        action_row.addWidget(self.open_board)
        action_row.addStretch(1)
        layout.addLayout(action_row)
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
