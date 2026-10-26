# Solide: analyseoppslag og fire tidsledd

Bestilt 26. oktober 2026. Grupper og svarfrister eies av Analyse_lookup.xlsx
i Power BI, ikke av Python eller kopierte verdier i faktafilene. Solide har
15 kalenderdøgn. Myriad og Idylla-kodene tilhører PRE.

## Hendelser

1. Prøvetaking → opprettet: før registrering.
2. Opprettet → metodevalg: transport.
3. Metodevalg → ekstraksjonsgodkjenning: PRE.
4. Ekstraksjonsgodkjenning → analyseresultat: Solide.

Metodevalg finnes som `Tidspunkt analyseresultat` på `EKSTRAKSJON-OU`, der
`Analyseresultat` inneholder metoden (for eksempel DNA FFPE/celler kolonne).
`Tidspunkt godkjenning` på samme registrering er slutt på PRE.
Resultattid på en konkret metodeanalyse med «Utført» er en annen hendelse.
Dette er valgt tolkning basert på de delte rådataene; må bekreftes mot LVMS
før tallene brukes som en dokumentert måling av fysisk mottak.

Match på samme Sample ID, seneste metodevalg som ikke ligger etter resultatet.
Godkjenning må ligge mellom metodevalg og analyseresultat for gyldig enhetstid.
En sen eller for tidlig godkjenning beholdes for kontroll, med eksplisitt status.
Manglende godkjenning beholdes som manglende. Endelig resultatgodkjenning brukes ikke som grense.
Etterbestilling beholdes som eget filter, og flytter ikke ekstraksjonsslutt.

Den stablede figuren bruker samme komplette, kronologiske kohort for alle
fire ledd, slik at gjennomsnittene summerer til totalen. Manglende tidsstempler
og ugyldig rekkefølge teller som utelatt, aldri som null dager. Eksisterende
365-dagers grense for kvalitetskontroll beholdes.

## Levering og kontroll

Appen eksporterer eksplisitt metodevalg, metode og koblingsstatus i tillegg til
de gamle feltene. Gamle eksporter kan ikke dokumentere det nye forløpet og må
kjøres på nytt fra arkivert rådata. Grupper og frister kobles etter analysekode
fra samme Excel-oppslag i statistikk og restanse. Nye gruppeforslag merkes rødt.
Koder uten oppslag skal fortsatt være synlige som mangler.

Tester dekker separate hendelser, etterbestilling, gjentatt ekstraksjon,
manglende godkjenning, feil prøve og ekstraksjon etter analyseresultat.
Rapportkontroll må også verifisere at fire ledd summerer til totalen, at PRE-
analyser er fjernet, og at ingen kjente analysekoder mangler gruppe eller frist.
