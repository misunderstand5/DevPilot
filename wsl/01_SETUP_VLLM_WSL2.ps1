$ErrorActionPreference = "Stop"
Write-Host "=== DevPilot vLLM WSL2 Setup ===" -ForegroundColor Cyan

try {
  wsl --status | Out-Host
} catch {
  Write-Host "WSL is not enabled. Running wsl --install -d Ubuntu-24.04 ..." -ForegroundColor Yellow
  wsl --install -d Ubuntu-24.04
  Write-Host "Please reboot Windows, finish Ubuntu first-run user creation, then run this script again." -ForegroundColor Yellow
  exit 0
}

$project = (Resolve-Path "$PSScriptRoot\..").Path
$wslProject = (wsl wslpath -a $project).Trim()
Write-Host "Project in WSL: $wslProject"
wsl bash -lc "cd '$wslProject' && bash wsl/bootstrap_vllm.sh"
