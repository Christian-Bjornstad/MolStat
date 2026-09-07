from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from molstat.lvms.edge import (
    EdgeLaunchError,
    EdgeProcess,
    _read_devtools_active_port,
    build_edge_arguments,
    find_edge_executable,
    wait_for_devtools_port,
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

    def test_reads_only_valid_announced_port(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            port_file = Path(temporary_directory) / "DevToolsActivePort"
            port_file.write_text("15142\n/devtools/browser/token\n", encoding="utf-8")
            self.assertEqual(_read_devtools_active_port(port_file), 15142)

            for value in ("", "not-a-port", "0", "1023", "65536"):
                with self.subTest(value=value):
                    port_file.write_text(value, encoding="utf-8")
                    with self.assertRaises(EdgeLaunchError):
                        _read_devtools_active_port(port_file)

    def test_waits_through_partial_port_file_until_edge_announces_port(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            port_file = profile / "DevToolsActivePort"
            port_file.write_text("partial", encoding="utf-8")
            ticks = [0.0]

            def clock() -> float:
                return ticks[0]

            def sleep(seconds: float) -> None:
                ticks[0] += seconds
                port_file.write_text("15142\n", encoding="utf-8")

            port = wait_for_devtools_port(
                profile,
                FakeProcess(),
                timeout_seconds=1,
                clock=clock,
                sleep=sleep,
            )

            self.assertEqual(port, 15142)

    def test_wait_fails_when_edge_exits_before_announcing_port(self) -> None:
        class ExitedProcess(FakeProcess):
            def poll(self) -> int:
                return 1

        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(EdgeLaunchError, "exited"):
                wait_for_devtools_port(
                    Path(temporary_directory),
                    ExitedProcess(),
                    timeout_seconds=1,
                )

    def test_start_removes_stale_file_and_uses_announced_port(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            port_file = profile / "DevToolsActivePort"
            port_file.write_text("49152\n", encoding="utf-8")

            def start(arguments, **kwargs):
                del kwargs
                self.assertFalse(port_file.exists())
                self.assertIn("--remote-debugging-port=0", arguments)
                port_file.write_text("15142\n", encoding="utf-8")
                return FakeProcess()

            edge = EdgeProcess.start(
                profile,
                edge_executable=Path("C:/Edge/msedge.exe"),
                process_factory=start,
            )

            self.assertEqual(edge.port, 15142)

    def test_start_closes_owned_process_when_port_discovery_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            process = FakeProcess()

            def fail(_profile: Path, _process: FakeProcess) -> int:
                raise EdgeLaunchError("dynamic port unavailable")

            with self.assertRaisesRegex(EdgeLaunchError, "dynamic port unavailable"):
                EdgeProcess.start(
                    Path(temporary_directory),
                    edge_executable=Path("C:/Edge/msedge.exe"),
                    process_factory=lambda *args, **kwargs: process,
                    port_waiter=fail,
                )

            self.assertTrue(process.terminated)

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

