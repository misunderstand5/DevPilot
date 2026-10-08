@echo off
setlocal
chcp 65001 >nul
cd /d %~dp0
set HF_ENDPOINT=https://hf-mirror.com
set HF_HUB_DISABLE_XET=1
docker version >nul 2>nul || (echo [ERROR] Start Docker Desktop first. & pause & exit /b 1)
if not exist .env copy /Y .env.example .env >nul
conda env list | findstr /C:"agentdev" >nul
if errorlevel 1 conda create -n agentdev python=3.11 -y || exit /b 1
conda run -n agentdev python -m pip install --upgrade pip || exit /b 1
conda run -n agentdev python -m pip install -r requirements.txt || exit /b 1
docker compose -f docker-compose.infra.yml up -d || exit /b 1
conda run -n agentdev python scripts\wait_infra.py || exit /b 1
conda run -n agentdev python scripts\migrate_auth_acl.py || exit /b 1
conda run -n agentdev python scripts\ingest_sample_docs.py || exit /b 1
echo SETUP COMPLETE. Login: admin / password configured by AUTH_ADMIN_PASSWORD in .env.
pause
