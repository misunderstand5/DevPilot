@echo off
chcp 65001 >nul
cd /d %~dp0
taskkill /FI "WINDOWTITLE eq DevPilot API*" /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq DevPilot vLLM*" /T /F >nul 2>nul
where wsl >nul 2>nul && wsl bash -lc "pkill -f 'vllm serve' || true" >nul 2>nul
docker compose -f docker-compose.infra.yml stop
echo DevPilot services stopped.
pause
