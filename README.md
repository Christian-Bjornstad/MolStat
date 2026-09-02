# MolStat

MolStat samler dagens LVMS-STAT og MolPat Puls i ett system:

- PyQt6-kontrollsenter for status, manuell kjøring og innstillinger
- nettleserbasert restansetavle på `127.0.0.1`
- daglig statistikk kl. 05:00
- restanse hver hele time kl. 06:00–18:00
- rådata, arbeidsfiler og SQLite kun på K-sensitiv
- identifikatorfrie CSV-filer til lokal SharePoint-synkmappe for Power BI

## Kom i gang på jobb-PC

1. Kjør `MOLSTAT_INSTALLER.cmd`.
2. Legg inn stiene og LVMS-adressen i Innstillinger.
3. Lagre, lukk og start MolStat på nytt.
4. Kjør installerfilen igjen for å opprette Windows-oppgavene.

Se [JOBBS-PC.md](JOBBS-PC.md) for kontrollpunkter og drift.

## Utvikling

```powershell
py -3 -m pip install -e ".[dev]"
py -3 -m pytest
```
