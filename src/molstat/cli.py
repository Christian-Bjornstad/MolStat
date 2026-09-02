from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Protocol, Sequence

from .config import MolStatSettings


class CliServices(Protocol):
    def gui(self) -> int: ...
    def run(self, kind: str) -> int: ...
    def serve(self) -> int: ...
    def auto(self) -> int: ...
    def install_automation(self) -> int: ...


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="molstat")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check-config")
    check.add_argument("--settings", required=True, type=Path)
    for command in ("gui", "serve", "auto", "install-automation"):
        item = commands.add_parser(command)
        item.add_argument("--settings", required=True, type=Path)
    run = commands.add_parser("run")
    run.add_argument("kind", choices=("statistics", "backlog"))
    run.add_argument("--settings", required=True, type=Path)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    services: CliServices | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if args.command == "check-config":
        if not args.settings.is_file():
            print(
                json.dumps(
                    {"status": "invalid", "errors": ["Innstillingsfil mangler."]},
                    ensure_ascii=False,
                )
            )
            return 2
        errors = MolStatSettings.load(args.settings).validate()
        if errors:
            print(json.dumps({"status": "invalid", "errors": errors}))
            return 2
        print(json.dumps({"status": "ok"}))
        return 0
    active = services or _default_services(args.settings)
    if args.command == "gui":
        return active.gui()
    if args.command == "run":
        return active.run(args.kind)
    if args.command == "serve":
        return active.serve()
    if args.command == "auto":
        return active.auto()
    if args.command == "install-automation":
        return active.install_automation()
    return 2


def _default_services(settings_path: Path) -> CliServices:
    from .services import DefaultServices

    return DefaultServices(settings_path)


if __name__ == "__main__":
    raise SystemExit(main())
