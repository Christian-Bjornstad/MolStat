from __future__ import annotations

from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit


_ASSET_ROOT = Path(__file__).with_name("web_assets")
_ROUTES = {
    "/board": ("text/html; charset=utf-8", _ASSET_ROOT / "board.html"),
    "/assets/board.css": ("text/css; charset=utf-8", _ASSET_ROOT / "board.css"),
    "/assets/board.js": (
        "text/javascript; charset=utf-8",
        _ASSET_ROOT / "board.js",
    ),
}
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class BoardServer:
    def __init__(
        self,
        snapshot_provider: Callable[[], dict[str, object]],
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        if host not in _LOOPBACK_HOSTS:
            raise ValueError("MolStat-tavlen er lokal inntil sikker deling er konfigurert.")
        self.snapshot_provider = snapshot_provider
        self.host = host
        self.requested_port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    @property
    def port(self) -> int:
        if self._server is None:
            return self.requested_port
        return int(self._server.server_address[1])

    def start(self) -> None:
        if self._server is not None:
            return
        provider = self.snapshot_provider

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self._respond(send_body=True)

            def do_HEAD(self) -> None:
                self._respond(send_body=False)

            def do_POST(self) -> None:
                self._method_not_allowed()

            def do_PUT(self) -> None:
                self._method_not_allowed()

            def do_PATCH(self) -> None:
                self._method_not_allowed()

            def do_DELETE(self) -> None:
                self._method_not_allowed()

            def _method_not_allowed(self) -> None:
                self.send_response(405)
                self.send_header("Allow", "GET, HEAD")
                self._security_headers()
                self.send_header("Content-Length", "0")
                self.end_headers()

            def _respond(self, *, send_body: bool) -> None:
                path = urlsplit(self.path).path
                if path == "/healthz":
                    self._send_json({"status": "ok"}, send_body=send_body)
                    return
                if path == "/api/v1/snapshot":
                    try:
                        payload = provider()
                    except Exception:
                        self._send_json(
                            {"status": "unavailable"},
                            status=503,
                            send_body=send_body,
                        )
                        return
                    self._send_json(payload, send_body=send_body)
                    return
                route = _ROUTES.get(path)
                if route is None:
                    self.send_response(404)
                    self._security_headers()
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                content_type, asset_path = route
                body = asset_path.read_bytes()
                self._send_bytes(
                    body,
                    content_type,
                    send_body=send_body,
                )

            def _send_json(
                self,
                payload: dict[str, object],
                *,
                status: int = 200,
                send_body: bool,
            ) -> None:
                body = json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                self._send_bytes(
                    body,
                    "application/json; charset=utf-8",
                    status=status,
                    send_body=send_body,
                )

            def _send_bytes(
                self,
                body: bytes,
                content_type: str,
                *,
                status: int = 200,
                send_body: bool,
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self._security_headers()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if send_body:
                    self.wfile.write(body)

            def _security_headers(self) -> None:
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "connect-src 'self'; object-src 'none'; base-uri 'none'; "
                    "frame-ancestors 'none'",
                )

            def log_message(self, format: str, *args: object) -> None:
                del format, args

        self._server = ThreadingHTTPServer((self.host, self.requested_port), Handler)
        self._thread = Thread(
            target=self._server.serve_forever,
            name="molstat-board",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=3)
