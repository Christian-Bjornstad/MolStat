# MolStat på jobb-PC

## Første oppsett

- Bruk en fast mappe på K-sensitiv som MolStat alene skriver til.
- Velg en synkronisert SharePoint-mappe for ferdige, identifikatorfrie filer.
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

Råfiler, identifikatorer, database og arbeidsfiler skal bli på K-sensitiv.
SharePoint-publisering bruker eksplisitte kolonnelister og atomisk filbytte.
Ved avvik stoppes publisering uten delvis Power BI-oppdatering.

`Analyseresultat` og `Ekstern analysekommentar` i Prøveflyt eksporteres ordrett.
Disse LVMS-feltene må derfor aldri inneholde prøve- eller pasientidentifikatorer.

## Drift

Kjør `MOLSTAT_INSTALL.cmd` første gang. Åpne deretter `MOLSTAT_START.cmd` for
kontrollsenteret. Begge åpner Python FELLES gjennom Ivanti PowerGate og legger
en kommando på utklippstavlen som limes inn med Ctrl+V. Automatikk- og
bootstraplogger ligger under `%LOCALAPPDATA%\MolStat`.
