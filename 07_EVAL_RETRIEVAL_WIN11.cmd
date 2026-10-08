@echo off
cd /d %~dp0
set HF_ENDPOINT=https://hf-mirror.com
conda run -n agentdev python scripts\eval_retrieval.py
pause
