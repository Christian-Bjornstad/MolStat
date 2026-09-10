# Spec: statistics-linking

**Status:** Godkjent 2026-09-10

## Objective

Koble eksisterende ANTALL-, RESULTATER- og ekstraksjonsbehandling til
prøveregisteret og legge pseudonym MolStat-ID til `resultater.csv` uten å endre
de eksisterende kolonnene. En prøve eller analyse
som også finnes i RESTANSE skal gjenbruke samme identitet når kildefeltene gir
entydig samsvar.

## Tech Stack

Eksisterende statistikkprosessor, SQLite-registeret og pytest. Dagens råarkiv
og historiske merge for Statistikk beholdes.

## Commands

```powershell
python -m pytest tests/statistics tests/registry tests/test_end_to_end.py -q
python -m compileall -q src tests
```

## Project Structure

- `src/molstat/statistics.py`: orkestrering etter eksisterende prosessering.
- `src/molstat/_statistics/processing.py`: koble MolStat-ID til detaljresultat.
- `src/molstat/registry.py`: kobling og hendelses-upsert.
- `tests/statistics/` og `tests/registry/`: kompatibilitet og identitet.

## Interface

Statistikkprosessoren leverer en intern strøm av prøve-, analyse- og
hendelsesdata ved siden av dagens publiseringsresultat. Databaseskriving skjer
før publisering markeres som fullført, men en registerfeil skal ikke produsere
en halv oppdatering.

## Code Style

```python
registry.import_statistics(
    unit_key=unit_key,
    occurrences=result.registry_occurrences,
    run_id=run_id,
)
```

Publiserings-CSV og intern sensitiv registerkontrakt skal være separate typer.

## Testing Strategy

Behold celle-for-celle-regresjonstestene for eksisterende kolonner. Kontroller
at `resultater.csv` får MolStat-ID og at `antall.csv` ikke får det.
Legg til tester for kobling på tvers av rapporttyper, manglende identifikator,
flere analyser per prøve og to forekomster med samme analysekode.

## Boundaries

- Always: behold dagens statistikkoutput og råarkiv uendret.
- Ask first: nye LVMS-felt eller endret rapportdefinisjon.
- Never: legg rått prøvenummer, PID eller WorkItem til SharePoint-output.

## Success Criteria

1. Eksisterende statistikkgullstandard består med kun MolStat-ID som ny kolonne.
2. Samme prøve gjenfinnes fra ANTALL, RESULTATER og RESTANSE.
3. Hendelser oppdateres idempotent ved tre dagers overlapp.
4. Tvetydige koblinger registreres som datakvalitetsavvik og slås ikke sammen automatisk.

## Open Questions

- Hvilke stabile ordre-/WorkItem-felt som finnes i hver av de tre rapportene må verifiseres på ekte headernivå.
