import json
from http.client import HTTPConnection

import pytest

from molstat.web import BoardServer


@pytest.fixture
def server():
    instance = BoardServer(
        lambda: {
            "schemaVersion": 1,
            "generatedAt": "2026-09-02T08:00:00",
            "unitLabel": "MolPat hemato",
            "isStale": False,
            "totals": {
                "ready": 3,
                "awaitingApproval": 1,
                "inTransit": 2,
                "overdue": 0,
            },
            "emptyAnalysisCount": 0,
            "analyses": [],
        },
        host="127.0.0.1",
        port=0,
    )
    instance.start()
    try:
        yield instance
    finally:
        instance.stop()


def _request(server: BoardServer, method: str, path: str):
    connection = HTTPConnection("127.0.0.1", server.port, timeout=3)
    connection.request(method, path)
    response = connection.getresponse()
    body = response.read()
    headers = dict(response.getheaders())
    connection.close()
    return response.status, headers, body


def test_snapshot_endpoint_returns_only_provider_contract(server: BoardServer) -> None:
    status, headers, body = _request(server, "GET", "/api/v1/snapshot")

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert json.loads(body)["schemaVersion"] == 1
    assert "sample" not in body.decode().casefold()


def test_board_health_head_and_security_headers(server: BoardServer) -> None:
    health_status, _, health = _request(server, "GET", "/healthz")
    board_status, headers, board = _request(server, "GET", "/board")
    head_status, _, head = _request(server, "HEAD", "/api/v1/snapshot")

    assert health_status == 200
    assert json.loads(health) == {"status": "ok"}
    assert board_status == 200
    assert b"MolStat" in board
    assert head_status == 200
    assert head == b""
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert "Access-Control-Allow-Origin" not in headers


def test_server_only_serves_allowlisted_assets_and_methods(server: BoardServer) -> None:
    assert _request(server, "GET", "/assets/board.css")[0] == 200
    assert _request(server, "GET", "/assets/board.js")[0] == 200
    assert _request(server, "POST", "/api/v1/snapshot")[0] == 405
    assert _request(server, "GET", "/unknown")[0] == 404
    assert _request(server, "GET", "/assets/other.js")[0] == 404
    assert _request(server, "GET", "/assets/%2e%2e/settings.json")[0] == 404


@pytest.mark.parametrize("host", ["0.0.0.0", "10.0.0.8", "molstat.internal"])
def test_non_loopback_binding_fails_closed(host: str) -> None:
    with pytest.raises(ValueError, match="lokal"):
        BoardServer(lambda: {}, host=host, port=8765)
