@echo off
cd /d %~dp0
echo WARNING: this removes MySQL/Redis/Qdrant demo volumes.
choice /M "Continue"
if errorlevel 2 exit /b 0
docker compose -f docker-compose.infra.yml down -v
docker compose -f docker-compose.infra.yml up -d
conda run -n agentdev python scripts\wait_infra.py
conda run -n agentdev python scripts\ingest_sample_docs.py
pause
