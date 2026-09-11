from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = (
    ROOT
    / "powerbi"
    / "Hemato_Statistikk_Optimert"
    / "Hemato Statistikk Rapport.Report"
)


def iter_report_files(report: Path) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    definition = report / "definition"
    for path in sorted(item for item in definition.rglob("*") if item.is_file()):
        files.append(("Report/" + path.relative_to(report).as_posix(), path))

    report_definition = json.loads((definition / "report.json").read_text(encoding="utf-8"))
    resources = report / "StaticResources"
    mapped_physical_files: set[Path] = set()
    for package in report_definition.get("resourcePackages", []):
        package_name = package["name"]
        package_root = resources / package_name
        for item in package.get("items", []):
            archive_path = f"Report/StaticResources/{package_name}/{item['path']}"
            expected_name = Path(item["path"]).name
            candidates = list(package_root.rglob(expected_name))
            if not candidates:
                candidates = list(package_root.rglob(item["name"]))
            if len(candidates) != 1:
                raise FileNotFoundError(
                    f"Could not resolve resource {package_name}/{item['path']}"
                )
            physical = candidates[0]
            mapped_physical_files.add(physical.resolve())
            files.append((archive_path, physical))

    if resources.exists():
        for path in sorted(item for item in resources.rglob("*") if item.is_file()):
            if path.resolve() not in mapped_physical_files:
                files.append(("Report/" + path.relative_to(report).as_posix(), path))
    return files


def package_pbix(
    source: Path,
    destination: Path,
    report: Path = DEFAULT_REPORT,
    omit_custom_theme: bool = False,
    active_page: str | None = None,
) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("Source and destination must be different files")
    if not source.is_file():
        raise FileNotFoundError(source)
    report = report.resolve()
    if not (report / "definition" / "report.json").is_file():
        raise FileNotFoundError(report / "definition" / "report.json")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{destination.stem}-", suffix=".pbix", dir=destination.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)

    try:
        with zipfile.ZipFile(source, "r") as original, zipfile.ZipFile(
            temporary, "w", allowZip64=True
        ) as rebuilt:
            for info in original.infolist():
                name = info.filename
                if (
                    name == "SecurityBindings"
                    or name.startswith("Report/definition/")
                    or name.startswith("Report/StaticResources/")
                ):
                    continue
                rebuilt.writestr(info, original.read(name))

            for archive_name, path in iter_report_files(report):
                if active_page and archive_name == "Report/definition/pages/pages.json":
                    pages = json.loads(path.read_text(encoding="utf-8"))
                    if active_page not in pages.get("pageOrder", []):
                        raise ValueError(f"Unknown active page: {active_page}")
                    pages["activePageName"] = active_page
                    rebuilt.writestr(
                        archive_name,
                        json.dumps(pages, ensure_ascii=False, separators=(",", ":")),
                        compress_type=zipfile.ZIP_DEFLATED,
                    )
                elif omit_custom_theme and archive_name == "Report/definition/report.json":
                    definition = json.loads(path.read_text(encoding="utf-8"))
                    definition.get("themeCollection", {}).pop("customTheme", None)
                    for package in definition.get("resourcePackages", []):
                        if package.get("name") == "RegisteredResources":
                            package["items"] = [
                                item
                                for item in package.get("items", [])
                                if item.get("type") != 202
                            ]
                    rebuilt.writestr(
                        archive_name,
                        json.dumps(definition, ensure_ascii=False, separators=(",", ":")),
                        compress_type=zipfile.ZIP_DEFLATED,
                    )
                else:
                    rebuilt.write(path, archive_name, compress_type=zipfile.ZIP_DEFLATED)

        with zipfile.ZipFile(temporary, "r") as package:
            package.testzip()
            entries = set(package.namelist())
            required = {
                "DataModel",
                "Report/definition/report.json",
                "Report/definition/pages/pages.json",
            }
            missing = required - entries
            if missing:
                raise ValueError(f"Packaged PBIX is missing: {sorted(missing)}")
            if "SecurityBindings" in entries:
                raise ValueError("SecurityBindings must be regenerated by Power BI Desktop")

        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Package the optimized PBIR report into a PBIX copy with cached data."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--omit-custom-theme", action="store_true")
    parser.add_argument("--active-page")
    args = parser.parse_args()
    package_pbix(
        args.source,
        args.destination,
        args.report,
        omit_custom_theme=args.omit_custom_theme,
        active_page=args.active_page,
    )
    print(args.destination.resolve())


if __name__ == "__main__":
    main()
