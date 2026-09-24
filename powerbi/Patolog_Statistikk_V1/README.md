# Patologstatistikk

## MolStat-mal

Åpne `Patolog_Statistikk_MolStat.pbit` på jobb-PC-en. Angi `MolStatPublicRoot`
som roten over `lege`-mappen i SharePoint og `MolStatPrivateRoot` som
`<K-sensitiv>/processed/lege/powerbi`. Den siste mappen får
`FactPatologRolle.csv`, `FactMakro.csv`, `DimPatolog.csv` og `DimDato.csv` fra
MolStat. Oppdater og lagre som PBIX på godkjent område. Malen har ti sider,
inkludert Prosessvolum, og inneholder ingen cached prøvedata. Den tidligere
`Patolog_Statistikk_V2.pbix` inneholder eldre data og lokale filbaner.

Ved første legekjøring må MolStat fullføre månedsvis historikk før alle
årstall vises. `prosess.csv` blir publisert separat i SharePoint.

## Prosessvolum (V2)

Siden **Prosessvolum** bruker MolStat-filen `lege/prosess.csv` med månedsaggregater fra LVMS-rapporten `PAT-ANTALL REGISTRERTE PRØVER PROSESS-OU`. Feltene er registrerte prøver (`Distinct_SampleId`), blokker og glass. Hemato Flow er prosess `HEMATO` i lab `OU-PAT-SPES-RA`; øvrige `HEMATO`-rader vises som Hemato uten Flow. Siden har filtre for måned, prosessgruppe, profil og lab. Tallene er summer av distinkte verdier **per LVMS-kilderad**; de må ikke tolkes som distinkt antall på tvers av lab eller profil.

Aktiver enheten **Patologer** i MolStat. Ved første kjøring hentes alle manglende hele måneder fra januar 2024 og frem til forrige måned, ett LVMS-uttrekk per måned. Hver ferdig måned arkiveres med én gang. Hvis kjøringen avbrytes, starter neste kjøring på første manglende måned. Deretter hentes inneværende måned til dagens dato og hele forrige måned ved hver kjøring. Nyeste uttrekk for hver måned brukes, slik at gjentatte kjøringer ikke dobbelttelles. Etter fullført kjøring publiseres `prosess.csv` i SharePoint-mappen `lege`; råfilene lagres i K-sensitiv MolStat-mappe. Førstegangskjøringen kan ta tid fordi den åpner LVMS én gang per måned.

Den eldre `Patolog_Statistikk_V2.pbit` har lokale kildebaner. Bruk MolStat-malen ovenfor for ny oppdatering.

Førsteversjon basert på de lokale LV-uttrekkene i Downloads/lege og det medfølgende legeregisteret. Originalrapporten og kildefilene er ikke endret. Rapporten er ikke publisert eller koblet til eksterne tjenester.

## Definisjoner

Bare brukere i faggrupper_liste.csv inngår i produksjons- og makrostatistikk. Brukernavn standardiseres til store bokstaver. Hovedansvarlig er standardvalg i produksjonsvisningene. Antall viser distinkte prøvenumre, ikke antall eksportlinjer, glass eller pasienter. Rolletall og legetall er ikke additive.

Eksportlinjer grupperes per prøve, bruker, rolle, profil, prosess og godkjenningstidspunkt. Siste fargetid innen denne gruppen brukes. Antall glass brukes ikke som produksjonstall fordi eksportens summeringsgrunnlag ikke er avklart.

Medianen teller hver prøve én gang i gjeldende filterutvalg, og bruker siste registrerte godkjenning i dette utvalget. Ved flere profiler/prosesser på dette tidspunktet brukes største beregnbare intervall. Sammenligning per lege bør alltid begrenses til sammenlignbar faggruppe, profil, prosess og rolle. Tidene er kalenderdøgn, ikke arbeidstimer.

Farget → godkjent bruker godkjenning minus siste ferdig-farget-tid. Negative og manglende intervaller blir blanke. Makro → godkjent kobler siste makrohendelse på samme prøvenummer senest ved godkjenning. Dette bekrefter ikke at hendelsen tilhører samme diagnostiske episode; koblingen er foreløpig. Det er ikke målt personlig arbeidstid.

Produksjon følger godkjenningsdato og makro følger makrodato. Tilgjengelig periode bestemmes av fullførte MolStat-uttrekk. Ingen individuell svarfrist, pasientforløp, restanse eller kobling til Hemato/Solide er konstruert uten nødvendige kilder.

## Oppdatering

PBIX-filen inneholder data og kan åpnes uten tilgang til K-disken. Oppdatering i Desktop leser de prosesserte CSV-filene i Data-mappen via lokale absolutte stier. Den henter ikke nye råuttrekk direkte.

For nye råuttrekk: behold samme kolonneformat i Downloads/lege, kjør tools/build_patolog_v1.py build fra MolStat-prosjektet, og oppdater deretter modellen i Desktop. Ved flytting til jobb-PC må filstiene i Power Query tilpasses til godkjent lokal lagringsplass. Ikke legg prøvenumre og legeopplysninger på åpne delingsområder.

PBIP- og semantisk modelldefinisjon er inkludert for videre arbeid. CSV-filer og PBIX inneholder prøvenumre og personopplysninger og må behandles med samme tilgangsbegrensning som kildene.
