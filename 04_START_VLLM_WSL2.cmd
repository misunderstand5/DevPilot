@echo off
setlocal
cd /d %~dp0
where wsl >nul 2>nul || (echo [WARN] WSL not found. Skip vLLM. & exit /b 0)
if not defined DEVPILOT_WSL_DISTRO set DEVPILOT_WSL_DISTRO=DevPilot-Ubuntu
if not defined DEVPILOT_WSL_USER set DEVPILOT_WSL_USER=devpilot
for /f "delims=" %%i in ('wsl -d %DEVPILOT_WSL_DISTRO% -u %DEVPILOT_WSL_USER% wslpath "%CD%"') do set WSL_DIR=%%i
wsl -d %DEVPILOT_WSL_DISTRO% -u %DEVPILOT_WSL_USER% bash -lc "test -x ~/venvs/vllm129/bin/python || test -x ~/venvs/vllm/bin/python" >nul 2>nul || (echo [WARN] vLLM env not installed in %DEVPILOT_WSL_DISTRO%. Run wsl\01_SETUP_VLLM_WSL2.ps1 first. & exit /b 0)
start "DevPilot vLLM" wsl -d %DEVPILOT_WSL_DISTRO% -u %DEVPILOT_WSL_USER% bash -lc "cd '%WSL_DIR%' && bash wsl/start_vllm.sh"
exit /b 0
