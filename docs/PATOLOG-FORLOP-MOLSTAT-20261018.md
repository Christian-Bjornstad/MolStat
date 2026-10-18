# Patologforløp i MolStat – 18.10.2026

## Dette er lagt til

Patologers statistikkjobb henter nå bare `PAT-TID-STØP-SNITT-OU` (rapportrollen `workflow`).
Enhetsfiler med gamle patolograpporter omstilles ved innlesing. De gamle rapportene
for prosessaggregater, produksjon og makro hentes ikke lenger. Eksisterende råarkiv
beholdes. Manuell import krever bare én forløpsfil for valgt måned.

LVMS-parametre lest fra «Definerte rapporter» i den åpne Citrix-økten:

- Rapporttype: `PRODSTAT`.
- Kategori: `PATOLOGI`.
- Rapport-ID: `PAT-TID-STØP-SNITT-OU`.
- Parametre: `Ankomsttid f.o.m.:`, `Ankomsttid t.o.m.:`, `Lab:`, `Prosess:`.
- Laboratorium: `OU-PAT-HIST-RA`.
- Prosesslisten ligger i `src/molstat/defaults/units/lege.json` under `workflow`.
  Den inkluderer 21 LVMS-koder, blant annet `HEMATO`, `HEMATO BENMARG` og
  `TARMSCREENING`. Begge hematologikodene vises som «Hemato og Beinmarg».
  Innlesingen støtter dessuten `HEMATO-BEINMARG` og `HEMATO BEINMARG`.
- Arkivnavn bruker ASCII: `PAT-TID-STOP-SNITT-OU`.

Den observerte manuelle perioden var 19.08.2026–18.10.2026 15:49.
Dette er dokumentasjon av den åpne dialogen, ikke perioden appen vil hente.

## Månedsvis historikk

Første kjøring bygger historikk fra appens eksisterende startpunkt
01.01.2024, én kalendermåned per rapport. Årsskifte, februar og skuddår
håndteres. Inneværende måned hentes fra den første til dagens dato;
sluttdatoens klokkeslett settes til 23:59:59 for å ta med hele siste dag.
Ingen forespørsel for denne rapporten spenner over flere måneder.

Hver historiske fil valideres og arkiveres før neste måned starter.
Ved feil kan neste kjøring fortsette fra manglende måned. Måneder med åpne
prøver eller ufargede glass hentes på nytt. Ferdige måneder kontrolleres
igjen etter 30 dager, slik at senere etterbestillinger også kan komme med.
Inneværende måned hentes hver kjøring.

Nyeste øyeblikksbilde per ankomstmåned erstatter eldre versjoner i
beregningen. Versjoner summeres aldri. Feil kolonner, feil periode,
feil lab/prosessfilter eller motstridende glassdata stopper oppdateringen.
Rapporttype og filtre valideres før kjøring.

## Filer til Power BI

Råfiler ligger under den valgte K-sensitive roten:

`raw/statistics/lege/PAT-TID-STOP-SNITT-OU__ÅÅÅÅ-MM-DD__ÅÅÅÅ-MM-DD.csv`

Nyeste bearbeidede filer legges stabilt under:

`processed/lege/powerbi/`

Filene heter `Prøver.csv`, `Glass.csv`, `Signeringer.csv`, `Grupper.csv`,
`Periode.csv`, `Leger.csv` og `Prioriteter.csv`. De følger samme kolonneskjema
som de oppdaterte Power BI-rapportene. Referansetid og restansealder
beregnes på nytt ved hver MolStat-kjøring.

Begge PBIX-filene har Power Query-parameteren **Datamappe**. Den peker nå
på de lokale datafilene som ble brukt for denne leveransen. På jobb-PC-en:
åpne **Transformer data → Rediger parametere**, og sett Datamappe til den
fulle K-sensitive stien som ender på `processed/lege/powerbi`.
Deretter velges **Oppdater**. Det er én parameter for alle sju tabellene.

Forløpsfilene følger appens eksisterende private Power BI-leveranse.
Den aggregerte `prosess.csv` beregnes nå fra samme forløpsfil og krever ikke et ekstra uttrekk. Profil er merket som ikke oppgitt i kilden.

## Ta oppdateringen i bruk

`MolStat_oppdatert_20261018.zip` inneholder appkoden, startskriptene,
standardoppsettene og denne veiledningen, uten rådata eller database.
Pakk den ut i den eksisterende MolStat-programmappen på jobb-PC-en,
behold eksisterende innstillinger og K-sensitiv rot, og start MolStat på nytt
med `MOLSTAT_START.cmd`. Neste statistikkjøring for Patologer tar med forløpet.
Første historikkjøring kan ta tid siden hver måned kjøres separat.

Det finnes ingen lokal MolStat-innstillingsfil for jobb-PC-en i denne økten.
Den aktive Citrix-installasjonen er derfor ikke oppgradert, og ingen full
historisk LVMS-kjøring er startet herfra. Faktisk parameterutfylling,
LVMS-eksport og nedlasting må verifiseres ved første kjøring på jobb-PC-en.

## Kontrollert

De nye CSV-dataene er kontrollert mot Power BI: 3 973 prøver, 40 002 unike
glass, 2 925 godkjente og 1 048 åpne i hele uttrekket. Alle 59 mål kjører;
731 visualbindinger er kontrollert. Telling, median og glassmengde er avstemt
per lege med alle roller, og rollediagrammene er avstemt per valgt lege/rolle. Median og summen av de fem
forløpstrinnene er avstemt uavhengig. Native rapportskjemaer validerer.
Automatiserte tester dekker månedsskifte, revisjoner, gjenopptakelse,
CSV-format, duplikater og LVMS-felter.

## Rapportgjennomgang – ny revisjon

- «Åpne med registrert lege» og sammenlikningsarket er fjernet.
- Godkjenningsrolle starter på Alle. Prøver per rolle følger legefilteret og har tall på søylene.
- Prøver og glass viser fordelingen av glassmengde og svartid per glassmengde.
- Legeutvikling viser godkjente prøver og median/P90 fra farget til godkjent per uke.
- Svartid over tid viser median, gjennomsnitt og P90 fra ankomst til godkjent.
- Ved flere roller hos samme lege teller prøven én gang i tidsmål og glassmengde.
- Samme prøve kan inngå hos flere leger og i flere roller. Å summere disse er ikke et pasientantall.
- Én prøve med fem glass gir én svartid. Glassvolumet er fem. Unikt prøvenummer er ikke unik pasient.
- Etterbestilling betyr at kildefeltet Glass etterbestilt er utfylt; årsaken er ikke oppgitt.
- Tid fra farget til godkjent bruker siste ferdige glass før godkjenning, og krever at alle glass opprettet før godkjenning var ferdig farget.
- Den stablede førstebestillingskjeden bruker siste tidspunkt per trinn for opprinnelige glass. Den summerer ikke parallelle glasstider.
- Den nye filen kan fortsatt ikke vise hvem som utførte makro, slik den eldre makrorapporten kunne. Makrovolum per lege er derfor ikke fremstilt.
