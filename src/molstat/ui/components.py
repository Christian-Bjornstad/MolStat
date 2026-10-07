"""Small shared pieces of the native MolStat interface."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget


def action_button(text: str, name: str, *, accessible_name: str | None = None,
                  primary: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.setAccessibleName(accessible_name or text)
    button.setMinimumHeight(44)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        button.setProperty("primary", True)
    return button


def help_text(text: str, *, name: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("cardDetail", True)
    if name:
        label.setObjectName(name)
    return label


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("sectionTitle", True)
    return label


def set_tone(widget: QWidget, tone: str) -> None:
    widget.setProperty("tone", tone)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def status_tone(state: str) -> str:
    normalized = state.casefold()
    if "feil" in normalized or normalized in {"failed", "error"}:
        return "danger"
    if normalized in {"busy", "running", "kjører", "pågår"}:
        return "working"
    if any(word in normalized for word in ("ikke klar", "oppsett", "delvis", "mangler")):
        return "warning"
    if normalized in {"fullført", "publisert", "gyldig", "succeeded"}:
        return "success"
    return "neutral"
