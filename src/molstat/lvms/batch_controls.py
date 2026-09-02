from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from molstat.lvms.control_identity import ControlIdentity


class BatchControlError(ValueError):
    """A batch document or control identity is unsafe."""


_FRAME_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,120}")
_CONTROL_FIELDS = frozenset(
    {"tag", "type", "id", "name", "role", "label", "locator"}
)
_ALLOWED_TAGS = frozenset(
    {"A", "BUTTON", "INPUT", "SELECT", "SPAN", "TD", "TEXTAREA"}
)


@dataclass(frozen=True)
class DocumentControlIdentity:
    frame: str
    control: ControlIdentity


def validate_document_control(
    identity: DocumentControlIdentity,
) -> DocumentControlIdentity:
    if (
        not isinstance(identity, DocumentControlIdentity)
        or not isinstance(identity.frame, str)
        or _FRAME_PATTERN.fullmatch(identity.frame) is None
        or not isinstance(identity.control, ControlIdentity)
    ):
        raise BatchControlError("batch control identity is invalid")
    return identity


def _bounded_text(value: object) -> str:
    if not isinstance(value, str) or len(value.strip()) > 120:
        raise BatchControlError("batch control metadata is invalid")
    return value.strip()


def sanitize_document_control(raw: object) -> DocumentControlIdentity:
    if not isinstance(raw, Mapping) or set(raw) != {"frame", "control"}:
        raise BatchControlError("batch document metadata is invalid")
    control_raw = raw["control"]
    if not isinstance(control_raw, Mapping) or set(control_raw) != _CONTROL_FIELDS:
        raise BatchControlError("batch control metadata is invalid")
    tag = _bounded_text(control_raw["tag"]).upper()
    control_type = _bounded_text(control_raw["type"]).lower()
    locator = control_raw["locator"]
    if (
        tag not in _ALLOWED_TAGS
        or control_type in {"hidden", "password"}
        or not isinstance(locator, list)
        or not 1 <= len(locator) <= 12
    ):
        raise BatchControlError("batch control metadata is invalid")
    safe_locator = tuple(_bounded_text(part) for part in locator)
    if any(not part for part in safe_locator):
        raise BatchControlError("batch control metadata is invalid")
    return validate_document_control(
        DocumentControlIdentity(
            frame=_bounded_text(raw["frame"]),
            control=ControlIdentity(
                tag=tag,
                control_type=control_type,
                element_id=_bounded_text(control_raw["id"]),
                name=_bounded_text(control_raw["name"]),
                role=_bounded_text(control_raw["role"]),
                label=_bounded_text(control_raw["label"]),
                locator=safe_locator,
            ),
        )
    )

