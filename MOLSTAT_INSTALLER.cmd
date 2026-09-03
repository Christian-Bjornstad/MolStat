@echo off
setlocal
cd /d "%~dp0"
echo Denne filen heter na MOLSTAT_INSTALL.cmd.
call "%~dp0MOLSTAT_INSTALL.cmd"
exit /b %errorlevel%
