# MolStat på jobb-PC

## Første oppsett

- Bruk en fast mappe på K-sensitiv som MolStat alene skriver til.
- Velg en synkronisert SharePoint-mappe som er godkjent for pseudonyme
  MolStat-ID-er i detaljfilene.
- Angi LVMS-adressen, og velg mapper og lookup-filer med «Bla gjennom …».
- Velg «Valider og lagre». Eventuelle oppstartsfeil vises i Diagnostikk.

## Planlagte oppgaver

- `MolStat - daglig statistikk`: standard kl. 05:00
- `MolStat - restansehenting`: standard hver time kl. 06:00–18:00

Tidene hentes fra MolStat-innstillingene når oppgavene installeres. Kjør
installasjon av automatikken på nytt etter at tidsfeltene er endret eller
importert. En eventuell gammel `MolStat - tavleserver` fjernes automatisk.

Windows ignorerer en ny start dersom samme oppgave allerede kjører. Databasen
har i tillegg en lease som hindrer samtidige skrivere.

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
