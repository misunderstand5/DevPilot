@echo off
setlocal
cd /d "%~dp0"
docker inspect devpilot-github-mcp >nul 2>nul
if errorlevel 1 (
  docker run -d --name devpilot-github-mcp --restart unless-stopped ^
    -p 127.0.0.1:8082:8082 ^
    ghcr.io/github/github-mcp-server:latest ^
    http --read-only --toolsets=repos || exit /b 1
) else (
  docker start devpilot-github-mcp >nul || exit /b 1
)
echo GitHub MCP is running at http://127.0.0.1:8082 in read-only mode.
endlocal
