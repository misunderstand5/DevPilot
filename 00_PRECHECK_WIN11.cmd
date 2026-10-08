@echo off
chcp 65001 >nul
cd /d %~dp0
echo ========================================
echo DevPilot Windows Precheck
echo ========================================
where conda >nul 2>nul || (echo [FAIL] conda not found & exit /b 1)
where docker >nul 2>nul || (echo [FAIL] Docker Desktop CLI not found & exit /b 1)
docker version >nul 2>nul || (echo [FAIL] Docker Desktop is not running & exit /b 1)
echo [PASS] Conda + Docker
where wsl >nul 2>nul && (echo [INFO] WSL detected & wsl --status) || echo [WARN] WSL not found; vLLM setup will require WSL2.
where nvidia-smi >nul 2>nul && nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || echo [WARN] nvidia-smi not found.
echo Precheck completed.
pause
