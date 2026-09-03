from __future__ import annotations

import os
import shutil
import socket
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EPHEMERAL_PORT_MIN = 1024
EPHEMERAL_PORT_MAX = 65535


class EdgeLaunchError(RuntimeError):
    """Managed Edge could not be found or launched safely."""


def find_edge_executable(
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> Path:
    environment = os.environ if environ is None else environ
    discovered = which("msedge")
    candidates = [Path(discovered)] if discovered else []

    for environment_name in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        root = environment.get(environment_name)
        if root:
            candidates.append(
                Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            )

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    raise EdgeLaunchError("managed Microsoft Edge was not found")


def reserve_loopback_port() -> int:
    for _ in range(10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            port = int(listener.getsockname()[1])
        if EPHEMERAL_PORT_MIN <= port <= EPHEMERAL_PORT_MAX:
            return port
    raise EdgeLaunchError("a non-privileged loopback port could not be reserved")


def build_edge_arguments(edge: Path, profile: Path, port: int) -> list[str]:
    if not EPHEMERAL_PORT_MIN <= port <= EPHEMERAL_PORT_MAX:
        raise EdgeLaunchError("remote debugging must use a non-privileged port")
    if not profile.is_absolute():
        raise EdgeLaunchError("Edge profile path must be absolute")

    origin = f"http://127.0.0.1:{port}"
    return [
        str(edge),
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        f"--remote-allow-origins={origin}",
        f"--user-data-dir={profile}",
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-mode",
        "--disable-features=msEdgeStartupBoost",
        "--disable-session-crashed-bubble",
        "about:blank",
    ]


@dataclass
class EdgeProcess:
    process: Any
    port: int

    @classmethod
    def start(
        cls,
        profile: Path,
        *,
        edge_executable: Path | None = None,
        port_reserver: Callable[[], int] = reserve_loopback_port,
        process_factory: Callable[..., Any] = subprocess.Popen,
    ) -> "EdgeProcess":
        profile.mkdir(parents=True, exist_ok=True)
        edge = edge_executable or find_edge_executable()
        port = port_reserver()
        arguments: Sequence[str] = build_edge_arguments(edge, profile.resolve(), port)
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        try:
            process = process_factory(
                arguments,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                creationflags=creation_flags,
            )
        except OSError as exc:
            raise EdgeLaunchError("managed Microsoft Edge could not be started") from exc
        return cls(process=process, port=port)

    def close(self, *, timeout_seconds: float = 5.0) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=timeout_seconds)
        except (subprocess.TimeoutExpired, TimeoutError):
            self.process.kill()
            self.process.wait(timeout=timeout_seconds)

