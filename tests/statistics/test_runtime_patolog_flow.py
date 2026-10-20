"""Counts and timings for the experimental PAT-TID workflow report."""
import importlib.util
from pathlib import Path
from datetime import datetime

from molstat._statistics import patolog_flow as flow


def source(**updates):
    row = {"Prøvenummer": "TEST-1", "Lab": "TEST", "Prosess": "HEMATO BENMARG", "Prioritet": "Low",
        "Prøvetakingstidspunkt": "01.10.2026 07:00", "Ankomsttid": "01.10.2026 08:00",
        "BeholderId": "B1", "Makro utført": "01.10.2026 10:00", "BlokkId": "BL1", "Støpt dato": "01.10.2026 12:00",
        "GlassId": "G1", "Glass opprettet": "01.10.2026 09:00", "Glass etterbestilt": "", "Glasstype": "SKANN",
        "Snittet dato": "01.10.2026 14:00", "Ferdig farget": "01.10.2026 16:00",
        "Godkjent dato": "02.10.2026 08:00", "Signert av": "Lege A", "Godkjent type": "Hovedansvarlig"}
    return row | updates


def test_role_duplicates_do_not_multiply_samples_or_glass():
    data = flow.process_rows([source(), source(**{"Signert av": "Lege B", "Godkjent type": "Medansvarlig"})])
    assert len(data["Prøver"]) == len(data["Glass"]) == 1
    assert len(data["Signeringer"]) == 2
    assert data["Prøver"][0]["Gruppe"] == "Hemato og Beinmarg"
    assert data["Prøver"][0]["AntallGlass"] == 1
    assert data["Prøver"][0]["KjedeGyldig"] == 1
    assert sum(data["Prøver"][0][f"Trinn{i}"] for i in range(1, 6)) == 1


def test_missing_glass_and_dates_are_not_zero_duration_or_slide():
    data = flow.process_rows([source(**{"GlassId": "", "Ferdig farget": "", "Godkjent dato": "", "Signert av": ""})])
    assert data["Glass"] == []
    sample = data["Prøver"][0]
    assert sample["AntallGlass"] == sample["UfargedeGlass"] == 0
    assert sample["Godkjent"] == 0 and sample["SvartidDager"] is None
    assert sample["KjedeGyldig"] == 0


def test_immun_and_afterorders_count_once_and_do_not_extend_initial_chain():
    data = flow.process_rows([source(), source(**{"GlassId": "G2", "Glasstype": "SKANN_IMM",
        "Glass etterbestilt": "03.10.2026 08:00", "Ferdig farget": "", "Snittet dato": ""})])
    sample = data["Prøver"][0]
    assert sample["AntallGlass"] == 2 and sample["UfargedeGlass"] == 1
    assert sample["ImmunGlass"] == 1 and sample["EtterbestilteGlass"] == 1
    assert sample["KjedeGyldig"] == 1 and sample["SvartidDager"] == 1


def test_negative_chain_is_flagged_and_not_clipped_to_zero():
    data = flow.process_rows([source(**{"Snittet dato": "01.10.2026 11:00"})])
    assert data["Prøver"][0]["KjedeGyldig"] == 0
    assert data["Prøver"][0]["Trinn3"] is None


def test_conflicting_glass_data_is_not_silently_deduplicated():
    import pytest
    with pytest.raises(ValueError, match="glass"):
        flow.process_rows([source(), source(**{"Glasstype": "SKANN_IMM"})])


def test_future_collection_date_cannot_shift_the_observation_date():
    data = flow.process_rows([source(**{"Prøvetakingstidspunkt": "30.04.2027 23:59"})])
    assert data["audit"]["as_of"] == "2026-10-02T08:00:00"
    assert data["audit"]["collection_after_arrival_samples"] == 1


def test_excel_wrappers_and_requested_bone_marrow_codes():
    for code in ("HEMATO", "HEMATO-BEINMARG", "HEMATO BENMARG"):
        row = {k: '=T("' + v + '")' for k, v in source(Prosess=code).items()}
        sample = flow.process_rows([row])["Prøver"][0]
        assert sample["Gruppe"] == "Hemato og Beinmarg"
        assert sample["Prøvenummer"] == "TEST-1"
        assert sample["Godkjent"] == 1


def test_age_bands_have_chronological_keys():
    from datetime import timedelta
    for age, expected in ((1, 1), (4, 2), (10, 3), (20, 4), (40, 5)):
        data = flow.process_rows([source()], as_of=datetime(2026, 10, 1, 8) + timedelta(days=age))
        assert data["Prøver"][0]["AldersgruppeSort"] == expected


def test_five_glasses_are_one_sample_and_use_last_ready_time():
    rows = [source(**{"GlassId": f"G{i}", "Ferdig farget": f"01.10.2026 {16+i:02}:00"}) for i in range(5)]
    sample, = flow.process_rows(rows)["Prøver"]
    assert sample["AntallGlass"] == 5
    assert sample["FørstebestilteGlass"] == 5
    assert sample["Glassmengde"] == "3–5 glass"
    assert sample["SvartidDager"] == 1
    assert sample["LegeDager"] == .5  # Last glass ready 20:00; approval next day 08:00.
