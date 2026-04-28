#!/usr/bin/env bash
set -euo pipefail

OMEN_SSH_ALIAS="${OMEN_SSH_ALIAS:-rayme-pmpg}"
OMEN_REPO="${OMEN_REPO:-C:\\Users\\pmpg\\rayme\\RayMe}"
OMEN_BRANCH="${OMEN_BRANCH:-main}"

SCRIPT_DIR=$(
  CDPATH= cd -- "$(dirname -- "$0")"
  pwd
)
REPO_ROOT=$(
  CDPATH= cd -- "$SCRIPT_DIR/.."
  pwd
)

local_head="$(git rev-parse HEAD)"

RAYME_SSH_ALIAS="${OMEN_SSH_ALIAS}" RAYME_SSH_USER="${OMEN_SSH_USER:-pmpg}" \
  "$REPO_ROOT/scripts/bootstrap-rayme-ssh.sh" restore >/dev/null

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
git checkout -- .
git clean -fd
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

$webLauncher = @"
@echo off
cd /d C:\Users\pmpg\rayme\RayMe
set "RAYME_WEB_BIND_HOST=192.168.1.199"
set "RAYME_WEB_PORT=8443"
set "RAYME_WEB_PUBLIC_URL=https://192.168.1.199:8443"
set "RAYME_AI_BACKEND_BASE_URL=https://192.168.1.199:9443"
set "RAYME_DATABASE_URL=sqlite+aiosqlite:///C:/Users/pmpg/rayme/RayMe/web-ui/server/data/rayme.sqlite3"
set "RAYME_ALLOWED_ORIGINS=https://192.168.1.199:8443,https://rayme.local:8443"
web-ui\server\.venv\Scripts\python.exe web-ui\server\scripts\run_dev_https.py --host 192.168.1.199 --port 8443 --cert C:\Users\pmpg\rayme\phase1-tls\rayme.local+1.pem --key C:\Users\pmpg\rayme\phase1-tls\rayme.local+1-key.pem >> C:\Users\pmpg\rayme\logs\web-ui.run.log 2>>&1
"@
Set-Content -Path "C:\Users\pmpg\rayme\start-web-ui.cmd" -Value $webLauncher -Encoding ASCII

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

Write-Host "== Asserting canonical scheduled tasks"
schtasks /Delete /TN RayMePhase1AI /F 2>&1 | Out-Null
schtasks /Delete /TN RayMePhase1Web /F 2>&1 | Out-Null
schtasks /Create /TN RayMePhase1AI /TR "C:\Users\pmpg\rayme\start-ai-backend.cmd" /SC ONCE /ST 23:59 /F | Out-Host
schtasks /Create /TN RayMePhase1Web /TR "C:\Users\pmpg\rayme\start-web-ui.cmd" /SC ONCE /ST 23:59 /F | Out-Host

Write-Host "== Starting scheduled tasks"
schtasks /Run /TN RayMePhase1AI | Out-Host

function Wait-RayMeListener {
  param(
    [Parameter(Mandatory = $true)][int]$Port,
    [int]$TimeoutSeconds = 180
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($listener) {
      return $listener
    }
    Start-Sleep -Seconds 2
  } while ((Get-Date) -lt $deadline)

  throw "Timed out waiting for listener on port $Port"
}

Write-Host "== Waiting for AI listener"
Wait-RayMeListener -Port 9443 | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize

schtasks /Run /TN RayMePhase1Web | Out-Host

Write-Host "== Waiting for web listener"
Wait-RayMeListener -Port 8443 | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize

Write-Host "== Verifying listeners"
Get-NetTCPConnection -State Listen -LocalPort 8443,9443 |
  Select-Object LocalAddress,LocalPort,OwningProcess |
  Format-Table -AutoSize

Write-Host "== Verifying health"
$aiHealth = curl.exe -k -sS https://192.168.1.199:9443/health
if ($LASTEXITCODE -ne 0) { throw "AI backend health request failed" }
$webHealth = curl.exe -k -sS https://192.168.1.199:8443/api/settings
if ($LASTEXITCODE -ne 0) { throw "Web UI settings request failed" }
$aiStatus = $aiHealth | ConvertFrom-Json
$aiStatus | Select-Object service,status,stt_ready,vad_ready,resident_tts_engine | Format-List
if (-not $aiStatus.stt_ready -or -not $aiStatus.vad_ready -or $aiStatus.resident_tts_engine -ne "f5") {
  throw "AI backend is not ready for live calls"
}
$webStatus = ($webHealth | ConvertFrom-Json).ai_backend_status
$webStatus | Select-Object endpoint_status,resident_tts_engine | Format-List
if ($webStatus.endpoint_status -match "unreachable" -or $webStatus.resident_tts_engine -ne "f5") {
  throw "Web UI cannot reach the resident F5 AI backend"
}
POWERSHELL

echo "OMEN deploy complete: ${local_head}"
