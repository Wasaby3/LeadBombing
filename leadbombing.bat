@echo off
REM Launcher for LeadBombing (uses the isolated .venv).
REM   No args            -> launches GUI
REM   With args          -> runs CLI, e.g.:
REM   leadbombing.bat -i "https://2gis.ru/..." -o out.csv -f csv
"%~dp0.venv\Scripts\leadbombing-cli.exe" %*
