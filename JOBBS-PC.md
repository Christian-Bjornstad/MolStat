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

Åpne **Diagnostikk → Åpne loggmappe** for å finne de faktiske loggfilene. Appen viser banen den bruker. Vanlig plassering er `%LOCALAPPDATA%/MolStat/logs/`, med `bootstrap.log` og `runtime.log`. Hvis profilmappen ikke kan brukes, forsøker appen `%TEMP%/MolStat/logs/`. Hendelsene vises fortsatt i Diagnostikk hvis ingen av mappene kan skrives til. Appens diagnostikklogger utelater eksterne feilmeldinger, kildelinjer og lokale variabelverdier.

Før uttrekk kontrollerer MolStat at databasekatalogen kan opprette, skrive, gi nytt navn til og slette en egen midlertidig testfil. Databaselåsen bekrefter deretter at SQLite faktisk kan skrive. På Windows fjerner appen skrivebeskyttet-attributtet på den valgte databasefilen og dens eventuelle `-journal`, `-wal` og `-shm` før en skriveforbindelse åpnes. Dette kontrolleres også ved nye forbindelser under lange kjøringer. Leseforbindelser endrer ikke filattributtene. Journalfiler slettes aldri som reparasjon, og appen bytter ikke til en tom reservedatabase.

DB_ACCESS med SQLITE_READONLY etter denne kontrollen betyr at tilgangen fortsatt nektes. Windows-rettigheter og sikkerhetsprogramvare kan ikke overstyres av MolStat. Diagnostikken viser trinn, utvidet SQLite-kode og tilgjengelig numerisk Windows-/OS-feilkode. Appen beholder den opprinnelige feilen hvis SQLite allerede har rullet tilbake transaksjonen. Ved vedvarende feil kan informasjonen i Diagnostikk brukes av IT til å kontrollere den valgte databasekatalogen.

## Automatiske gjenforsøk og stopp

Ved midlertidig filtilgang eller låsing prøver trygge delsteg igjen etter 5, 15, 30 og 60 sekunder, inntil fem forsøk. Dette gjelder blant annet skrivekontroll av databasen, arkivering, Excel-kandidater og filpublisering. Nytt forsøk og trinn vises i statuslinjen og Diagnostikk. Filfeil vises som FILE_ACCESS, FILE_BUSY, FILE_UNAVAILABLE eller FILE_IO med numerisk OS-feilkode. Manglende filer, ugyldig oppsett, diskfull og korrupt database gjentas ikke automatisk.

Et innsendt LVMS-rapportforsøk får maksimalt fem minutter fra eksport startes til CSV er bekreftet. Ved tidsavbrudd lukkes den eide nettleseren før neste forsøk. Hvert forsøk bruker egen nedlastingsmappe, slik at en forsinket CSV fra et eldre forsøk ikke kan bli brukt som ny rapport. Bekreftede rapporter hentes ikke på nytt fordi et annet delsteg feiler.

Etter to tidsavbrudd på samme rapport kan datoperioden deles i to. Alle delene må være hentet og kontrollert før de samles til én fil for den opprinnelige perioden og importeres. Patolog beholder månedlige filer. En enkeltdag prøves maksimalt tre ganger; oppdeling er begrenset til åtte nivåer og 24 rapportforespørsler per opprinnelig rapport. Ved vedvarende feil stoppes kjøringen med en forklaring. Restansestatus kan endres mens delrapportene hentes, så delte uttrekk er ikke et helt samtidig øyeblikksbilde.

**Stopp kjøring** avbryter venting og hindrer neste delsteg. Appen venter på trygg nettleser- og filopprydding før den blir klar igjen. Pågående databaseoperasjoner og tilbakeføring av filsett avbrytes ikke midt i kritisk opprydding. Databaseimporter og usikre COMMIT gjentas aldri automatisk. Publiseringsfeil krever ikke et nytt LVMS-uttrekk: ferdigbehandlede kandidater beholdes. Validerte Excel-kandidater beholdes hvis installasjon ikke kan bekreftes.

Hvis en råfil er sikkert arkivert, stopper ikke nektet sletting av nedlastingskopien resten av behandlingen. Ukjente filer og ufullførte forsøksmapper beholdes. Ved en usikker nettverksrespons etter filflytting kontrolleres resultatet eller tidligere filsett gjenopprettes; appen prøver ikke blindt å gjenta en mulig fullført flytting.

DB_LEASE_LOST betyr at databaseeierskapet er mistet. PRIVATE_FILES_LOCKED betyr at rapportfilene ikke kunne erstattes: lukk programmer som holder CSV-filene åpne og prøv igjen. PRIVATE_FILES_RECOVERY betyr at gjenopprettingskopier må kontrolleres før rapportene oppdateres.

Manuell import validerer LVMS-filer før de arkiveres og bruker samme behandlings- og publiseringsflyt. Ved publiseringsfeil beholdes kandidaten for gjenforsøk. Bruk Oppdater Excel-søk eller Prøv publisering igjen fra appen etter at filtilgang er rettet.
