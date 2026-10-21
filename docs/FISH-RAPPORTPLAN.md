# FISH-rapport

Oppdatert 21. oktober 2026. Rapporten er bygget med de samme ti sidene, navigasjonen, fargene og diagramoppsettet som den oppdaterte Solide-rapporten, som bygger på Hemato V13. Ingen egen datakvalitetsside er lagt til.

Rapportfilen ligger lokalt i `outputs/fish_20261021/FISH_Statistikk_ferdig.pbix`. Power BI-filer og produksjonsdata er utelatt fra Git. Rapporten er ikke publisert til Power BI-tjenesten.

## Sider og datamodell

Sidene er Oversikt, Antall per uke, Antall per rapportgruppe, Antall per analyse, Svartid over tid, Stablet tidsforløp, Svartid per analyse, Oppfølging, Uke og sesong og Brukerveiledning.

Bestillinger og resultater ligger i separate faktatabeller med felles analyseoppslag og kalender. Bestillingsvolum følger bestillingsdato; resultatbaserte mål følger resultatdato. Materialfilter gjelder resultatdata, siden bestillingsfilen ikke har materiale. Analyse- og årfiltre er kontrollert mot begge faktatabellene.

Analyseregisteret fra brukerens `Statistikk, FISH.xlsm` er innebygd: 61 koder med fem kalenderdøgn fra bestilling til analyseresultat. Normoppnåelse beregnes per gyldig resultat og endres ikke med perspektivvelgeren. Oppslagsfeltene er tomme i MolStat-eksporten og fylles derfor i Power BI. Priser eller kliniske resultater er ikke konstruert.

Perspektivene er prøvetaking → resultat, opprettet → resultat og FISH-bestilling → resultat. Opprettet er registreringstidspunkt; det antas ikke å være fysisk ankomst. Bestilling → godkjenning er et eget mål. FISH har ingen ekstraksjonsdata eller sikker etterbestillingsindikator i uttrekket, så disse egenskapene overføres ikke fra Solide.

Stablet tidsforløp bruker samme komplette utvalg for alle deler: prøvetaking → opprettet, opprettet → FISH-bestilling og FISH-bestilling → resultat. Summen er total gjennomsnittstid. Femdagersnormen gjelder bare FISH-delen og brukes ikke som frist for hele det stablede forløpet. Manglende, negative og over 365 døgn lange intervaller blir ikke gjort om til null.

## Rettet import og kontroll mot ekte data

Resultatfilen i `data.zip` har 13 kommentarer med uescapede anførselstegn inne i tekst som går over flere linjer. Den tidligere CSV-leseren delte disse postene og fylte ut fortsettelsesradene med tomme felt. Den felles LVMS-leseren bevarer nå kommentaren som ett felt. Samme leser brukes ved sammenslåing, vanlig behandling og manuell import. Uavklarte felt-/kolonnefeil stoppes; råfilene beholdes uendret.

Manuell FISH-import validerer analysebestilling mot valgt uttrekksperiode, ikke prøvens opprettelsesdato. Begge originale FISH-filer er kontrollert gjennom hele importflyten med register, lokal publisering og Excel-søk uten LVMS-tilgang. De publiserte CSV-filene er identiske med rapportens korrigerte inndata.

Uttrekket er behandlet med den rettede leseren. De berørte postene har fått datoene tilbake, og kommentarfragmenter blir ikke lenger falske ekskluderte analysekoder. Forskjellen mellom antall bestillinger og resultater brukes ikke som restanse.

Alle 90 mål er kjørt i Power BI-motoren. Hovedtall, normoppnåelse, medianer og summerte tidsdeler er avstemt mot uavhengige CSV-beregninger for alle analyser og år med data. Den lagrede PBIX-filen inneholder de ekte, korrigerte dataene, med SharePoint som kilde for senere oppdatering. Produksjonstall og kontrollfiler ligger bare i den lokale leveransen under outputs og tas ikke inn i Git.

## Videre oppdatering

Standardkilden er `fish/antall.csv` og `fish/resultater.csv` under samme MolStat-rot i SharePoint som Solide. Bruk oppdatert MolStat for å behandle og publisere neste uttrekk. De to korrigerte CSV-filene følger også den lokale leveransen og kan erstatte den tidligere FISH-eksporten.

Ved bruk av lokale eksportfiler settes parameteren `MolStatKilde` til `Lokal`, og `MolStatLokalMappe` settes til mappen med de to behandlede CSV-filene. Råfiler skal ikke brukes direkte som Power BI-kilde. `MolStat-ID` er foreløpig tom i FISH-eksporten, så rapporten gir ikke prøvesøk eller unike prøvetellinger basert på denne kolonnen.
