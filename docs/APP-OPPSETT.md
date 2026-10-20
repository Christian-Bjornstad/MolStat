# Enhetsfiler og drift

Se [README](../README.md) for oppsett og [jobb-PC-veiledningen](../JOBBS-PC.md) for oppgradering og feilsøking.

Enhetsfilen er JSON med schema_version=1, key, label, profile, statistics og valgfritt backlog. statistics har rapportroller med job_key, fetch_report_id, report_id og analysis_codes. Patolog har kun workflow med laboratory og process_codes. Hemato og Solide har antall, resultater og ekstraksjon; Flow/FISH har antall og resultater; Preanalyse har resultater.

Restanseinnhold består av report, analyses og columns. En separat valgt restansefil erstatter backlog-innholdet i enhetsfilen for den kjøringen. Filene leses og valideres ved jobbstart og endrer ikke en jobb som allerede kjører. Brukeren eier filplasseringen og filinnholdet; MolStat skriver dem ikke om.

Appinnstillinger lagres som schema_version=3. Eldre schema_version=2 kan leses; gamle statistics_lookup_path-felt ignoreres og eksporteres ikke videre. Innstillinger og LVMS-tilkobling ligger i LocalAppData/MolStat, uavhengig av valgt datarot. Ingen analyseoppslag eller standardenhetsfiler er med i installasjonspakken.
