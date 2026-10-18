# Patologforløp – lokal utprøving

Brukerbestilling 18.10.2026: undersøk PAT-TID-STØP-SNITT-OU.csv og lag
restanse og et bredt utvalg statistikksider i eksisterende Power BI-stil.
Oppdatert brukerbestilling samme dag: integrer rapporten i MolStat med månedlige uttrekk. Lokal kode/defaultkonfigurasjon er oppdatert; jobb-PC-kjøring gjenstår.

Byggere: src/molstat/_statistics/patolog_flow.py (grain, kvalitet, tider) og
tools/build_patolog_flow.py (modell, mål og rapporter).

Prøver telles én gang per prøvenummer, glass én gang per GlassId og
signeringer én gang per prøve/lege/rolle/godkjenning. Ingen stille filtrering
av ukjente prosesskoder eller motstridende gjentatte glass.

Restanse følger valgt ankomstperiode. Blått viser mottatte prøver i perioden,
grønt viser godkjente i perioden etter godkjenningsdato, lilla ufargede glass
på periodens prøver. Rødt viser ikke-godkjente prøver over en foreløpig
gruppegrense. Gruppesider med ingen data merkes som manglende dekning.
År/måned finnes øverst, startperiode oktober 2026; alle måneder kan velges.

Varselgrense er foreløpig P90 av godkjente ankomst–godkjent-tider, avrundet
opp til hele kalenderdager. Grupper med færre enn 30 bruker samlet P90.
Grensen er beskrivende for dette uttrekket, ikke en godkjent tjenestefrist.

Stablede tider er gjennomsnitt av fem trinn på samme komplette, monotone
prøveutvalg: ankomst, siste makro/støp/snitt/farging i førstebestillingen,
godkjent. Etterbestillinger vises separat. Manglende og negative tider er
blanke og inngår ikke som null. Telleren bak tidsmål vises.

Legeintervallet krever at alle glass opprettet senest ved godkjenning er
ferdig farget før godkjenning. Roller skiller hoved- og medansvarlige.
Tider er forløpstid og kan ikke tolkes som aktivt personlig arbeid.

Filen mangler uttrekkstidspunkt. Siste faktiske prosesstempel brukes som
eksplisitt referansetid 15.10.2026 12:37; prøvetaking utelates fra denne
beregningen fordi feltet inneholder fremtidige datoer. Ikke historiske
restansesnapshots eller historisk komplett produksjon utenfor filens utvalg.

Verifisering: pytest syntetiske grain-/tidsprøver, Python-avstemming,
PBIR-validering, alle DAX-mål kjøres mot lokal modell, PBIX åpnes og
utvalgte sider kontrolleres i Desktop. Ingen skyopplasting.
