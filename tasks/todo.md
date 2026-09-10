# Task List: MolStat prøveregister og Excel-søk

## Task 1: Verifiser LVMS-identitetskontrakten

**Description:** Kartlegg headerne i RESTANSE, ANTALL, RESULTATER og ekstraksjonsrapporten og velg en stabil forekomst-ID. Les bare feltnavn og syntetiser testdata; ingen produksjonsrader eller verdier skal inn i Git eller logger.

**Acceptance criteria:**
- [ ] WorkItem-/ordrelinjefelt er bekreftet mot produksjonsheader. Kandidatfeltene er dokumentert; lokal produksjonskonfigurasjon mangler på utviklingsmaskinen.
- [x] Primær og reserve forekomstnøkkel er definert uten mutable status-/resultatfelt.
- [x] Regler for mulig gjenbruk av prøvenummer er dokumentert.

**Verification:**
- [x] Kjør `python -m pytest tests/registry/test_identity_contract.py -q`.
- [x] Skann diffen for produksjonsidentifikatorer og lokale K-stier.

**Dependencies:** None

**Files likely touched:**
- `config/backlog-columns.json`
- `src/molstat/_statistics/units.py`
- `tests/registry/test_identity_contract.py`
- `SPEC-sample-registry.md`

**Estimated scope:** Medium

## Task 2: Migrer databasen til registerskjema

**Description:** Legg til schema v5-tabellene for prøve, identifikator, analyseforekomst, hendelse, kildeobservasjon, importkjøring og nåværende restanse. Migreringen er additiv og beholder alle eksisterende tabeller og rader.

**Acceptance criteria:**
- [ ] Ny database opprettes med alle registertabeller, fremmednøkler og indekser.
- [ ] Schema v4 migreres til v5 uten sletting eller omskriving av eksisterende data.
- [ ] Ukjent skjemaversjon avvises og hele migreringen rulles tilbake.

**Verification:**
- [ ] Kjør `python -m pytest tests/test_database.py tests/registry/test_migration.py -q`.
- [ ] Kjør `python -m compileall -q src tests`.

**Dependencies:** Task 1

**Files likely touched:**
- `src/molstat/database.py`
- `tests/test_database.py`
- `tests/registry/test_migration.py`

**Estimated scope:** Medium

## Task 3: Implementer idempotent prøveregister

**Description:** Bygg domenetyper og databaseoperasjoner som oppretter stabil MolStat-ID, gjenbruker prøveidentitet og bevarer flere analyseforekomster. Legg til eksakte og prefiksbaserte søk.

**Acceptance criteria:**
- [ ] Gjentatt import gir samme MolStat-ID og ingen duplikatforekomster.
- [ ] Samme prøvenummer kan ha flere analyser og samme analysekode flere ganger.
- [ ] Tvetydige koblinger blir avvik og slås ikke sammen automatisk.

**Verification:**
- [ ] Kjør `python -m pytest tests/registry/test_registry.py tests/registry/test_search.py -q`.
- [ ] Kontroller `EXPLAIN QUERY PLAN` for de sentrale søkene.

**Dependencies:** Task 2

**Files likely touched:**
- `src/molstat/registry.py`
- `tests/registry/test_registry.py`
- `tests/registry/test_search.py`

**Estimated scope:** Medium

## Checkpoint: Identity foundation

- [ ] Tasks 1–3 er fullført.
- [ ] `python -m pytest tests/test_database.py tests/registry -q` består.
- [ ] En schema v4-kopi migrerer uten tap.
- [ ] Menneskelig gjennomgang bekrefter MolStat-ID og forekomstnøkkel.

## Task 4: Gjør RESTANSE-perioden fast og slutt å arkivere råfiler

**Description:** Erstatt den inkrementelle RESTANSE-planleggingen med fast 01.01.2024–dagens dato. Behandle nedlastingen som en avgrenset arbeidsfil og behold Statistikkens råarkiv uendret.

**Acceptance criteria:**
- [ ] Alle RESTANSE-jobber bruker 01.01.2024–dagens dato uavhengig av arkivfiler.
- [ ] Vellykket RESTANSE-kjøring oppretter ingen ny fil i `raw/backlog`.
- [ ] Midlertidige filer ryddes avgrenset uten å slette eksisterende arkivfiler.

**Verification:**
- [ ] Kjør `python -m pytest tests/test_fetching.py tests/test_archive.py tests/test_end_to_end.py -q`.
- [ ] Verifiser med syntetiske røtter at Statistikk fortsatt arkiverer.

**Dependencies:** Task 3

**Files likely touched:**
- `src/molstat/fetching.py`
- `src/molstat/system.py`
- `tests/test_fetching.py`
- `tests/test_end_to_end.py`

**Estimated scope:** Medium

## Task 5: Bygg transaksjonell RESTANSE-nåtilstand

**Description:** Importer alle gyldige forekomster til registeret og erstatt `backlog_current` først når hele rapporten er validert. Forsvunne rader mister bare nåtilstandsmarkeringen.

**Acceptance criteria:**
- [ ] Registeroppdatering og ny `backlog_current` committes sammen.
- [ ] Tom, korrupt eller avkortet fil beholder forrige komplette nåtilstand.
- [ ] En forsvunnet rad finnes fortsatt i permanent prøve-/analysehistorikk.

**Verification:**
- [ ] Kjør `python -m pytest tests/backlog tests/registry/test_backlog_linking.py -q`.
- [ ] Injiser feil før commit og sammenlign databasen byte-/radmessig etter rollback.

**Dependencies:** Task 4

**Files likely touched:**
- `src/molstat/backlog.py`
- `src/molstat/_backlog/ingestion.py`
- `src/molstat/registry.py`
- `tests/registry/test_backlog_linking.py`

**Estimated scope:** Medium

## Task 6: Koble Statistikk til prøveregisteret

**Description:** Eksponer en intern sensitiv registerkontrakt fra eksisterende statistikkprosessering og importer forekomster/hendelser uten å endre publiserte CSV-filer.

**Acceptance criteria:**
- [ ] ANTALL, RESULTATER og ekstraksjon kan kobles til samme prøve.
- [ ] Tredagers overlapp er idempotent i registeret.
- [ ] Eksisterende `antall.csv` og `resultater.csv` er celle-for-celle uendret.

**Verification:**
- [ ] Kjør `python -m pytest tests/statistics tests/registry/test_statistics_linking.py -q`.
- [ ] Kjør relevante gullstandard-/ende-til-ende-tester.

**Dependencies:** Task 3

**Files likely touched:**
- `src/molstat/statistics.py`
- `src/molstat/_statistics/processing.py`
- `src/molstat/registry.py`
- `tests/registry/test_statistics_linking.py`

**Estimated scope:** Medium

## Checkpoint: Source integration

- [ ] Tasks 4–6 er fullført.
- [ ] `python -m pytest tests/backlog tests/statistics tests/registry tests/test_end_to_end.py -q` består.
- [ ] Samme syntetiske prøve fra RESTANSE og Statistikk har én MolStat-ID.
- [ ] Ingen nye RESTANSE-råfiler blir liggende igjen.

## Task 7: Legg til backup og integritetskontroll

**Description:** Ta konsistent, verifisert backup før migrering og innfør avgrenset helsesjekk. Rotasjon aktiveres først etter at retensjonen er godkjent.

**Acceptance criteria:**
- [ ] Backup bruker SQLite backup-API og ligger i eksplisitt K-sensitiv undermappe.
- [ ] Backup åpnes og består `PRAGMA integrity_check` før den regnes som gyldig.
- [ ] Restore-test gjenskaper register, hendelser og nåtilstand.

**Verification:**
- [ ] Kjør `python -m pytest tests/registry/test_backup.py tests/test_database.py -q`.
- [ ] Kjør syntetisk restore-rehearsal i midlertidig mappe.

**Dependencies:** Tasks 2, 5, 6

**Files likely touched:**
- `src/molstat/backup.py`
- `src/molstat/database.py`
- `tests/registry/test_backup.py`

**Estimated scope:** Medium

## Task 8: Belastnings- og søkeoptimaliser registeret

**Description:** Generer syntetiske data tilsvarende minst ti år, mål import/søk og juster bare dokumenterte flaskehalser og indekser.

**Acceptance criteria:**
- [ ] Volumtesten dekker minst 300 000 prøver og flere analyseforekomster per prøve.
- [ ] Eksakt prøve-/MolStat-ID-søk bruker indeks og gir korrekt treff.
- [ ] Ingen unikhetsbrudd, datatap eller ubegrenset minnevekst oppstår.

**Verification:**
- [ ] Kjør `python -m pytest tests/registry/test_volume.py -q`.
- [ ] Registrer målt import- og søketid uten produksjonsdata.

**Dependencies:** Tasks 3, 5, 6

**Files likely touched:**
- `src/molstat/registry.py`
- `tests/registry/test_volume.py`
- `tests/registry/fixtures.py`

**Estimated scope:** Small

## Checkpoint: Data safety

- [ ] Tasks 7–8 er fullført.
- [ ] Backup- og restore-test består.
- [ ] Belastningstesten består med dokumenterte målinger.
- [ ] Retensjon og K-sensitiv målmappe er bekreftet før produksjon.

## Task 9: Verifiser XLSX-generator i målmiljøet

**Description:** Lag en liten syntetisk workbook-spike med tabeller, tekst-ID, dato og dynamiske formler. Verifiser installasjon i Python FELLES og åpning/rekalkulering i jobb-PC-ens Excel før produksjonsavhengigheten låses.

**Acceptance criteria:**
- [ ] Filen åpnes uten reparasjonsvarsel og formler rekalkulerer i mål-Excel.
- [ ] Ledende nuller og lange identifikatorer bevares som tekst.
- [ ] Generatorvalg, versjonsgrense og installasjonskonsekvens er dokumentert og godkjent.

**Verification:**
- [ ] Kjør målrettet generator-/installasjonstest.
- [ ] Åpne syntetisk fil manuelt i jobb-PC-ens Excel og endre søkecellen.

**Dependencies:** Checkpoint Data safety

**Files likely touched:**
- `pyproject.toml` etter eksplisitt generatorgodkjenning
- `tests/excel_search/test_generator_compatibility.py`
- `SPEC-excel-search.md`

**Estimated scope:** Small

## Task 10: Implementer Excel-lesemodellen og grunnlayouten

**Description:** Les én konsistent database-snapshot og bygg `Prøvesøk`, `Prøver`, `Analyser` og `Om` med avtalte felt, tabeller, formater og oppdateringstid.

**Acceptance criteria:**
- [ ] Prøve- og analyseantall avstemmes mot database-snapshotet.
- [ ] Identifikatorer er tekst og datoer er ekte Excel-datoer.
- [ ] Datatabeller har autofilter, fryste overskrifter og avtalte kolonner.

**Verification:**
- [ ] Kjør `python -m pytest tests/excel_search/test_read_model.py tests/excel_search/test_workbook_structure.py -q`.
- [ ] Inspiser verdier, typer og tabellnavn i generert syntetisk fil.

**Dependencies:** Task 9

**Files likely touched:**
- `src/molstat/excel_search.py`
- `tests/excel_search/test_read_model.py`
- `tests/excel_search/test_workbook_structure.py`

**Estimated scope:** Medium

## Task 11: Implementer søkeformler og årsdeling

**Description:** Legg inn eksakt søk, prefikssøk, entydig valgt prøve og analysefilter. Innfør en testet radgrensevakt som deler analysene på årsark før Excel-grensen nærmes.

**Acceptance criteria:**
- [ ] Tomt, eksakt og prefiksbasert søk gir avtalte resultater.
- [ ] Gjentatt analysekode vises som flere forekomster.
- [ ] Radgrensevakten oppretter deterministiske årsark og formlene søker i alle aktive år.

**Verification:**
- [ ] Kjør `python -m pytest tests/excel_search/test_formulas.py tests/excel_search/test_partitioning.py -q`.
- [ ] Rekalkuler og skann etter `#REF!`, `#VALUE!`, `#NAME?`, `#SPILL!` og `#CALC!`.

**Dependencies:** Task 10

**Files likely touched:**
- `src/molstat/excel_search.py`
- `tests/excel_search/test_formulas.py`
- `tests/excel_search/test_partitioning.py`

**Estimated scope:** Medium

## Task 12: Publiser arbeidsboken sikkert

**Description:** Skriv først til en unik stagingfil, valider den, flush til disk og erstatt `Prøvesøk.xlsx` atomisk. Håndter låst målfil som en egen, ikke-destruktiv status.

**Acceptance criteria:**
- [ ] Ugyldig kandidat erstatter aldri forrige gyldige arbeidsbok.
- [ ] Låst målfil påvirker ikke databasejobben og gir en trygg retry-status.
- [ ] Midlertidige filer ryddes uten brede globs eller sletting utenfor eksportmappen.

**Verification:**
- [ ] Kjør `python -m pytest tests/excel_search/test_publication.py -q`.
- [ ] Simuler valideringsfeil, låst fil og avbrudd mellom skriving og bytte.

**Dependencies:** Tasks 10–11

**Files likely touched:**
- `src/molstat/excel_search.py`
- `tests/excel_search/test_publication.py`

**Estimated scope:** Small

## Checkpoint: Excel

- [ ] Tasks 9–12 er fullført.
- [ ] Alle workbook-tester består.
- [ ] Alle ark er rendret og visuelt kontrollert.
- [ ] Mål-Excel åpner filen uten varsel og rekalkulerer søk.
- [ ] En låst fil beholder forrige gyldige arbeidsbok.

## Task 13: Koble Excel-eksport til MolStat-kjøringer

**Description:** Generer arbeidsboken etter vellykket registeroppdatering, og vis sist generert-/eventuelt låst-status uten identifikatorer eller sensitive stier i diagnostikken.

**Acceptance criteria:**
- [ ] Vellykket RESTANSE eller Statistikk oppdaterer arbeidsboken fra siste konsistente database.
- [ ] Excel-feil gjør ikke datainnhentingen mislykket eller korrupt.
- [ ] Status viser tidspunkt og handlingsrettet feil uten prøveverdier eller full K-sti.

**Verification:**
- [ ] Kjør `python -m pytest tests/test_services.py tests/test_orchestrator.py tests/excel_search -q`.
- [ ] Kjør syntetisk manuell og tidsstyrt flyt.

**Dependencies:** Task 12

**Files likely touched:**
- `src/molstat/services.py`
- `src/molstat/system.py`
- `src/molstat/orchestrator.py`
- `tests/test_services.py`
- `tests/test_orchestrator.py`

**Estimated scope:** Medium

## Task 14: Full ende-til-ende- og personvernverifikasjon

**Description:** Bevis hele flyten med syntetiske identifikatorer, gjentatte analyser, forsvunnet restanse, overlappende statistikk og låst Excel-fil. Kontroller at eksisterende SharePoint-output ikke endres.

**Acceptance criteria:**
- [ ] Én prøve kobles korrekt på tvers av alle rapporter og vises riktig i Excel.
- [ ] SharePoint-output beholder eksakt eksisterende kolonnekontrakt og personverngrense.
- [ ] Full testpakke, bytekodekompilering og diff-kontroll består.

**Verification:**
- [ ] Kjør `python -m pytest -q`.
- [ ] Kjør `python -m compileall -q src tests`.
- [ ] Kjør `git diff --check`.
- [ ] Gjennomfør syntetisk volum-, personvern- og restore-rehearsal.

**Dependencies:** Task 13

**Files likely touched:**
- `tests/test_end_to_end.py`
- `tests/test_privacy_boundary.py`
- `tests/excel_search/test_end_to_end.py`

**Estimated scope:** Medium

## Task 15: Dokumenter drift og rull ut kontrollert

**Description:** Dokumenter hvor `Prøvesøk.xlsx` ligger, hvordan brukeren søker, hva «sist oppdatert» betyr, hva som skjer ved låst fil, og hvordan backup/restore håndteres. Pilotér i separat K-sensitiv mappe før automatisk produksjon.

**Acceptance criteria:**
- [ ] Operatørguiden beskriver søk, oppdatering, låst fil og gjenoppretting.
- [ ] Ingen reelle stier, identifikatorer eller skjermbilder med sensitivt innhold finnes i Git.
- [ ] Pilot er verifisert før produksjonsmålet aktiveres.

**Verification:**
- [ ] Skann dokumentasjonen for brukernavn, lokale stier og syntetiske hemmelighetsmarkører.
- [ ] Gjennomfør manuell akseptansetest med godkjent testprøve på jobb-PC.
- [ ] Kjør `git status --short` og bekreft bare forventede endringer.

**Dependencies:** Task 14

**Files likely touched:**
- `README.md`
- `JOBBS-PC.md`
- `SPEC-excel-search.md` ved eventuelle godkjente driftsjusteringer

**Estimated scope:** Small

## Checkpoint: Complete

- [ ] Alle Tasks 1–15 er fullført.
- [ ] Alle godkjente spesifikasjoner og suksesskriterier er oppfylt.
- [ ] Produksjonsdatabase er sikkerhetskopiert og restore-testet.
- [ ] `Prøvesøk.xlsx` er godkjent i mål-Excel på K-sensitiv.
- [ ] Hele testpakken og personvernkontrollen er grønn.
- [ ] Løsningen er klar for operativ overlevering.
