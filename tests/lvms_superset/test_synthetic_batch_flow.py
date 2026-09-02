from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from molstat.lvms.batch_controls import DocumentControlIdentity
from molstat.lvms.batch_form import BatchReportForm
from molstat.lvms.batch_navigation import (
    DEFINED_REPORTS_LABEL,
    REPORTS_SECTION_LABEL,
    DefinedReportsNavigator,
    discover_defined_reports_page,
)
from molstat.lvms.batch_runner import BatchRunnerDependencies, run_report_batch
from molstat.lvms.browser_session import OwnedBrowserStart
from molstat.lvms.cdp import PageIdentity, PageTarget
from molstat.lvms.config import AppConfig
from molstat.lvms.dom_actions import DocumentDomActions
from molstat.lvms.downloads import CsvArrivalDetector, finalize_csv
from molstat.lvms.report_job import ReportJob, validate_report_job


EXPECTED_ORIGIN = "https://lvms.example.invalid"
JOB_KEYS = ("ordered", "answered", "extraction")


def raw_control(
    frame: str,
    tag: str,
    element_id: str,
    *,
    name: str = "",
    control_type: str = "",
    label: str = "",
) -> dict[str, object]:
    return {
        "frame": frame,
        "control": {
            "tag": tag,
            "type": control_type,
            "id": element_id,
            "name": name,
            "role": "",
            "label": label,
            "locator": [f"{tag.lower()}#{element_id}"],
        },
    }


def jobs() -> tuple[ReportJob, ...]:
    return tuple(
        validate_report_job(
            {
                "job_key": key,
                "report_type": "TYPE_A",
                "category": "CATEGORY_A",
                "report_id": f"REPORT-{key.upper()}",
                "report_groups": ["OU-HEM"],
                "analysis_codes": [f"ANALYSIS-{key.upper()}"],
                "created_from": "01.08.2026",
                "created_to": "07.08.2026",
                "output_stem": key,
            }
        )
        for key in JOB_KEYS
    )


class SyntheticEdge:
    def __init__(self, harness: "SyntheticBatchHarness") -> None:
        self.harness = harness

    def close(self) -> None:
        self.harness.edge_closed = True


class SyntheticConnection:
    def __init__(self, harness: "SyntheticBatchHarness") -> None:
        self.harness = harness

    def close(self) -> None:
        self.harness.connection_closed = True


class SyntheticPage:
    def __init__(self, harness: "SyntheticBatchHarness") -> None:
        self.harness = harness
        self.destination = False
        self.navigation_stage = 0
        self.form_stage = 0
        self.focused = ""
        self.tokens: dict[str, str] = {}
        self.values: dict[str, str] = {}
        self.token_number = 0

    def navigate(self, url: str, origin: str, *, timeout_seconds: float) -> PageIdentity:
        del url, timeout_seconds
        return PageIdentity(origin, "Synthetic LVMS")

    def configure_downloads(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)

    def current_origin(self) -> str:
        return EXPECTED_ORIGIN

    def _page_contract(self) -> dict[str, object] | None:
        if not self.destination:
            return None
        return {
            "job_type": raw_control(
                "pageentry",
                "INPUT",
                "report-type",
                name="menu",
                control_type="text",
            ),
            "clear": raw_control(
                "_nav_frame1",
                "BUTTON",
                "clear",
                name="menu",
                control_type="button",
            ),
            "export": raw_control(
                "_nav_frame1",
                "BUTTON",
                "export",
                name="menu",
                control_type="button",
            ),
        }

    def evaluate_safe(self, expression: str, *, timeout_seconds: float = 2) -> object:
        del timeout_seconds
        if "LVMS_DEFINED_REPORTS_PAGE" in expression:
            return self._page_contract()
        if "LVMS_NAVIGATION_ANCHOR" in expression:
            if self.navigation_stage == 0 and REPORTS_SECTION_LABEL in expression:
                return raw_control("top", "A", "section", label="external reports")
            if self.navigation_stage == 1 and DEFINED_REPORTS_LABEL in expression:
                return raw_control("top", "A", "defined_reports", label="defined reports")
            return None
        if "LVMS_REPORT_ROLE" in expression:
            roles = {
                "category": (1, "SELECT", "category", "kategori", ""),
                "report_id": (2, "SELECT", "report-id", "rapport id", ""),
                "notes": (0, "TEXTAREA", "notes", "notater", ""),
                "analysis_codes": (3, "TEXTAREA", "analyses", "angi analyse(r)", ""),
                "report_groups": (
                    3,
                    "INPUT",
                    "report-groups",
                    "velg en eller flere rapportgrupper",
                    "text",
                ),
                "created_from": (
                    3,
                    "INPUT",
                    "created-from",
                    "analyse opprettet fom:",
                    "text",
                ),
                "created_to": (
                    3,
                    "INPUT",
                    "created-to",
                    "analyse opprettet tom:",
                    "text",
                ),
            }
            for role, (stage, tag, element_id, label, control_type) in roles.items():
                if f'const requestedRole = "{role}"' in expression:
                    if self.form_stage < stage:
                        return None
                    return raw_control(
                        "_nav_frame1",
                        tag,
                        element_id,
                        label=label,
                        control_type=control_type,
                    )
        raise AssertionError("unexpected synthetic safe evaluation")

    def _available(self, element_id: str) -> bool:
        if element_id == "section":
            return self.navigation_stage == 0
        if element_id == "defined_reports":
            return self.navigation_stage == 1
        if not self.destination:
            return False
        stages = {
            "report-type": 0,
            "clear": 0,
            "export": 0,
            "category": 1,
            "report-id": 2,
            "notes": 0,
            "analyses": 3,
            "report-groups": 3,
            "created-from": 3,
            "created-to": 3,
        }
        return element_id in stages and self.form_stage >= stages[element_id]

    def resolve_document_control(self, identity: DocumentControlIdentity) -> str | None:
        element_id = identity.control.element_id
        if not self._available(element_id):
            return None
        self.token_number += 1
        token = f"{self.token_number:032x}"
        self.tokens[token] = element_id
        return token

    def focus_control(self, token: str) -> None:
        self.focused = self.tokens[token]

    def activate_control(self, token: str) -> None:
        element_id = self.tokens[token]
        if element_id == "section":
            self.navigation_stage = 1
            self.harness.navigation_route.append("section")
        elif element_id == "defined_reports":
            self.destination = True
            self.navigation_stage = 2
            self.harness.navigation_route.append("defined_reports")
        elif element_id == "clear":
            self.form_stage = 0
            self.values.clear()
        elif element_id == "export":
            self.harness.export_count += 1
            destination = self.harness.config.download_directory / (
                f"synthetic-{self.harness.export_count}.csv"
            )
            destination.write_bytes(b"metric,count\nsynthetic,1\n")
        elif element_id in {
            "report-id",
            "notes",
            "analyses",
            "report-groups",
            "created-from",
            "created-to",
        }:
            pass
        else:
            raise AssertionError("unexpected synthetic activation")

    def hover_control(self, token: str) -> None:
        element_id = self.tokens[token]
        if element_id != "section":
            raise AssertionError("unexpected synthetic hover")
        self.navigation_stage = 1
        self.harness.navigation_route.append("section")

    def choose_native_option(self, token: str, text: str) -> bool:
        element_id = self.tokens[token]
        self.values[element_id] = text
        if element_id == "report-type":
            self.form_stage = 1
        elif element_id == "category":
            self.form_stage = 2
        elif element_id == "report-id":
            self.form_stage = 3
        else:
            raise AssertionError("unexpected synthetic selector")
        return True

    def replace_focused_text(self, text: str) -> None:
        self.values[self.focused] = text

    def press_key(self, key: str) -> None:
        if key != "ENTER" or self.focused != "report-id":
            raise AssertionError(f"unexpected synthetic key {key}")


@dataclass
class SyntheticBatchHarness:
    root: Path
    config: AppConfig
    page: SyntheticPage
    navigation_route: list[str]
    export_count: int = 0
    edge_closed: bool = False
    connection_closed: bool = False
    csv_open_count: int = 0
    csv_read_count: int = 0

    @classmethod
    def from_fixture(cls, fixture: Path, root: Path) -> "SyntheticBatchHarness":
        html = fixture.read_text(encoding="utf-8")
        for marker in (
            "jobtypeselector",
            "_nav_frame1",
            'id="clear"',
            'id="export"',
            "Definerte rapporter",
        ):
            if marker not in html:
                raise AssertionError("synthetic fixture is incomplete")
        config = AppConfig(
            f"{EXPECTED_ORIGIN}/",
            EXPECTED_ORIGIN,
            root / "profile",
            root / "downloads",
        )
        harness = cls(root, config, page=None, navigation_route=[])  # type: ignore[arg-type]
        harness.page = SyntheticPage(harness)
        return harness

    @property
    def config_path(self) -> Path:
        return self.root / "config.json"

    @property
    def jobs_path(self) -> Path:
        return self.root / "jobs.json"

    def completed_files(self) -> tuple[Path, ...]:
        return tuple((self.root / "rådata").glob("*.csv"))

    def dependencies(self) -> BatchRunnerDependencies:
        edge = SyntheticEdge(self)
        connection = SyntheticConnection(self)
        ticks = {"value": 0.0}

        def clock() -> float:
            ticks["value"] += 0.1
            return ticks["value"]

        return BatchRunnerDependencies(
            config_load=lambda path, root: self.config,
            jobs_load=lambda path: jobs(),
            browser_open=lambda profile: OwnedBrowserStart(
                edge,
                PageTarget(
                    "page",
                    "ws://127.0.0.1:49152/devtools/page/page",
                    49152,
                ),
            ),
            connection_open=lambda target: connection,
            page_factory=lambda active_connection: self.page,
            actions_factory=DocumentDomActions,
            navigator_factory=lambda origin, active_clock, sleeper: DefinedReportsNavigator(
                origin, clock=active_clock, sleep=sleeper
            ),
            form_factory=lambda page, actions, origin, active_clock, sleeper: BatchReportForm(
                page,
                actions,
                origin,
                clock=active_clock,
                sleep=sleeper,
            ),
            contract_discover=discover_defined_reports_page,
            detector_factory=CsvArrivalDetector,
            finalizer=finalize_csv,
            clock=clock,
            sleeper=lambda seconds: None,
        )


def test_synthetic_batch_navigates_frames_exports_three_and_never_reads_csv(
    tmp_path: Path,
) -> None:
    harness = SyntheticBatchHarness.from_fixture(
        Path("tests/fixtures/batch_defined_reports.html"), tmp_path.resolve()
    )

    result = run_report_batch(
        harness.config_path,
        harness.jobs_path,
        JOB_KEYS,
        dependencies=harness.dependencies(),
        output=io.StringIO(),
        repository_root=harness.root,
    )

    assert result == 0
    assert harness.navigation_route == ["section", "defined_reports"]
    assert harness.export_count == 3
    assert sorted(path.name for path in harness.completed_files()) == [
        "answered__2026-08-01__2026-08-07.csv",
        "extraction__2026-08-01__2026-08-07.csv",
        "ordered__2026-08-01__2026-08-07.csv",
    ]
    assert harness.csv_open_count == 0
    assert harness.csv_read_count == 0
    assert harness.edge_closed and harness.connection_closed

