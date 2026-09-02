# MolStat – samlet design

**Dato:** 02.09.2026  
**Status:** Godkjent arkitektur, klar for implementasjonsplan

## Mål

MolStat skal erstatte LVMS-STAT og MolPat Puls med ett komplett system. Det skal ha én kodebase, én PyQt6-kontrollapp, én konfigurasjon, én scheduler, én database og én felles LVMS-hentemotor. Brukeren skal ikke måtte forholde seg til de tidligere applikasjonene eller separate moduler.

## Avgrensning og kilder

- Utgangspunktet er de lokale `main`-grenene i `LVMS-STAT` og `MolPat-Pulse`.
- Validert prosesseringslogikk, datakontrakter og tester gjenbrukes selektivt i en ny kodebase; repositoriene slås ikke mekanisk sammen.
- De gamle repositoriene endres ikke som del av etableringen av MolStat.
- Arbeidsnavn, prosjektnavn og appnavn er `MolStat`.

## Samlet arkitektur

MolStat bygges som én Python-pakke. Interne komponentgrenser brukes bare for sikkerhet, testbarhet og feilisolasjon:

1. **Henting:** én Edge/CDP-runtime og én kø som kjører LVMS-rapporter uten overlapp.
2. **Lagring:** råarkiv, SQLite-database, kjørelogg og manifest på K-sensitiv.
3. **Behandling:** statistikk- og restansereglene kjøres fra samme orkestrator og deler felles infrastruktur.
4. **Publisering:** identifikatorfrie statistikkfiler til SharePoint og aggregert snapshot til restansetavlen.
5. **Presentasjon:** PyQt6-kontrollsenter og separat, skrivebeskyttet nettlesertavle.

Avhengighetsretningen er `presentasjon/scheduler → orkestrator → henting/behandling → lagring/publisering`. Presentasjonen skal aldri lese råfiler direkte.

## Planlagt drift

- Statistikkhenting kjøres daglig kl. 05:00.
- Restansehenting kjøres hver hele time fra og med 06:00 til og med 18:00.
- Hentinger serialiseres. En jobb som allerede kjører skal ikke overlappes av neste jobb.
- Systemet er dimensjonert for én aktiv drifts-PC. En annen PC kan overta, men en lease/lås skal hindre samtidige databaseskrivere.
- Manuell kjøring er tilgjengelig fra kontrollappen og bruker samme kø og sikkerhetsregler.

## Data og sikkerhetsgrense

K-sensitiv er autoritativ lagringsplass for:

- alle rå CSV-filer;
- SQLite-databasen og migrasjoner;
- manifest, kjørestatus og tekniske logger;
- data som inneholder prøve- eller pasientidentifikatorer.

SharePoint-stien velges i innstillingene og mottar bare ferdig prosesserte Power BI-filer. Før publisering skal MolStat validere en eksplisitt kolonne-allowlist og avvise datasett med pasientnummer, prøve-ID eller andre forbudte identifikatorfelt. Publisering skjer via midlertidig fil og atomisk erstatning, slik at Power BI aldri leser en halvskrevet fil.

Restansetavlen mottar bare aggregerte tall. Den skal aldri eksponere SampleID, PID, WorkItem, råresultat, kommentarer, filstier eller databaseinnhold.

Logger skal inneholde jobbnivå, tidspunkt, varighet, antall rader og feilårsak, men aldri CSV-rader eller identifikatorverdier. Ved utilgjengelig K-sensitiv eller ugyldig eksport skal systemet feile lukket og beholde siste gyldige datasett.

## Database

MolStat bruker én SQLite-database på K-sensitiv med migrasjonsversjon, integritetssjekk og transaksjoner. Databasen kan inneholde separate tabeller for råmetadata, statistikkresultater, aktive restanser, jobber og publiseringer, men dette er én samlet database og ett system.

Bare én prosess får skrive om gangen. Nettlesertavlen leser et identifikatorfritt snapshot generert av systemet, ikke sensitive tabeller over nettverket. Databasekopi og gjenoppretting skal kunne utføres uten å endre råarkivet.

## PyQt6-kontrollsenter

Kontrollappen skal være et tilgjengelig, profesjonelt desktop-grensesnitt med:

- samlet driftsoversikt for statistikk, restanse, database og SharePoint;
- statuskort med siste vellykkede kjøring, neste kjøring og tydelig feiltilstand;
- manuell «Kjør nå»-handling;
- innstillinger for K-sensitiv, SharePoint, LVMS og nettlesertavle;
- diagnostikk og personvernsikker driftslogg;
- start/åpne-funksjon for nettlesertavlen.

Designet skal bruke tydelig tastaturnavigasjon, synlig fokus, minst 4,5:1 kontrast, tekst i tillegg til statusfarger og konsistente norske begreper. Innstillinger skal valideres før de kan aktiveres.

## Nettlesertavle

Restansetavlen finnes kun i nettleser. Den viderefører den aggregerte tavlemodellen fra MolPat Puls og viser klare prøver, manglende godkjenning, prøver på vei, over frist, datakvalitet og ferskhet. Standard binding er lokal (`127.0.0.1`). Eventuell internnettdeling forblir av som standard og krever eksplisitt sikkerhetsoppsett.

## Feilhåndtering

- Statistikk og restanse har separate jobbtransaksjoner; feil i den ene ødelegger ikke siste gyldige resultat fra den andre.
- Råfiler overskrives aldri.
- Manifest/database oppdateres først etter vellykket arkivering.
- SharePoint beholder siste gyldige publisering dersom ny behandling eller personvernkontroll feiler.
- Appen viser handlingsrettet feilårsak og hvilken del av flyten som feilet.

## Test- og migreringsstrategi

Implementeringen skjer i små, testdrevne vertikale steg:

1. felles konfigurasjon, lagringskontrakt og databaseskjema;
2. samlet LVMS-runtime og jobborkestrator;
3. statistikkflyt med eksisterende gullstandard;
4. restanseflyt med eksisterende datakontrakt;
5. personvernkontroll og atomisk SharePoint-publisering;
6. nettlesertavle;
7. PyQt6-kontrollsenter og Windows-planlegging;
8. ende-til-ende-verifikasjon og overgang fra de gamle appene.

Eksisterende tester porteres før tilhørende produksjonskode. Statistikkoutput skal fortsatt være celle-for-celle kompatibel med godkjent gullstandard, og restanseklassifisering/snapshot skal beholde de validerte reglene fra MolPat Puls.

## Akseptansekriterier

1. MolStat kan installeres og startes som én app uten LVMS-STAT eller MolPat Puls installert.
2. Daglig statistikk og timesbasert restanse kan kjøres automatisk og manuelt uten overlapp.
3. Alle rådata, identifikatorer og databasen forblir på K-sensitiv.
4. SharePoint mottar bare validerte, identifikatorfrie Power BI-filer.
5. Nettlesertavlen eksponerer bare aggregert, identifikatorfri informasjon.
6. Feil bevarer råarkiv og siste gyldige statistikk- og tavleresultat.
7. PyQt6-kontrollsenteret viser status og konfigurerer hele systemet.
8. Statistikkens gullstandard og restansens klassifiseringskontrakt består automatiserte tester.
9. En sekundær PC kan overta etter at aktiv lease er frigitt, uten databasekorrupsjon.

## Konfigurerbare produksjonsverdier

Faktisk K-sensitiv rot, SharePoint-synkmappe, LVMS-adresse, Edge-profil og eventuell sikker nettverkskonfigurasjon lagres i lokale innstillinger ved produksjonsoppsett. Hemmeligheter og interne produksjonsstier skal ikke legges i Git.
