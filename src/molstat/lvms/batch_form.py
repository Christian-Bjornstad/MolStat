from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Protocol

from molstat.lvms.batch_controls import (
    BatchControlError,
    DocumentControlIdentity,
    sanitize_document_control,
)
from molstat.lvms.batch_navigation import DefinedReportsPage
from molstat.lvms.report_job import ReportJob


class BatchFormError(RuntimeError):
    """The dynamic report form could not be populated safely."""


_ROLE_ALIASES = {
    "category": ("category", "kategori"),
    "report_id": ("report id", "rapport id"),
    "notes": ("notes", "notater"),
    "analysis_codes": ("analyses", "angi analyse(r)"),
    "created_from": ("created from", "analyse opprettet fom:"),
    "created_to": ("created to", "analyse opprettet tom:"),
}
_CLEAR_DYNAMIC_ROLES = ("analysis_codes", "created_from", "created_to")
_ROLE_TAGS = {
    "category": frozenset({"INPUT", "SELECT"}),
    "report_id": frozenset({"INPUT", "SELECT"}),
    "notes": frozenset({"INPUT", "TEXTAREA"}),
    "analysis_codes": frozenset({"INPUT", "TEXTAREA"}),
    "created_from": frozenset({"INPUT"}),
    "created_to": frozenset({"INPUT"}),
}
_ROLE_TYPES = {
    "category": frozenset({"", "text", "search"}),
    "report_id": frozenset({"", "text", "search"}),
    "notes": frozenset({"", "text", "search"}),
    "analysis_codes": frozenset({"", "text", "search"}),
    "created_from": frozenset({"", "text", "date"}),
    "created_to": frozenset({"", "text", "date"}),
}


class FormPage(Protocol):
    def current_origin(self) -> str: ...

    def evaluate_safe(
        self, expression: str, *, timeout_seconds: float = 2
    ) -> object: ...


class FormActions(Protocol):
    def activate(self, control: DocumentControlIdentity) -> None: ...

    def choose_text(self, control: DocumentControlIdentity, text: str) -> None: ...

    def commit_choice(self, control: DocumentControlIdentity) -> None: ...

    def replace_text(self, control: DocumentControlIdentity, text: str) -> None: ...


def _role_script(role: str) -> str:
    encoded_role = json.dumps(role)
    encoded_aliases = json.dumps(_ROLE_ALIASES[role], ensure_ascii=False)
    return rf"""
(() => {{
  /* LVMS_REPORT_ROLE */
  const requestedRole = {encoded_role};
  const aliases = {encoded_aliases};
  const clean = (text) => String(text || "").replace(/\s+/g, " ").trim().toLowerCase();
  const visible = (el) => {{
    const style = el.ownerDocument.defaultView.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      rect.width > 0 && rect.height > 0 && !el.disabled;
  }};
  const excluded = (el) => Boolean(el.closest(
    "[contenteditable='true']," +
    "[id*='patient' i],[class*='patient' i],[id*='sample' i]," +
    "[class*='sample' i],[id*='result' i],[class*='result' i]"
  ));
  const locator = (el) => {{
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 12) {{
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
    }}
    return parts;
  }};
  const label = (el) => {{
    const aria = el.getAttribute("aria-label");
    if (aria) return clean(aria).slice(0, 120);
    if (el.labels && el.labels.length) return clean(Array.from(el.labels)
      .map((item) => item.textContent).join(" ")).slice(0, 120);
    const container = el.closest("td,th,[role='cell'],[role='gridcell']");
    const previous = container ? container.previousElementSibling : null;
    if (previous) {{
      const text = clean(previous.textContent);
      if (text) return text.slice(0, 120);
      const previousControl = previous.querySelector("input,select,textarea");
      if (previousControl)
        return clean(previousControl.value).slice(0, 120);
    }}
    return "";
  }};
  const identity = (el, frame) => ({{
    frame,
    control: {{
      tag: String(el.tagName || "").slice(0, 120),
      type: String(el.getAttribute("type") || "").trim().toLowerCase().slice(0, 120),
      id: String(el.getAttribute("id") || "").trim().slice(0, 120),
      name: String(el.getAttribute("name") || "").trim().slice(0, 120),
      role: String(el.getAttribute("role") || "").trim().slice(0, 120),
      label: label(el),
      locator: locator(el)
    }}
  }});
  const documents = [{{frame: "top", document}}];
  for (const frame of document.querySelectorAll("iframe,frame")) {{
    if (!visible(frame)) continue;
    const frameName = String(
      frame.getAttribute("name") || frame.getAttribute("id") || ""
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
  const candidates = [];
  for (const item of documents) {{
    for (const control of item.document.querySelectorAll("input,select,textarea")) {{
      const text = label(control);
      const matchesAlias = aliases.some(
        (alias) => text === alias || text.startsWith(alias + " ")
      );
      if (visible(control) && !excluded(control) && matchesAlias)
        candidates.push(identity(control, item.frame));
    }}
  }}
  if (candidates.length === 0) return null;
  return candidates.length === 1 ? candidates[0] : {{ambiguous: true}};
}})()
""".strip()


def discover_report_role(
    page: FormPage, expected_origin: str, role: str
) -> DocumentControlIdentity | None:
    if role not in _ROLE_ALIASES:
        raise BatchFormError("report form role is invalid")
    if page.current_origin() != expected_origin:
        raise BatchFormError("Edge reached an unexpected origin")
    raw = page.evaluate_safe(_role_script(role), timeout_seconds=10)
    if raw is None:
        return None
    try:
        identity = sanitize_document_control(raw)
    except BatchControlError as exc:
        raise BatchFormError("report form control metadata is invalid") from exc
    control = identity.control
    label = " ".join(control.label.lower().split())
    aliases = _ROLE_ALIASES[role]
    if (
        control.tag not in _ROLE_TAGS[role]
        or (control.tag == "INPUT" and control.control_type not in _ROLE_TYPES[role])
        or control.role.lower() in {"grid", "treegrid"}
        or (
            control.role.lower() == "gridcell"
            and role not in _CLEAR_DYNAMIC_ROLES
        )
        or not any(label == alias or label.startswith(alias + " ") for alias in aliases)
    ):
        raise BatchFormError("report form control is incompatible")
    return identity


class BatchReportForm:
    def __init__(
        self,
        page: FormPage,
        actions: FormActions,
        expected_origin: str,
        *,
        timeout_seconds: float = 120,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise BatchFormError("report form timeout is invalid")
        self._page = page
        self._actions = actions
        self._expected_origin = expected_origin
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._sleep = sleep

    def _wait_for(self, role: str) -> DocumentControlIdentity:
        deadline = self._clock() + self._timeout_seconds
        while self._clock() < deadline:
            control = discover_report_role(
                self._page, self._expected_origin, role
            )
            if control is not None:
                return control
            self._sleep(0.1)
        raise BatchFormError("report form did not reach the required stage")

    def wait_until_clear(self) -> None:
        deadline = self._clock() + self._timeout_seconds
        while self._clock() < deadline:
            cleared = tuple(
                discover_report_role(self._page, self._expected_origin, role)
                is None
                for role in _CLEAR_DYNAMIC_ROLES
            )
            if all(cleared):
                # LVMS can briefly remove the parameter grid while rebuilding the
                # previous report after an export. Require a second clear state
                # before the next report starts against the form.
                self._sleep(1.0)
                stable = tuple(
                    discover_report_role(self._page, self._expected_origin, role)
                    is None
                    for role in _CLEAR_DYNAMIC_ROLES
                )
                if all(stable):
                    return
            self._sleep(0.1)
        raise BatchFormError("report form did not clear")

    def populate(self, page_contract: DefinedReportsPage, job: ReportJob) -> None:
        if not isinstance(page_contract, DefinedReportsPage) or not isinstance(
            job, ReportJob
        ):
            raise BatchFormError("report form input is invalid")
        self._actions.choose_text(page_contract.job_type, job.report_type)
        category = self._wait_for("category")
        self._actions.choose_text(category, job.category)
        report_id = self._wait_for("report_id")
        self._actions.choose_text(report_id, job.report_id)
        self._sleep(0.5)
        # LVMS rebuilds the parameter grid after a report choice.  On the
        # work computer that refresh sometimes replaced the SELECT with a
        # new, empty control before Enter was sent.  Reapply the choice to
        # the live control, then rediscover once more before committing it.
        report_id = self._wait_for("report_id")
        self._actions.choose_text(report_id, job.report_id)
        self._sleep(0.5)
        report_id = self._wait_for("report_id")
        self._actions.commit_choice(report_id)
        analysis_codes = self._wait_for("analysis_codes")
        created_from = self._wait_for("created_from")
        created_to = self._wait_for("created_to")
        start, end = job.interval.as_lvms()
        self._actions.replace_text(analysis_codes, job.analysis_text())
        self._actions.replace_text(created_from, start)
        self._sleep(0.5)
        created_to = self._wait_for("created_to")
        self._actions.replace_text(created_to, end)

