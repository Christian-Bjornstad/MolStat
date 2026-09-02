from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlIdentity:
    """Bounded metadata used to find one report control."""

    tag: str
    control_type: str = ""
    element_id: str = ""
    name: str = ""
    role: str = ""
    label: str = ""
    locator: tuple[str, ...] = ()

