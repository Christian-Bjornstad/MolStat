# MolStat på jobb-PC

## Første oppsett

- Bruk en fast mappe på K-sensitiv som MolStat alene skriver til.
- Velg en synkronisert SharePoint-mappe for ferdige, identifikatorfrie filer.
- Angi LVMS-adressen og lookup-filene i Innstillinger.
- Start appen på nytt etter lagring, og kjør installerfilen igjen.

## Planlagte oppgaver

- `MolStat - daglig statistikk`: kl. 05:00
- `MolStat - restansehenting`: hver time kl. 06:00–18:00
- `MolStat - tavleserver`: ved pålogging

Windows ignorerer en ny start dersom samme oppgave allerede kjører. Databasen
har i tillegg en lease som hindrer samtidige skrivere.

## Sikkerhetsgrense

Råfiler, identifikatorer, database og arbeidsfiler skal bli på K-sensitiv.
SharePoint-publisering bruker eksplisitte kolonnelister og atomisk filbytte.
Ved avvik stoppes publisering uten delvis Power BI-oppdatering.

## Drift

Åpne `MOLSTAT_START.cmd` for kontrollsenteret. Automatikklogger ligger under
`%LOCALAPPDATA%\MolStat`.
