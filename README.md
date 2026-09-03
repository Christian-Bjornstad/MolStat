# MolStat

MolStat samler dagens LVMS-STAT og MolPat Puls i ett system:

- PyQt6-kontrollsenter for status, manuell kjøring og innstillinger
- nettleserbasert restansetavle på `127.0.0.1`
- daglig statistikk kl. 05:00
- restanse hver hele time kl. 06:00–18:00
- rådata, arbeidsfiler og SQLite kun på K-sensitiv
- identifikatorfrie CSV-filer til lokal SharePoint-synkmappe for Power BI

## Kom i gang på jobb-PC

1. Kjør `MOLSTAT_INSTALL.cmd` og lim den kopierte kommandoen inn i Python FELLES.
2. Legg inn stiene og LVMS-adressen i Innstillinger.
3. Bruk «Bla gjennom …» for å kontrollere mappene og lookup-filene.
4. Velg «Valider og lagre». Kjøreoppsettet lastes inn uten omstart.

Se [JOBBS-PC.md](JOBBS-PC.md) for kontrollpunkter og drift.

## Utvikling

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```
