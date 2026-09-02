from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MolStatSettings:
    sensitive_root: Path
    sharepoint_root: Path | None = None
    statistics_hour: int = 5
    backlog_first_hour: int = 6
    backlog_last_hour: int = 18

    def validate(self) -> tuple[str, ...]:
        if self.sharepoint_root is not None and _same_path(
            self.sensitive_root, self.sharepoint_root
        ):
            return ("K-sensitiv og SharePoint må være ulike mapper.",)
        return ()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload["sensitive_root"] = str(self.sensitive_root)
        payload["sharepoint_root"] = (
            str(self.sharepoint_root) if self.sharepoint_root is not None else None
        )
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    @classmethod
    def load(cls, path: Path) -> MolStatSettings:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["sensitive_root"] = Path(payload["sensitive_root"])
        if payload.get("sharepoint_root") is not None:
            payload["sharepoint_root"] = Path(payload["sharepoint_root"])
        return cls(**payload)


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(str(first.resolve())) == os.path.normcase(
        str(second.resolve())
    )
