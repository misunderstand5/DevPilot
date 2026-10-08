@echo off
cd /d %~dp0
conda run -n agentdev python scripts\check_llm.py
pause
