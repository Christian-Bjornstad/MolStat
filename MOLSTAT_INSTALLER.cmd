@echo off
setlocal
cd /d "%~dp0"
py -3 -m pip install -e ".[dev]"
if errorlevel 1 goto :error
if not exist "%LOCALAPPDATA%\MolStat\settings.json" (
  echo MolStat er installert. Fyll inn Innstillinger, lagre og start pa nytt.
  call "%~dp0MOLSTAT_START.cmd"
  exit /b 0
)
py -3 -m molstat.cli check-config --settings "%LOCALAPPDATA%\MolStat\settings.json"
if errorlevel 1 goto :error
py -3 -m molstat.cli install-automation --settings "%LOCALAPPDATA%\MolStat\settings.json"
if errorlevel 1 goto :error
echo MolStat og planlagte oppgaver er installert.
exit /b 0
:error
echo Installasjonen stoppet. Se feilmeldingen over.
pause
exit /b 1
