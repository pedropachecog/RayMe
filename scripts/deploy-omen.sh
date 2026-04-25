#!/usr/bin/env bash
set -euo pipefail

OMEN_SSH_ALIAS="${OMEN_SSH_ALIAS:-rayme-pmpg}"
OMEN_REPO="${OMEN_REPO:-C:\\Users\\pmpg\\rayme\\RayMe}"
OMEN_BRANCH="${OMEN_BRANCH:-main}"

local_head="$(git rev-parse HEAD)"

EXPECTED_HEAD="${local_head}" OMEN_REPO="${OMEN_REPO}" OMEN_BRANCH="${OMEN_BRANCH}" \
ssh "${OMEN_SSH_ALIAS}" "powershell -NoProfile -ExecutionPolicy Bypass -Command - " <<'POWERSHELL'
$ErrorActionPreference = "Stop"
$repo = $env:OMEN_REPO
if (-not $repo) { $repo = "C:\Users\pmpg\rayme\RayMe" }
$branch = $env:OMEN_BRANCH
if (-not $branch) { $branch = "main" }
$expectedHead = $env:EXPECTED_HEAD

Set-Location $repo
Write-Host "== OMEN deploy: repo $(Get-Location)"
git fetch origin $branch
git pull --ff-only origin $branch
$actualHead = (git rev-parse HEAD).Trim()
Write-Host "== OMEN commit $actualHead"
if ($expectedHead -and $actualHead -ne $expectedHead) {
  throw "OMEN checkout is $actualHead, expected $expectedHead"
}

$cudaRuntimeBin = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin"
if (-not (Test-Path "$cudaRuntimeBin\cublas64_12.dll")) {
  throw "Missing CUDA 12 runtime at $cudaRuntimeBin. Expected cublas64_12.dll for faster-whisper GPU STT."
}

Write-Host "== Verifying AI GPU runtime"
$env:PATH = "$cudaRuntimeBin;$env:PATH"
& "$repo\ai-backend\.venv\Scripts\python.exe" -c "import torch, torchaudio; assert '+cpu' not in torch.__version__.lower(), torch.__version__; assert torch.version.cuda, torch.__version__; assert torch.cuda.is_available(), torch.__version__; print('torch', torch.__version__, 'cuda', torch.version.cuda, 'device', torch.cuda.get_device_name(0)); print('torchaudio', torchaudio.__version__)"

Write-Host "== Writing scheduled task launchers"
$aiLauncher = @"
@echo off
cd /d C:\Users\pmpg\rayme\RayMe
set "PATH=$cudaRuntimeBin;%PATH%"
ai-backend\.venv\Scripts\python.exe ai-backend\scripts\run_https.py --host 192.168.1.199 --port 9443 --cert C:\Users\pmpg\rayme\phase1-tls\rayme.local+1.pem --key C:\Users\pmpg\rayme\phase1-tls\rayme.local+1-key.pem >> C:\Users\pmpg\rayme\logs\ai-backend.run.log 2>>&1
"@
Set-Content -Path "C:\Users\pmpg\rayme\start-ai-backend.cmd" -Value $aiLauncher -Encoding ASCII

Write-Host "== Building web client"
Set-Location "$repo\web-ui\client"
npm run build
Set-Location $repo

Write-Host "== Stopping existing port owners"
$ports = Get-NetTCPConnection -State Listen -LocalPort 8443,9443 -ErrorAction SilentlyContinue
if ($ports) {
  $ports | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize
  $ports.OwningProcess | Sort-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force }
}
Start-Sleep -Seconds 3

Write-Host "== Starting scheduled tasks"
schtasks /Run /TN RayMePhase1AI | Out-Host
Start-Sleep -Seconds 12
schtasks /Run /TN RayMePhase1Web | Out-Host
Start-Sleep -Seconds 8

Write-Host "== Verifying listeners"
Get-NetTCPConnection -State Listen -LocalPort 8443,9443 |
  Select-Object LocalAddress,LocalPort,OwningProcess |
  Format-Table -AutoSize

Write-Host "== Verifying health"
$aiHealth = curl.exe -k -sS https://192.168.1.199:9443/health
$webHealth = curl.exe -k -sS https://192.168.1.199:8443/api/settings
$aiHealth | ConvertFrom-Json | Select-Object service,status,resident_tts_engine | Format-List
$webStatus = ($webHealth | ConvertFrom-Json).ai_backend_status
$webStatus | Select-Object endpoint_status,resident_tts_engine | Format-List
POWERSHELL

echo "OMEN deploy complete: ${local_head}"
