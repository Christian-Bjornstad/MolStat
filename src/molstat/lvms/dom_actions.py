from __future__ import annotations

from typing import Protocol

from molstat.lvms.batch_controls import DocumentControlIdentity


class DomActionError(RuntimeError):
    """A requested report-page action could not be performed safely."""


class ActionPage(Protocol):
    def current_origin(self) -> str: ...

    def resolve_document_control(
        self, control: DocumentControlIdentity
    ) -> str | None: ...

    def focus_control(self, token: str) -> None: ...

    def activate_control(self, token: str) -> None: ...

    def hover_control(self, token: str) -> None: ...

    def replace_focused_text(self, text: str) -> None: ...

    def choose_native_option(self, token: str, text: str) -> bool: ...

    def press_key(self, key: str) -> None: ...


class DocumentDomActions:
    def __init__(self, page: ActionPage, expected_origin: str) -> None:
        self._page = page
        self._expected_origin = expected_origin

    def _require_expected_origin(self) -> None:
        if self._page.current_origin() != self._expected_origin:
            raise DomActionError("Edge reached an unexpected origin")

    def _resolve(self, control: DocumentControlIdentity) -> str:
        self._require_expected_origin()
        token = self._page.resolve_document_control(control)
        if token is None:
            raise DomActionError("report control is not uniquely available")
        return token

    def activate(self, control: DocumentControlIdentity) -> None:
        self._page.activate_control(self._resolve(control))

    def hover(self, control: DocumentControlIdentity) -> None:
        self._page.hover_control(self._resolve(control))

    def replace_text(self, control: DocumentControlIdentity, text: str) -> None:
        token = self._resolve(control)
        self._page.activate_control(token)
        self._page.replace_focused_text(text)

    def commit_choice(self, control: DocumentControlIdentity) -> None:
        token = self._resolve(control)
        self._page.activate_control(token)
        self._page.focus_control(token)
        self._page.press_key("ENTER")

    def choose_text(self, control: DocumentControlIdentity, text: str) -> None:
        token = self._resolve(control)
        if self._page.choose_native_option(token, text):
            return
        self._page.activate_control(token)
        self._page.focus_control(token)
        self._page.replace_focused_text(text)

