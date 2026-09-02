from __future__ import annotations

from collections.abc import Callable
from typing import Any

from molstat.lvms.config import AppConfig


class BrowserCleanupError(RuntimeError):
    """Owned browser startup failed and cleanup did not complete."""


def close_owned(connection: Any | None, edge: Any | None) -> bool:
    failed = False
    for resource in (connection, edge):
        if resource is None:
            continue
        try:
            resource.close()
        except Exception:
            failed = True
    return failed


def open_page(
    config: AppConfig,
    dependencies: Any,
    *,
    stage: Callable[[str], None] | None = None,
) -> tuple[Any, Any, Any]:
    if stage is not None:
        stage("edge_start")
    opened = dependencies.browser_open(config.profile_directory)
    connection: Any | None = None
    try:
        if stage is not None:
            stage("cdp_connect")
        connection = dependencies.connection_open(opened.target)
        page = dependencies.page_factory(connection)
        if stage is not None:
            stage("lvms_open")
        page.navigate(config.landing_url, config.expected_origin, timeout_seconds=120)
        return opened.edge, connection, page
    except Exception as exc:
        if close_owned(connection, opened.edge):
            raise BrowserCleanupError(
                "owned browser cleanup did not complete"
            ) from exc
        raise

