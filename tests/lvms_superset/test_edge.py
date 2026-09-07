from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from molstat.lvms.edge import (
    EdgeLaunchError,
    EdgeProcess,
    build_edge_arguments,
    find_edge_executable,
)


class FakeProcess:
    def __init__(self, *, needs_kill: bool = False) -> None:
        self.needs_kill = needs_kill
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def poll(self) -> int | None:
        return None if not self.terminated and not self.killed else 0

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float) -> int:
        self.wait_calls += 1
        if self.needs_kill and not self.killed:
            raise TimeoutError
        return 0

    def kill(self) -> None:
        self.killed = True


class EdgeTests(unittest.TestCase):
    def test_finds_edge_from_path_before_standard_locations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            edge = Path(temporary_directory) / "msedge.exe"
            edge.touch()

            result = find_edge_executable({}, lambda _: str(edge))

        self.assertEqual(result, edge.resolve())

    def test_reports_when_edge_is_not_available(self) -> None:
        with self.assertRaisesRegex(EdgeLaunchError, "managed Microsoft Edge"):
            find_edge_executable({}, lambda _: None)

    def test_builds_visible_loopback_only_dedicated_profile_launch(self) -> None:
        arguments = build_edge_arguments(
            Path("C:/Edge/msedge.exe"), Path("C:/Profiles/lvms")
        )

        self.assertIn("--remote-debugging-address=127.0.0.1", arguments)
        self.assertIn("--remote-debugging-port=0", arguments)
        self.assertFalse(
            any(value.startswith("--remote-allow-origins=") for value in arguments)
        )
        self.assertIn("--user-data-dir=C:\\Profiles\\lvms", arguments)
        self.assertIn("--disable-session-crashed-bubble", arguments)
        self.assertNotIn("--headless", arguments)
        self.assertEqual(arguments[-1], "about:blank")

    def test_rejects_relative_profile_path(self) -> None:
        with self.assertRaises(EdgeLaunchError):
            build_edge_arguments(Path("C:/Edge/msedge.exe"), Path("relative"))

    def test_close_terminates_only_the_tracked_child(self) -> None:
        process = FakeProcess()
        edge = EdgeProcess(process=process, port=49152)

        edge.close()

        self.assertTrue(process.terminated)
        self.assertFalse(process.killed)
        self.assertEqual(process.wait_calls, 1)

    def test_close_kills_tracked_child_after_timeout(self) -> None:
        process = FakeProcess(needs_kill=True)
        edge = EdgeProcess(process=process, port=49152)

        edge.close()

        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)
        self.assertEqual(process.wait_calls, 2)


if __name__ == "__main__":
    unittest.main()

