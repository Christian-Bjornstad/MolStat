"""Solide's method selection is distinct from ordering and completion."""
import csv
import pytest
from molstat._statistics.processing import build_resultater_solide, process_reports, SOLIDE_PRE_CODES


def result(**changes):
    return {"Sample.ID": "S1", "Analyse": "TERT-OU",
            "Tidspunkt.prøvetaking": "01.01.2024 08:00",
            "Tidspunkt.opprettet": "02.01.2024 08:00",
            "Tidspunkt.analysebestilling": "07.01.2024 08:00",
            "Tidspunkt.analyseresultat": "08.01.2024 08:00",
            "Tidspunkt.godkjenning": "10.01.2024 08:00", **changes}


def extraction(**changes):
    return {"Sample.ID": "S1", "Analyse": "EKSTRAKSJON-OU",
            "Analyseresultat": "DNA FFPE/celler kolonne",
            "Tidspunkt.analysebestilling": "02.01.2024 09:00",
            "Tidspunkt.analyseresultat": "03.01.2024 08:00",
            "Tidspunkt.godkjenning": "05.01.2024 08:00", **changes}


def test_selection_completion_and_late_order_are_separate():
    row = build_resultater_solide([result()], [extraction()], {})[0]
    assert row["Ekstraksjon.valgt"] == "2024/01/03 08:00:00"
    assert row["Ekstraksjon.ferdig"] == "2024/01/05 08:00:00"
    assert row["Starttid.svartid"] == row["Ekstraksjon.ferdig"]
    assert row["Ekstraksjon.metode"] == "DNA FFPE/celler kolonne"


def test_never_uses_execution_timestamp_as_selection_or_approval_as_result():
    late = extraction(**{"Tidspunkt.godkjenning": "09.01.2024 08:00"})
    method = extraction(Analyse="EKSTRAFFPEKOL-OU", Analyseresultat="Utført")
    row = build_resultater_solide([result()], [late, method], {})[0]
    assert row["Ekstraksjon.valgt"] == "2024/01/03 08:00:00"
    assert row["Ekstraksjon.ferdig"] == "2024/01/09 08:00:00"
    assert row["Ekstraksjon.status"] == "Ekstraksjon godkjent etter analyseresultat"
    assert row["Starttid.svartid"] == ""


def test_missing_completion_is_not_fabricated():
    row = build_resultater_solide([result()], [extraction(**{"Tidspunkt.godkjenning": ""})], {})[0]
    assert row["Ekstraksjon.valgt"] == "2024/01/03 08:00:00"
    assert row["Ekstraksjon.ferdig"] == ""


@pytest.mark.parametrize('method', ['Ikke utført', 'Ikke utført DNA', 'Ikke aktuell RNA'])
def test_not_performed_and_wrong_sample_do_not_match(method):
    rows = [extraction(Analyseresultat=method), extraction(**{"Sample.ID": "S2"})]
    row = build_resultater_solide([result()], rows, {})[0]
    assert row["Ekstraksjon.valgt"] == ""


def test_repeat_selection_matches_latest_eligible_event():
    first = extraction()
    second = extraction(**{"Tidspunkt.analyseresultat": "06.01.2024 08:00",
                           "Tidspunkt.godkjenning": "07.01.2024 08:00"})
    row = build_resultater_solide([result()], [first, second], {})[0]
    assert row["Ekstraksjon.valgt"] == "2024/01/06 08:00:00"


def test_pre_analyses_are_excluded_from_solide_results():
    codes = ["MYRIAD-OU", "KRAS-VAR-OU", "NRASBRAF-VAR-OU", "MSI-OU", "GENEFUSION-OU", "EGFR-VAR-OU"]
    assert build_resultater_solide([result(Analyse=c) for c in codes], [], {}) == []


def test_pipeline_excludes_pre_from_counts_and_results(tmp_path):
    codes = {'TERT-OU', *SOLIDE_PRE_CODES}
    def write(name, rows):
        path = tmp_path / name
        with path.open('w', encoding='cp1252', newline='') as f:
            writer = csv.DictWriter(f, list(rows[0]), delimiter=';')
            writer.writeheader()
            writer.writerows(rows)
        return path
    ordered = write('ordered.csv', [result(Analyse=c) for c in codes])
    answered = write('answered.csv', [result(Analyse=c) for c in codes])
    extracts = write('extraction.csv', [extraction()])
    assert process_reports(ordered, answered, extracts, codes, tmp_path/'out', profile='solide') == {'antall': 1, 'resultater': 1}


def test_result_timestamp_cannot_be_replaced_by_final_approval():
    row = build_resultater_solide([result(**{'Tidspunkt.analyseresultat': ''})], [extraction()], {})[0]
    assert row['Ekstraksjon.valgt'] == ''
    assert row['Starttid.svartid'] == ''
