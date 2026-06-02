param(
  [string]$Repo = "C:\Users\pmpg\rayme\RayMe",
  [string]$WebUrl = "https://192.168.1.199:8443",
  [int]$AiPort = 9443,
  [int]$WebPort = 8443,
  [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

function Write-RayMeStep {
  param([Parameter(Mandatory = $true)][string]$Message)
  Write-Host "== $Message"
}

function Test-RayMeListener {
  param([Parameter(Mandatory = $true)][int]$Port)

  $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
  return [bool]$listener
}

function Wait-RayMeListener {
  param(
    [Parameter(Mandatory = $true)][int]$Port,
    [Parameter(Mandatory = $true)][int]$TimeoutSeconds
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    if (Test-RayMeListener -Port $Port) {
      Write-RayMeStep "Port $Port is listening"
      return
    }
    Start-Sleep -Seconds 2
  } while ((Get-Date) -lt $deadline)

  throw "Timed out waiting for RayMe listener on port $Port"
}

function Assert-RayMeScheduledTask {
  param([Parameter(Mandatory = $true)][string]$TaskName)

  $output = & schtasks.exe /Query /TN $TaskName /FO LIST 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "Missing scheduled task '$TaskName'. Run scripts\deploy-omen.sh from the RayMe repo before using this launcher. $output"
  }
}

function Start-RayMeTaskIfNeeded {
  param(
    [Parameter(Mandatory = $true)][string]$TaskName,
    [Parameter(Mandatory = $true)][int]$Port
  )

  if (Test-RayMeListener -Port $Port) {
    Write-RayMeStep "$TaskName is already available on port $Port"
    return
  }

  Write-RayMeStep "Starting $TaskName"
  & schtasks.exe /Run /TN $TaskName | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to start scheduled task '$TaskName'"
  }

  Wait-RayMeListener -Port $Port -TimeoutSeconds $TimeoutSeconds
}

if (-not (Test-Path $Repo)) {
  throw "RayMe checkout not found at $Repo. Run scripts\deploy-omen.sh before using this launcher."
}

Set-Location $Repo

Assert-RayMeScheduledTask -TaskName "RayMePhase1AI"
Assert-RayMeScheduledTask -TaskName "RayMePhase1Web"

Start-RayMeTaskIfNeeded -TaskName "RayMePhase1AI" -Port $AiPort
Start-RayMeTaskIfNeeded -TaskName "RayMePhase1Web" -Port $WebPort

Write-RayMeStep "Opening $WebUrl"
Start-Process $WebUrl
