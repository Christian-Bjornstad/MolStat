# Plan for kommentarer og oppfølging

Power BI-tabellen er **ikke** en skriveflate og skal ikke fremstilles som om kommentarer lagres i rapporten. Dagens datasett mangler en dokumentert, stabil og personvernmessig egnet saksnøkkel. Kommentarflyt aktiveres derfor først når en stabil nøkkel og en godkjent lagringskilde finnes.

## Anbefalt løsning

Bruk en separat SharePoint-liste som førstevalg dersom OUS allerede har godkjent området. Dataverse eller SQL er bedre alternativer ved strengere tilgangsstyring, større volum eller behov for revisjonslogg. Power Apps kan bygges inn som skriveflate i rapporten.

Foreslåtte felt:

- **Stabil saksnøkkel** – pseudonymisert og uforanderlig ID fra kildesystemet; aldri fritekst eller pasientidentifikator.
- **Status** – Ny, Under vurdering, Tiltak avtalt, Avventer og Lukket.
- **Eier** – ansvarlig funksjon eller godkjent brukerkonto.
- **Kommentar** – kort, faglig oppfølgingsnotat uten pasientopplysninger.
- **Opprettet dato** – automatisk tidsstempel.
- **Sist endret** – automatisk tidsstempel.
- **Rapportgruppe** og **Analyse** – lagres som hjelpeattributter for filtrering, men er ikke nøkkel.

## Integrasjon

Oppfølgingssiden kan senere kobles med en én-til-mange-relasjon fra den stabile saksnøkkelen til kommentarlisten. Radnivåsikkerhet, dataklassifisering, oppbevaringstid og revisjon må avklares før produksjonssetting. Inntil dette er gjort viser rapporten analyse-, tids- og datakvalitetsstatus, men tilbyr ikke falsk writeback.
