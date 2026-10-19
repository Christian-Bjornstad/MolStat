# MolStat på jobb-PC

Ved appoppgraderingen: følg [oppsett og pilot](docs/APP-OPPSETT.md).
Behold eksisterende rot og database; schema 7 migreres etter verifisert backup.

## Første oppsett

- Bruk en fast mappe på K-sensitiv som MolStat alene skriver til.
- Velg nøyaktig den samme eksisterende K-sensitive roten på alle PC-er. Ikke
  lag en egen MolStat-mappe per PC; databasen ligger alltid relativt under
  `data/molstat.sqlite3`.
- Velg en synkronisert SharePoint-mappe som er godkjent for pseudonyme
  MolStat-ID-er i detaljfilene.
- Angi LVMS-adressen, og velg mapper og lookup-filer med «Bla gjennom …».
- Velg «Valider og lagre». Eventuelle oppstartsfeil vises i Diagnostikk.

## Oppdatering 19. oktober 2026

Bytt hele programmappen med den oppdaterte pakken; behold eksisterende
innstillingsfil og datarot. Ikke erstatt bare CMD-filen.

- Hemato og Solide har hver sin **Restanse**-knapp. Den henter bare restansen.
  **Kjør Hemato/Solide** henter både statistikk og restanse.
- Under **Innstillinger → Hemato/Solide → Restanse** kan du velge en egen
  JSON-fil. **Valider og lagre** oppretter separate filer under
  `config/restanse` i dataroten dersom ingen fil er valgt. Filene inneholder
  `report`, `analyses` og `columns`: rapportgrupper, analysekoder, navn, frister
  og CSV-kolonner. **Åpne mappe** viser filen som kan redigeres. Neste kjøring
  leser filen på nytt og lager et fast oppsett for akkurat den kjøringen.
- Aktiver **Patologer** i Innstillinger for å hente kun
  **PAT-TID-STØP-SNITT-OU**. Uttrekkene tas én kalendermåned om gangen fra
  januar 2024 til dagens dato. Inneværende måned og eldre måneder med åpne
  prøver oppdateres igjen. Legeregister er ikke nødvendig for dette uttrekket.
- Excel-genereringen bruker nå en egen lesetilkobling, slik at den ikke prøver
  å oppdatere skrivelåsen. SQLite-sorteringer bruker minnet fremfor Python
  FELLES sin TEMP-mappe. Selve databasen og transaksjonsjournalen lagres som før.

Dersom `SQLITE_READONLY` fortsatt oppstår ved selve Flow/FISH-importen, trengs
feilens stakk fra `%LOCALAPPDATA%/MolStat/logs/runtime.log` på jobb-PC-en.
En database som faktisk er skrivebeskyttet av Windows kan ikke oppdateres av
appen; vellykkede syntetiske tester erstatter ikke prøving på jobb-PC-en.

## Planlagte oppgaver

- `MolStat - daglig statistikk`: standard kl. 05:00
- `MolStat - restansehenting`: standard hver time kl. 06:00–18:00

Tidene hentes fra MolStat-innstillingene når oppgavene installeres. Kjør
installasjon av automatikken på nytt etter at tidsfeltene er endret eller
importert. En eventuell gammel `MolStat - tavleserver` fjernes automatisk.

Windows ignorerer en ny start dersom samme oppgave allerede kjører. Databasen
har i tillegg en lease som hindrer samtidige skrivere.
Installer de planlagte oppgavene på bare én fast drifts-PC. Kontrollsenteret kan
åpnes fra andre PC-er mot samme database, men to manuelle kjøringer skal ikke
startes samtidig.

## Sikkerhetsgrense

Råfiler, råidentifikatorer, database og arbeidsfiler skal bli på K-sensitiv.
SharePoint-publisering bruker eksplisitte kolonnelister og atomisk filbytte.
Ved avvik stoppes publisering uten delvis Power BI-oppdatering.

`MolStat-ID` publiseres i `resultater.csv` og Prøveflyt-historikken. ID-en er
pseudonym og gjør detaljrader koblingsbare over tid. `antall.csv` inneholder
ikke MolStat-ID.

`Analyseresultat` og `Ekstern analysekommentar` i Prøveflyt eksporteres ordrett.
Disse LVMS-feltene må derfor aldri inneholde prøve- eller pasientidentifikatorer.

## Drift

Kjør `MOLSTAT_INSTALL.cmd` første gang. Åpne deretter `MOLSTAT_START.cmd` for
kontrollsenteret. Begge åpner Python FELLES gjennom Ivanti PowerGate og legger
en kommando på utklippstavlen som limes inn med Ctrl+V. Automatikk- og
bootstraplogger ligger under `%LOCALAPPDATA%\MolStat`.

### Oppstartsfeil med `schema_version`

`MolStatSettings.__init__() got an unexpected keyword argument 'schema_version'`
betyr at gammel innlesingskode åpner en nyere innstillingsfil. Oppdater hele
programmappen fra den nye pakken, behold innstillingsfilen og databasen,
og start på nytt med `MOLSTAT_START.cmd` fra den oppdaterte mappen.
Det oppdaterte startskriptet laster MolStat-modulene på nytt også når
Python FELLES allerede er åpent. Endring av `schema_version` i innstillingene
er ikke nødvendig.

Oppstarten viser full sti til programmappe, innstillingsfil og
`bootstrap.log`. Ved kjøring i Citrix gjelder stiene Citrix-maskinen og
brukerprofilen der. Hvis AppData ikke er skrivbar, vises faktisk loggsti
under den midlertidige mappen. Kopier den viste stien i Filutforsker i samme
Citrix-økt for å finne loggen.

## Prøvesøk.xlsx

`Prøvesøk.xlsx` ligger direkte i den valgte K-sensitive roten. Filen inneholder
prøvenummer og skal ikke flyttes til SharePoint-mappen. De publiserte
detaljfilene inneholder bare pseudonym MolStat-ID, aldri rått prøvenummer.
Lim inn opptil 50 prøvenumre eller MolStat-ID-er i de gule radene på arket
`Prøvesøk`, ett søk per rad, og velg `Eksakt` eller `Prefiks`. Alle tilhørende
analyseforekomster vises automatisk. `I RESTANSE nå` betyr
at forekomsten fantes i siste komplette og vellykkede RESTANSE-import.

Hvis arbeidsboken er åpen under en oppdatering, fortsetter databaseimporten.
Lukk filen før neste kjøring; MolStat beholder den forrige gyldige filen frem
til den kan erstattes atomisk. Ikke rediger arkene `Prøver` eller `Analyser` som
en datakilde—endringer der blir erstattet ved neste generering og skrives aldri
til databasen.

## Backup og gjenoppretting

Før et eldre databaseskjema migreres, lager MolStat en kontrollert backup under
`data/backups` i K-sensitiv rot og godkjenner den bare når SQLite-integriteten
er `ok`. Backupfiler roteres ikke automatisk. Gjenoppretting skal gjøres som en
planlagt driftsoperasjon mens MolStat og planlagte oppgaver er stoppet, og den
gjenopprettede kopien skal integritetskontrolleres før kjøring aktiveres igjen.

## Pilot før produksjonsaktivering

- Bekreft faktisk WorkItem-/ordrelinjeheader i RESTANSE, ANTALL, RESULTATER og
  ekstraksjonsrapporten. Uten feltet brukes en markert reserveidentitet.
- Åpne en syntetisk `Prøvesøk.xlsx` i jobb-PC-ens Excel og kontroller at filen
  åpnes uten reparasjonsvarsel.
- Skriv et langt prøvenummer med ledende nuller i søkecellen og kontroller at
  nullene beholdes.
- Test eksakt søk, prefikssøk, flere treff og gjentatt analysekode.
- Hold arbeidsboken åpen under én testkjøring, og bekreft at databasen oppdateres
  mens forrige Excel-fil beholdes.
- Godkjenn backupretensjon og den endelige K-sensitive pilotmappen før
  automatisk produksjonskjøring aktiveres.
