from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from molstat.lvms.batch_controls import (
    BatchControlError,
    DocumentControlIdentity,
    sanitize_document_control,
)


class BatchNavigationError(RuntimeError):
    """The Defined Reports page could not be reached safely."""


DEFINED_REPORTS_LABEL = "Definerte rapporter"
REPORTS_SECTION_LABEL = "Eksterne rapporter"
MORE_LABEL = "Mer"
_NAVIGATION_LABELS = frozenset(
    {DEFINED_REPORTS_LABEL, REPORTS_SECTION_LABEL, MORE_LABEL}
)


class SafePage(Protocol):
    def current_origin(self) -> str: ...

    def evaluate_safe(
        self, expression: str, *, timeout_seconds: float = 2
    ) -> object: ...


class NavigationActions(Protocol):
    def activate(self, identity: DocumentControlIdentity) -> None: ...

    def hover(self, identity: DocumentControlIdentity) -> None: ...


@dataclass(frozen=True)
class DefinedReportsPage:
    job_type: DocumentControlIdentity
    clear: DocumentControlIdentity
    export: DocumentControlIdentity


_IDENTITY_SCRIPT = r"""
  const clean = (text) => String(text || "").replace(/\s+/g, " ").trim().toLowerCase();
  const visible = (el) => {
    const style = el.ownerDocument.defaultView.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      rect.width > 0 && rect.height > 0 && !el.disabled;
  };
  const locator = (el) => {
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 12) {
      let part = clean(node.tagName);
      const id = String(node.getAttribute("id") || "").trim();
      const name = String(node.getAttribute("name") || "").trim();
      if (id) part += "#" + id;
      else if (name) part += "[name=" + name + "]";
      else if (node.parentElement) part += ":nth-child(" +
        (Array.from(node.parentElement.children).indexOf(node) + 1) + ")";
      parts.unshift(part.slice(0, 120));
      if (id) break;
      node = node.parentElement;
    }
    return parts;
  };
  const label = (el) => {
    const aria = el.getAttribute("aria-label");
    if (aria) return clean(aria).slice(0, 120);
    if (el.labels && el.labels.length) return clean(Array.from(el.labels)
      .map((item) => item.textContent).join(" ")).slice(0, 120);
    const container = el.closest("td,th,[role='cell'],[role='gridcell']");
    const previous = container ? container.previousElementSibling : null;
    if (previous && !previous.querySelector("input,select,textarea,button,a"))
      return clean(previous.textContent).slice(0, 120);
    return "";
  };
  const identity = (el, frame) => ({
    frame,
    control: {
      tag: String(el.tagName || "").slice(0, 120),
      type: String(el.getAttribute("type") || "").trim().toLowerCase().slice(0, 120),
      id: String(el.getAttribute("id") || "").trim().slice(0, 120),
      name: String(el.getAttribute("name") || "").trim().slice(0, 120),
      role: String(el.getAttribute("role") || "").trim().slice(0, 120),
      label: label(el),
      locator: locator(el)
    }
  });
"""


DEFINED_REPORTS_PAGE_SCRIPT = (
    r"""
(() => {
  /* LVMS_DEFINED_REPORTS_PAGE */
"""
    + _IDENTITY_SCRIPT
    + r"""
  const documents = [{frame: "top", document}];
  for (const frame of Array.from(document.querySelectorAll("iframe,frame"))) {
    if (!visible(frame)) continue;
    const frameName = String(
      frame.getAttribute("id") || frame.getAttribute("name") || ""
    ).trim();
    if (!/^[A-Za-z0-9_-]{1,120}$/.test(frameName)) continue;
    try {
      const frameDocument = frame.contentDocument;
      if (frameDocument && frameDocument.documentElement)
        documents.push({frame: frameName, document: frameDocument});
    } catch (error) {
      continue;
    }
  }
  const jobTypes = [];
  const clears = [];
  const exports = [];
  for (const entry of documents) {
    for (const control of Array.from(entry.document.querySelectorAll(
      "input[name='menu'][data-datafield='reportType' i]"
    )).filter(visible)) jobTypes.push({frame: entry.frame, control});
    for (const control of Array.from(entry.document.querySelectorAll(
      "button#clear[name='menu'][type='button']"
    )).filter(visible)) clears.push({frame: entry.frame, control});
    for (const control of Array.from(entry.document.querySelectorAll(
      "button#export[name='menu'][type='button']"
    )).filter(visible)) exports.push({frame: entry.frame, control});
  }
  if (!jobTypes.length) return {missing: "job_type"};
  if (!clears.length) return {missing: "clear"};
  if (!exports.length) return {missing: "export"};
  return {
    job_type: identity(jobTypes[0].control, jobTypes[0].frame),
    clear: identity(clears[0].control, clears[0].frame),
    export: identity(exports[0].control, exports[0].frame)
  };
})()
"""
).strip()


def _navigation_anchor_script(label: str) -> str:
    encoded_label = json.dumps(label)
    return (
        r"""
(() => {
  /* LVMS_NAVIGATION_ANCHOR */
"""
        + _IDENTITY_SCRIPT
        + f"""
  const wanted = {encoded_label};
  const normalizedWanted = clean(wanted);
  const documents = [{{frame: "top", document}}];
  for (const frame of Array.from(document.querySelectorAll("iframe,frame"))) {{
    if (!visible(frame)) continue;
    const frameName = String(
      frame.getAttribute("id") || frame.getAttribute("name") || ""
    ).trim();
    if (!/^[A-Za-z0-9_-]{{1,120}}$/.test(frameName)) continue;
    try {{
      const frameDocument = frame.contentDocument;
      if (frameDocument && frameDocument.documentElement)
        documents.push({{frame: frameName, document: frameDocument}});
    }} catch (error) {{
      continue;
    }}
  }}
  const matches = [];
  for (const entry of documents) {{
    for (const control of Array.from(
      entry.document.querySelectorAll(
        "td.sitemap_TramStopNormText,td,a,button,span"
      )
    )) {{
      if (!visible(control)) continue;
      const exactControl = clean(control.textContent) === normalizedWanted;
      const exactDescendant = Array.from(control.querySelectorAll("*"))
        .some((node) => visible(node) && clean(node.textContent) === normalizedWanted);
      if (exactControl || exactDescendant)
        matches.push({{frame: entry.frame, control}});
    }}
  }}
  const tramLine = normalizedWanted === clean("Definerte rapporter")
    ? matches.find((match) => match.control.matches(
        "td.sitemap_TramStopNormText"
      ))
    : null;
  const selected = tramLine || matches[0];
  return selected ? identity(selected.control, selected.frame) : null;
}})()
"""
    ).strip()


def _require_origin(page: SafePage, expected_origin: str) -> None:
    if page.current_origin() != expected_origin:
        raise BatchNavigationError("Edge reached an unexpected origin")


def _document(raw: object) -> DocumentControlIdentity:
    try:
        return sanitize_document_control(raw)
    except BatchControlError as exc:
        raise BatchNavigationError("Defined Reports metadata is invalid") from exc


def discover_defined_reports_page(
    page: SafePage, expected_origin: str
) -> DefinedReportsPage | None:
    _require_origin(page, expected_origin)
    raw = page.evaluate_safe(DEFINED_REPORTS_PAGE_SCRIPT, timeout_seconds=10)
    if raw is None:
        return None
    if isinstance(raw, Mapping) and set(raw) == {"missing"}:
        missing = raw["missing"]
        if missing in {"job_type", "clear", "export"}:
            raise BatchNavigationError(
                f"Defined Reports {missing} is missing"
            )
    if not isinstance(raw, Mapping) or set(raw) != {"job_type", "clear", "export"}:
        raise BatchNavigationError("Defined Reports metadata is invalid")
    job_type = _document(raw["job_type"])
    clear = _document(raw["clear"])
    export = _document(raw["export"])
    return DefinedReportsPage(job_type, clear, export)


def discover_navigation_anchor(
    page: SafePage, expected_origin: str, label: str
) -> DocumentControlIdentity | None:
    if label not in _NAVIGATION_LABELS:
        raise BatchNavigationError("navigation label is not allowed")
    _require_origin(page, expected_origin)
    raw = page.evaluate_safe(_navigation_anchor_script(label), timeout_seconds=5)
    if raw is None:
        return None
    identity = _document(raw)
    is_more_span = label == MORE_LABEL and identity.control.tag == "SPAN"
    is_defined_reports_tram = (
        label == DEFINED_REPORTS_LABEL and identity.control.tag == "TD"
    )
    if identity.control.tag not in {"A", "BUTTON"} and not (
        is_more_span or is_defined_reports_tram
    ):
        raise BatchNavigationError("navigation control is invalid")
    return identity


class DefinedReportsNavigator:
    def __init__(
        self,
        expected_origin: str,
        *,
        timeout_seconds: float = 20,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise BatchNavigationError("navigation timeout is invalid")
        self._expected_origin = expected_origin
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._sleep = sleep

    def reach(
        self,
        page: SafePage,
        actions: NavigationActions,
        *,
        stage: Callable[[str], None] = lambda value: None,
    ) -> DefinedReportsPage:
        deadline = self._clock() + self._timeout_seconds
        used_more = False
        hovered_section = False
        activated_section = False
        used_defined_reports = False
        last_missing_control: str | None = None
        while self._clock() < deadline:
            try:
                current_origin = page.current_origin()
            except Exception:
                stage("defined_reports_contract_evaluation")
                raise
            if current_origin != self._expected_origin:
                stage("defined_reports_wait_origin")
                self._sleep(0.1)
                continue
            stage(
                "defined_reports_wait_form"
                if used_defined_reports
                else "defined_reports_probe_form"
            )
            try:
                contract = discover_defined_reports_page(
                    page, self._expected_origin
                )
            except BatchNavigationError as exc:
                error = str(exc)
                if error == "Edge reached an unexpected origin":
                    stage("defined_reports_contract_origin")
                    raise
                elif error.startswith("Defined Reports ") and error.endswith(
                    " is missing"
                ):
                    missing = error.removeprefix("Defined Reports ").removesuffix(
                        " is missing"
                    )
                    if missing not in {"job_type", "clear", "export"}:
                        stage("defined_reports_contract_metadata")
                        raise
                    last_missing_control = missing
                    stage(f"defined_reports_missing_{missing}")
                    contract = None
                    if used_defined_reports:
                        self._sleep(0.1)
                        continue
                else:
                    stage("defined_reports_contract_metadata")
                    raise
            except Exception:
                stage("defined_reports_contract_evaluation")
                raise
            if contract is not None:
                stage("defined_reports_ready")
                return contract
            if used_defined_reports:
                self._sleep(0.1)
                continue
            if not used_defined_reports:
                stage("defined_reports_find_direct")
                anchor = discover_navigation_anchor(
                    page, self._expected_origin, DEFINED_REPORTS_LABEL
                )
                if anchor is not None:
                    stage("defined_reports_activate_direct")
                    actions.activate(anchor)
                    used_defined_reports = True
                    stage("defined_reports_wait_form")
                    _require_origin(page, self._expected_origin)
                    self._sleep(0.1)
                    continue
            if not activated_section:
                stage("defined_reports_find_section")
                anchor = discover_navigation_anchor(
                    page, self._expected_origin, REPORTS_SECTION_LABEL
                )
                if anchor is not None:
                    if not hovered_section:
                        stage("defined_reports_hover_section")
                        actions.hover(anchor)
                        hovered_section = True
                    else:
                        stage("defined_reports_activate_section")
                        actions.activate(anchor)
                        activated_section = True
                    _require_origin(page, self._expected_origin)
                    self._sleep(0.1)
                    continue
            if not used_more:
                stage("defined_reports_find_more")
                anchor = discover_navigation_anchor(
                    page, self._expected_origin, MORE_LABEL
                )
                if anchor is not None:
                    stage("defined_reports_activate_more")
                    actions.activate(anchor)
                    used_more = True
                    _require_origin(page, self._expected_origin)
                    self._sleep(0.1)
                    continue
            self._sleep(0.1)
        if last_missing_control is not None:
            stage(f"defined_reports_missing_{last_missing_control}")
            raise BatchNavigationError(
                f"Defined Reports {last_missing_control} is missing"
            )
        raise BatchNavigationError("Defined Reports navigation timed out")

