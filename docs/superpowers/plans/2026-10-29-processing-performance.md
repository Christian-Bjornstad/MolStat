# Raskere behandling og robuste statistikkuttrekk

**Mål:** Redusere lokal behandling og Excel-oppdatering; mål for brukerens daglige Hemato-uttrekk er høyst tre minutter. Arbeids-PC-ens faktiske nettverks- og datamengder må måles der før tidsmålet kan bekreftes.

**Arkitektur:** Behold Python FELLES, eksisterende datalagring, råarkiv, identiteter, rapportkolonner og sikre publiseringsrutiner. Mål syntetiske data før/etter. Unngå gjentatt registerimport av bekreftet arkivhistorikk; bygg Excel én gang etter en samlet kjøring. Behold full historikk i Power BI og Excel.

**Krav fra brukeren:** Statistikk for alle seks enheter henter fra siste arkiverte rapportsluttdato med eksisterende to dagers overlapp. Uttrekk over to kalendermåneder deles i kalendermåneder. Restanse beholder full periode. Forbigående LVMS-feil ventes og prøves på nytt, deretter kortere perioder med eksisterende grenser og avbruddsstøtte. Test og push til Git.

## Oppgaver

- [x] Profilere historisk Hemato-behandling og daglig oppdatering. Legg regresjonstest før optimalisering av registerimport og eventuell dokumentert datoparsingflaskehals (`statistics.py`, `_statistics/processing.py`, statistikktester).
- [x] Profilere Excel-lesemodell, generering og validering; optimaliser målte flaskehalser uten å endre søkeregler, skjema, personvern eller filgjenoppretting (`excel_search.py`, Excel-tester).
- [x] Test at samlet enhets-/statistikk-/restansekjøring lager Excel én gang, også ved delvis feil, og at enkeltkjøring fortsatt oppdaterer (`system.py`, `test_system_excel_batching.py`).
- [x] Test og innfør månedlig oppdeling for alle statistikkenheter over to måneder; behold overlapp og månedsvis gjenopptak. Utvid bare uttrykkelig forbigående LVMS-feil til venting/retry/oppdeling (`fetching.py`, hentetester).
- [x] Dokumenter før/etter-målinger og praktiske begrensninger; kjør hele testpakken og gjennomgå diff. Sluttkontroll: 1064 tester bestått i ren, midlertidig kildekodekopi. Lokal hovedmappe har eksisterende, ignorerte Power BI-databaseartefakter under outputs som treffer personverntestens rekursive filsøk; brukerfilene beholdes.
- [x] Gjøre de verifiserte endringene klare for separate commits og push på gjeldende branch.

## Kontroller

Historikk uten database, eksakt-periode-korreksjoner, gjentatt identisk uttrekk, endret rapportoppsett, delvis importfeil, avbrudd, mistet skrivelås, låst Excel-fil, månedsskifter/skuddår og avbrutt førstegangsinnlasting skal bevare data og kunne gjenopptas. Ingen produksjonsdata brukes i ytelsesmålinger.
