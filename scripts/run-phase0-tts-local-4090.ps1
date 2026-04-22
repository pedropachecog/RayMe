param(
    [switch]$ForceInstall,
    [double]$F5Speed = 1.5,
    [string]$PythonSelector = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter()]
        [string[]]$ArgumentList = @()
    )

    Write-Host ">> $FilePath $($ArgumentList -join ' ')"
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($ArgumentList -join ' ')"
    }
}

function Copy-IfExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    if (Test-Path $Source) {
        Copy-Item -Force $Source $Destination
    }
}

function Clear-StagedSamples {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SampleDir
    )

    foreach ($name in @("f5.wav", "xtts.wav", "qwen3.wav")) {
        $path = Join-Path $SampleDir $name
        if (Test-Path $path) {
            Remove-Item -Force $path
        }
    }
}

function Resolve-PythonLauncher {
    param(
        [Parameter()]
        [string]$PreferredSelector = ""
    )

    $candidates = @()
    if ($PreferredSelector) {
        if ($PreferredSelector -eq "python") {
            $candidates += @{
                File = "python"
                Args = @()
                Label = "python"
            }
        } else {
            $candidates += @{
                File = "py"
                Args = @("-$PreferredSelector")
                Label = "py -$PreferredSelector"
            }
            $candidates += @{
                File = "python"
                Args = @()
                Label = "python"
            }
        }
    } else {
        $candidates += @(
            @{
                File = "py"
                Args = @("-3.11")
                Label = "py -3.11"
            },
            @{
                File = "py"
                Args = @("-3.12")
                Label = "py -3.12"
            },
            @{
                File = "py"
                Args = @("-3.13")
                Label = "py -3.13"
            },
            @{
                File = "python"
                Args = @()
                Label = "python"
            }
        )
    }

    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.File -ErrorAction SilentlyContinue)) {
            continue
        }

        try {
            $version = & $candidate.File @($candidate.Args + @("-c", "import sys; print(sys.version)"))
            if ($LASTEXITCODE -eq 0) {
                return @{
                    File = $candidate.File
                    Args = $candidate.Args
                    Label = $candidate.Label
                    Version = ($version | Select-Object -First 1)
                }
            }
        } catch {
        }
    }

    throw "No usable Python launcher found. Install Python 3.11+ or pass -PythonSelector explicitly."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$phaseDir = Join-Path $repoRoot ".planning\phases\00-measurement-gate"
$probeDir = Join-Path $phaseDir "probes"
$fixtureDir = Join-Path $probeDir "fixtures"
$sampleStageDir = Join-Path $fixtureDir "tts_samples"
$venvDir = Join-Path $phaseDir ".venv-phase0"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"
$resultsDir = Join-Path $phaseDir "results\local_4090"
$samplesDir = Join-Path $resultsDir "samples"

$shortRefAudio = Join-Path $fixtureDir "short_ref_audio.wav"
$shortRefText = Join-Path $fixtureDir "short_ref_transcript.txt"
$targetText1Min = Join-Path $fixtureDir "target_text_1min.txt"
$ttsProbe = Join-Path $probeDir "tts_ttfa.py"
$productionProbe = Join-Path $probeDir "f5_production_chunking.py"
$requirementsFile = Join-Path $phaseDir "requirements-phase0.txt"

New-Item -ItemType Directory -Force $resultsDir | Out-Null
New-Item -ItemType Directory -Force $samplesDir | Out-Null
New-Item -ItemType Directory -Force $sampleStageDir | Out-Null

Write-Host "== Host GPU =="
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    Invoke-Checked -FilePath "nvidia-smi" -ArgumentList @("--query-gpu=name,memory.total,driver_version", "--format=csv,noheader")
} else {
    throw "nvidia-smi not found on host PATH."
}

$needsInstall = $ForceInstall -or -not (Test-Path $pythonExe)
if (-not $needsInstall) {
    try {
        Invoke-Checked -FilePath $pythonExe -ArgumentList @("-c", "import torch, faster_whisper, TTS, qwen_tts, jiwer, soundfile, librosa, pynvml, httpx; print('phase0 imports ok')")
    } catch {
        $needsInstall = $true
    }
}

if ($needsInstall) {
    $launcher = Resolve-PythonLauncher -PreferredSelector $PythonSelector
    Write-Host "== Python launcher =="
    Write-Host "Using $($launcher.Label): $($launcher.Version)"

    if (-not (Test-Path $venvDir)) {
        Invoke-Checked -FilePath $launcher.File -ArgumentList @($launcher.Args + @("-m", "venv", $venvDir))
    }

    Invoke-Checked -FilePath $pythonExe -ArgumentList @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")
    Invoke-Checked -FilePath $pythonExe -ArgumentList @("-m", "pip", "install", "torch==2.5.1", "torchvision==0.20.1", "torchaudio==2.5.1", "--index-url", "https://download.pytorch.org/whl/cu118")
    Invoke-Checked -FilePath $pythonExe -ArgumentList @("-m", "pip", "install", "-r", $requirementsFile)
    Invoke-Checked -FilePath $pythonExe -ArgumentList @("-c", "import torch, faster_whisper, TTS, qwen_tts, jiwer, soundfile, librosa, pynvml, httpx; print(torch.__version__, torch.cuda.is_available(), torch.version.cuda)")
}

Write-Host "== Short benchmark =="
Clear-StagedSamples -SampleDir $sampleStageDir
$shortJson = Join-Path $resultsDir "tts_ttfa.json"
Invoke-Checked -FilePath $pythonExe -ArgumentList @(
    $ttsProbe,
    "--ref-audio", $shortRefAudio,
    "--ref-text", $shortRefText,
    "--output", $shortJson
)
Copy-IfExists -Source (Join-Path $sampleStageDir "f5.wav") -Destination (Join-Path $samplesDir "f5_short.wav")
Copy-IfExists -Source (Join-Path $sampleStageDir "xtts.wav") -Destination (Join-Path $samplesDir "xtts_short.wav")
Copy-IfExists -Source (Join-Path $sampleStageDir "qwen3.wav") -Destination (Join-Path $samplesDir "qwen3_short.wav")

Write-Host "== Long benchmark =="
Clear-StagedSamples -SampleDir $sampleStageDir
$longJson = Join-Path $resultsDir "tts_ttfa_1min.json"
Invoke-Checked -FilePath $pythonExe -ArgumentList @(
    $ttsProbe,
    "--ref-audio", $shortRefAudio,
    "--ref-text", $shortRefText,
    "--target-text-file", $targetText1Min,
    "--output", $longJson
)
Copy-IfExists -Source (Join-Path $sampleStageDir "f5.wav") -Destination (Join-Path $samplesDir "f5_1min_baseline.wav")
Copy-IfExists -Source (Join-Path $sampleStageDir "xtts.wav") -Destination (Join-Path $samplesDir "xtts_1min.wav")
Copy-IfExists -Source (Join-Path $sampleStageDir "qwen3.wav") -Destination (Join-Path $samplesDir "qwen3_1min.wav")

Write-Host "== Production-style F5 =="
$productionJson = Join-Path $resultsDir "f5_production_chunked_speed15.json"
Invoke-Checked -FilePath $pythonExe -ArgumentList @(
    $productionProbe,
    "--ref-audio", $shortRefAudio,
    "--ref-text", $shortRefText,
    "--target-text-file", $targetText1Min,
    "--speed", $F5Speed.ToString([System.Globalization.CultureInfo]::InvariantCulture),
    "--output", $productionJson,
    "--combined-out", (Join-Path $samplesDir "f5_production_chunked_speed15.wav"),
    "--ack-out", (Join-Path $samplesDir "f5_ack_speed15.wav"),
    "--remainder-out", (Join-Path $samplesDir "f5_remainder_chunked_speed15.wav")
)

Write-Host ""
Write-Host "Local 4090 artifacts:"
Write-Host "  $resultsDir"
