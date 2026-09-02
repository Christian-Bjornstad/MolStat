from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from molstat.lvms.cdp import CdpTimeout, PageTarget, wait_for_page_target
from molstat.lvms.edge import EdgeLaunchError, EdgeProcess


@dataclass(frozen=True)
class OwnedBrowserStart:
    edge: EdgeProcess
    target: PageTarget


def open_owned_browser(
    profile: Path,
    *,
    attempts: int = 3,
    edge_start: Callable[[Path], EdgeProcess] = EdgeProcess.start,
    target_wait: Callable[[int], PageTarget] = wait_for_page_target,
    sleeper: Callable[[float], None] = time.sleep,
) -> OwnedBrowserStart:
    if attempts not in range(1, 4):
        raise EdgeLaunchError("Edge startup attempts are invalid")
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        edge: EdgeProcess | None = None
        try:
            edge = edge_start(profile)
            return OwnedBrowserStart(edge, target_wait(edge.port))
        except (EdgeLaunchError, CdpTimeout) as exc:
            last_error = exc
            if edge is not None:
                edge.close()
            if attempt < attempts:
                sleeper(attempt * 1.5)
    raise EdgeLaunchError("managed Microsoft Edge CDP could not be started") from last_error

