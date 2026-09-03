from __future__ import annotations

import unittest
from pathlib import Path

from molstat.lvms.browser_session import open_owned_browser
from molstat.lvms.cdp import CdpTimeout, PageTarget


class FakeEdge:
    def __init__(self, port: int) -> None:
        self.port = port
        self.closed = False

    def close(self) -> None:
        self.closed = True


class BrowserSessionTests(unittest.TestCase):
    def test_retries_target_timeout_and_closes_failed_edge(self) -> None:
        first = FakeEdge(49152)
        second = FakeEdge(49153)
        edges = iter((first, second))
        waits: list[int] = []
        sleeps: list[float] = []

        def target_wait(port: int) -> PageTarget:
            waits.append(port)
            if port == 49152:
                raise CdpTimeout("stale broker")
            return PageTarget(
                "page-2",
                "ws://127.0.0.1:49153/devtools/page/page-2",
                49153,
            )

        result = open_owned_browser(
            Path("C:/Profiles/lvms"),
            attempts=2,
            edge_start=lambda _: next(edges),
            target_wait=target_wait,
            sleeper=sleeps.append,
        )

        self.assertTrue(first.closed)
        self.assertFalse(second.closed)
        self.assertIs(result.edge, second)
        self.assertEqual(result.target.target_id, "page-2")
        self.assertEqual(waits, [49152, 49153])
        self.assertEqual(sleeps, [1.5])


if __name__ == "__main__":
    unittest.main()

