@echo off
setlocal
chcp 65001 >nul
cd /d %~dp0
docker compose -f docker-compose.infra.yml up -d || exit /b 1
conda run -n agentdev python scripts\wait_infra.py || exit /b 1
conda run -n agentdev python scripts\migrate_auth_acl.py || exit /b 1
conda run -n agentdev python scripts\migrate_rbac.py || exit /b 1
conda run -n agentdev python scripts\migrate_memory_v2.py || exit /b 1
call 04_START_VLLM_WSL2.cmd
start "DevPilot API" cmd /k "cd /d %~dp0 && set HF_ENDPOINT=https://hf-mirror.com && conda run -n agentdev python -m uvicorn app.main:app --host 0.0.0.0 --port 8001"
timeout /t 5 >nul
start http://127.0.0.1:8001/docs
echo DevPilot started. Swagger: http://127.0.0.1:8001/docs
pause
