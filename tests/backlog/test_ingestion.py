from pathlib import Path

import pytest

from molstat.backlog import (
    CsvContract,
    CsvImportError,
    classify_workflow,
    read_restanse_csv,
)
from molstat.backlog import WorkflowStage


@pytest.mark.parametrize(
    ("status", "arrival", "result", "comment", "stage"),
    [
        ("Initial", "31.08.2026 08:00", "", "", WorkflowStage.READY),
        ("Initial", "", "", "", WorkflowStage.IN_TRANSIT),
        ("Initial", "NA", "", "", WorkflowStage.IN_TRANSIT),
        (
            "Completed",
            "31.08.2026 08:00",
            "Ikke påvist",
            "",
            WorkflowStage.AWAITING_APPROVAL,
        ),
        (
            "Completed",
            "31.08.2026 08:00",
            "Ikke utført",
            "",
            WorkflowStage.AWAITING_APPROVAL,
        ),
        (
            "Completed",
            "31.08.2026 08:00",
            "Utført",
            "",
            None,
        ),
        (
            "Completed",
            "31.08.2026 08:00",
            "Utfort",
            "",
            None,
        ),
        (
            "Completed",
            "31.08.2026 08:00",
            "Markør påvist",
            "",
            None,
        ),
        (
            "Completed",
            "31.08.2026 08:00",
            "Etablert klon",
            "",
            None,
        ),
        (
            "Completed",
            "31.08.2026 08:00",
            "",
            "Ikke utfort etter vurdering",
            WorkflowStage.AWAITING_APPROVAL,
        ),
    ],
)
def test_classify_workflow(status, arrival, result, comment, stage):
    assert classify_workflow(
        status,
        arrival,
        result,
        comment,
        ("completed",),
    ) is stage


def contract() -> CsvContract:
    return CsvContract(
        delimiter=";", encoding="utf-8",
        columns={"sample_id": "Sample ID", "analysis_code": "Analyse", "created_at": "Tidspunkt", "status": "Status"},
        completed_values=("completed", "ferdig", "besvart"),
    )


def test_reads_and_deduplicates_rows(tmp_path):
    path = tmp_path / "restanse.csv"
    path.write_text(
        "Sample ID;Analyse;Tidspunkt;Status\n"
        "S1;PML-RARA-OU;15.08.2026 10:00;pending\n"
        "S1;PML-RARA-OU;15.08.2026 10:00;pending\n"
        "S2;FLT3-ITD-OU;15.08.2026 11:00;completed\n",
        encoding="utf-8",
    )
    result = read_restanse_csv(path, contract())
    assert len(result.samples) == 2
    assert result.duplicate_rows == 1
    assert result.samples[1].stage is WorkflowStage.AWAITING_APPROVAL


def test_same_sample_and_analysis_is_unique_across_timestamps(tmp_path):
    path = tmp_path / "restanse.csv"
    path.write_text(
        "Sample ID;Analyse;Tidspunkt;Status\n"
        "S1;A-OU;15.08.2026 10:00;pending\n"
        "S1;A-OU;15.08.2026 11:00;besvart\n",
        encoding="utf-8",
    )

    result = read_restanse_csv(path, contract())

    assert len(result.samples) == 1
    assert result.duplicate_rows == 1
    assert result.samples[0].stage is WorkflowStage.AWAITING_APPROVAL


def test_reports_missing_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("Sample ID;Analyse\nS1;A-OU\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="mangler kolonner"):
        read_restanse_csv(path, contract())


def test_skips_blank_rows_and_reports_invalid_rows(tmp_path):
    path = tmp_path / "mixed.csv"
    path.write_text(
        "Sample ID;Analyse;Tidspunkt;Status\n"
        ";;;;\n"
        "S1;A-OU;ugyldig;pending\n"
        "S2;A-OU;15.08.2026 10:00;pending\n",
        encoding="utf-8",
    )
    result = read_restanse_csv(path, contract())
    assert len(result.samples) == 1
    assert result.invalid_rows == 1


def test_unwraps_lvms_excel_text_wrapper(tmp_path):
    path = tmp_path / "wrapped.csv"
    path.write_text(
        "Sample ID;Analyse;Tidspunkt;Status\n"
        '=T("S1");=T("PML-RARA-OU");=T("15.08.2026 10:00");=T("pending")\n',
        encoding="utf-8",
    )
    result = read_restanse_csv(path, contract())
    assert len(result.samples) == 1
    assert result.samples[0].sample_id == "S1"
    assert result.samples[0].analysis_code == "PML-RARA-OU"


def real_contract() -> CsvContract:
    return CsvContract(
        delimiter=";", encoding="utf-8",
        columns={
            "sample_id": "SampleID",
            "analysis_code": "Analyse",
            "created_at": "Tidspunkt analysebestilling",
            "status": "Status analyse",
            "preliminary_status": "Status prelgruppe",
            "result": "Analyseresultat",
            "external_comment": "Ekstern analysekommentar",
        },
        completed_values=("completed",),
    )


def test_uses_analysis_order_time_not_arrival_time(tmp_path):
    """Tidsgrunnlaget skal være 'Tidspunkt analysebestilling', ikke ankomst."""
    path = tmp_path / "restanse.csv"
    path.write_text(
        "SampleID;Analyse;Tidspunkt ankomst;Tidspunkt analysebestilling;Status analyse;Status prelgruppe;Analyseresultat\n"
        "S1;TRG-OU;01.06.2026 08:00;13.08.2026 12:31;Initial;Initial;\n",
        encoding="utf-8",
    )

    result = read_restanse_csv(path, real_contract())

    assert len(result.samples) == 1
    # ordered_at skal være bestillingstidspunktet, ikke ankomst.
    from datetime import datetime
    assert result.samples[0].ordered_at == datetime(2026, 8, 13, 12, 31)


def test_completed_analysis_with_non_initial_preliminary_status_is_awaiting_approval(tmp_path):
    path = tmp_path / "restanse.csv"
    path.write_text(
        "SampleID;Analyse;Tidspunkt ankomst;Tidspunkt analysebestilling;Status analyse;Status prelgruppe;Analyseresultat\n"
        "S1;TRG-OU;21.08.2026 09:00;21.08.2026 09:00;Completed;Til signering;\n"
        "S2;TRG-OU;21.08.2026 09:00;21.08.2026 09:00;Completed;Initial;\n",
        encoding="utf-8",
    )

    result = read_restanse_csv(path, real_contract())

    assert [sample.sample_id for sample in result.samples] == ["S1"]
    assert result.samples[0].stage is WorkflowStage.AWAITING_APPROVAL
    assert result.excluded_rows == 1


def test_not_performed_in_result_is_awaiting_approval(tmp_path):
    path = tmp_path / "restanse.csv"
    path.write_text(
        "SampleID;Analyse;Tidspunkt ankomst;Tidspunkt analysebestilling;Status analyse;Status prelgruppe;Analyseresultat;Ekstern analysekommentar\n"
        "S1;TRG-OU;21.08.2026 09:00;21.08.2026 09:00;Initial;Initial;Ikke utført;\n"
        "S2;TRG-OU;21.08.2026 09:00;21.08.2026 09:00;Initial;Initial;;\n",
        encoding="utf-8",
    )

    result = read_restanse_csv(path, real_contract())

    assert [sample.sample_id for sample in result.samples] == ["S1", "S2"]
    assert result.excluded_rows == 0
    assert result.samples[0].stage is WorkflowStage.AWAITING_APPROVAL


def test_not_performed_in_external_comment_is_awaiting_approval(tmp_path):
    path = tmp_path / "restanse.csv"
    path.write_text(
        "SampleID;Analyse;Tidspunkt ankomst;Tidspunkt analysebestilling;Status analyse;Status prelgruppe;Analyseresultat;Ekstern analysekommentar\n"
        "S1;TRG-OU;21.08.2026 09:00;21.08.2026 09:00;Initial;Initial;;IkKe UtFøRt etter vurdering\n"
        "S2;TRG-OU;21.08.2026 09:00;21.08.2026 09:00;Initial;Initial;;\n",
        encoding="utf-8",
    )

    result = read_restanse_csv(path, real_contract())

    assert [sample.sample_id for sample in result.samples] == ["S1", "S2"]
    assert result.excluded_rows == 0
    assert result.samples[0].stage is WorkflowStage.AWAITING_APPROVAL


def test_performed_or_marker_results_are_excluded_from_list(tmp_path):
    """Utført, markør-påvist og etablert-resultater skal ikke telles på tavla."""
    path = tmp_path / "restanse.csv"
    path.write_text(
        "SampleID;Analyse;Tidspunkt ankomst;Tidspunkt analysebestilling;Status analyse;Status prelgruppe;Analyseresultat;Ekstern analysekommentar\n"
        "S1;TRG-OU;21.08.2026 09:00;21.08.2026 09:00;Completed;Pending approval;Utført;\n"
        "S2;TRG-OU;21.08.2026 09:00;21.08.2026 09:00;Completed;Pending approval;Markør påvist;\n"
        "S3;TRG-OU;21.08.2026 09:00;21.08.2026 09:00;Completed;Pending approval;Etablert klon;\n"
        "S4;TRG-OU;21.08.2026 09:00;21.08.2026 09:00;Completed;Pending approval;Positiv;\n",
        encoding="utf-8",
    )

    result = read_restanse_csv(path, real_contract())

    assert [sample.sample_id for sample in result.samples] == ["S4"]
    assert result.excluded_rows == 3
    assert result.samples[0].stage is WorkflowStage.AWAITING_APPROVAL


def test_collapses_subanalyses_to_one_sample_in_group(tmp_path):
    path = tmp_path / "restanse.csv"
    path.write_text(
        "SampleID;Analyse;Tidspunkt ankomst;Tidspunkt analysebestilling;Status analyse;Status prelgruppe;Analyseresultat\n"
        "S1;IGH-VDJ-OU;21.08.2026 09:00;21.08.2026 09:00;Initial;Initial;\n"
        "S1;TRG-OU;21.08.2026 10:00;21.08.2026 10:00;Initial;Initial;\n"
        "S2;TRG-OU;21.08.2026 11:00;21.08.2026 11:00;Initial;Initial;\n",
        encoding="utf-8",
    )

    result = read_restanse_csv(
        path,
        real_contract(),
        analysis_groups={"Klonalitet": ("IGH-VDJ-OU", "TRG-OU")},
    )

    assert [(sample.sample_id, sample.analysis_code) for sample in result.samples] == [
        ("S1", "Klonalitet"),
        ("S2", "Klonalitet"),
    ]
    assert result.duplicate_rows == 1


def test_excludes_rows_without_order_time(tmp_path):
    path = tmp_path / "restanse.csv"
    path.write_text(
        "SampleID;Analyse;Tidspunkt ankomst;Tidspunkt analysebestilling;Status analyse;Status prelgruppe;Analyseresultat\n"
        "S1;TRG-OU;21.08.2026 09:00;NA;Initial;Initial;\n"
        "S2;TRG-OU;21.08.2026 09:00;;Initial;Initial;\n"
        "S3;TRG-OU;21.08.2026 09:00;21.08.2026 09:00;Initial;Initial;\n",
        encoding="utf-8",
    )

    result = read_restanse_csv(path, real_contract())

    assert [sample.sample_id for sample in result.samples] == ["S3"]
    assert result.excluded_rows == 2

