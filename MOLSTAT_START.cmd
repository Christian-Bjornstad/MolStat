@echo off
setlocal
cd /d "%~dp0"
py -3 -m molstat.cli gui --settings "%LOCALAPPDATA%\MolStat\settings.json"
if errorlevel 1 pause
