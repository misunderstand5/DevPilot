@echo off
cd /d %~dp0
conda run -n agentdev mcp dev app\mcp_server.py
pause
