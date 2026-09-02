from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .config import MolStatSettings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="molstat")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check-config")
    check.add_argument("--settings", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "check-config":
        errors = MolStatSettings.load(args.settings).validate()
        if errors:
            print(json.dumps({"status": "invalid", "errors": errors}))
            return 2
        print(json.dumps({"status": "ok"}))
        return 0
    return 2
