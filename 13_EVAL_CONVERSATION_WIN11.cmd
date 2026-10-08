@echo off
cd /d "%~dp0"
call conda run -n agentdev python scripts\eval_conversation.py
pause
