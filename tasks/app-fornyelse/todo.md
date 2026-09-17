# Oppgaver: fornyelse av MolStat

Hovedplan: [plan.md](plan.md). Leveransestatus og testbevis: [status.md](status.md).
Avkryssede punkter er lokalt verifisert. Åpne punkter omfatter jobb-PC-pilot
og planlagte utvidelser som ikke inngår i den leverte lokale versjonen.
Tidligere implementering beholdes; åpne produksjonskontroller kobles inn her.
Filomfang er veiledende. Del en oppgave videre hvis den overstiger ca. fem filer.

## 1. Bevar årsak og trinn fra LVMS til app

Avhengigheter: ingen. Omfang: M.
Filer: `fetching.py`, `lvms/batch_runner.py`, `services.py`, relevante tester.
- [x] Strukturert feil viser trinn, kode, kjørings-ID og forsøk uten sensitive data.
- [x] Syntetiske navigasjons-, nedlastings- og oppryddingsfeil beholder riktig årsak.
- [x] Verifiser med `python -m pytest tests/test_fetching.py tests/lvms/test_batch_runner.py tests/test_services.py -q` og nye feiltester.

## 2. Rett gjenåpning av eksisterende database

Avhengigheter: 1. Omfang: M.
Filer: `database.py`, `services.py`, `test_database.py`, `test_services.py`.
- [x] Lag reproduksjon eller dokumenter miljøavhengig begrensning før retting; skill tilgang, lås, sti og skjema.
- [x] Gjentatt åpning/restart bevarer identiteter og historikk; forbindelser lukkes deterministisk.
- [ ] Verifiser med `python -m pytest tests/test_database.py tests/test_services.py -q`; UNC/nettverksdisk inngår i oppgave 12.

## 3. Gjør migrering og gjenoppretting forutsigbar

Avhengigheter: 2. Omfang: M.
Filer: `database.py`, `backup.py`, `tests/registry/test_migration.py`, `tests/registry/test_backup.py`.
- [ ] Støttede eldre skjemaer migreres med verifisert backup og bevarte rader/ID-er.
- [ ] Ukjent/skadet database blokkeres; feilinjeksjon bevarer original og backup kan gjenopprettes på kopi.
- [ ] Verifiser med `python -m pytest tests/registry/test_migration.py tests/registry/test_backup.py -q`.

### Kontrollpunkt A
- [ ] Eksisterende database kan brukes etter restart; resterende miljøbegrensninger er konkrete.
- [x] Ingen automatisk opprettelse av erstatningsdatabase ved åpnefeil.

## 4. Definer enhetsfil med maler

Avhengigheter: ingen. Omfang: M.
Filer: ny formatkontrakt, enhetsskjema, Hemato-mal, Solide-mal, kontrakttester.
- [ ] Dokumenter separate lister for antall, resultater, ekstraksjon og restanse med syntetiske eksempler.
- [x] Definer referanser, aktivering, profiler, CSV-kontrakt og endrings-/historikkregler.
- [x] Test at malene er gyldige og at dagens oppsett kan representeres uten informasjonstap.

## 5. Implementer streng filvalidering

Avhengigheter: 4. Omfang: M.
Filer: ny konfigurasjonsleser, `config.py`, fokuserte parser-/kontrakttester.
- [x] Feil i JSON, duplikate nøkler, typer, referanser og lister gir presis felt-/linjefeil.
- [ ] Valider CSV-header, skilletegn, encoding og quoting separat fra JSON-syntaks.
- [ ] Test gyldige maler samt ugyldige/endrede filer, BOM, ukjent versjon og ugyldige stier.

## 6. Importer og aktiver enhetsoppsett i innstillinger

Avhengigheter: 5. Omfang: M.
Filer: `ui/settings.py`, `services.py`, `config.py`, `tests/ui/test_control_center.py`, `tests/test_config.py`.
- [ ] Filvalg gir validering og endringsoversikt før atomisk aktivering; feil beholder aktiv versjon.
- [ ] Aktiv enhetsfil og lookup kan eksporteres/importeres med validerte referanser og tydelig lokal stistatus.
- [x] Test Qt-flyten og `python -m pytest tests/test_config.py tests/test_services.py tests/ui/test_control_center.py -q`.

## 7a. Koble statistikk til ett oppsett per kjøring

Avhengigheter: 5, 6. Omfang: M.
Filer: `fetching.py`, `_statistics/units.py`, `services.py`, statistikk- og fetchingtester.
- [x] Les/valider før kjøring; samme snapshot brukes til uthenting og behandling.
- [ ] Endring av analysekoder påvirker neste kjøring; dagens output er lik med migrert oppsett.
- [ ] Verifiser med `python -m pytest tests/statistics tests/test_fetching.py -q` og endring-under-kjøring-test.

## 7b. Koble restanse og enhetsregister til oppsettet

Avhengigheter: 7a. Omfang: M; del videre hvis koblingen krever flere filer.
Filer: `system.py`, `modules.py`, `services.py`, relevante enhets-/restansetester.
- [x] Fjern fast Hemato-ruting der samme støttede restanseprofil kan brukes for flere enheter.
- [ ] Henting, klassifisering, UI og jobbvalg bruker samme enhetsoppsett; deaktivering sletter ikke historikk.
- [ ] Verifiser med `python -m pytest tests/test_modules.py tests/backlog tests/test_end_to_end.py -q` og to syntetiske enheter.

### Kontrollpunkt B
- [ ] Hemato kjøres ende til ende fra importert fil; kodeendring er ikke nødvendig for analyser.
- [x] Feil fil blokkerer før LVMS, og eksisterende Power BI-output har samme kontrakt.

## 8a. Samle mappeoppsett og migreringsoversikt

Avhengigheter: 3, 6. Omfang: M.
Filer: ny mappekontrakt, `config.py`, `services.py`, migrerings-/stitester.
- [x] Kartlegg eksisterende rot og behold `data/molstat.sqlite3` og `Prøvesøk.xlsx`.
- [ ] Kontroller overlapp, tilgang, relative referanser og flere databasekandidater før overgang.
- [ ] Test eksisterende/fersk rot og avbrutt kopiering i midlertidige mapper; ingen originaler slettes.

## 8b. Skill behandling fra publisering

Avhengigheter: 8a, 7b. Omfang: M.
Filer: `system.py`, `publisher.py`, `archive.py`, ende-til-ende-/publiseringstester.
- [x] Råarkiv, midlertidig restanse og prosesserte kandidater følger mappekontrakten og kjørings-ID.
- [x] Låst SharePoint-fil kan prøves igjen fra ferdig kandidat; siste gyldige output beholdes.
- [x] Verifiser med `python -m pytest tests/test_archive.py tests/test_publisher.py tests/test_privacy_boundary.py tests/test_end_to_end.py -q`.

## 9. Innfør tilstandsbasert venting og avgrenset gjenforsøk

Avhengigheter: 1, 7b, 8b. Omfang: M.
Filer: `lvms/batch_runner.py`, `fetching.py`, `orchestrator.py`, fokuserte tester.
- [ ] Bare midlertidige feil gjentas, maksimalt to ganger; avbrudd og opprydding fungerer.
- [x] Uavklart rapportstatus stopper automatisk ny innsending; manuell kontroll kreves før nytt uttrekk.
- [ ] Test treg side/nedlasting, feil først–suksess deretter, varig feil og avbrudd med injiserte klokker/avhengigheter.

## 10. Gjør Excel-søket lett å kontrollere og oppdatere

Avhengigheter: 3, 8b. Omfang: M.
Filer: `excel_search.py`, `system.py`, `services.py`, Excel- og statustester.
- [x] Appen skiller gammel lesekopi/låst fil/feilet eksport fra vellykket databaseimport og kan regenerere uten LVMS.
- [ ] Søk håndterer flere verdier, nuller, flere analyser, tom database og årsdeling; gamle søkekontrakter beholdes.
- [ ] Kjør `python -m pytest tests/excel_search -q`; dokumenter mål-Excel-test for delvis fungerende søk i oppgave 12.

## 11a. Samle palett, former og komponenttilstander

Avhengigheter: ingen; implementeres etter fundamentet for å holde endringene adskilt. Omfang: M.
Filer: `ui/theme.py`, `ui/dashboard.py`, `ui/diagnostics.py`, Qt-tester.
- [ ] Bruk planens temaverdier, konsekvent avrunding/avstand og status med tekst/ikon.
- [ ] Mål kontrast, kontroller fokus og visuell skalering; ingen klipping på avtalte skjermstørrelser.
- [ ] Qt-tester og visuell rendering med syntetisk status ved normal og høy DPI.

## 11b. Samle navigasjon og innstillinger

Avhengigheter: 6, 9, 10, 11a. Omfang: M.
Filer: `ui/app.py`, `ui/settings.py`, `ui/dashboard.py`, `tests/ui/test_control_center.py`.
- [ ] Oversikt, kjøringer, enheter og innstillinger har tydelig oppgavefordeling og synlig aktiv konfigurasjon.
- [ ] Import, database, publisering og Excel viser egne tilstander med handlinger der noe må rettes.
- [ ] Test tastaturflyt, filimportfeil, kjøring/avbrudd og manuell Excel-regenerering uten Citrix.

### Kontrollpunkt C
- [ ] Feil, venting og delvis suksess er forståelige i appen.
- [ ] Import, publisering og Excel er verifisert sammen med syntetiske data.

## 12. Verifiser på jobb-PC og dokumenter overgang

Avhengigheter: alle relevante foregående oppgaver. Omfang: M.
Filer: `README.md`, `JOBBS-PC.md`, pilotprotokoll og denne oppgavelisten.
- [x] Kjør full `python -m pytest -q`, `python -m compileall -q src` og `git diff --check`; dokumenter eventuelle eksisterende feil uten å skjule dem.
- [ ] Pilot verifiserer samme database etter restart, nettverkslåsing, backup/restore på kopi, LVMS-identitet/nedlasting og reell Excel-rekalkulering med syntetiske søk.
- [x] Dokumenter filredigering, nye analyser, tilbakeføring, feilkoder og retensjon; gamle miljøkontrollpunkter beholdes åpne.

## Fullføringskriterium
- [ ] Alle seks brukerønsker og eksisterende Excel-søk er verifisert; feilene er ikke bare skjult med generelle gjenforsøk.
- [ ] Ingen tap av historikk, ny uønsket database eller endring i avtalte Power BI-/personvernkontrakter.
