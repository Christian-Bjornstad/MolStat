# MolStat

MolStat henter statistikk og restanse fra LVMS og leverer behandlede CSV-filer til Power BI. Hemato og Solide har statistikk og restanse. Flow, FISH og Preanalyse har statistikk. Patologer bruker bare PAT-TID-STØP-SNITT-OU, én kalendermåned om gangen fra januar 2024.

## Oppsett

Start med `MOLSTAT_INSTALL.cmd` og deretter `MOLSTAT_START.cmd`. På jobb-PC med Python FELLES brukes den medfølgende start-/installasjonsflyten. Se [JOBBS-PC.md](JOBBS-PC.md).

Velg datarot, SharePoint-mappe og LVMS-adresse i Innstillinger. Velg din egen enhetsfil (JSON) for hver aktivert enhet. For Hemato og Solide kan du velge en separat restansefil, eller bruke restanseinnholdet i enhetsfilen. Valgte filer brukes direkte, også etter omstart. Ingen config-kopier eller standardfiler opprettes.

Appen trenger ingen CSV-/Excel-oppslagsfiler eller legeregister. Gamle lookup-stier ignoreres. Analyseoppslag med grupper, navn, priser og normer kobles i Power BI. MolStat beholder tidsstempler og beregnbare intervaller; oppslagsavhengige verdier er tomme eller ikke beregnet.

## Lagring

```text
Valgt datarot/
  database/
    molstat.sqlite3
    backups/
  data/
    raw/
    processed/
  Prøvesøk.xlsx
```

Ved oppgradering flyttes den gamle databasen fra `data/molstat.sqlite3`, og gamle `raw/` og `processed/` flyttes under `data/`. En verifisert databasekopi beholdes før flytting. Lukk alle andre MolStat-vinduer før første oppstart med ny versjon. Ved låsing eller kollisjoner stoppes flyttingen; ingen tom erstatningsdatabase opprettes.

Eksisterende `config/` og `work/` på en annen PC slettes ikke blindt: velg først egne JSON-filer utenfor gammel config, og bevar eventuelle uavklarte nedlastinger. Ny versjon oppretter ingen av disse mappene. Midlertidige jobber ligger privat under data/raw og ryddes når nedlastingene er arkivert.

Rådata og databasen publiseres ikke. Bare avtalte rapportkolonner sendes til valgt SharePoint-mappe. Prøvesøk.xlsx kan genereres fra databasen. Patolog publiserer `Prøver.csv`, `Glass.csv`, `Signeringer.csv`, `Grupper.csv`, `Periode.csv`, `Leger.csv` og `Prioriteter.csv` i SharePoint-mappen `lege/`. De samme tabellene beholdes lokalt under `data/processed/lege/powerbi/`. Patologtabellene beholder prøvenummer, glass-ID og legeidentitet som i den lokale modellen. Nye kjøringer lager og publiserer ikke `prosess.csv`.

## Utvikling

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

Tester bruker syntetiske data og egne JSON-fixtures under tests/. Repoet inneholder appkoden, tester og start-/installasjonsfiler. Power BI-prosjekter, oppslag, rådata, databaser og byggeartefakter inngår ikke.
