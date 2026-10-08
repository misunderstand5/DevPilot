@echo off
cd /d %~dp0
set HF_ENDPOINT=https://hf-mirror.com
set HF_HUB_DISABLE_XET=1
conda run -n agentdev python scripts\ingest_sample_docs.py
pause
