@echo off
cd /d %~dp0
conda run -n agentdev python scripts\smoke_test.py
pause
