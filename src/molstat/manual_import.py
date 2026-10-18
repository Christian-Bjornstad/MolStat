"""Operator-selected LVMS files enter the normal pipeline through private copies."""
from __future__ import annotations

from collections.abc import Mapping
from copy import copy
from dataclasses import dataclass
from datetime import date, timedelta
import csv
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory

from ._statistics.processing import clean_text, parse_tidspunkt
from .system import CapabilityRun, MolStatSystem
from .unit_settings import UnitFile
from .lvms.report import ReportRequest


class ManualImportError(ValueError):
    """A safe, actionable validation message without raw report contents."""


@dataclass(frozen=True, slots=True)
class ManualImportPlan:
    unit_key: str
    job_kind: str
    date_from: date
    date_to: date
    files: Mapping[str, Path]


def manual_import_roles(definition: UnitFile, job_kind: str) -> tuple[str, ...]:
    if job_kind == "backlog":
        if not definition.payload.get("backlog"):
            raise ManualImportError("Enheten har ikke restanseoppsett.")
        return ("backlog",)
    if job_kind != "statistics":
        raise ManualImportError("Velg statistikk eller restanse.")
    if definition.unit.profile == "lege":
        if set(definition.payload["statistics"]) == {"workflow"}:
            return ("workflow",)
        return ("current", "previous", "production_current", "production_previous",
                "macro_current", "macro_previous")
    return tuple(definition.payload["statistics"])


def validate_manual_import(plan: ManualImportPlan, definition: UnitFile) -> None:
    if plan.unit_key != definition.key:
        raise ManualImportError("Enhetsfilen tilhører en annen enhet.")
    if plan.date_from > plan.date_to or plan.date_to > date.today():
        raise ManualImportError("Velg en gyldig periode som slutter senest i dag.")
    if plan.job_kind == "backlog" and (
        plan.date_from != date(2024, 1, 1) or plan.date_to != date.today()
    ):
        raise ManualImportError("Restanse krever hele uttrekket fra 01.01.2024 til i dag.")
    if definition.unit.profile == "lege" and (
        plan.date_from.day != 1
        or (plan.date_from.year, plan.date_from.month) != (plan.date_to.year, plan.date_to.month)
    ):
        raise ManualImportError("Patologer krever perioden fra første dag i én måned.")
    required = set(manual_import_roles(definition, plan.job_kind))
    if set(plan.files) != required:
        raise ManualImportError("Velg én CSV-fil for hver rapportrolle i skjemaet.")
    seen: set[Path] = set()
    for role, source in plan.files.items():
        path = Path(source)
        if not path.is_file() or path.suffix.lower() != ".csv":
            raise ManualImportError(f"{role}: velg en tilgjengelig CSV-fil fra LVMS.")
        resolved = path.resolve()
        if resolved in seen:
            raise ManualImportError("Samme fil kan ikke brukes til flere rapportroller.")
        seen.add(resolved)


def _copy_csv(source: Path, destination: Path, encoding: str) -> None:
    # Decode before writing, so Excel's UTF-8 CSV option is accepted as well.
    if source.stat().st_size > 128 * 1024 * 1024:
        raise ManualImportError("CSV-filen er større enn 128 MB. Del uttrekket i kortere perioder.")
    data = source.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = data.decode("utf-16")
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = data.decode("cp1252")
            except UnicodeDecodeError as exc:
                raise ManualImportError("CSV-filen har en ukjent tegnkoding.") from exc
    if "\0" in text or not text.strip():
        raise ManualImportError("Filen er tom eller er ikke et tekstbasert CSV-uttrekk.")
    try:
        destination.write_text(text, encoding=encoding, newline="")
    except UnicodeEncodeError as exc:
        raise ManualImportError("CSV-filen inneholder tegn som ikke støttes av enhetens CSV-format.") from exc


def _require_date_in_period(moment, request: ReportRequest, role: str) -> None:
    if moment is None or not request.date_from <= moment.date() <= request.date_to:
        raise ManualImportError(f"{role}: rapporten inneholder rader utenfor valgt periode. Kontroller datoene for uttrekket.")


def _validate_statistics_csv(path: Path, profile: str, role: str, request: ReportRequest) -> None:
    if profile == "lege" and role == "workflow":
        from ._statistics.patolog_flow import validate_month
        validate_month(path, request.date_from, request.date_to)
        return
    if profile == "lege":
        from ._statistics.patolog_process import _count, _text
        from ._statistics.patolog_reports import SOURCE_FIELDS, _moment
        if role in {"current", "previous"}:
            with path.open(encoding="cp1252", newline="") as stream:
                first_line = next(stream, "")
                if not first_line.strip().startswith("Totalt antall registrerte rekvisisjoner"):
                    stream.seek(0)
                reader = csv.reader(stream, delimiter=";", strict=True)
                header = next(reader, [])
                required = {"Profil", "Lab", "Distinct_SampleId", "Distinct_Ant. blokker", "Distinct_Ant. glass"}
                if (not required <= set(header) or len(header) != len(set(header))
                        or not ({"s_w_labprocess", "s_w_labprosess"} & set(header))):
                    raise ManualImportError(f"{role}: prosessrapporten mangler forventede kolonner eller har duplikate kolonnenavn.")
                for raw in reader:
                    if not any(value.strip() for value in raw):
                        continue
                    if len(raw) != len(header):
                        raise ManualImportError(f"{role}: en rad har feil antall kolonner.")
                    row = dict(zip(header, raw))
                    for name in ("Distinct_SampleId", "Distinct_Ant. blokker", "Distinct_Ant. glass"):
                        _count(row[name])
                    process_code = _text(row.get("s_w_labprocess") or row.get("s_w_labprosess"))
                    if not _text(row["Profil"]) or not _text(row["Lab"]) or not process_code:
                        raise ManualImportError(f"{role}: en rad mangler profil, lab eller prosesskode.")
        else:
            report_role = role.split("_")[0]
            with path.open(encoding="cp1252", newline="") as stream:
                next(stream, "")  # LVMS doctor exports begin with a report title.
                reader = csv.reader(stream, delimiter=";", strict=True)
                header = next(reader, [])
                if not SOURCE_FIELDS[report_role] <= set(header) or len(header) != len(set(header)):
                    raise ManualImportError(f"{role}: legerapporten mangler forventede kolonner eller har duplikate kolonnenavn.")
                sample_column = "Antall prøver" if report_role == "production" else "SampleID"
                user_column = "Godkjent av" if report_role == "production" else "Makro av"
                for raw in reader:
                    if not any(value.strip() for value in raw):
                        continue
                    if len(raw) != len(header):
                        raise ManualImportError(f"{role}: en rad har feil antall kolonner.")
                    row = {name: _text(value) for name, value in zip(header, raw)}
                    if not row[sample_column] or not row[user_column]:
                        raise ManualImportError(f"{role}: en rad mangler prøvenummer eller brukernavn.")
                    for name in (("Godkj. når", "Ferdig farget") if report_role == "production" else ("Makro når",)):
                        _moment(row[name])
                    period_column = "Godkj. når" if report_role == "production" else "Makro når"
                    _require_date_in_period(_moment(row[period_column]), request, role)
        return
    with path.open(encoding="cp1252", newline="") as stream:
        reader = csv.reader(stream, delimiter=";", strict=True)
        header = [name.strip().replace(" ", ".") for name in next(reader, [])]
        required = {"Sample.ID", "Analyse", "Tidspunkt.analysebestilling"}
        if role in {"resultater", "ekstraksjon"}:
            required.add("Tidspunkt.analyseresultat")
        if not required <= set(header) or len(header) != len(set(header)):
            raise ManualImportError(f"{role}: mangler forventede kolonner eller har duplikate kolonnenavn.")
        for raw in reader:
            if not any(value.strip() for value in raw):
                continue
            if len(raw) != len(header):
                raise ManualImportError(f"{role}: en rad har feil antall kolonner.")
            row = dict(zip(header, (clean_text(value) for value in raw)))
            if not row["Sample.ID"] or not row["Analyse"]:
                raise ManualImportError(f"{role}: en rad mangler prøvenummer eller analysekode.")
            for name, value in row.items():
                if name.startswith("Tidspunkt.") and value and value.upper() not in {"NA", "N/A"}:
                    if parse_tidspunkt(value) is None:
                        raise ManualImportError(f"{role}: ugyldig datoformat. Bruk originalt LVMS-uttrekk.")
            if parse_tidspunkt(row["Tidspunkt.analysebestilling"]) is None:
                raise ManualImportError(f"{role}: analysebestilling mangler et gyldig tidspunkt.")
            # The normal LVMS statistics query filters the request creation
            # timestamp. Older ordered/resulted events can belong to a request
            # created inside this interval, so only check the source filter.
            if "Tidspunkt.opprettet" in row:
                _require_date_in_period(parse_tidspunkt(row["Tidspunkt.opprettet"]), request, role)


def _copy_statistics_history(system: MolStatSystem, staging: Path,
                             requests: tuple[ReportRequest, ...], definition: UnitFile) -> None:
    """Probe the same history the real processor will read, without writes."""
    existing = system.archive.sensitive_root / "raw" / "statistics" / requests[0].unit
    replacing = {
        (request.report_name, request.date_from.isoformat(), request.date_to.isoformat())
        for request in requests
    }
    pattern = re.compile(r"^(.*)__(\d{4}-\d{2}-\d{2})__(\d{4}-\d{2}-\d{2})(?:__r(\d+))?\.csv$")
    latest = {}
    for source in existing.glob("*.csv"):
        match = pattern.fullmatch(source.name)
        if match is None or match.groups()[:3] in replacing:
            continue
        interval = match.groups()[:3]
        revision = int(match.group(4) or 1)
        if interval not in latest or revision > latest[interval][0]:
            latest[interval] = revision, source
    by_report = {report["report_id"]: role for role, report in definition.payload["statistics"].items()}
    for (report_name, start, end), (_, source) in latest.items():
        role = by_report.get(report_name)
        if role is None:
            continue
        request = ReportRequest("statistics", definition.key, report_name,
                                date.fromisoformat(start), date.fromisoformat(end))
        try:
            _validate_statistics_csv(source, definition.unit.profile, role, request)
        except (ValueError, csv.Error, UnicodeError) as exc:
            raise ManualImportError("Tidligere arkiv kunne ikke behandles. Importer et korrigert uttrekk for den tidligere perioden først.") from exc
        # Old same-interval revisions are intentionally omitted: the incoming
        # file supersedes all of them in the actual archive after publication.
        shutil.copy2(source, staging / source.name)


def _request(plan: ManualImportPlan, definition: UnitFile, role: str) -> ReportRequest:
    start, end = plan.date_from, plan.date_to
    report_role = role
    if plan.job_kind == "backlog":
        report_id = definition.payload["backlog"]["report"]["output_stem"]
    else:
        if definition.unit.profile == "lege":
            report_role = role.split("_")[0]
            if role == "previous" or role.endswith("_previous"):
                end = start - timedelta(days=1)
                start = end.replace(day=1)
        report_id = definition.payload["statistics"][report_role]["report_id"]
    return ReportRequest(plan.job_kind, plan.unit_key, report_id, start, end)


def process_manual_import(
    system: MolStatSystem, plan: ManualImportPlan, definition: UnitFile,
) -> tuple[CapabilityRun, ...]:
    """Must be called within the normal writer lease (via DefaultServices)."""
    validate_manual_import(plan, definition)
    error = getattr(system, "capability_errors", {}).get((plan.unit_key, plan.job_kind))
    if error is not None:
        raise error
    private_root = system.archive.sensitive_root / "work" / "manual-import"
    private_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="import-", dir=private_root) as temporary:
        staging = Path(temporary)
        roles = manual_import_roles(definition, plan.job_kind)
        requests = tuple(_request(plan, definition, role) for role in roles)
        if plan.job_kind == "statistics":
            _copy_statistics_history(system, staging, requests, definition)
        reports = []
        for role, request in zip(roles, requests, strict=True):
            destination = staging / f"{request.report_name}__{request.date_from}__{request.date_to}.csv"
            encoding = definition.payload["backlog"]["columns"]["encoding"] if plan.job_kind == "backlog" else "cp1252"
            _copy_csv(Path(plan.files[role]), destination, encoding)
            try:
                if plan.job_kind == "statistics":
                    _validate_statistics_csv(destination, definition.unit.profile, role, request)
                    if definition.unit.profile == "lege" and role == "workflow":
                        from ._statistics.patolog_flow import validate_month
                        report = definition.unit.report_by_key("workflow")
                        validate_month(destination, request.date_from, request.date_to,
                                       laboratory=report.laboratory, processes=report.process_codes)
                else:
                    from ._backlog.ingestion import read_restanse_csv
                    processor = getattr(system, "backlog_processors", {}).get(plan.unit_key, system.backlog_processor)
                    imported = read_restanse_csv(destination, processor.contract, analysis_groups=processor.config.source_groups)
                    if not imported.rows_read or imported.invalid_rows:
                        raise ManualImportError("Restansefilen er tom eller inneholder ugyldige rader.")
                    for sample in imported.samples:
                        _require_date_in_period(sample.ordered_at, request, role)
            except (ValueError, csv.Error, UnicodeError) as exc:
                if isinstance(exc, ManualImportError):
                    raise
                raise ManualImportError(f"{role}: CSV-formatet eller innholdet er ugyldig.") from exc
            reports.append((request, destination))
        selected = copy(system)
        if plan.job_kind == "statistics":
            # Validate the complete set and processing rules without touching the
            # permanent archive/register. Failed manual files cannot poison history.
            probe = copy(system.statistics_processors[plan.unit_key])
            probe.database = None
            try:
                probe.process(plan.unit_key, tuple(path for _, path in reports), staging / "validation")
            except Exception as exc:
                raise ManualImportError("Filsettet kunne ikke behandles. Kontroller rapportroller og lookup-fil.") from exc
            selected.statistics_fetch = lambda _keys: {plan.unit_key: tuple(reports)}
            summary = selected.run_statistics_unit(plan.unit_key)
        else:
            selected.backlog_fetchers = {plan.unit_key: lambda: reports[0]}
            summary = selected.run_backlog_unit(plan.unit_key)
        # Propagate the shared Excel export result to the service status view.
        system.excel_status = selected.excel_status
        return (CapabilityRun(plan.unit_key, plan.job_kind, summary),)
