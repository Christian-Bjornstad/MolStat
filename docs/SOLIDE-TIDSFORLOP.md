# Solide: analyseoppslag og fire tidsledd

Bestilt 26. oktober 2026. Grupper og svarfrister eies av Analyse_lookup.xlsx
i Power BI, ikke av Python eller kopierte verdier i faktafilene. Solide har
15 kalenderdøgn. Myriad og Idylla-kodene tilhører PRE.

## Hendelser

1. Prøvetaking → opprettet: før registrering.
2. Opprettet → metodevalg: transport.
3. Metodevalg → ekstraksjon ferdig: PRE.
4. Ekstraksjon ferdig → analyseresultat: Solide.

Metodevalg finnes som `Tidspunkt analyseresultat` på `EKSTRAKSJON-OU`, der
`Analyseresultat` inneholder metoden (for eksempel DNA FFPE/celler kolonne).
Slutt på PRE er det opprinnelige `Ekstraksjon.ferdig`: tidspunkt analyseresultat
på ekstraksjonsraden som den gamle Solide-regelen valgte. Denne regelen velger
siste ekstraksjonsresultat på samme prøve før endelig resultatgodkjenning.
Ekstraksjonens eget godkjenningstidspunkt brukes ikke som slutt på PRE.

Metodevalget knyttes til siste metodevalg på EKSTRAKSJON-OU før ekstraksjonsslutt
og analyseresultat. Etterbestilling beholdes som eget filter, og flytter ikke
ekstraksjonsslutt. Enhetstid kan beregnes fra ekstraksjonsslutt selv når
metodevalget mangler. Manglende hendelser blir ikke null dager.

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
manglende tidspunkter, feil prøve og ekstraksjon etter analyseresultat.
Rapportkontroll må også verifisere at fire ledd summerer til totalen, at PRE-
analyser er fjernet, og at ingen kjente analysekoder mangler gruppe eller frist.

Rapportvisningen omtaler ikke gyldighet, datakvalitet eller utelatte rader.
Interne datokontroller beholdes, og deres hjelpefelt skjules i modellen.
