@echo off
setlocal EnableExtensions
docker info >nul 2>nul
if not errorlevel 1 exit /b 0

echo [DevPilot] Docker engine is not running. Starting Docker Desktop...
set "DOCKER_DESKTOP=%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
if not exist "%DOCKER_DESKTOP%" set "DOCKER_DESKTOP=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if not exist "%DOCKER_DESKTOP%" (
  echo [DevPilot] Docker Desktop is not installed. Install it, enable the WSL2 engine, then retry.
  exit /b 1
)

start "" /min "%DOCKER_DESKTOP%"
for /L %%I in (1,1,90) do (
  docker info >nul 2>nul
  if not errorlevel 1 (
    echo [DevPilot] Docker Desktop is ready.
    exit /b 0
  )
  if %%I==1 echo [DevPilot] Waiting for Docker Linux engine (up to 90 seconds)...
  ping 127.0.0.1 -n 2 >nul
)

echo [DevPilot] Docker Desktop did not become ready. Open Docker Desktop and check WSL2/Linux containers.
exit /b 1
