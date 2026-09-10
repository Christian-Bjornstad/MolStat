# Spec: data-safety

**Status:** Godkjent 2026-09-10

## Objective

Sørge for at prøveregisteret tåler avbrudd, gjentatte importer, sekundær PC og
flere års vekst uten tap eller stille overskriving.

## Tech Stack

SQLite med `synchronous=FULL`, eksisterende writer lease, Python
`sqlite3.Connection.backup`, pytest og K-sensitiv filsystemtilgang.

## Commands

```powershell
python -m pytest tests/test_database.py tests/registry tests/test_end_to_end.py -q
python -m compileall -q src tests
```

## Project Structure

- `src/molstat/database.py`: migrering, pragmas og helsesjekk.
- `src/molstat/backup.py`: konsistent backup, rotasjon og restore-verifikasjon.
- `src/molstat/orchestrator.py`: lease og jobbgrenser.
- `tests/registry/` og `tests/test_database.py`: feilinjeksjon og gjenoppretting.

## Operational Contract

Bare én MolStat-skriver kan være aktiv. Database og sikkerhetskopier ligger
under den konfigurerte K-sensitive roten. Direkte samtidig skriving fra flere
PC-er eller Excel støttes ikke. Excel er kun en generert lesekopi.

## Code Style

```python
with database.writer_lease(owner, ttl):
    with database.transaction():
        registry.apply(validated_batch)
```

Alle flertrinnsendringer skal ha én tydelig transaksjonsgrense.

## Testing Strategy

Injiser feil før og under commit, simuler utløpt lease, kjør `integrity_check`,
gjenopprett en testbackup og belast databasen med flere års syntetiske prøver,
analyseforekomster og overlappende importer.

## Boundaries

- Always: backup før skjemamigrering, verifiser backup og begrens rotasjon til en eksplisitt undermappe.
- Ask first: endre backup-retensjon eller støtte flere samtidige skrivere.
- Never: kjør SQLite med direkte Excel-skrivetilgang eller slett ukjente filer under sensitiv rot.

## Success Criteria

1. Avbrutt import etterlater databasen i forrige konsistente tilstand.
2. Ukjent skjemaversjon avvises uten endring.
3. Backup kan åpnes og består integritetskontroll.
4. Flere års syntetisk volum kan importeres og søkes uten nøkkelkollisjoner.

## Open Questions

- Endelig backup-retensjon må avtales med lokal lagrings- og personvernpolicy. Planen bruker et konservativt, konfigurerbart forslag.
- Hvis K-sensitiv er SMB/nettverksdisk, skal én utpekt PC eie skrivingen. Reell flerbrukerskriving krever en godkjent databaseserver.
