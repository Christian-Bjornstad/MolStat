# Enhetsfiler og drift

Se [README](../README.md) for oppsett og [jobb-PC-veiledningen](../JOBBS-PC.md) for oppgradering og feilsøking.

Enhetsfilen er JSON med schema_version=1, key, label, profile, statistics og valgfritt backlog. statistics har rapportroller med job_key, fetch_report_id, report_id og analysis_codes. Patolog har kun workflow med laboratory og process_codes. Hemato og Solide har antall, resultater og ekstraksjon; Flow/FISH har antall og resultater; Preanalyse har resultater.

Restanseinnhold består av report, analyses og columns. En separat valgt restansefil erstatter backlog-innholdet i enhetsfilen for den kjøringen. Filene leses og valideres ved jobbstart og endrer ikke en jobb som allerede kjører. Brukeren eier filplasseringen og filinnholdet; MolStat skriver dem ikke om.

Appinnstillinger lagres som schema_version=3. Eldre schema_version=2 kan leses; gamle statistics_lookup_path-felt ignoreres og eksporteres ikke videre. Innstillinger og LVMS-tilkobling ligger i LocalAppData/MolStat, uavhengig av valgt datarot. Ingen analyseoppslag eller standardenhetsfiler er med i installasjonspakken.

Statistikkens henteperiode styres av råarkivet for hver rapport, også ved manuell import. Uten arkiv starter rapporten 01.01.2024. Med arkiv starter den to dager før siste arkiverte sluttdato, slik at de tre siste arkiverte dagene oppdateres sammen med nye dager. Patolog henter ikke gamle måneder på nytt fordi prøver er åpne eller filene er eldre enn 30 dager. Nye Patolog-uttrekk erstatter hele ankomstintervallet sitt i den lokale sammenstillingen; historikk utenfor intervallet beholdes. Eldre saker utenfor overlappen kan oppdateres ved å importere et nytt uttrekk for ønsket periode. Restanse bruker fortsatt fullperioden, uavhengig av arkivert historikk.

Oversikt viser fremdrift mens jobben går: aktiv enhet, statistikk/restanse, henting med datoer, behandling, publisering og Excel-søk. Enhetskort oppdateres straks hver funksjon er ferdig eller har feilet. Fremdriftslinjen teller ferdigbehandlede oppgaver (statistikk og restanse hver for seg); den anslår ikke tidsbruk eller prosent av innleste rader. Aktivitet og medgått tid vises også under lange uttrekk. Ved feil fortsetter «Kjør aktive enheter» med neste funksjon/enhet; ved Stopp avsluttes kjøringen etter trygg opprydding.

Fremdriftskontrollen bruker Qt sin [QProgressBar](https://doc.qt.io/qt-6/qprogressbar.html), med ubestemt aktivitetsvisning under pågående arbeid og oppgaveteller for total fremdrift.
