from __future__ import annotations

import unittest

from molstat.lvms.batch_controls import DocumentControlIdentity
from molstat.lvms.batch_navigation import (
    BatchNavigationError,
    DefinedReportsNavigator,
    discover_defined_reports_page,
    discover_navigation_anchor,
)


EXPECTED_ORIGIN = "https://lvms.example.invalid"
OTHER_ORIGIN = "https://other.example.invalid"


def raw_control(
    tag: str,
    element_id: str,
    *,
    name: str = "",
    control_type: str = "",
    label: str = "",
) -> dict[str, object]:
    return {
        "tag": tag,
        "type": control_type,
        "id": element_id,
        "name": name,
        "role": "",
        "label": label,
        "locator": [f"{tag.lower()}#{element_id}"],
    }


def raw_document(
    frame: str, control: dict[str, object]
) -> dict[str, object]:
    return {"frame": frame, "control": control}


def page_contract_payload() -> dict[str, object]:
    return {
        "job_type": raw_document(
            "pageentry",
            raw_control(
                "INPUT",
                "report-type",
                name="menu",
                control_type="text",
            ),
        ),
        "clear": raw_document(
            "_nav_frame1",
            raw_control("BUTTON", "clear", name="menu", control_type="button"),
        ),
        "export": raw_document(
            "_nav_frame1",
            raw_control("BUTTON", "export", name="menu", control_type="button"),
        ),
    }


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


class NavigationState:
    def __init__(self, route: tuple[str, ...] = (), *, destination: bool = False) -> None:
        self.route = route
        self.position = 0
        self.destination = destination
        self.origin = EXPECTED_ORIGIN
        self.activations: list[str] = []
        self.page = self
        self.actions = self

    def current_origin(self) -> str:
        return self.origin

    def evaluate_safe(self, expression: str, *, timeout_seconds: float = 2) -> object:
        del timeout_seconds
        if "LVMS_DEFINED_REPORTS_PAGE" in expression:
            return page_contract_payload() if self.destination else None
        if "LVMS_NAVIGATION_ANCHOR" in expression:
            if self.position >= len(self.route):
                return None
            next_step = self.route[self.position]
            if next_step == "section" and "Eksterne rapporter" in expression:
                return raw_document(
                    "top", raw_control("A", "section", label="external reports")
                )
            if next_step == "defined_reports" and "Definerte rapporter" in expression:
                return raw_document(
                    "top", raw_control("A", "defined_reports", label="defined reports")
                )
            return None
        raise AssertionError("unexpected safe expression")

    def activate(self, identity: DocumentControlIdentity) -> None:
        step = identity.control.element_id
        self.activations.append(step)
        if self.position >= len(self.route) or step != self.route[self.position]:
            raise AssertionError("unexpected navigation action")
        self.position += 1
        if self.position == len(self.route):
            self.destination = True

    def hover(self, identity: DocumentControlIdentity) -> None:
        self.activate(identity)


class ResponsiveNavigationState:
    def __init__(self, layout: str) -> None:
        self.layout = layout
        self.stage = "landing"
        self.origin = EXPECTED_ORIGIN
        self.interactions: list[str] = []

    def current_origin(self) -> str:
        return self.origin

    def evaluate_safe(self, expression: str, *, timeout_seconds: float = 2) -> object:
        del timeout_seconds
        if "LVMS_DEFINED_REPORTS_PAGE" in expression:
            return page_contract_payload() if self.stage == "destination" else None
        if "LVMS_NAVIGATION_ANCHOR" not in expression:
            raise AssertionError("unexpected safe expression")
        if "Definerte rapporter" in expression:
            if self.layout == "direct" and self.stage == "landing":
                return raw_document(
                    "workflow_frame",
                    raw_control("A", "defined_reports", label="defined reports"),
                )
            if self.stage == "section_open":
                return raw_document(
                    "top", raw_control("A", "defined_reports", label="defined reports")
                )
        if "Eksterne rapporter" in expression and (
            (self.layout in {"wide", "click_required"} and self.stage == "landing")
            or (self.layout == "click_required" and self.stage == "section_hovered")
            or self.stage == "more_open"
        ):
            return raw_document(
                "top", raw_control("A", "section", label="external reports")
            )
        if "Mer" in expression and self.layout == "narrow" and self.stage == "landing":
            return raw_document("top", raw_control("SPAN", "more", label="more"))
        return None

    def activate(self, identity: DocumentControlIdentity) -> None:
        element_id = identity.control.element_id
        self.interactions.append(f"activate:{element_id}")
        if element_id == "more" and self.stage == "landing":
            self.stage = "more_open"
        elif element_id == "section" and self.stage in {
            "landing",
            "more_open",
            "section_hovered",
        }:
            self.stage = "section_open"
        elif element_id == "defined_reports" and self.stage in {
            "landing",
            "section_open",
        }:
            self.stage = "destination"
        else:
            raise AssertionError("unexpected activation")

    def hover(self, identity: DocumentControlIdentity) -> None:
        element_id = identity.control.element_id
        self.interactions.append(f"hover:{element_id}")
        if element_id != "section" or self.stage not in {"landing", "more_open"}:
            raise AssertionError("unexpected hover")
        if self.layout == "click_required":
            self.stage = "section_hovered"
        else:
            self.stage = "section_open"


class TickingClock:
    def __init__(self) -> None:
        self.value = -1.0

    def __call__(self) -> float:
        self.value += 1.0
        return self.value


class BatchNavigationTests(unittest.TestCase):
    def test_page_requires_all_three_controls_in_exact_documents(self) -> None:
        page = FakeSafePage(page_contract_payload())

        contract = discover_defined_reports_page(page, EXPECTED_ORIGIN)

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(contract.job_type.frame, "pageentry")
        self.assertEqual(contract.job_type.control.element_id, "report-type")
        self.assertEqual(contract.clear.frame, "_nav_frame1")
        self.assertEqual(contract.export.control.element_id, "export")
        expression = page.expressions[0]
        self.assertNotIn(".src", expression)
        self.assertNotIn(".value", expression)
        self.assertNotIn("!el.readOnly", expression)
        self.assertIn("visible(frame)", expression)
        self.assertIn("data-datafield='reportType' i", expression)
        self.assertIn("button#clear[name='menu'][type='button']", expression)
        self.assertIn("button#export[name='menu'][type='button']", expression)
        self.assertIn('documents.push({frame: frameName, document: frameDocument})', expression)
        self.assertIn("if (!jobTypes.length)", expression)
        self.assertIn("if (!clears.length)", expression)
        self.assertIn("if (!exports.length)", expression)
        self.assertNotIn("length !== 1", expression)

    def test_page_rejects_absent_or_wrong_origin_contract(self) -> None:
        self.assertIsNone(
            discover_defined_reports_page(FakeSafePage(None), EXPECTED_ORIGIN)
        )
        with self.assertRaises(BatchNavigationError):
            discover_defined_reports_page(
                FakeSafePage(page_contract_payload(), OTHER_ORIGIN), EXPECTED_ORIGIN
            )

    def test_page_rejects_malformed_contract_metadata(self) -> None:
        malformed = page_contract_payload()
        malformed["export"] = None

        with self.assertRaises(BatchNavigationError):
            discover_defined_reports_page(FakeSafePage(malformed), EXPECTED_ORIGIN)

    def test_page_reports_sanitized_missing_control(self) -> None:
        with self.assertRaisesRegex(
            BatchNavigationError, "Defined Reports job_type is missing"
        ):
            discover_defined_reports_page(
                FakeSafePage({"missing": "job_type"}), EXPECTED_ORIGIN
            )

    def test_navigation_anchor_accepts_allowlisted_control_in_same_origin_frame(self) -> None:
        payload = raw_document(
            "workflow_frame",
            raw_control("A", "defined_reports", label="defined reports"),
        )
        page = FakeSafePage(payload)

        anchor = discover_navigation_anchor(
            page, EXPECTED_ORIGIN, "Definerte rapporter"
        )

        self.assertIsNotNone(anchor)
        assert anchor is not None
        self.assertEqual(anchor.frame, "workflow_frame")
        with self.assertRaises(BatchNavigationError):
            discover_navigation_anchor(page, EXPECTED_ORIGIN, "Arbitrary label")

    def test_navigation_accepts_lvms_span_only_for_more_menu(self) -> None:
        more = FakeSafePage(
            raw_document("top", raw_control("SPAN", "more", label="more"))
        )

        anchor = discover_navigation_anchor(more, EXPECTED_ORIGIN, "Mer")

        self.assertIsNotNone(anchor)
        assert anchor is not None
        self.assertEqual(anchor.control.tag, "SPAN")
        self.assertIn(
            '"td.sitemap_TramStopNormText,td,a,button,span"',
            more.expressions[0],
        )

        with self.assertRaises(BatchNavigationError):
            discover_navigation_anchor(
                FakeSafePage(
                    raw_document(
                        "top",
                        raw_control("SPAN", "external", label="external reports"),
                    )
                ),
                EXPECTED_ORIGIN,
                "Eksterne rapporter",
            )

    def test_navigation_prioritizes_actual_lvms_tram_stop_text_cell(self) -> None:
        tram_line = FakeSafePage(
            raw_document(
                "top",
                raw_control("TD", "defined_reports_tram", label=""),
            )
        )

        anchor = discover_navigation_anchor(
            tram_line, EXPECTED_ORIGIN, "Definerte rapporter"
        )

        self.assertIsNotNone(anchor)
        assert anchor is not None
        self.assertEqual(anchor.control.tag, "TD")
        expression = tram_line.expressions[0]
        self.assertIn('"td.sitemap_TramStopNormText,td,a,button,span"', expression)
        self.assertIn('matches.find((match) => match.control.matches(', expression)
        self.assertIn('"td.sitemap_TramStopNormText"', expression)
        self.assertIn("tramLine || matches[0]", expression)

    def test_navigator_handles_direct_wide_and_narrow_responsive_routes(self) -> None:
        expected = {
            "direct": ["activate:defined_reports"],
            "wide": ["hover:section", "activate:defined_reports"],
            "narrow": [
                "activate:more",
                "hover:section",
                "activate:defined_reports",
            ],
            "click_required": [
                "hover:section",
                "activate:section",
                "activate:defined_reports",
            ],
        }
        for layout, interactions in expected.items():
            with self.subTest(layout=layout):
                state = ResponsiveNavigationState(layout)
                navigator = DefinedReportsNavigator(
                    EXPECTED_ORIGIN,
                    timeout_seconds=20,
                    clock=TickingClock(),
                    sleep=lambda seconds: None,
                )

                navigator.reach(state, state)

                self.assertEqual(state.interactions, interactions)

    def test_navigator_accepts_page_already_at_destination(self) -> None:
        state = NavigationState(destination=True)
        navigator = DefinedReportsNavigator(
            EXPECTED_ORIGIN, clock=lambda: 0.0, sleep=lambda seconds: None
        )

        result = navigator.reach(state.page, state.actions)

        self.assertEqual(result.export.control.element_id, "export")
        self.assertEqual(state.activations, [])

    def test_navigator_uses_direct_or_section_then_defined_reports_route(self) -> None:
        for route in (("defined_reports",), ("section", "defined_reports")):
            with self.subTest(route=route):
                state = NavigationState(route)
                navigator = DefinedReportsNavigator(
                    EXPECTED_ORIGIN,
                    clock=lambda: 0.0,
                    sleep=lambda seconds: None,
                )

                navigator.reach(state.page, state.actions)

                self.assertEqual(state.activations, list(route))

    def test_navigator_stops_after_origin_change_or_deadline(self) -> None:
        state = NavigationState(("defined_reports",))

        class OriginChangingActions:
            def activate(self, identity: DocumentControlIdentity) -> None:
                state.activate(identity)
                state.origin = OTHER_ORIGIN

        navigator = DefinedReportsNavigator(
            EXPECTED_ORIGIN, clock=lambda: 0.0, sleep=lambda seconds: None
        )
        with self.assertRaises(BatchNavigationError):
            navigator.reach(state.page, OriginChangingActions())

        unavailable = NavigationState()
        timed = DefinedReportsNavigator(
            EXPECTED_ORIGIN,
            timeout_seconds=2,
            clock=TickingClock(),
            sleep=lambda seconds: None,
        )
        with self.assertRaises(BatchNavigationError):
            timed.reach(unavailable.page, unavailable.actions)

    def test_navigator_only_polls_after_defined_reports_activation(self) -> None:
        class DelayedDestination:
            def __init__(self) -> None:
                self.activations: list[str] = []
                self.destination_checks = 0

            def current_origin(self) -> str:
                return EXPECTED_ORIGIN

            def evaluate_safe(
                self, expression: str, *, timeout_seconds: float = 2
            ) -> object:
                del timeout_seconds
                if "LVMS_DEFINED_REPORTS_PAGE" in expression:
                    self.destination_checks += 1
                    return (
                        page_contract_payload()
                        if self.destination_checks >= 3
                        else None
                    )
                if "Definerte rapporter" in expression:
                    return raw_document(
                        "top", raw_control("A", "defined_reports")
                    )
                if "Eksterne rapporter" in expression:
                    return raw_document("top", raw_control("A", "section"))
                raise AssertionError("unexpected expression")

            def activate(self, identity: DocumentControlIdentity) -> None:
                self.activations.append(identity.control.element_id)

        state = DelayedDestination()
        navigator = DefinedReportsNavigator(
            EXPECTED_ORIGIN, clock=lambda: 0.0, sleep=lambda seconds: None
        )

        navigator.reach(state, state)

        self.assertEqual(state.activations, ["defined_reports"])

    def test_navigator_reports_bounded_navigation_substages(self) -> None:
        state = NavigationState(("defined_reports",))
        stages: list[str] = []
        navigator = DefinedReportsNavigator(
            EXPECTED_ORIGIN, clock=lambda: 0.0, sleep=lambda seconds: None
        )

        navigator.reach(state, state, stage=stages.append)

        self.assertIn("defined_reports_find_direct", stages)
        self.assertIn("defined_reports_activate_direct", stages)
        self.assertEqual(stages[-1], "defined_reports_ready")

    def test_navigator_reports_contract_metadata_failure(self) -> None:
        page = FakeSafePage({"unexpected": "shape"})
        stages: list[str] = []
        navigator = DefinedReportsNavigator(
            EXPECTED_ORIGIN, clock=lambda: 0.0, sleep=lambda seconds: None
        )

        with self.assertRaises(BatchNavigationError):
            navigator.reach(page, NavigationState().actions, stage=stages.append)

        self.assertEqual(stages[-1], "defined_reports_contract_metadata")

    def test_navigator_reports_missing_control_stage(self) -> None:
        class MissingExportPage:
            def __init__(self) -> None:
                self.probes = 0

            def current_origin(self) -> str:
                return EXPECTED_ORIGIN

            def evaluate_safe(self, expression: str, *, timeout_seconds: float = 2):
                del timeout_seconds
                if "LVMS_DEFINED_REPORTS_PAGE" in expression:
                    self.probes += 1
                    return {"missing": "export"}
                return None

        page = MissingExportPage()
        stages: list[str] = []
        navigator = DefinedReportsNavigator(
            EXPECTED_ORIGIN,
            timeout_seconds=3,
            clock=TickingClock(),
            sleep=lambda seconds: None,
        )

        with self.assertRaisesRegex(
            BatchNavigationError, "Defined Reports export is missing"
        ):
            navigator.reach(page, NavigationState().actions, stage=stages.append)

        self.assertEqual(stages[-1], "defined_reports_missing_export")
        self.assertGreater(page.probes, 1)

    def test_navigator_does_not_let_loading_form_block_navigation(self) -> None:
        class LoadingLanding(NavigationState):
            def __init__(self) -> None:
                super().__init__(("defined_reports",))
                self.probes = 0

            def evaluate_safe(self, expression: str, *, timeout_seconds: float = 2):
                if "LVMS_DEFINED_REPORTS_PAGE" in expression:
                    self.probes += 1
                    if self.probes == 1:
                        return {"missing": "job_type"}
                return super().evaluate_safe(
                    expression, timeout_seconds=timeout_seconds
                )

        state = LoadingLanding()
        navigator = DefinedReportsNavigator(
            EXPECTED_ORIGIN, clock=lambda: 0.0, sleep=lambda seconds: None
        )

        navigator.reach(state, state)

        self.assertEqual(state.activations, ["defined_reports"])

    def test_navigator_reports_contract_evaluation_failure(self) -> None:
        class BrokenPage:
            def current_origin(self) -> str:
                return EXPECTED_ORIGIN

            def evaluate_safe(self, expression: str, *, timeout_seconds: float = 2):
                del expression, timeout_seconds
                raise RuntimeError("private browser detail")

        stages: list[str] = []
        navigator = DefinedReportsNavigator(
            EXPECTED_ORIGIN, clock=lambda: 0.0, sleep=lambda seconds: None
        )

        with self.assertRaises(RuntimeError):
            navigator.reach(BrokenPage(), NavigationState().actions, stage=stages.append)

        self.assertEqual(stages[-1], "defined_reports_contract_evaluation")

    def test_navigator_waits_for_transient_origin_to_return(self) -> None:
        state = NavigationState(destination=True)
        origins = [OTHER_ORIGIN, OTHER_ORIGIN]
        state.current_origin = (  # type: ignore[method-assign]
            lambda: origins.pop(0) if origins else EXPECTED_ORIGIN
        )
        stages: list[str] = []
        navigator = DefinedReportsNavigator(
            EXPECTED_ORIGIN,
            timeout_seconds=10,
            clock=TickingClock(),
            sleep=lambda seconds: None,
        )

        result = navigator.reach(state, state, stage=stages.append)

        self.assertEqual(result.export.control.element_id, "export")
        self.assertIn("defined_reports_wait_origin", stages)
        self.assertEqual(stages[-1], "defined_reports_ready")


if __name__ == "__main__":
    unittest.main()

