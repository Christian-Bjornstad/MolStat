# Uttrekk og Prøvesøk – 1. november 2026

Alle rapporter forsøker først hele den manglende perioden i ett uttrekk. Ved en forbigående LVMS-feil deles bare den feilede perioden i kalenderår, deretter kalendermåneder hvis et årsuttrekk feiler. Delår og delmåneder avgrenses til forespurt periode. Store enkeltmåneder kan fortsatt deles i kortere perioder etter gjenforsøk. Innlogging, feil oppsett, usikker nedlasting og avbrudd stopper fortsatt kjøringen med sin feilkode.

Dette gjelder Hemato, Solide, Flow, FISH, Preanalyse, Patolog og restanse. Historikkstarten er fortsatt januar 2024. Eksisterende arkiver bestemmer hva som mangler per rapport; FISH beholder én kalendermåneds overlapp, de andre statistikkrapportene to dager. Patolog beholder lab-/prosessfilter og kontrollpunkter. Bare vellykkede deluttrekk arkiveres under oppdelingen, slik at en avbrutt innlasting kan fortsette fra bekreftet dekning. Vellykkede delperioder forbruker ikke grensen for sammenhengende feilforsøk.

Prøvesøk får ark- og strukturbeskyttelse. De gule søkefeltene A5:A54 og søketypen B56 kan redigeres. Formler, data og resultatfelt er låst, mens resultater fortsatt kan markeres og kopieres. Excel anbefaler å åpne filen skrivebeskyttet; det går fortsatt an å søke i denne modusen og lagre en egen kopi. Lim inn søk som verdier. Arkpassordet er `MolStat`, for bevisst vedlikehold. Dette er vern mot utilsiktet redigering, ikke tilgangskontroll.

Søkehjelpeformlene lagres med eksplisitt matriseberegning utenfor Excel-tabellen. Det hindrer at Excel legger til `@` i søkeområdet og gir `#VALUE!`. Numeriske formelbuffere, XML og beskyttelse valideres før publisering. En ugyldig kandidat erstatter ikke den eksisterende filen; låst fil følger eksisterende gjenforsøksflyt.

Etter oppdatering av programkoden må Excel-søket genereres på nytt for å få rettelsene. Bruk appens oppdatering av Excel-søk eller neste Hemato-/Solide-kjøring, og lukk den gamle filen først. Databasen trenger ikke bygges på nytt.

Kontrollert med syntetiske uttrekk for kalendergrenser, fallback, alle statistikkenheter og gjenopptaking etter avbrudd. En syntetisk Prøvesøk-fil er åpnet og rekalkulert i installert Excel 16.0; søk og blokkering av formeloverskriving er kontrollert. Dette måler ikke faktisk LVMS-/nettverksytelse på jobb-PC.
