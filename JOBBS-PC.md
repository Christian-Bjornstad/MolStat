# MolStat på jobb-PC

## Oppdatering 20. oktober 2026

Bytt hele programmappen med den nye pakken; behold den lokale innstillingsfilen og eksisterende datarot. Lukk alle andre MolStat-vinduer og vent til jobber er ferdige før første oppstart.

Velg Innstillinger, datarot, SharePoint-mappe og LVMS-adresse. For hver aktiv enhet velges brukerens egen enhets-JSON. Valgt filbane beholdes; appen lager ingen kopier under config. Hemato/Solide kan bruke en separat restanse-JSON eller restanseinnholdet i enhetsfilen. Ingen CSV-/Excel-oppslag velges i appen. En gammel manglende lege.csv blokkerer ikke kjøring.

Hvis en tidligere innstilling peker på en generert config-kopi, velg originalfilen på nytt før den gamle config-mappen ryddes. Originalens tidligere plassering kan ikke gjettes sikkert.

## Mapper

Databasen ligger i `database/molstat.sqlite3`, og verifiserte sikkerhetskopier ligger i `database/backups/`. Råarkivet ligger i `data/raw/`, og behandlede filer i `data/processed/`. Prøvesøk.xlsx ligger direkte i dataroten. Alle PC-er som skal dele samme database må velge samme rot.

Appen flytter gamle data fra de tidligere plasseringene. En låst database eller to databaser på gammel og ny plassering gir DB_LOCATION og stopper flyttingen. Original eller verifisert kopi beholdes. Ikke opprett en ny datarot for å omgå en slik feil.

Gamle config- og work-mapper fra andre installasjoner beholdes til egne oppsett og eventuelle uavklarte nedlastinger er sikret. Ny versjon lager ingen slike mapper. Vellykkede nedlastinger arkiveres før midlertidige jobbmapper fjernes.

## Power BI

Koble analyseoppslagene i Power BI. Grupper, navn, priser og normer kommer ikke lenger fra MolStat-oppslag. Kontroller at rapportene bruker egne oppslag til disse verdiene før nye eksportfiler tas i bruk. Patologs private fakta ligger i `data/processed/lege/powerbi/`.

## Oppstart og diagnostikk

Kjør MOLSTAT_INSTALL.cmd ved første installasjon og MOLSTAT_START.cmd ved vanlig oppstart. Python FELLES-starteren beholder den eksisterende støtten for lokal installasjon av Python-avhengigheter. Ingen nettverksdatabase eller oppslagsfil trengs for å åpne Innstillinger.

Logger skrives til `%LOCALAPPDATA%/MolStat/logs/bootstrap.log` og `runtime.log`. Windows kan ha en annen LocalAppData-plassering enn mappen man navigerer til manuelt; åpne banen via adressefeltet i Filutforsker.

DB_LEASE_LOST betyr at databaseeierskapet er mistet. SQLITE_READONLY krever kontroll av faktisk skrivetilgang til databasekatalogen. PRIVATE_FILES_LOCKED betyr at rapportfilene ikke kunne erstattes: lukk programmer som holder CSV-filene åpne og prøv igjen. PRIVATE_FILES_RECOVERY betyr at gjenopprettingskopier må kontrolleres før rapportene oppdateres.

Manuell import validerer LVMS-filer før de arkiveres og bruker samme behandlings- og publiseringsflyt. Ved publiseringsfeil beholdes kandidaten for gjenforsøk. Bruk Oppdater Excel-søk eller Prøv publisering igjen fra appen etter at filtilgang er rettet.
