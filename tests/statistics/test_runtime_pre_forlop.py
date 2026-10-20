import csv

import pytest

from molstat._statistics import pre_reports


def test_pre_preserves_source_dates_material_and_time_without_norm(tmp_path):
    source = tmp_path / 'lvms.csv'
    with source.open('w', encoding='cp1252', newline='') as handle:
        writer = csv.writer(handle, delimiter=';')
        writer.writerow(['Sample ID', 'PID', 'Analyse', 'Materiale', 'Tidspunkt prøvetaking',
                         'Tidspunkt opprettet', 'Tidspunkt analysebestilling',
                         'Tidspunkt analyseresultat', 'Tidspunkt godkjenning'])
        writer.writerow(['SECRET-SAMPLE', 'SECRET-PERSON', 'EKSTRAKSJON-OU', 'Blod',
                         '01.03.2026 06:00:00', '01.03.2026 08:00:00',
                         '01.03.2026 08:30:00', '02.03.2026 08:00:00', '02.03.2026 10:00:00'])
    lookup = tmp_path / 'lookup.csv'
    with lookup.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, ['Analyse', 'Aktivitetstype', 'Rapportgruppe',
                                        'NormProsess', 'NormTotalt'], delimiter=';')
        writer.writeheader()
        writer.writerow(dict(Analyse='EKSTRAKSJON-OU', Aktivitetstype='ValgEkstraksjon',
                             Rapportgruppe='Valg', NormProsess='', NormTotalt=''))
    out = tmp_path / 'out'
    pre_reports.process(source, out, {'EKSTRAKSJON-OU'})
    with (out / 'resultater.csv').open(encoding='utf-8-sig', newline='') as handle:
        row = next(csv.DictReader(handle, delimiter=';'))
    assert row['Tidspunkt.prøvetaking'] == '2026/03/01 06:00:00'
    assert row['Tidspunkt.analysebestilling'] == '2026/03/01 08:30:00'
    assert row['Materiale'] == 'Blod'
    assert float(row['Totaldager']) == 1
    assert row['Totalstatus'] == 'Gyldig'
    assert row['Totalnormstatus'] == 'Ingen norm'
    text = (out / 'resultater.csv').read_text(encoding='utf-8-sig')
    assert 'SECRET-SAMPLE' not in text and 'SECRET-PERSON' not in text


def test_pre_missing_dates_are_not_invented(tmp_path):
    source = tmp_path / 'lvms.csv'
    with source.open('w', encoding='cp1252', newline='') as handle:
        writer = csv.writer(handle, delimiter=';')
        writer.writerow(['Sample ID', 'Analyse', 'Tidspunkt opprettet', 'Tidspunkt analyseresultat'])
        writer.writerow(['S1', 'EKSTRAKSJON-OU', '02.03.2026 08:00:00', '01.03.2026 08:00:00'])
    lookup = tmp_path / 'lookup.csv'
    lookup.write_text('Analyse;Aktivitetstype;Rapportgruppe;NormProsess;NormTotalt\n'
                      'EKSTRAKSJON-OU;ValgEkstraksjon;Valg;;\n', encoding='utf-8')
    out = tmp_path / 'out'
    summary = pre_reports.process(source, out, {'EKSTRAKSJON-OU', 'CHOICE', 'PREP'})
    with (out / 'resultater.csv').open(encoding='utf-8-sig', newline='') as handle:
        row = next(csv.DictReader(handle, delimiter=';'))
    assert row['Tidspunkt.prøvetaking'] == row['Tidspunkt.analysebestilling'] == ''
    assert row['Totaldager'] == ''
    assert row['Totalstatus'] == 'Negativ tid'
    assert summary['valid_total'] == 0


def test_pre_process_duration_does_not_require_a_norm(tmp_path):
    source = tmp_path / 'lvms.csv'
    source.write_text('Sample ID;Analyse;Tidspunkt opprettet;Tidspunkt analyseresultat\n'
                      'S1;CHOICE;01.03.2026 08:00:00;01.03.2026 09:00:00\n'
                      'S1;PREP;01.03.2026 08:00:00;02.03.2026 09:00:00\n', encoding='cp1252')
    lookup = tmp_path / 'lookup.csv'
    lookup.write_text('Analyse;Aktivitetstype;Rapportgruppe;NormProsess;NormTotalt\n'
                      'CHOICE;ValgEkstraksjon;Valg;;\n'
                      'PREP;UtførtForbehandling;Forbehandling;;\n', encoding='utf-8')
    out = tmp_path / 'out'
    pre_reports.process(source, out, {'EKSTRAKSJON-OU', 'CHOICE', 'PREP'})
    with (out / 'resultater.csv').open(encoding='utf-8-sig', newline='') as handle:
        rows = {row['Analyse']: row for row in csv.DictReader(handle, delimiter=';')}
    assert rows['PREP']['Prosessdager'] == ''
    assert rows['PREP']['Prosessnormstatus'] == 'Ikke beregnet'
    assert rows['CHOICE']['Prosessstatus'] == 'Ikke definert'
