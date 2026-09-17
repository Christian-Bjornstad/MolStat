# Leveransestatus 17. september 2026

Lokal implementering ligger på `codex/robust-app-config`.
Driftsveiledning: [APP-OPPSETT.md](../../docs/APP-OPPSETT.md).

## Levert og lokalt kontrollert

- Feil fra LVMS beholder kode, trinn, forsøk og kjørings-ID. Bare trygge,
  midlertidige feil før innsending får høyst to automatiske gjenforsøk.
- SQLite-forbindelser lukkes deterministisk og read-only URI håndterer UNC.
  Eksisterende databaser gjenåpnes; schema 7 bevarer historikk og skiller
  restansens nåtilstand per enhet. Feil databaseplassering blokkeres.
- Hemato og Solide har egne JSON-filer med separate rapportlister.
  Filvalg, validering og atomisk aktivering er integrert i innstillinger.
  Oppsett og lookup kontrolleres før uttrekk og fryses gjennom kjøringen.
- Råarkiv, oppsettversjoner, database, arbeidsfiler og prosesserte kandidater
  har separate mapper. Mislykket publisering kan gjenopptas fra siste kandidat
  med hashkontroll, uten nytt LVMS-uttrekk eller import.
- Ny palett, tydelige felter, fokus og statuser. Arbeiderfeil rydder opp i
  kjøretilstanden; innstillinger låses under kjøring og ukonfigurert kjøring blokkeres.
- Eksisterende Excel-søk beholdes. Appen kan regenerere arbeidsboken fra
  databasen og viser eksportstatus uavhengig av import/publisering.

## Testbevis

- `python -m pytest -q -o addopts=''`: **571 passed**, 49,41 sekunder.
- `python -m compileall -q src`: exit 0.
- `git diff --check`: exit 0; kun Git-varsler om LF/CRLF.
- Wheel bygget: `artifacts/app-fornyelse/dist/molstat-0.1.0-py3-none-any.whl`.
- Qt-oversikt og innstillinger rendret og inspisert lokalt, inkludert 1100 px bredde.
- Regresjonstester dekker beholdte forbindelser, URI, schema 6-overgang,
  flere enheters restansetilstand, ugyldige oppsett, trygg retry, siste
  publiseringskandidat og faktisk Excel-regenerering.

## Gjenstående miljøkontroll

Citrix/LVMS var ikke åpent. Sporadisk feil på jobb-PC kan derfor ikke erklæres
rotårsaksverifisert i det faktiske miljøet. Følg pilotlisten i driftsveiledningen:
samme database etter restart, reell UNC-tilgang/låsing, LVMS-identitet og
nedlasting, SharePoint-lås og rekalkulering i målversjonen av Excel.
Gamle kontrollpunkter for prøveregister og Excel står åpne til dette er gjort.

## Videre planutvidelser

Den opprinnelige planen var bredere enn den leverte versjonen. Dedikert
avbrytknapp/progresjon, oppdeling i flere navigasjonssider, kontroll ved høy DPI,
streng CSV-quotingkontroll og selvstendig eksportpakke med alle enhetsfiler
er ikke implementert. Automatisk retensjon er ikke aktivert.
Innstillingene støtter fortsatt Hemato og Solide; nye analysekoder krever
ingen kodeendring, mens helt nye beregningsprofiler/enhetstyper krever kode.
