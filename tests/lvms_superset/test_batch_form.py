from __future__ import annotations

import unittest

from molstat.lvms.batch_controls import DocumentControlIdentity
from molstat.lvms.batch_form import (
    BatchFormError,
    BatchReportForm,
    discover_report_role,
)
from molstat.lvms.batch_navigation import DefinedReportsPage
from molstat.lvms.report_job import ReportJob, validate_report_job
from molstat.lvms.control_identity import ControlIdentity


EXPECTED_ORIGIN = "https://lvms.example.invalid"
OTHER_ORIGIN = "https://other.example.invalid"


def raw_control(
    tag: str,
    element_id: str,
    *,
    label: str,
    control_type: str = "",
    role: str = "",
) -> dict[str, object]:
    return {
        "frame": "_nav_frame1",
        "control": {
            "tag": tag,
            "type": control_type,
            "id": element_id,
            "name": element_id,
            "role": role,
            "label": label,
            "locator": [f"{tag.lower()}#{element_id}"],
        },
    }


ROLE_PAYLOADS = {
    "category": raw_control("SELECT", "category", label="kategori"),
    "report_id": raw_control("SELECT", "report-id", label="rapport id"),
    "notes": raw_control("TEXTAREA", "notes", label="notater"),
    "analysis_codes": raw_control("TEXTAREA", "analyses", label="angi analyse(r)"),
    "report_groups": raw_control(
        "INPUT",
        "report-groups",
        label="velg en eller flere rapportgrupper",
        control_type="text",
    ),
    "created_from": raw_control(
        "INPUT", "created-from", label="analyse opprettet fom:", control_type="text"
    ),
    "created_to": raw_control(
        "INPUT", "created-to", label="analyse opprettet tom:", control_type="text"
    ),
}


def identity(
    frame: str, tag: str, element_id: str, **values: str
) -> DocumentControlIdentity:
    return DocumentControlIdentity(
        frame,
        ControlIdentity(tag, element_id=element_id, **values),
    )


def defined_reports_page() -> DefinedReportsPage:
    return DefinedReportsPage(
        job_type=identity(
            "top",
            "SELECT",
            "jobtypeselector",
            name="jobtypeselector",
        ),
        clear=identity(
            "_nav_frame1",
            "BUTTON",
            "clear",
            name="menu",
            control_type="button",
        ),
        export=identity(
            "_nav_frame1",
            "BUTTON",
            "export",
            name="menu",
            control_type="button",
        ),
    )


def job() -> ReportJob:
    return validate_report_job(
        {
            "job_key": "ordered",
            "report_type": "TYPE_A",
            "category": "CATEGORY_A",
            "report_id": "REPORT-A",
            "report_groups": ["OU-HEM", "OU-MOTTAKMOLPAT"],
            "analysis_codes": ["ANALYSIS-A", "ANALYSIS-B"],
            "created_from": "01.08.2026",
            "created_to": "07.08.2026",
            "output_stem": "ordered",
        }
    )


class FakeSafePage:
    def __init__(self, payload: object, origin: str = EXPECTED_ORIGIN) -> None:
        self.payload = payload
        self.origin = origin
        self.expressions: list[str] = []

    def current_origin(self) -> str:
        return self.origin

    def evaluate_safe(self, expression: str, *, timeout_seconds: float = 2) -> object:
        del timeout_seconds
        self.expressions.append(expression)
        return self.payload


class FormState:
    def __init__(self, *, missing_role: str | None = None) -> None:
        self.missing_role = missing_role
        self.calls: list[tuple[str, str, str, str]] = []
        self.activated: list[str] = []
        self.commits: list[str] = []
        self.page = self
        self.actions = self

    def current_origin(self) -> str:
        return EXPECTED_ORIGIN

    def evaluate_safe(self, expression: str, *, timeout_seconds: float = 2) -> object:
        del timeout_seconds
        for role, payload in ROLE_PAYLOADS.items():
            if f'const requestedRole = "{role}"' in expression:
                return None if role == self.missing_role else payload
        raise AssertionError("requested role was not encoded")

    def choose_text(self, control: DocumentControlIdentity, text: str) -> None:
        self.calls.append(("choose", control.frame, control.control.element_id, text))

    def replace_text(self, control: DocumentControlIdentity, text: str) -> None:
        self.calls.append(("replace", control.frame, control.control.element_id, text))

    def activate(self, control: DocumentControlIdentity) -> None:
        self.activated.append(control.control.element_id)

    def commit_choice(self, control: DocumentControlIdentity) -> None:
        self.commits.append(control.control.element_id)


class SlowParameterState(FormState):
    def __init__(self) -> None:
        super().__init__()
        self.analysis_checks = 0

    def evaluate_safe(self, expression: str, *, timeout_seconds: float = 2) -> object:
        if 'const requestedRole = "analysis_codes"' in expression:
            self.analysis_checks += 1
            if self.analysis_checks <= 25:
                return None
        return super().evaluate_safe(expression, timeout_seconds=timeout_seconds)


class RefreshingFinalParameterState(FormState):
    def __init__(self) -> None:
        super().__init__()
        self.created_to_checks = 0

    def evaluate_safe(self, expression: str, *, timeout_seconds: float = 2) -> object:
        del timeout_seconds
        if 'const requestedRole = "created_to"' in expression:
            self.created_to_checks += 1
            payload = dict(ROLE_PAYLOADS["created_to"])
            control = dict(payload["control"])  # type: ignore[arg-type]
            control["id"] = f"{control['id']}-{self.created_to_checks}"
            payload["control"] = control
            return payload
        return super().evaluate_safe(expression)

    def replace_text(self, control: DocumentControlIdentity, text: str) -> None:
        if control.control.element_id.startswith("created-to"):
            if control.control.element_id != "created-to-2":
                raise AssertionError("stale final parameter identity")
        super().replace_text(control, text)


class RefreshingReportIdState(FormState):
    def __init__(self) -> None:
        super().__init__()
        self.report_id_checks = 0

    def evaluate_safe(self, expression: str, *, timeout_seconds: float = 2) -> object:
        del timeout_seconds
        if 'const requestedRole = "report_id"' in expression:
            self.report_id_checks += 1
            payload = dict(ROLE_PAYLOADS["report_id"])
            control = dict(payload["control"])  # type: ignore[arg-type]
            control["id"] = f"report-id-{self.report_id_checks}"
            payload["control"] = control
            return payload
        return super().evaluate_safe(expression)

    def commit_choice(self, control: DocumentControlIdentity) -> None:
        if control.control.element_id != "report-id-3":
            raise AssertionError("stale report id identity")
        super().commit_choice(control)

class TickingClock:
    def __init__(self) -> None:
        self.value = -1.0

    def __call__(self) -> float:
        self.value += 1.0
        return self.value


class ClearingPage:
    def __init__(self, *, dynamic_roles_present: bool) -> None:
        self.dynamic_roles_present = dynamic_roles_present
        self.category_checks = 0

    def current_origin(self) -> str:
        return EXPECTED_ORIGIN

    def evaluate_safe(self, expression: str, *, timeout_seconds: float = 2) -> object:
        del timeout_seconds
        if 'const requestedRole = "category"' in expression:
            self.category_checks += 1
            return ROLE_PAYLOADS["category"]
        for role in ("analysis_codes", "created_from", "created_to"):
            if f'const requestedRole = "{role}"' in expression:
                return ROLE_PAYLOADS[role] if self.dynamic_roles_present else None
        return None


class ReappearingClearPage(ClearingPage):
    def __init__(self) -> None:
        super().__init__(dynamic_roles_present=False)
        self.round = 0

    def evaluate_safe(self, expression: str, *, timeout_seconds: float = 2) -> object:
        for role in ("analysis_codes", "created_from", "created_to"):
            if f'const requestedRole = "{role}"' in expression:
                result = ROLE_PAYLOADS[role] if self.round == 1 else None
                if role == "created_to":
                    self.round += 1
                return result
        return super().evaluate_safe(expression, timeout_seconds=timeout_seconds)


class BatchFormTests(unittest.TestCase):
    def test_discovers_each_supported_role_across_named_documents(self) -> None:
        expected_ids = {
            "category": "category",
            "report_id": "report-id",
            "notes": "notes",
            "analysis_codes": "analyses",
            "report_groups": "report-groups",
            "created_from": "created-from",
            "created_to": "created-to",
        }
        for role, expected_id in expected_ids.items():
            with self.subTest(role=role):
                page = FakeSafePage(ROLE_PAYLOADS[role])

                result = discover_report_role(page, EXPECTED_ORIGIN, role)

                self.assertIsNotNone(result)
                assert result is not None
                self.assertEqual(result.control.element_id, expected_id)
                script = page.expressions[0]
                for forbidden in (
                    ".src",
                    ".href",
                    "document.cookie",
                    "localStorage",
                    "sessionStorage",
                ):
                    self.assertNotIn(forbidden, script)
                self.assertNotIn("!el.readOnly", script)
                self.assertIn("if (!visible(frame)) continue;", script)
                self.assertIn("ambiguous: true", script)
                self.assertNotIn("[role='grid']", script)
                self.assertNotIn("[role='treegrid']", script)
                self.assertNotIn("!previous.querySelector", script)
                self.assertIn('previous.querySelector("input,select,textarea")', script)
                self.assertIn("previousControl.value", script)
                self.assertIn("[id*='patient' i]", script)

    def test_role_discovery_rejects_unknown_absent_or_wrong_origin(self) -> None:
        with self.assertRaises(BatchFormError):
            discover_report_role(FakeSafePage(None), EXPECTED_ORIGIN, "unknown")
        self.assertIsNone(
            discover_report_role(FakeSafePage(None), EXPECTED_ORIGIN, "category")
        )
        with self.assertRaises(BatchFormError):
            discover_report_role(
                FakeSafePage(ROLE_PAYLOADS["category"], OTHER_ORIGIN),
                EXPECTED_ORIGIN,
                "category",
            )

    def test_role_discovery_rejects_incompatible_or_unsafe_controls(self) -> None:
        invalid = (
            raw_control("BUTTON", "category", label="kategori"),
            raw_control("INPUT", "category", label="kategori", control_type="hidden"),
            raw_control("INPUT", "category", label="kategori", role="gridcell"),
            {**ROLE_PAYLOADS["category"], "frame": ""},
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                with self.assertRaises(BatchFormError):
                    discover_report_role(
                        FakeSafePage(payload), EXPECTED_ORIGIN, "category"
                    )

    def test_role_discovery_accepts_gridcell_parameter_input(self) -> None:
        payload = raw_control(
            "INPUT",
            "analyses",
            label="angi analyse(r)",
            control_type="text",
            role="gridcell",
        )

        result = discover_report_role(
            FakeSafePage(payload), EXPECTED_ORIGIN, "analysis_codes"
        )

        self.assertIsNotNone(result)

    def test_populate_advances_in_strict_stage_order(self) -> None:
        state = FormState()
        form = BatchReportForm(
            state.page,
            state.actions,
            EXPECTED_ORIGIN,
            clock=lambda: 0.0,
            sleep=lambda seconds: None,
        )

        form.populate(defined_reports_page(), job())

        self.assertEqual(
            state.calls,
            [
                ("choose", "top", "jobtypeselector", "TYPE_A"),
                ("choose", "_nav_frame1", "category", "CATEGORY_A"),
                ("choose", "_nav_frame1", "report-id", "REPORT-A"),
                ("choose", "_nav_frame1", "report-id", "REPORT-A"),
                (
                    "replace",
                    "_nav_frame1",
                    "report-groups",
                    "OU-HEM,OU-MOTTAKMOLPAT",
                ),
                ("replace", "_nav_frame1", "analyses", "ANALYSIS-A,ANALYSIS-B"),
                ("replace", "_nav_frame1", "created-from", "01.08.2026"),
                ("replace", "_nav_frame1", "created-to", "07.08.2026"),
            ],
        )

        self.assertEqual(state.activated, [])
        self.assertEqual(state.commits, ["report-id"])

    def test_missing_stage_stops_before_later_actions(self) -> None:
        state = FormState(missing_role="report_id")
        form = BatchReportForm(
            state.page,
            state.actions,
            EXPECTED_ORIGIN,
            timeout_seconds=2,
            clock=TickingClock(),
            sleep=lambda seconds: None,
        )

        with self.assertRaises(BatchFormError):
            form.populate(defined_reports_page(), job())

        self.assertEqual(
            state.calls,
            [
                ("choose", "top", "jobtypeselector", "TYPE_A"),
                ("choose", "_nav_frame1", "category", "CATEGORY_A"),
            ],
        )
        self.assertEqual(state.activated, [])

    def test_populate_waits_for_slow_lvms_parameter_refresh(self) -> None:
        state = SlowParameterState()
        form = BatchReportForm(
            state.page,
            state.actions,
            EXPECTED_ORIGIN,
            clock=TickingClock(),
            sleep=lambda seconds: None,
        )

        form.populate(defined_reports_page(), job())

        self.assertEqual(state.analysis_checks, 26)
        self.assertEqual(
            state.calls[-1],
            ("replace", "_nav_frame1", "created-to", "07.08.2026"),
        )

    def test_populate_rediscovers_final_parameter_after_grid_refresh(self) -> None:
        state = RefreshingFinalParameterState()
        form = BatchReportForm(
            state.page,
            state.actions,
            EXPECTED_ORIGIN,
            clock=TickingClock(),
            sleep=lambda seconds: None,
        )

        form.populate(defined_reports_page(), job())

        self.assertEqual(state.created_to_checks, 2)

    def test_populate_reapplies_and_rediscovers_report_id_before_enter(self) -> None:
        state = RefreshingReportIdState()
        form = BatchReportForm(
            state.page,
            state.actions,
            EXPECTED_ORIGIN,
            clock=TickingClock(),
            sleep=lambda seconds: None,
        )

        form.populate(defined_reports_page(), job())

        report_choices = [
            call for call in state.calls if call[2].startswith("report-id-")
        ]
        self.assertEqual(
            report_choices,
            [
                ("choose", "_nav_frame1", "report-id-1", "REPORT-A"),
                ("choose", "_nav_frame1", "report-id-2", "REPORT-A"),
            ],
        )
        self.assertEqual(state.report_id_checks, 3)

    def test_wait_until_clear_allows_persistent_empty_choice_controls(self) -> None:
        page = ClearingPage(dynamic_roles_present=False)
        form = BatchReportForm(
            page,
            FormState().actions,
            EXPECTED_ORIGIN,
            timeout_seconds=2,
            clock=TickingClock(),
            sleep=lambda seconds: None,
        )

        form.wait_until_clear()

        self.assertEqual(page.category_checks, 0)

    def test_wait_until_clear_times_out_while_a_dynamic_role_remains(self) -> None:
        page = ClearingPage(dynamic_roles_present=True)
        form = BatchReportForm(
            page,
            FormState().actions,
            EXPECTED_ORIGIN,
            timeout_seconds=2,
            clock=TickingClock(),
            sleep=lambda seconds: None,
        )

        with self.assertRaises(BatchFormError):
            form.wait_until_clear()

    def test_wait_until_clear_requires_clear_state_to_remain_stable(self) -> None:
        page = ReappearingClearPage()
        form = BatchReportForm(
            page,
            FormState().actions,
            EXPECTED_ORIGIN,
            timeout_seconds=10,
            clock=TickingClock(),
            sleep=lambda seconds: None,
        )

        form.wait_until_clear()

        self.assertGreaterEqual(page.round, 4)


if __name__ == "__main__":
    unittest.main()

