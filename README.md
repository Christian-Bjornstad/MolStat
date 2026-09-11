# MolStat

MolStat henter molekylærpatologisk statistikk og restanse fra LVMS, lagrer
historikken på K-sensitiv og publiserer avtalte, prosesserte CSV-filer til en
lokal SharePoint-synkmappe. Kontrollappen gir manuell kjøring, status,
diagnostikk og flyttbare innstillinger i ett grensesnitt.

## Enheter

| Enhet | Tilgjengelig nå | Kjøring |
|---|---|---|
| Hemato | Ja | Statistikk og Prøveflyt/restanse |
| Solide | Ja | Statistikk |
| Lege | Kommer | Deaktivert plassholder |
| Flow | Kommer | Deaktivert plassholder |
| Pre | Kommer | Deaktivert plassholder |
| Hist | Kommer | Deaktivert plassholder |

`Kjør alt` starter alle ferdige funksjoner for aktiverte enheter. En feil i én
funksjon stopper ikke de øvrige; kontrollappen viser da at kjøringen er delvis
fullført. Knappene `Hemato` og `Solide` kjører bare den valgte enheten.

## Sikker dataflyt

```text
LVMS
  ├─ Statistikk -> K-sensitiv/raw/statistics -> permanent SQLite-register
  └─ RESTANSE 01.01.2024–i dag -> avgrenset arbeidsfil -> SQLite-register
                                           ├─ Prøvesøk.xlsx på K-sensitiv
                                           └─ pseudonym historikk -> SharePoint/MolStat
```

Statistikkråfiler, SampleID, PID, Workitem, database, kildefingeravtrykk og
arbeidsfiler forblir på K-sensitiv. RESTANSE hentes alltid for hele perioden
fra 01.01.2024 til dagens dato og råfilen fjernes etter import; den bygges ikke
opp som et filarkiv. Publisering bruker eksakte kolonnelister og atomisk
filbytte. Hvis import, databaseoppdatering, personvernkontroll eller publisering
feiler, beholdes forrige gyldige fil.

## Prøvesøk i Excel

Etter en vellykket RESTANSE- eller Statistikk-import oppdaterer MolStat
`Prøvesøk.xlsx` direkte i roten av den valgte K-sensitive mappen. Arbeidsboken
er makrofri og en ren lesekopi; den har ingen databasekobling og kan ikke skrive
tilbake til SQLite.

På arket `Prøvesøk`:

1. Lim inn ett eller flere prøvenumre eller MolStat-ID-er i de gule radene,
   ett søk per rad.
2. Velg `Eksakt` eller `Prefiks`.
3. Alle prøvetreff og tilhørende analyseforekomster vises til høyre, også når
   samme analysekode er bestilt flere ganger.

MolStat-ID tildeles som en kort, permanent serie (`M-000001`, `M-000002`, …).
`WorkItem` og intern identitetsstatus brukes fortsatt til sikker kobling i
databasen, men vises ikke i arbeidsboken.

`Prøver` og `Analyser` har vanlige Excel-tabeller med autofilter. `Om` viser
når lesekopien sist ble generert. Hvis filen er åpen og låst i Excel, beholdes
forrige gyldige arbeidsbok og MolStat prøver igjen ved neste kjøring.

Databasen er fasit. Den ligger under `data` i K-sensitiv rot. Før migrering av
et eldre databaseskjema opprettes en verifisert SQLite-backup under
`data/backups`. Automatisk sletting eller rotasjon av backupfiler er ikke
aktivert før lokal retensjonspolicy er godkjent.

## Mappestruktur i SharePoint

Brukeren velger roten `MolStat`. Appen oppretter og oppdaterer denne strukturen:

```text
MolStat/
├─ hemato/
│  ├─ antall.csv
│  └─ resultater.csv
├─ solide/
│  ├─ antall.csv
│  └─ resultater.csv
└─ Prøveflyt/
   └─ restansehistorikk_hemato.csv
```

Den gamle `Prøveflyt/restansehistorikk.csv` slettes ikke automatisk. Fjern den
først når eventuelle eksterne datakilder er flyttet til Hemato-filnavnet.

## Installasjon på jobb-PC

1. Kjør `MOLSTAT_INSTALL.cmd`.
2. Python FELLES åpnes via Ivanti PowerGate.
3. Lim inn den kopierte kommandoen med `Ctrl+V`, og trykk `Enter`.
4. Start senere med `MOLSTAT_START.cmd` på samme måte.

Detaljer og driftskontroller finnes i [JOBBS-PC.md](JOBBS-PC.md).

## Første gangs oppsett

Åpne `Innstillinger` og velg:

- én fast K-sensitiv rot som MolStat kan skrive til;
- den lokalt synkroniserte SharePoint-roten for MolStat;
- fullstendig LVMS-adresse;
- lookup-fil for hver aktiv statistikkenhet;
- hvilke av de tilgjengelige enhetene som skal være aktive.

Velg `Valider og lagre`. Utilgjengelige eller manglende obligatoriske stier
blokkerer kjøring og beskrives med feltnavn i appen.

## Kjøring og automatisering

Kontrollappen støtter `Kjør alt`, `Hemato` og `Solide`. Windows Task Scheduler
bruker fortsatt de kompatible CLI-målene:

- `statistics` én gang daglig ved `statistics_hour`;
- `backlog` én gang per hele time fra `backlog_first_hour` til og med
  `backlog_last_hour`.

Standardverdiene er henholdsvis kl. 05:00 og hver time kl. 06:00–18:00.
Klokkeslettene følger den lagrede/importerte innstillingsfilen når automatikken
installeres, og `auto` bruker de samme verdiene. Samtidige skrivere stoppes av
en tidsbegrenset SQLite-lease; Windows-oppgavene bruker også `IgnoreNew`.

## Flytte innstillinger mellom PC-er

`Eksporter …` lager som standard `molstat-innstillinger.json` i UTF-8. Filen
inneholder røtter, LVMS-adresse, tidsplan, enhetsaktivering og lookup-stier.
Den inneholder ikke passord, cookies, sesjonstokener, Edge-profil, dynamisk
CDP-port, database eller rådata.

`Importer …` validerer hele filen før gjeldende oppsett erstattes. Gyldige
PC-spesifikke stier som ikke finnes lokalt blir importert og merket `Må velges
på denne PC-en`. Kjøring forblir sperret til nødvendige stier er tilgjengelige.

Begge PC-er skal velge den samme eksisterende K-sensitive roten. MolStat finner
da databasen relativt som `data/molstat.sqlite3`; det skal ikke opprettes en ny
undermappe eller database for hver PC. En database med gjeldende skjema åpnes
uten migrering eller backup ved vanlig oppstart, slik at en annen PC kan koble
seg til uten en unødvendig skriveoperasjon. Installer planlagte skrivejobber på
bare én fast drifts-PC. Andre PC-er kan åpne kontrollsenteret og overta manuell
kjøring når ingen annen MolStat-kjøring pågår.

## Prøveflyt-data

`restansehistorikk_hemato.csv` bygges på nytt fra hele den permanente
timeshistorikken. Den bruker semikolon, CRLF-kompatible poster og UTF-8 med BOM.
Én rad representerer én restanseanalyse i ett timesnapshot, slik at en
analysegruppe kan filtreres og drilles ned til de konkrete analysene.

Kolonnene er, i fast rekkefølge:

1. `Observert_tidspunkt`
2. `Enhet`
3. `Materiale`
4. `Analyse`
5. `Nukleinsyre`
6. `Analysegruppe_kode`
7. `Analysegruppe`
8. `Tidspunkt.prøvetaking`
9. `Tidspunkt.ankomst`
10. `Tidspunkt.analysebestilling`
11. `Prioritet.analyse`
12. `Prioritet.rekvisisjon`
13. `Status.analyse`
14. `Status.prelgruppe`
15. `Restansestatus`
16. `Svarfrist`
17. `Analyseresultat`
18. `Ekstern.analysekommentar`
19. `Klassifikatorversjon`
20. `MolStat-ID`

`MolStat-ID` finnes også i statistikkfilen `resultater.csv`, men ikke i den
aggregerte `antall.csv`. `Rapportgruppe` er ikke med i Prøveflyt-filen;
`Analysegruppe_kode` og `Analysegruppe` er den
autoritative inndelingen. `Nukleinsyre` og `Svarfrist` hentes fra
Hemato-lookup-filen.

## Personvernansvar for fritekst

`Analyseresultat` og `Ekstern.analysekommentar` eksporteres ordrett fra LVMS
etter at teknisk `=T("...")`-innpakning er fjernet. MolStat maskerer eller
tolker ikke disse feltene. Operatørene må derfor aldri skrive prøve-, pasient-
eller andre identifikatorer i dem. Friteksten skal ikke betraktes som
automatisk anonymisert.

`MolStat-ID` er pseudonym, ikke anonym. Det gjør detaljrader koblingsbare over
tid, og de publiserte detaljfilene må derfor bare brukes i et SharePoint- og
Power BI-område som er godkjent for dette. Rått SampleID, PID og WorkItem
publiseres fortsatt aldri.

## Utvikling og test

```powershell
python -m pip install -e ".[dev]"
python -m molstat gui --settings "$env:LOCALAPPDATA\MolStat\settings.json"
python -m molstat check-config --settings "$env:LOCALAPPDATA\MolStat\settings.json"
python -m pytest
```

Prosjektet krever Python 3.11 eller nyere. Jobb-PC-skriptene kontrollerer det
konkrete Python FELLES-miljøet som organisasjonen bruker. Excel-eksporten bruker
`XlsxWriter` og krever ikke at Excel kjører under genereringen.

## Mer dokumentasjon

- [Oppsett og drift på jobb-PC](JOBBS-PC.md)
- [Godkjent enhets- og Prøveflyt-design](docs/superpowers/specs/2026-09-09-molstat-enheter-og-proveflyt-design.md)
- [Implementeringsplan](docs/superpowers/plans/2026-09-09-molstat-enheter-og-proveflyt-implementation.md)
