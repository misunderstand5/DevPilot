@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
call conda run -n agentdev python scripts\eval_ab.py
pause
