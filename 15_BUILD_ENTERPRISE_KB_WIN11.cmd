@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
call conda run -n agentdev python scripts\generate_enterprise_corpus.py
call conda run -n agentdev python scripts\ingest_enterprise_corpus.py
pause
