# Spec: sample-registry

**Status:** Godkjent 2026-09-10

## Objective

Opprette ett permanent, søkbart prøveregister i eksisterende SQLite-database på
K-sensitiv. MolStat genererer en stabil intern nøkkel. Ett prøvenummer kan ha
mange analyser, og samme analyse kan forekomme flere ganger uten at forekomster
overskriver hverandre.

## Tech Stack

Python 3.11+, stdlib `sqlite3`, eksisterende `MolStatDatabase` og pytest.
Databasen forblir `data/molstat.sqlite3` under konfigurert sensitiv rot.

## Commands

```powershell
python -m pytest tests/test_database.py tests/registry -q
python -m compileall -q src tests
```

## Project Structure

- `src/molstat/database.py`: skjemaversjon og additive migreringer.
- `src/molstat/registry.py`: normalisering, identitetsoppløsning og spørringer.
- `tests/registry/`: migrering, idempotens, duplikater og søk.

## Data Contract

- `sample`: intern numerisk ID, visbar `molstat_key`, første/siste observasjon.
- `sample_identifier`: kilde, identifikatortype, original verdi og normalisert verdi.
- `analysis_occurrence`: prøve, analysekode, bestillingstid og stabil kilde-ID.
- `analysis_event`: hendelsestype, tidspunkt, kilde og importkjøring.
- `source_observation`: første/siste gang forekomsten ble sett per rapporttype.
- `import_run`: status, intervall, radantall, kildefingeravtrykk og feilklasse uten identifikatorer.

`sample_identifier` er unik på `(source_system, identifier_type,
normalized_value)`. `analysis_occurrence` bruker WorkItem-/ordrelinje-ID når
LVMS tilbyr det. En dokumentert sammensatt nøkkel brukes bare som reserve.

## Code Style

```python
@dataclass(frozen=True, slots=True)
class SampleIdentity:
    molstat_key: str
    sample_number: str = field(repr=False)
```

Små domenetyper, parameteriserte SQL-spørringer, eksplisitte transaksjoner og
ingen identifikatorer i `repr`, logger eller feiltekster.

## Testing Strategy

Testene skal bevise at ny import er idempotent, at én prøve får flere analyser,
at gjentatt identisk analysekode får separate forekomster, og at RESTANSE og
Statistikk kan kobles til samme forekomst. Migrering testes fra dagens skjema
med alle eksisterende tabeller og rader bevart.

## Boundaries

- Always: behold eksisterende data, bruk fremmednøkler/unikhetskrav og normaliser identifikatorer deterministisk.
- Ask first: endre formatet på `molstat_key` etter produksjonsstart eller slå sammen tvetydige prøver.
- Never: bruk status/resultat som identitetsdel, logg prøveverdier eller slett en prøve ved vanlig import.

## Success Criteria

1. Samme prøvenummer gir samme MolStat-nøkkel ved gjentatt import.
2. Ulike analyseforekomster blir aldri kollapset på bare prøvenummer og analysekode.
3. Eksakt søk på prøvenummer eller MolStat-nøkkel bruker indeks.
4. Dagens database migreres additivt og kan åpnes etter omstart.

## Open Questions

- Utviklingsmaskinen hadde ingen lokal MolStat-konfigurasjon 2026-09-10. Faktisk
  LVMS-kolonne for WorkItem-/ordrelinje-ID må derfor bekreftes mot en sensitiv
  produksjonsheader før registereksporten aktiveres. Kontrakten støtter
  `WorkItem`, `Workitem` og `WorkItem ID` uten å gjøre feltet obligatorisk.
- Avklar om prøvenummer kan gjenbrukes mellom år eller enheter. Inntil dette er verifisert inngår `source_system` i identitetsgrensen.
