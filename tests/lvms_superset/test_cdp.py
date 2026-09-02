from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from molstat.lvms.batch_controls import DocumentControlIdentity
from molstat.lvms.cdp import (
    BrowserPage,
    CdpConnection,
    CdpProtocolError,
    CdpNavigationError,
    CdpTimeout,
    PageIdentity,
    discover_page,
)
from molstat.lvms.control_identity import ControlIdentity


class FakeSocket:
    def __init__(self, messages: list[str]) -> None:
        self.messages = list(messages)
        self.sent: list[dict[str, object]] = []
        self.closed = False

    def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    def recv(self) -> str:
        return self.messages.pop(0)

    def settimeout(self, timeout: float) -> None:
        del timeout

    def close(self) -> None:
        self.closed = True


class FakeHttpResponse:
    def __init__(self, payload: object) -> None:
        self.stream = BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)


class FakeCdp:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def call(
        self,
        method: str,
        params: dict[str, object] | None = None,
        *,
        timeout_seconds: float = 10,
    ) -> dict[str, object]:
        del timeout_seconds
        self.calls.append((method, params))
        return self.responses.pop(0)


def evaluated(value: object) -> dict[str, object]:
    return {"result": {"value": value}}


class CdpTests(unittest.TestCase):
    def test_matches_response_to_command_id(self) -> None:
        socket = FakeSocket(
            [
                '{"method":"Page.loadEventFired","params":{}}',
                '{"id":1,"result":{"result":{"value":"ready"}}}',
            ]
        )
        connection = CdpConnection(socket)

        result = connection.call(
            "Runtime.evaluate", {"expression": "document.readyState"}
        )

        self.assertEqual(result["result"]["value"], "ready")
        self.assertEqual(socket.sent[0]["id"], 1)

    def test_sanitizes_protocol_errors(self) -> None:
        socket = FakeSocket(
            ['{"id":1,"error":{"message":"patient-bearing internal detail"}}']
        )
        connection = CdpConnection(socket)

        with self.assertRaisesRegex(CdpProtocolError, "rejected Runtime.evaluate") as caught:
            connection.call("Runtime.evaluate")

        self.assertNotIn("patient-bearing", str(caught.exception))

    def test_discovers_only_loopback_page_target(self) -> None:
        payload = [
            {
                "type": "page",
                "id": "page-1",
                "webSocketDebuggerUrl": "ws://127.0.0.1:49152/devtools/page/page-1",
            }
        ]

        target = discover_page(
            49152,
            opener=lambda request, timeout: FakeHttpResponse(payload),
        )

        self.assertEqual(target.target_id, "page-1")
        self.assertEqual(target.port, 49152)

    def test_discovers_os_selected_non_privileged_loopback_port(self) -> None:
        payload = [
            {
                "type": "page",
                "id": "page-low",
                "webSocketDebuggerUrl": "ws://127.0.0.1:15142/devtools/page/page-low",
            }
        ]

        target = discover_page(
            15142, opener=lambda request, timeout: FakeHttpResponse(payload)
        )

        self.assertEqual(target.port, 15142)

    def test_rejects_non_loopback_websocket_target(self) -> None:
        payload = [
            {
                "type": "page",
                "id": "page-1",
                "webSocketDebuggerUrl": "ws://remote.invalid:49152/devtools/page/page-1",
            }
        ]

        with self.assertRaisesRegex(CdpProtocolError, "unsafe page target"):
            discover_page(
                49152,
                opener=lambda request, timeout: FakeHttpResponse(payload),
            )

    def test_navigation_returns_origin_and_capped_title(self) -> None:
        cdp = FakeCdp(
            [
                {},
                {},
                {},
                evaluated("complete"),
                evaluated("https://lvms.example.invalid"),
                evaluated("L" * 200),
            ]
        )
        page = BrowserPage(cdp)

        identity = page.navigate(
            "https://lvms.example.invalid/",
            "https://lvms.example.invalid",
            timeout_seconds=1,
            clock=lambda: 0,
            sleep=lambda seconds: None,
        )

        self.assertEqual(identity.origin, "https://lvms.example.invalid")
        self.assertEqual(identity.title, "L" * 120)

    def test_navigation_allows_transient_sso_origin(self) -> None:
        cdp = FakeCdp(
            [
                {},
                {},
                {},
                evaluated("complete"),
                evaluated("https://sso.example.invalid"),
                evaluated("complete"),
                evaluated("https://lvms.example.invalid"),
                evaluated("LVMS"),
            ]
        )
        ticks = iter((0.0, 0.0, 0.1))
        page = BrowserPage(cdp)

        identity = page.navigate(
            "https://lvms.example.invalid/",
            "https://lvms.example.invalid",
            timeout_seconds=1,
            clock=lambda: next(ticks),
            sleep=lambda seconds: None,
        )

        self.assertEqual(identity, PageIdentity("https://lvms.example.invalid", "LVMS"))

    def test_navigation_exposes_only_bounded_network_error_category(self) -> None:
        page = BrowserPage(
            FakeCdp([{}, {}, {"errorText": "net::ERR_NAME_NOT_RESOLVED private-url"}])
        )

        with self.assertRaises(CdpNavigationError) as caught:
            page.navigate(
                "https://lvms.example.invalid/",
                "https://lvms.example.invalid",
            )

        self.assertEqual(str(caught.exception), "Edge navigation failed: net::ERR_NAME_NOT_RESOLVED")
        self.assertEqual(caught.exception.category, "net::ERR_NAME_NOT_RESOLVED")
        self.assertNotIn("private-url", str(caught.exception))

    def test_navigation_times_out_when_sso_never_returns_to_expected_origin(self) -> None:
        cdp = FakeCdp(
            [
                {},
                {},
                {},
                evaluated("complete"),
                evaluated("https://unexpected.invalid"),
            ]
        )
        ticks = iter((0.0, 0.0, 1.0))
        page = BrowserPage(cdp)

        with self.assertRaises(CdpTimeout) as caught:
            page.navigate(
                "https://lvms.example.invalid/",
                "https://lvms.example.invalid",
                timeout_seconds=1,
                clock=lambda: next(ticks),
                sleep=lambda seconds: None,
            )

        self.assertEqual(str(caught.exception), "SSO did not return to the expected origin")

    def test_exposes_only_bounded_safe_evaluation_and_origin(self) -> None:
        cdp = FakeCdp([evaluated({"safe": True}), evaluated("https://lvms.example.invalid")])
        page = BrowserPage(cdp)
        self.assertEqual(page.evaluate_safe("({safe: true})"), {"safe": True})
        self.assertEqual(page.current_origin(), "https://lvms.example.invalid")

    def test_current_origin_rejects_non_string(self) -> None:
        page = BrowserPage(FakeCdp([evaluated({"origin": "unsafe"})]))
        with self.assertRaisesRegex(CdpProtocolError, "invalid origin"):
            page.current_origin()

    def test_configures_absolute_owned_download_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory).resolve() / "inbox"
            cdp = FakeCdp([{}])
            page = BrowserPage(cdp)

            page.configure_downloads(directory)

            self.assertTrue(directory.is_dir())
            self.assertEqual(
                cdp.calls[-1],
                (
                    "Browser.setDownloadBehavior",
                    {
                        "behavior": "allow",
                        "downloadPath": str(directory),
                        "eventsEnabled": True,
                    },
                ),
            )

    def test_rejects_relative_download_directory(self) -> None:
        with self.assertRaisesRegex(CdpProtocolError, "absolute"):
            BrowserPage(FakeCdp([])).configure_downloads(Path("relative"))

    def test_insert_text_uses_cdp_input_without_evaluating_page_content(self) -> None:
        cdp = FakeCdp([{}])
        page = BrowserPage(cdp)

        page.insert_text("ANALYSIS-A")

        self.assertEqual(cdp.calls, [("Input.insertText", {"text": "ANALYSIS-A"})])

    def test_press_key_is_limited_to_enter_and_tab(self) -> None:
        for key in ("ENTER", "TAB"):
            with self.subTest(key=key):
                cdp = FakeCdp([{}, {}])
                BrowserPage(cdp).press_key(key)
                self.assertEqual(cdp.calls[0][0], "Input.dispatchKeyEvent")
                self.assertEqual(cdp.calls[1][0], "Input.dispatchKeyEvent")

        with self.assertRaisesRegex(CdpProtocolError, "unsupported key"):
            BrowserPage(FakeCdp([])).press_key("DELETE")

    def test_resolves_control_in_one_named_accessible_frame(self) -> None:
        cdp = FakeCdp([evaluated(1)])
        page = BrowserPage(cdp)

        token = page.resolve_document_control(
            DocumentControlIdentity(
                "_nav_frame1",
                ControlIdentity("BUTTON", element_id="export"),
            )
        )

        self.assertIsNotNone(token)
        expression = cdp.calls[0][1]["expression"]  # type: ignore[index]
        self.assertIn("contentDocument", expression)
        self.assertIn("_nav_frame1", expression)
        self.assertNotIn(".src", expression)
        self.assertIn("visible(frame)", expression)
        self.assertIn("!el.disabled", expression)
        self.assertNotIn("!el.readOnly", expression)
        self.assertNotIn("!previous.querySelector", expression)
        self.assertIn('previous.querySelector("input,select,textarea")', expression)
        self.assertIn("previousControl.value", expression)

    def test_document_resolution_requires_exactly_one_match(self) -> None:
        identity = DocumentControlIdentity(
            "_nav_frame1", ControlIdentity("BUTTON", element_id="export")
        )
        for count in (0, 2):
            with self.subTest(count=count):
                page = BrowserPage(FakeCdp([evaluated(count)]))
                self.assertIsNone(page.resolve_document_control(identity))

    def test_document_resolution_supports_top_without_frame_content_access(self) -> None:
        cdp = FakeCdp([evaluated(1)])

        token = BrowserPage(cdp).resolve_document_control(
            DocumentControlIdentity(
                "top", ControlIdentity("SELECT", element_id="jobtypeselector")
            )
        )

        self.assertIsNotNone(token)
        expression = cdp.calls[0][1]["expression"]  # type: ignore[index]
        self.assertIn('wanted.frame === "top"', expression)
        self.assertIn("try", expression)

    def test_document_resolution_can_resolve_lvms_more_span(self) -> None:
        cdp = FakeCdp([evaluated(1)])

        token = BrowserPage(cdp).resolve_document_control(
            DocumentControlIdentity("top", ControlIdentity("SPAN"))
        )

        self.assertIsNotNone(token)
        expression = cdp.calls[0][1]["expression"]  # type: ignore[index]
        self.assertIn('"a,button,input,select,span,td,textarea"', expression)

    def test_focus_requires_control_to_become_active_in_its_own_document(self) -> None:
        cdp = FakeCdp([evaluated("focus-failed")])

        with self.assertRaisesRegex(CdpProtocolError, "no longer available"):
            BrowserPage(cdp).focus_control("a" * 32)

        expression = cdp.calls[0][1]["expression"]  # type: ignore[index]
        self.assertIn("control.ownerDocument.activeElement", expression)

    def test_activate_dispatches_real_pointer_click(self) -> None:
        cdp = FakeCdp([evaluated({"x": 88.0, "y": 44.0}), {}, {}, {}])

        BrowserPage(cdp).activate_control("a" * 32)

        self.assertEqual(
            cdp.calls[1:],
            [
                (
                    "Input.dispatchMouseEvent",
                    {"type": "mouseMoved", "x": 88.0, "y": 44.0},
                ),
                (
                    "Input.dispatchMouseEvent",
                    {
                        "type": "mousePressed",
                        "x": 88.0,
                        "y": 44.0,
                        "button": "left",
                        "clickCount": 1,
                    },
                ),
                (
                    "Input.dispatchMouseEvent",
                    {
                        "type": "mouseReleased",
                        "x": 88.0,
                        "y": 44.0,
                        "button": "left",
                        "clickCount": 1,
                    },
                ),
            ],
        )

    def test_hover_moves_the_real_pointer_to_the_resolved_control(self) -> None:
        cdp = FakeCdp([evaluated({"x": 125.5, "y": 42.25}), {}])
        page = BrowserPage(cdp)

        page.hover_control("a" * 32)

        self.assertEqual(cdp.calls[1], (
            "Input.dispatchMouseEvent",
            {"type": "mouseMoved", "x": 125.5, "y": 42.25},
        ))
        expression = cdp.calls[0][1]["expression"]  # type: ignore[index]
        self.assertIn("scrollIntoView", expression)
        self.assertIn("frameElement", expression)

    def test_native_select_detection_is_safe_across_frame_realms(self) -> None:
        cdp = FakeCdp([evaluated("selected")])

        selected = BrowserPage(cdp).choose_native_option(
            "a" * 32, "CATEGORY_A"
        )

        self.assertTrue(selected)
        expression = cdp.calls[0][1]["expression"]  # type: ignore[index]
        self.assertIn('control.tagName !== "SELECT"', expression)
        self.assertNotIn("instanceof HTMLSelectElement", expression)

    def test_connection_close_surfaces_sanitized_failure(self) -> None:
        class BrokenCloseSocket(FakeSocket):
            def close(self) -> None:
                raise OSError("private socket detail")

        connection = CdpConnection(BrokenCloseSocket([]))
        with self.assertRaisesRegex(CdpProtocolError, "did not close") as caught:
            connection.close()
        self.assertNotIn("private socket detail", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

