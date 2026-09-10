# Spec: restanse-current

**Status:** Godkjent 2026-09-10

## Objective

Hver RESTANSE-kjøring skal hente ett komplett uttrekk fra 01.01.2024 til
dagens lokale dato. Uttrekket skal oppdatere nåværende restanse i databasen,
mens permanente prøver og analyseforekomster beholdes når de ikke lenger finnes
i LVMS-restansen. RESTANSE-råfiler skal ikke bygge en filhistorikk.

## Tech Stack

Eksisterende LVMS/CDP-runtime, Python CSV-behandling, SQLite og pytest.

## Commands

```powershell
python -m pytest tests/test_fetching.py tests/backlog tests/test_end_to_end.py -q
python -m compileall -q src tests
```

## Project Structure

- `src/molstat/fetching.py`: fast RESTANSE-intervall.
- `src/molstat/system.py`: midlertidig filflyt uten `RawArchive` for RESTANSE.
- `src/molstat/backlog.py`: validert, transaksjonell nåtilstand.
- `tests/backlog/`: kontrakt, duplikater, rollback og forsvunne prøver.

## Interface

En vellykket import leverer normaliserte prøve-/analyseforekomster til
`sample-registry` og erstatter `backlog_current` i én transaksjon. En rad som
forsvinner markeres som ikke lenger i restanse, men slettes ikke fra registeret.

## Code Style

```python
RESTANSE_FROM = date(2024, 1, 1)
interval = ReportInterval(RESTANSE_FROM, today)
```

Fast forretningsregel skal være navngitt og testet, ikke utledes fra gamle
filnavn.

## Testing Strategy

Test eksakt start-/sluttdato uavhengig av arkivinnhold, full rollback ved tom,
korrupt eller ufullstendig fil, gjentatt identisk import, og at midlertidige
arbeidsfiler ryddes uten å berøre eldre brukerdata.

## Boundaries

- Always: valider hele uttrekket før nåtilstand erstattes og behold siste gyldige nåtilstand ved feil.
- Ask first: sletting av eksisterende `raw/backlog`-filer.
- Never: bruk tidligere arkivdato til å forkorte RESTANSE-intervallet eller publiser prøveidentifikatorer.

## Success Criteria

1. Alle RESTANSE-jobber sender 01.01.2024–dagens dato til LVMS.
2. Ingen ny permanent råfil opprettes under `raw/backlog`.
3. Besvarte/forsvunne prøver fjernes fra `backlog_current`, men finnes fortsatt i prøveregisteret.
4. Feil etter nedlasting endrer ikke sist gyldige databaseinnhold.

## Open Questions

- Om en mislykket råfil skal beholdes kortvarig i en avgrenset karantene for feilsøking. Standard er ingen bevaring, bare teknisk metadata uten identifikatorer.
