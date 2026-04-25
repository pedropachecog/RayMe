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
