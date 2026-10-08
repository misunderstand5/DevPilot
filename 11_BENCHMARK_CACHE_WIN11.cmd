@echo off
cd /d %~dp0
conda run -n agentdev python scripts\benchmark_cache.py
pause
