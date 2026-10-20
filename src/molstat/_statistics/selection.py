"""Use the selected JSON's exact code list for each report role."""
from collections.abc import Collection, Mapping

AnalysisSelection = Collection[str] | Mapping[str, Collection[str]]


def codes_for_report(selection: AnalysisSelection, role: str) -> frozenset[str]:
    values = selection.get(role, ()) if isinstance(selection, Mapping) else selection
    return frozenset(values)
