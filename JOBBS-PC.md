# MolStat på jobb-PC

## Oppdatering 29. oktober 2026

Bytt hele programmappen med den nye pakken; behold den lokale innstillingsfilen og eksisterende datarot. Lukk alle andre MolStat-vinduer og vent til jobber er ferdige før første oppstart.

Velg Innstillinger, datarot, SharePoint-mappe og LVMS-adresse. For hver aktiv enhet velges brukerens egen enhets-JSON. Valgt filbane beholdes; appen lager ingen kopier under config. Hemato/Solide kan bruke en separat restanse-JSON eller restanseinnholdet i enhetsfilen. Ingen CSV-/Excel-oppslag velges i appen. En gammel manglende lege.csv blokkerer ikke kjøring.

Hvis en tidligere innstilling peker på en generert config-kopi, velg originalfilen på nytt før den gamle config-mappen ryddes. Originalens tidligere plassering kan ikke gjettes sikkert.

Alle statistikkenheter henter fra siste arkiverte sluttdato minus to dager til i dag, separat for hver rapport. Bare rapporter uten råarkiv starter i januar 2024. Manglende statistikk over to kalendermåneder hentes én kalendermåned om gangen for Hemato, Solide, Flow, FISH og Preanalyse; Patolog bruker alltid månedsavgrensede uttrekk. Bekreftede måneder arkiveres underveis, slik at neste forsøk kan fortsette etter avbrudd. Restanse bruker fortsatt hele perioden og får ikke denne månedsplanleggingen. Oversikt viser aktiv enhet og trinn, en fremdriftslinje med antall ferdigbehandlede oppgaver og medgått tid.

Statistikkbehandlingen skriver ikke lenger hele registerhistorikken på nytt hver dag. Første kjøring med den nye versjonen kan fortsatt gjøre én full registerinnhenting for å etablere et sikkert kontrollpunkt. Deretter importeres bare nye eller endrede råarkiver. Power BI-filene og Excel-søket beholder komplett historikk. En samlet kjøring oppdaterer Excel én gang etter siste deljobb. Se [målinger og begrensninger](docs/YTELSE.md).

## Daglig automatisk oppdatering

Start MolStat som vanlig med MOLSTAT_START.cmd og la vinduet være åpent, gjerne minimert. Velg klokkeslett med timer og minutter i **Innstillinger → Automatikk → Daglig kl.**, og trykk **Valider og lagre**. Standard er 07:00. Endringen tas i bruk uten omstart og beholdes ved neste oppstart og overføring av innstillinger. Et nytt tidspunkt starter en ny kjøring uavhengig av tidligere kjøringer samme dag. Har appen kjørt kl. 07:00, kan du for eksempel lagre 09:15 og få en ny kjøring kl. 09:15.

Programmet kjører statistikk og restanse for alle lagrede, aktive enheter hver dag fra valgt tidspunkt, med behandling, SharePoint-publisering og Excel-søk. Oversikt viser status for automatikken. Ingen ekstra exe, Windows-oppgave eller administratorrettighet kreves for tidsstyringen.

PC-en må være på og våken, med norsk tidssone og tilgang til LVMS, datarot og SharePoint. Skjermen kan være av. Programmet kan ikke kjøre mens PC-en sover eller er slått av; dagens kjøring tas igjen når MolStat er tilgjengelig etter valgt tidspunkt. Tiden kontrolleres ved oppstart og hvert 30. sekund. Pågående arbeid får fullføre først. Vanlig LVMS-innlogging og nettlesertilgang må fortsatt fungere.

Samme automatiske forsøk for samme dato og valgte klokkeslett kjøres ikke på nytt ved hver tidskontroll, etter omstart eller i et annet vindu med samme database. Ved feil eller «Stopp kjøring»: se Diagnostikk, rett årsaken og velg et nytt tidspunkt eller bruk «Kjør aktive enheter». De eksisterende, avgrensede gjenforsøkene inne i delsteg beholdes.

Den tidligere Windows-installasjonen brukes ikke lenger. Ved oppstart fjernes gjenkjennelige, gamle MolStat-startere (`statistics.cmd`, `backlog.cmd`, `board.cmd`) i `%LOCALAPPDATA%/MolStat/`. Egne skript og innstillinger beholdes. Dersom gamle oppgaver fortsatt vises i Windows Oppgaveplanlegging, kan «MolStat - daglig statistikk», «MolStat - restansehenting» og «MolStat - tavleserver» slettes eller deaktiveres der. Appen kjører ingen Windows-kommando for dette. Hvis opprydding nektes, vises det i Diagnostikk; deaktiver da oppgavene manuelt. Gamle tidsplanverdier i innstillingsfilen styrer ikke lenger kjøringen.

## Mapper

Databasen ligger i `database/molstat.sqlite3`, og verifiserte sikkerhetskopier ligger i `database/backups/`. Råarkivet ligger i `data/raw/`, og behandlede filer i `data/processed/`. Prøvesøk.xlsx ligger direkte i dataroten. Alle PC-er som skal dele samme database må velge samme rot.

Appen flytter gamle data fra de tidligere plasseringene. En låst database eller to databaser på gammel og ny plassering gir DB_LOCATION og stopper flyttingen. Original eller verifisert kopi beholdes. Ikke opprett en ny datarot for å omgå en slik feil.

Gamle config- og work-mapper fra andre installasjoner beholdes til egne oppsett og eventuelle uavklarte nedlastinger er sikret. Ny versjon lager ingen slike mapper. Vellykkede nedlastinger arkiveres før midlertidige jobbmapper fjernes.

## Power BI

Koble analyseoppslagene i Power BI. Grupper, navn, priser og normer kommer ikke lenger fra MolStat-oppslag. Kontroller at rapportene bruker egne oppslag til disse verdiene før nye eksportfiler tas i bruk.

Patolog publiserer de sju tabellene `Prøver.csv`, `Glass.csv`, `Signeringer.csv`, `Grupper.csv`, `Periode.csv`, `Leger.csv` og `Prioriteter.csv` til SharePoint-mappen `lege/`, med samme kolonner og koblingsnøkler som de lokale kopiene i `data/processed/lege/powerbi/`. Tabellene inneholder prøvenummer, glass-ID og legeidentitet. Råfiler og `source_audit.json` følger ikke med. Nye kjøringer lager ikke `prosess.csv`; en eksisterende kopi slettes ikke automatisk. Rapporter som bruker den, må bytte til de nye tabellene.

Kjør patolog eller importer et gyldig uttrekk med den nye versjonen for å opprette den nye SharePoint-leveransen. En gammel publiseringskandidat med bare `prosess.csv` passer ikke den nye filkontrakten og må behandles på nytt. Nye kandidater med alle sju tabeller støtter vanlig «Prøv publisering igjen».

Planen for en senere FISH-rapport ligger i [FISH-RAPPORTPLAN.md](docs/FISH-RAPPORTPLAN.md).

## Oppstart og diagnostikk

Kjør MOLSTAT_INSTALL.cmd ved første installasjon og MOLSTAT_START.cmd ved vanlig oppstart. Python FELLES-starteren beholder den eksisterende støtten for lokal installasjon av Python-avhengigheter. Ingen nettverksdatabase eller oppslagsfil trengs for å åpne Innstillinger.

Åpne **Diagnostikk → Åpne loggmappe** for å finne de faktiske loggfilene. Appen viser banen den bruker. Vanlig plassering er `%LOCALAPPDATA%/MolStat/logs/`, med `bootstrap.log` og `runtime.log`. Hvis profilmappen ikke kan brukes, forsøker appen `%TEMP%/MolStat/logs/`. Hendelsene vises fortsatt i Diagnostikk hvis ingen av mappene kan skrives til. Appens diagnostikklogger utelater eksterne feilmeldinger, kildelinjer og lokale variabelverdier.

Før uttrekk kontrollerer MolStat at databasekatalogen kan opprette, skrive, gi nytt navn til og slette en egen midlertidig testfil. Databaselåsen bekrefter deretter at SQLite faktisk kan skrive. På Windows fjerner appen skrivebeskyttet-attributtet på den valgte databasefilen og dens eventuelle `-journal`, `-wal` og `-shm` før en skriveforbindelse åpnes. Dette kontrolleres også ved nye forbindelser under lange kjøringer. Leseforbindelser endrer ikke filattributtene. Journalfiler slettes aldri som reparasjon, og appen bytter ikke til en tom reservedatabase.

DB_ACCESS med SQLITE_READONLY etter denne kontrollen betyr at tilgangen fortsatt nektes. Windows-rettigheter og sikkerhetsprogramvare kan ikke overstyres av MolStat. Diagnostikken viser trinn, utvidet SQLite-kode og tilgjengelig numerisk Windows-/OS-feilkode. Appen beholder den opprinnelige feilen hvis SQLite allerede har rullet tilbake transaksjonen. Ved vedvarende feil kan informasjonen i Diagnostikk brukes av IT til å kontrollere den valgte databasekatalogen.

## Automatiske gjenforsøk og stopp

Ved midlertidig filtilgang eller låsing prøver trygge delsteg igjen etter 5, 15, 30 og 60 sekunder, inntil fem forsøk. Dette gjelder blant annet skrivekontroll av databasen, arkivering, Excel-kandidater og filpublisering. Nytt forsøk og trinn vises i statuslinjen og Diagnostikk. Filfeil vises som FILE_ACCESS, FILE_BUSY, FILE_UNAVAILABLE eller FILE_IO med numerisk OS-feilkode. Manglende filer, ugyldig oppsett, diskfull og korrupt database gjentas ikke automatisk.

Et innsendt LVMS-rapportforsøk får maksimalt fem minutter fra eksport startes til CSV er bekreftet. Ved tidsavbrudd lukkes den eide nettleseren før neste forsøk. Hvert forsøk bruker egen nedlastingsmappe, slik at en forsinket CSV fra et eldre forsøk ikke kan bli brukt som ny rapport. Bekreftede rapporter hentes ikke på nytt fordi et annet delsteg feiler.

Ved en uttrykkelig forbigående LVMS-feil venter appen fem sekunder og prøver samme rapport på nytt. Etter to slike feil kan datoperioden deles i to og hver del prøves separat. Dette gjelder forbigående tidsavbrudd, LVMS- og skjemafeil; permanente oppsetts-, innloggings- og CSV-feil deles ikke blindt. Alle delene må være hentet og kontrollert før de samles til én fil for den opprinnelige perioden og importeres. En enkeltdag prøves maksimalt tre ganger, med fem og femten sekunders venting; oppdeling er begrenset til åtte nivåer og 24 rapportforespørsler per opprinnelig rapport. Ved vedvarende feil stoppes kjøringen med en forklaring. Restansestatus kan endres mens delrapportene hentes, så delte uttrekk er ikke et helt samtidig øyeblikksbilde.

**Stopp kjøring** avbryter venting og hindrer neste delsteg. Appen venter på trygg nettleser- og filopprydding før den blir klar igjen. Pågående databaseoperasjoner og tilbakeføring av filsett avbrytes ikke midt i kritisk opprydding. Databaseimporter og usikre COMMIT gjentas aldri automatisk. Publiseringsfeil krever ikke et nytt LVMS-uttrekk: ferdigbehandlede kandidater beholdes. Validerte Excel-kandidater beholdes hvis installasjon ikke kan bekreftes.

Hvis en råfil er sikkert arkivert, stopper ikke nektet sletting av nedlastingskopien resten av behandlingen. Ukjente filer og ufullførte forsøksmapper beholdes. Ved en usikker nettverksrespons etter filflytting kontrolleres resultatet eller tidligere filsett gjenopprettes; appen prøver ikke blindt å gjenta en mulig fullført flytting.

DB_LEASE_LOST betyr at databaseeierskapet er mistet. PRIVATE_FILES_LOCKED betyr at rapportfilene ikke kunne erstattes: lukk programmer som holder CSV-filene åpne og prøv igjen. PRIVATE_FILES_RECOVERY betyr at gjenopprettingskopier må kontrolleres før rapportene oppdateres.

Manuell import validerer LVMS-filer før de arkiveres og bruker samme behandlings- og publiseringsflyt. Ved publiseringsfeil beholdes kandidaten for gjenforsøk. Bruk Oppdater Excel-søk eller Prøv publisering igjen fra appen etter at filtilgang er rettet.

LVMS-leseren håndterer kommentarer over flere linjer med uescapede anførselstegn inne i teksten. Dette gjelder både automatisk behandling og manuell import. Kommentaren beholdes som ett felt, slik at datoer og materiale ikke forskyves eller telles som ekstra rader. Uavsluttede tekstfelt og feil kolonneantall i kommentarrapporter stoppes før behandling; originalfilene omskrives ikke. Oppdaterte FISH-filer må behandles/publiseres med den rettede appversjonen før senere Power BI-oppdateringer.

Ved manuell FISH-import kontrolleres perioden mot analysebestilling, slik LVMS-feltet «analyse opprettet» gjør. Prøvens egen opprettelsesdato kan være eldre eller mangle uten at en gyldig FISH-bestilling avvises. Oppgi fortsatt den faktiske fra-/til-perioden som ble valgt i LVMS.

Ved statistikkimport oppgis perioden som faktisk ble valgt i LVMS. Et femdagersuttrekk kan overlappe to dager som allerede finnes: helt identiske rader fjernes ved sammenslåing, og historikken beholdes. Datoene gjettes eller omskrives ikke. For Hemato, Solide, Flow, FISH og Preanalyse kan begge versjonene beholdes hvis samme post har fått nye verdier mellom ulike, overlappende perioder; dette er ikke en generell oppdatering etter prøvenummer. Et korrigert uttrekk for nøyaktig samme fra-/til-periode erstatter derimot tidligere revisjoner av den perioden i behandlingen. Patolog tillater også noen få dager og perioder over månedsskifter: det nyeste uttrekket erstatter alle rader i sin ankomstperiode, og øvrig historikk beholdes. Gamle Patolog-saker utenfor den automatiske overlappen oppdateres ved et nytt manuelt uttrekk for ønsket periode. Restanse krever hele perioden fra 01.01.2024 til i dag.
