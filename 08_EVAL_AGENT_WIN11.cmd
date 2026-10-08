@echo off
cd /d %~dp0
conda run -n agentdev python scripts\eval_agent.py
pause
