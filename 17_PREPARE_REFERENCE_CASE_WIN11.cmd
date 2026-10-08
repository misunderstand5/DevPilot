@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
call conda run --no-capture-output -n agentdev python scripts\prepare_reference_case.py --live --ingest --seed-ops
if errorlevel 1 exit /b 1
echo Online Boutique reference case is ready.
