param(
  [string]$Repo = "C:\Users\pmpg\rayme\RayMe",
  [string]$BindHost = "192.168.1.199",
  [string]$WebUrl = "https://192.168.1.199:8443",
  [int]$AiPort = 9443,
  [int]$WebPort = 8443,
  [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$script:Children = @()
$script:EventSubscriptions = @()
$script:Stopping = $false
$script:JobHandle = [IntPtr]::Zero
$script:FatalMessage = $null

if ($Host -and $Host.UI -and $Host.UI.RawUI) {
  $Host.UI.RawUI.WindowTitle = "RayMe Console"
}

Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class RayMeJobObject
{
    [StructLayout(LayoutKind.Sequential)]
    public struct JOBOBJECT_BASIC_LIMIT_INFORMATION
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public long Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct IO_COUNTERS
    {
        public ulong ReadOperationCount;
        public ulong WriteOperationCount;
        public ulong OtherOperationCount;
        public ulong ReadTransferCount;
        public ulong WriteTransferCount;
        public ulong OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    {
        public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
        public IO_COUNTERS IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    public const int JobObjectExtendedLimitInformation = 9;
    public const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr CreateJobObject(IntPtr lpJobAttributes, string lpName);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool SetInformationJobObject(
        IntPtr hJob,
        int infoType,
        IntPtr lpJobObjectInfo,
        uint cbJobObjectInfoLength);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool AssignProcessToJobObject(IntPtr hJob, IntPtr hProcess);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool CloseHandle(IntPtr hObject);

    public static IntPtr CreateKillOnCloseJob()
    {
        IntPtr job = CreateJobObject(IntPtr.Zero, null);
        if (job == IntPtr.Zero)
        {
            throw new InvalidOperationException("CreateJobObject failed.");
        }

        JOBOBJECT_EXTENDED_LIMIT_INFORMATION info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

        int length = Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
        IntPtr infoPtr = Marshal.AllocHGlobal(length);
        try
        {
            Marshal.StructureToPtr(info, infoPtr, false);
            if (!SetInformationJobObject(job, JobObjectExtendedLimitInformation, infoPtr, (uint)length))
            {
                throw new InvalidOperationException("SetInformationJobObject failed.");
            }
        }
        finally
        {
            Marshal.FreeHGlobal(infoPtr);
        }

        return job;
    }
}
"@

function Write-RayMe {
  param(
    [string]$Prefix,
    [string]$Message,
    [ConsoleColor]$Color = [ConsoleColor]::Gray,
    [string]$LogPath = $null
  )

  if ([string]::IsNullOrWhiteSpace($Message)) {
    return
  }

  $line = "[$Prefix] $Message"
  Write-Host $line -ForegroundColor $Color
  if ($LogPath) {
    Add-Content -Path $LogPath -Value $line -Encoding UTF8
  }
}

function Quote-ProcessArgument {
  param([string]$Argument)

  if ($null -eq $Argument) {
    return '""'
  }
  if ($Argument -notmatch '[\s"]') {
    return $Argument
  }

  return '"' + ($Argument -replace '"', '\"') + '"'
}

function Stop-RayMeChildren {
  if ($script:Stopping) {
    return
  }
  $script:Stopping = $true

  Write-RayMe "RAYME" "Stopping RayMe processes..." ([ConsoleColor]::Yellow)

  foreach ($subscription in $script:EventSubscriptions) {
    try {
      Unregister-Event -SubscriptionId $subscription.Id -ErrorAction SilentlyContinue
      Remove-Job -Id $subscription.Id -Force -ErrorAction SilentlyContinue
    }
    catch {
    }
  }

  foreach ($child in $script:Children) {
    try {
      if ($child -and -not $child.HasExited) {
        Write-RayMe "RAYME" "Stopping PID $($child.Id)..." ([ConsoleColor]::DarkYellow)
        $child.Kill()
      }
    }
    catch {
    }
  }

  if ($script:JobHandle -ne [IntPtr]::Zero) {
    try {
      [void][RayMeJobObject]::CloseHandle($script:JobHandle)
    }
    catch {
    }
    $script:JobHandle = [IntPtr]::Zero
  }
}

function Stop-PortOwners {
  param([int[]]$Ports)

  foreach ($port in $Ports) {
    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
      $ownerPid = $listener.OwningProcess
      if (-not $ownerPid -or $ownerPid -eq $PID) {
        continue
      }

      try {
        $process = Get-Process -Id $ownerPid -ErrorAction Stop
        Write-RayMe "RAYME" "Port $port is already in use by PID $ownerPid ($($process.ProcessName)); stopping it so this console owns RayMe." ([ConsoleColor]::Yellow)
        Stop-Process -Id $ownerPid -Force -ErrorAction Stop
      }
      catch {
        Write-RayMe "RAYME" "Could not stop PID $ownerPid on port ${port}: $($_.Exception.Message)" ([ConsoleColor]::Red)
      }
    }
  }
}

function Test-PortOpen {
  param(
    [string]$HostName,
    [int]$Port
  )

  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $async = $client.BeginConnect($HostName, $Port, $null, $null)
    if (-not $async.AsyncWaitHandle.WaitOne(1000, $false)) {
      return $false
    }
    $client.EndConnect($async)
    return $true
  }
  catch {
    return $false
  }
  finally {
    $client.Close()
  }
}

function Wait-Port {
  param(
    [string]$Name,
    [string]$HostName,
    [int]$Port,
    [int]$TimeoutSeconds
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  Write-RayMe "RAYME" "Waiting for $Name on https://$HostName`:$Port ..." ([ConsoleColor]::Cyan)

  while ((Get-Date) -lt $deadline) {
    if (Test-PortOpen -HostName $HostName -Port $Port) {
      Write-RayMe "RAYME" "$Name is listening on port $Port." ([ConsoleColor]::Green)
      return
    }
    Start-Sleep -Milliseconds 500
  }

  throw "$Name did not start listening on port $Port within $TimeoutSeconds seconds."
}

function Start-RayMeProcess {
  param(
    [string]$Name,
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$WorkingDirectory,
    [hashtable]$Environment,
    [string]$LogPath,
    [ConsoleColor]$Color
  )

  if (-not (Test-Path $FilePath)) {
    throw "$Name executable not found: $FilePath"
  }

  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $FilePath
  $psi.Arguments = ($Arguments | ForEach-Object { Quote-ProcessArgument $_ }) -join " "
  $psi.WorkingDirectory = $WorkingDirectory
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.CreateNoWindow = $true

  foreach ($key in $Environment.Keys) {
    $psi.EnvironmentVariables[$key] = [string]$Environment[$key]
  }

  $process = New-Object System.Diagnostics.Process
  $process.StartInfo = $psi
  $process.EnableRaisingEvents = $true

  Write-RayMe "RAYME" "Starting $Name..." ([ConsoleColor]::Cyan)
  [void]$process.Start()

  if ($script:JobHandle -ne [IntPtr]::Zero) {
    [void][RayMeJobObject]::AssignProcessToJobObject($script:JobHandle, $process.Handle)
  }

  $outSubscription = Register-ObjectEvent -InputObject $process -EventName OutputDataReceived -MessageData @{
    Name = $Name
    Color = $Color
    LogPath = $LogPath
  } -Action {
    if ($EventArgs.Data) {
      $data = $Event.MessageData
      $line = "[$($data.Name)] $($EventArgs.Data)"
      Write-Host $line -ForegroundColor $data.Color
      Add-Content -Path $data.LogPath -Value $line -Encoding UTF8
    }
  }
  $errSubscription = Register-ObjectEvent -InputObject $process -EventName ErrorDataReceived -MessageData @{
    Name = $Name
    Color = [ConsoleColor]::Red
    LogPath = $LogPath
  } -Action {
    if ($EventArgs.Data) {
      $data = $Event.MessageData
      $line = "[$($data.Name)] $($EventArgs.Data)"
      Write-Host $line -ForegroundColor $data.Color
      Add-Content -Path $data.LogPath -Value $line -Encoding UTF8
    }
  }

  $script:EventSubscriptions += $outSubscription
  $script:EventSubscriptions += $errSubscription
  $script:Children += $process

  $process.BeginOutputReadLine()
  $process.BeginErrorReadLine()

  return $process
}

try {
  $resolvedRepo = (Resolve-Path $Repo).Path
  $logDir = "C:\Users\pmpg\rayme\logs"
  New-Item -ItemType Directory -Path $logDir -Force | Out-Null
  $aiLogPath = Join-Path $logDir "ai-backend.console.log"
  $webLogPath = Join-Path $logDir "web-ui.console.log"

  Set-Content -Path $aiLogPath -Value "[RAYME] AI console log started $(Get-Date -Format o)" -Encoding UTF8
  Set-Content -Path $webLogPath -Value "[RAYME] Web console log started $(Get-Date -Format o)" -Encoding UTF8

  $script:JobHandle = [RayMeJobObject]::CreateKillOnCloseJob()

  Register-EngineEvent PowerShell.Exiting -Action {
    Stop-RayMeChildren
  } | Out-Null

  Write-RayMe "RAYME" "RayMe foreground console starting." ([ConsoleColor]::Green)
  Write-RayMe "RAYME" "Keep this window open while using RayMe. Close it or press Ctrl+C to stop everything." ([ConsoleColor]::Yellow)
  Write-RayMe "RAYME" "Open this URL after startup: $WebUrl" ([ConsoleColor]::White)

  Stop-PortOwners -Ports @($AiPort, $WebPort)

  $certPath = "C:\Users\pmpg\rayme\phase1-tls\rayme.local+1.pem"
  $keyPath = "C:\Users\pmpg\rayme\phase1-tls\rayme.local+1-key.pem"
  $aiPython = Join-Path $resolvedRepo "ai-backend\.venv\Scripts\python.exe"
  $webPython = Join-Path $resolvedRepo "web-ui\server\.venv\Scripts\python.exe"
  $cudaPath = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin"
  $databaseUrl = "sqlite+aiosqlite:///$($resolvedRepo -replace '\\','/')/web-ui/server/data/rayme.sqlite3"

  $aiEnv = @{
    "PYTHONUNBUFFERED" = "1"
    "PATH" = "$cudaPath;$env:PATH"
  }
  $webEnv = @{
    "PYTHONUNBUFFERED" = "1"
    "RAYME_WEB_BIND_HOST" = $BindHost
    "RAYME_WEB_PORT" = [string]$WebPort
    "RAYME_WEB_PUBLIC_URL" = $WebUrl
    "RAYME_AI_BACKEND_BASE_URL" = "https://$BindHost`:$AiPort"
    "RAYME_DATABASE_URL" = $databaseUrl
    "RAYME_ALLOWED_ORIGINS" = "$WebUrl,https://rayme.local:$WebPort"
  }

  $aiProcess = Start-RayMeProcess `
    -Name "AI" `
    -FilePath $aiPython `
    -Arguments @(
      "-u",
      (Join-Path $resolvedRepo "ai-backend\scripts\run_https.py"),
      "--host",
      $BindHost,
      "--port",
      [string]$AiPort,
      "--cert",
      $certPath,
      "--key",
      $keyPath
    ) `
    -WorkingDirectory $resolvedRepo `
    -Environment $aiEnv `
    -LogPath $aiLogPath `
    -Color ([ConsoleColor]::Magenta)

  Wait-Port -Name "AI backend" -HostName $BindHost -Port $AiPort -TimeoutSeconds $TimeoutSeconds

  $webProcess = Start-RayMeProcess `
    -Name "WEB" `
    -FilePath $webPython `
    -Arguments @(
      "-u",
      (Join-Path $resolvedRepo "web-ui\server\scripts\run_dev_https.py"),
      "--host",
      $BindHost,
      "--port",
      [string]$WebPort,
      "--cert",
      $certPath,
      "--key",
      $keyPath
    ) `
    -WorkingDirectory $resolvedRepo `
    -Environment $webEnv `
    -LogPath $webLogPath `
    -Color ([ConsoleColor]::Cyan)

  Wait-Port -Name "Web UI" -HostName $BindHost -Port $WebPort -TimeoutSeconds $TimeoutSeconds

  Write-RayMe "RAYME" "Ready." ([ConsoleColor]::Green)
  Write-RayMe "RAYME" "Open: $WebUrl" ([ConsoleColor]::White)
  Write-RayMe "RAYME" "Logs are streaming below. Close this window to stop RayMe." ([ConsoleColor]::Yellow)

  while ($true) {
    foreach ($child in $script:Children) {
      if ($child.HasExited) {
        throw "$($child.StartInfo.FileName) exited with code $($child.ExitCode)."
      }
    }
    Start-Sleep -Milliseconds 500
  }
}
catch [System.Management.Automation.PipelineStoppedException] {
  Write-RayMe "RAYME" "Stop requested." ([ConsoleColor]::Yellow)
}
catch {
  $script:FatalMessage = $_.Exception.Message
  Write-RayMe "RAYME" "ERROR: $script:FatalMessage" ([ConsoleColor]::Red)
}
finally {
  Stop-RayMeChildren

  if ($script:FatalMessage) {
    Write-RayMe "RAYME" "RayMe stopped because of the error above. Press Enter to close this window." ([ConsoleColor]::Yellow)
    try {
      [void](Read-Host)
    }
    catch {
    }
    exit 1
  }

  Write-RayMe "RAYME" "RayMe stopped." ([ConsoleColor]::Green)
}
