from __future__ import annotations

import json
import math
import re
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import websocket

from molstat.lvms.batch_controls import (
    BatchControlError,
    DocumentControlIdentity,
    validate_document_control,
)
from molstat.lvms.edge import EPHEMERAL_PORT_MAX, EPHEMERAL_PORT_MIN
from molstat.lvms.control_identity import ControlIdentity


MAX_DISCOVERY_BYTES = 64 * 1024
MAX_CDP_MESSAGE_CHARS = 1024 * 1024


class CdpError(RuntimeError):
    """The local Edge DevTools connection failed safely."""


class CdpProtocolError(CdpError):
    """Edge returned malformed or rejected DevTools data."""


class CdpTimeout(CdpError):
    """A bounded DevTools operation did not finish in time."""


_NETWORK_ERROR_PATTERN = re.compile(r"net::ERR_[A-Z0-9_]{1,80}")


class CdpNavigationError(CdpProtocolError):
    """Edge navigation failed with a bounded, non-sensitive network category."""

    def __init__(self, error_text: object) -> None:
        match = _NETWORK_ERROR_PATTERN.search(error_text if isinstance(error_text, str) else "")
        self.category = match.group(0) if match else "net::ERR_FAILED"
        super().__init__(f"Edge navigation failed: {self.category}")


@dataclass(frozen=True)
class PageTarget:
    target_id: str
    websocket_url: str
    port: int


@dataclass(frozen=True)
class PageIdentity:
    origin: str
    title: str


def _validate_ephemeral_port(port: int) -> None:
    if not isinstance(port, int) or not EPHEMERAL_PORT_MIN <= port <= EPHEMERAL_PORT_MAX:
        raise CdpProtocolError("DevTools port is not ephemeral")


def discover_page(
    port: int,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> PageTarget:
    _validate_ephemeral_port(port)
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/json/list",
        method="GET",
        headers={"Accept": "application/json"},
    )
    try:
        with opener(request, timeout=2) as response:
            payload_bytes = response.read(MAX_DISCOVERY_BYTES + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise CdpTimeout("Edge remote debugging is not available") from exc

    if len(payload_bytes) > MAX_DISCOVERY_BYTES:
        raise CdpProtocolError("Edge discovery response is too large")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CdpProtocolError("Edge discovery response is invalid") from exc
    if not isinstance(payload, list):
        raise CdpProtocolError("Edge discovery response is invalid")

    for item in payload:
        if not isinstance(item, dict) or item.get("type") != "page":
            continue
        target_id = item.get("id")
        websocket_url = item.get("webSocketDebuggerUrl")
        if not isinstance(target_id, str) or not isinstance(websocket_url, str):
            raise CdpProtocolError("Edge returned an unsafe page target")
        parsed = urlsplit(websocket_url)
        try:
            target_port = parsed.port
        except ValueError as exc:
            raise CdpProtocolError("Edge returned an unsafe page target") from exc
        if (
            parsed.scheme != "ws"
            or parsed.hostname != "127.0.0.1"
            or target_port != port
            or not parsed.path.startswith("/devtools/page/")
        ):
            raise CdpProtocolError("Edge returned an unsafe page target")
        return PageTarget(target_id=target_id, websocket_url=websocket_url, port=port)

    raise CdpTimeout("Edge has not created a page target")


def wait_for_page_target(
    port: int,
    *,
    timeout_seconds: float = 20,
    discover: Callable[[int], PageTarget] = discover_page,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> PageTarget:
    deadline = clock() + timeout_seconds
    while clock() < deadline:
        try:
            return discover(port)
        except CdpTimeout:
            sleep(0.2)
    raise CdpTimeout("Edge connection timed out")


class CdpConnection:
    def __init__(self, socket: Any) -> None:
        self._socket = socket
        self._next_id = 1
        self._pending: dict[int, dict[str, object]] = {}
        self._closed = False

    @classmethod
    def open(
        cls,
        target: PageTarget,
        *,
        socket_factory: Callable[..., Any] = websocket.create_connection,
    ) -> "CdpConnection":
        _validate_ephemeral_port(target.port)
        parsed = urlsplit(target.websocket_url)
        if parsed.hostname != "127.0.0.1" or parsed.port != target.port:
            raise CdpProtocolError("Edge returned an unsafe page target")
        try:
            socket = socket_factory(
                target.websocket_url,
                timeout=10,
                origin=f"http://127.0.0.1:{target.port}",
                enable_multithread=False,
            )
        except Exception as exc:
            raise CdpTimeout("Edge DevTools WebSocket is not available") from exc
        return cls(socket)

    def call(
        self,
        method: str,
        params: dict[str, object] | None = None,
        *,
        timeout_seconds: float = 10,
    ) -> dict[str, object]:
        if self._closed:
            raise CdpProtocolError("Edge DevTools connection is closed")
        if not method or timeout_seconds <= 0:
            raise CdpProtocolError("invalid DevTools command")

        command_id = self._next_id
        self._next_id += 1
        command: dict[str, object] = {"id": command_id, "method": method}
        if params is not None:
            command["params"] = params

        try:
            self._socket.send(json.dumps(command, separators=(",", ":")))
            self._socket.settimeout(timeout_seconds)
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                pending = self._pending.pop(command_id, None)
                if pending is not None:
                    return self._command_result(method, pending)

                raw_message = self._socket.recv()
                if not isinstance(raw_message, str) or len(raw_message) > MAX_CDP_MESSAGE_CHARS:
                    raise CdpProtocolError("Edge returned an invalid DevTools response")
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError as exc:
                    raise CdpProtocolError("Edge returned an invalid DevTools response") from exc
                if not isinstance(message, dict):
                    raise CdpProtocolError("Edge returned an invalid DevTools response")
                response_id = message.get("id")
                if isinstance(response_id, int):
                    if response_id == command_id:
                        return self._command_result(method, message)
                    self._pending[response_id] = message
                # Asynchronous events are intentionally ignored in this slice.
        except CdpError:
            raise
        except (TimeoutError, websocket.WebSocketTimeoutException) as exc:
            raise CdpTimeout(f"Edge timed out during {method}") from exc
        except Exception as exc:
            raise CdpProtocolError(f"Edge failed during {method}") from exc

        raise CdpTimeout(f"Edge timed out during {method}")

    @staticmethod
    def _command_result(method: str, message: dict[str, object]) -> dict[str, object]:
        if "error" in message:
            raise CdpProtocolError(f"Edge rejected {method}")
        result = message.get("result", {})
        if not isinstance(result, dict):
            raise CdpProtocolError(f"Edge returned an invalid result for {method}")
        return result

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._socket.close()
        except Exception as exc:
            raise CdpProtocolError("Edge DevTools connection did not close") from exc


class BrowserPage:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def _evaluate(self, expression: str, *, timeout_seconds: float) -> object:
        response = self._connection.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": False,
            },
            timeout_seconds=timeout_seconds,
        )
        remote_object = response.get("result")
        if not isinstance(remote_object, dict) or "value" not in remote_object:
            raise CdpProtocolError("Edge returned an invalid evaluation result")
        return remote_object["value"]

    def evaluate_safe(self, expression: str, *, timeout_seconds: float = 2) -> object:
        return self._evaluate(expression, timeout_seconds=timeout_seconds)

    def current_origin(self) -> str:
        origin = self._evaluate("location.origin", timeout_seconds=2)
        if not isinstance(origin, str):
            raise CdpProtocolError("Edge returned an invalid origin")
        return origin

    def configure_downloads(self, directory: Path) -> None:
        if not directory.is_absolute():
            raise CdpProtocolError("download directory must be absolute")
        resolved = directory.resolve()
        try:
            resolved.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise CdpProtocolError("download directory is unavailable") from exc
        self._connection.call(
            "Browser.setDownloadBehavior",
            {
                "behavior": "allow",
                "downloadPath": str(resolved),
                "eventsEnabled": True,
            },
            timeout_seconds=5,
        )

    @staticmethod
    def _validate_text(text: str, *, maximum: int = 50_000) -> None:
        if not isinstance(text, str) or len(text) > maximum or "\x00" in text:
            raise CdpProtocolError("input text is invalid")

    def insert_text(self, text: str) -> None:
        self._validate_text(text)
        self._connection.call(
            "Input.insertText", {"text": text}, timeout_seconds=5
        )

    def press_key(self, key: str) -> None:
        keys = {
            "ENTER": ("Enter", "Enter", 13),
            "TAB": ("Tab", "Tab", 9),
        }
        if key not in keys:
            raise CdpProtocolError("unsupported key")
        key_name, code, windows_code = keys[key]
        common: dict[str, object] = {
            "key": key_name,
            "code": code,
            "windowsVirtualKeyCode": windows_code,
            "nativeVirtualKeyCode": windows_code,
        }
        self._connection.call(
            "Input.dispatchKeyEvent", {"type": "rawKeyDown", **common}, timeout_seconds=5
        )
        self._connection.call(
            "Input.dispatchKeyEvent", {"type": "keyUp", **common}, timeout_seconds=5
        )

    @staticmethod
    def _control_payload(control: ControlIdentity) -> dict[str, object]:
        values = (
            control.tag,
            control.control_type,
            control.element_id,
            control.name,
            control.role,
            control.label,
        )
        if (
            not control.tag
            or any(not isinstance(value, str) or len(value) > 120 for value in values)
            or not isinstance(control.locator, tuple)
            or len(control.locator) > 12
            or any(not isinstance(part, str) or len(part) > 120 for part in control.locator)
        ):
            raise CdpProtocolError("report control identity is invalid")
        return {
            "tag": control.tag,
            "type": control.control_type,
            "id": control.element_id,
            "name": control.name,
            "role": control.role,
            "label": control.label,
            "locator": list(control.locator),
        }

    def resolve_document_control(
        self, identity: DocumentControlIdentity
    ) -> str | None:
        try:
            validated = validate_document_control(identity)
        except BatchControlError as exc:
            raise CdpProtocolError("report document identity is invalid") from exc
        payload = {
            "frame": validated.frame,
            **self._control_payload(validated.control),
        }
        serialized_identity = json.dumps(payload, separators=(",", ":"))
        token = secrets.token_hex(16)
        token_json = json.dumps(token)
        expression = rf"""
(() => {{
  const wanted = {serialized_identity};
  const clean = (text) => String(text || "").replace(/\s+/g, " ").trim().toLowerCase();
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
  const visible = (el) => {{
    const style = el.ownerDocument.defaultView.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      rect.width > 0 && rect.height > 0;
  }};
  let selectedDocument = wanted.frame === "top" ? document : null;
  if (!selectedDocument) {{
    const frames = Array.from(document.querySelectorAll("iframe,frame")).filter(
      (frame) => visible(frame) &&
        (String(frame.getAttribute("id") || "") === wanted.frame ||
          String(frame.getAttribute("name") || "") === wanted.frame)
    );
    if (frames.length !== 1) return 0;
    try {{
      selectedDocument = frames[0].contentDocument;
      if (!selectedDocument || !selectedDocument.documentElement) return 0;
    }} catch (error) {{
      return 0;
    }}
  }}
  const matches = Array.from(selectedDocument.querySelectorAll(
    "a,button,input,select,span,td,textarea"
  ))
    .filter((el) => visible(el) && !el.disabled &&
      el.tagName === wanted.tag &&
      String(el.getAttribute("type") || "").slice(0, 120) === wanted.type &&
      String(el.getAttribute("id") || "").slice(0, 120) === wanted.id &&
      String(el.getAttribute("name") || "").slice(0, 120) === wanted.name &&
      String(el.getAttribute("role") || "").slice(0, 120) === wanted.role &&
      label(el) === wanted.label && JSON.stringify(locator(el)) === JSON.stringify(wanted.locator));
  window.__LVMS_STAT_CONTROLS__ = new Map();
  if (matches.length === 1) window.__LVMS_STAT_CONTROLS__.set({token_json}, matches[0]);
  return matches.length;
}})()
"""
        count = self._evaluate(expression, timeout_seconds=5)
        return token if count == 1 else None

    def _use_control(self, token: str, operation: str) -> object:
        if not isinstance(token, str) or len(token) != 32:
            raise CdpProtocolError("report control token is invalid")
        token_json = json.dumps(token)
        expression = rf"""
(() => {{
  const controls = window.__LVMS_STAT_CONTROLS__;
  const control = controls instanceof Map ? controls.get({token_json}) : null;
  if (!control || !control.isConnected) return "missing";
  {operation}
}})()
"""
        return self._evaluate(expression, timeout_seconds=5)

    def focus_control(self, token: str) -> None:
        if self._use_control(
            token,
            'control.focus(); return control.ownerDocument.activeElement === control ? "ok" : "focus-failed";',
        ) != "ok":
            raise CdpProtocolError("report control is no longer available")

    def _control_point(self, token: str) -> dict[str, float]:
        point = self._use_control(
            token,
            r'''
control.scrollIntoView({block: "center", inline: "center"});
const rect = control.getBoundingClientRect();
let x = rect.left + rect.width / 2;
let y = rect.top + rect.height / 2;
let view = control.ownerDocument.defaultView;
while (view && view.frameElement) {
  const frameRect = view.frameElement.getBoundingClientRect();
  x += frameRect.left;
  y += frameRect.top;
  view = view.frameElement.ownerDocument.defaultView;
}
return {x, y};
''',
        )
        if (
            not isinstance(point, dict)
            or set(point) != {"x", "y"}
            or any(
                isinstance(point[key], bool)
                or not isinstance(point[key], (int, float))
                or not math.isfinite(point[key])
                or not 0 <= point[key] <= 100_000
                for key in ("x", "y")
            )
        ):
            raise CdpProtocolError("report control position is invalid")
        return {"x": float(point["x"]), "y": float(point["y"])}

    def activate_control(self, token: str) -> None:
        point = self._control_point(token)
        for params in (
            {"type": "mouseMoved", **point},
            {
                "type": "mousePressed",
                **point,
                "button": "left",
                "clickCount": 1,
            },
            {
                "type": "mouseReleased",
                **point,
                "button": "left",
                "clickCount": 1,
            },
        ):
            self._connection.call(
                "Input.dispatchMouseEvent", params, timeout_seconds=5
            )

    def hover_control(self, token: str) -> None:
        point = self._control_point(token)
        self._connection.call(
            "Input.dispatchMouseEvent",
            {"type": "mouseMoved", "x": point["x"], "y": point["y"]},
            timeout_seconds=5,
        )

    def choose_native_option(self, token: str, text: str) -> bool:
        self._validate_text(text, maximum=200)
        text_json = json.dumps(text)
        result = self._use_control(
            token,
            rf'''
if (control.tagName !== "SELECT") return "custom";
const matches = Array.from(control.options).filter(
  (option) => String(option.textContent || "").trim() === {text_json}
);
if (matches.length !== 1) return "option-missing";
control.selectedIndex = matches[0].index;
control.dispatchEvent(new Event("input", {{bubbles: true}}));
control.dispatchEvent(new Event("change", {{bubbles: true}}));
return "selected";
''',
        )
        if result == "selected":
            return True
        if result == "custom":
            return False
        raise CdpProtocolError("report option is not uniquely available")

    def replace_focused_text(self, text: str) -> None:
        self._validate_text(text)
        common: dict[str, object] = {
            "key": "a",
            "code": "KeyA",
            "windowsVirtualKeyCode": 65,
            "nativeVirtualKeyCode": 65,
            "modifiers": 2,
        }
        self._connection.call(
            "Input.dispatchKeyEvent", {"type": "rawKeyDown", **common}, timeout_seconds=5
        )
        self._connection.call(
            "Input.dispatchKeyEvent", {"type": "keyUp", **common}, timeout_seconds=5
        )
        self.insert_text(text)

    def navigate(
        self,
        landing_url: str,
        expected_origin: str,
        *,
        timeout_seconds: float = 30,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> PageIdentity:
        self._connection.call("Page.enable", timeout_seconds=timeout_seconds)
        self._connection.call("Runtime.enable", timeout_seconds=timeout_seconds)
        navigation = self._connection.call(
            "Page.navigate",
            {"url": landing_url},
            timeout_seconds=timeout_seconds,
        )
        if navigation.get("errorText"):
            raise CdpNavigationError(navigation["errorText"])

        deadline = clock() + timeout_seconds
        last_origin: object = None
        while clock() < deadline:
            state = self._evaluate(
                "document.readyState", timeout_seconds=min(2, timeout_seconds)
            )
            last_origin = self._evaluate("location.origin", timeout_seconds=2)
            if state in {"interactive", "complete"} and last_origin == expected_origin:
                break
            sleep(0.1)
        else:
            if last_origin != expected_origin:
                raise CdpTimeout("SSO did not return to the expected origin")
            raise CdpTimeout("Edge navigation timed out")

        title = self._evaluate("document.title", timeout_seconds=2)
        safe_title = title.strip()[:120] if isinstance(title, str) else ""
        return PageIdentity(origin=expected_origin, title=safe_title)

