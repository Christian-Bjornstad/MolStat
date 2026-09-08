from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class MolStatSettings:
    sensitive_root: Path
    sharepoint_root: Path | None = None
    statistics_hour: int = 5
    backlog_first_hour: int = 6
    backlog_last_hour: int = 18
    statistics_lookup_paths: dict[str, Path] = field(default_factory=dict)
    lvms_config_path: Path | None = None
    lvms_url: str = ""
    power_bi_report_url: str = ""

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if self.sharepoint_root is not None and _same_path(
            self.sensitive_root, self.sharepoint_root
        ):
            errors.append("K-sensitiv og SharePoint må være ulike mapper.")
        if self.power_bi_report_url and not _valid_power_bi_url(
            self.power_bi_report_url
        ):
            errors.append(
                "Power BI-lenken må være en HTTPS-lenke på app.powerbi.com."
            )
        return tuple(errors)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload["sensitive_root"] = str(self.sensitive_root)
        payload["sharepoint_root"] = (
            str(self.sharepoint_root) if self.sharepoint_root is not None else None
        )
        payload["statistics_lookup_paths"] = {
            unit: str(value)
            for unit, value in self.statistics_lookup_paths.items()
        }
        payload["lvms_config_path"] = (
            str(self.lvms_config_path) if self.lvms_config_path is not None else None
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
        payload["statistics_lookup_paths"] = {
            str(unit): Path(value)
            for unit, value in payload.get("statistics_lookup_paths", {}).items()
        }
        if payload.get("lvms_config_path") is not None:
            payload["lvms_config_path"] = Path(payload["lvms_config_path"])
        return cls(**payload)


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(str(first.resolve())) == os.path.normcase(
        str(second.resolve())
    )


def _valid_power_bi_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == "app.powerbi.com"
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
    )
