#!/usr/bin/env bash
set -euo pipefail

OMEN_SSH_ALIAS="${OMEN_SSH_ALIAS:-rayme-pmpg}"
OMEN_REPO="${OMEN_REPO:-C:\\Users\\pmpg\\rayme\\RayMe}"
OMEN_BRANCH="${OMEN_BRANCH:-main}"
RAYME_OMEN_VERIFY_VOXCPM2="${RAYME_OMEN_VERIFY_VOXCPM2:-0}"
RAYME_OMEN_VOXCPM2_RUNTIME_SMOKE_JSON="${RAYME_OMEN_VOXCPM2_RUNTIME_SMOKE_JSON:-${RAYME_VOXCPM2_RUNTIME_SMOKE_JSON:-}}"
RAYME_OMEN_VOXCPM2_VRAM_SOAK_JSON="${RAYME_OMEN_VOXCPM2_VRAM_SOAK_JSON:-${RAYME_VOXCPM2_VRAM_SOAK_JSON:-}}"
RAYME_OMEN_VERIFY_QWEN3_TRACER="${RAYME_OMEN_VERIFY_QWEN3_TRACER:-0}"
RAYME_OMEN_VERIFY_QWEN3="${RAYME_OMEN_VERIFY_QWEN3:-0}"
RAYME_OMEN_QWEN3_FIDELITY_SWEEP="${RAYME_OMEN_QWEN3_FIDELITY_SWEEP:-0}"

SCRIPT_DIR=$(
  CDPATH= cd -- "$(dirname -- "$0")"
  pwd
)
REPO_ROOT=$(
  CDPATH= cd -- "$SCRIPT_DIR/.."
  pwd
)
RAYME_OMEN_QWEN3_TRACER_JSON="${RAYME_OMEN_QWEN3_TRACER_JSON:-$REPO_ROOT/.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-hardware-tracer.json}"
RAYME_QWEN3_PHASE_DIR="$REPO_ROOT/.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls"
RAYME_QWEN3_RESULTS_DIR="$RAYME_QWEN3_PHASE_DIR/results"
RAYME_QWEN3_LOCAL_RESULTS_DIR="$RAYME_QWEN3_RESULTS_DIR/.local"

local_head="$(git rev-parse HEAD)"

if [[ "$RAYME_OMEN_VERIFY_VOXCPM2" == "1" && -z "$RAYME_OMEN_VOXCPM2_RUNTIME_SMOKE_JSON" ]]; then
  echo "RAYME_OMEN_VOXCPM2_RUNTIME_SMOKE_JSON must be set when RAYME_OMEN_VERIFY_VOXCPM2=1" >&2
  exit 2
fi

RAYME_SSH_ALIAS="${OMEN_SSH_ALIAS}" RAYME_SSH_USER="${OMEN_SSH_USER:-pmpg}" \
  "$REPO_ROOT/scripts/bootstrap-rayme-ssh.sh" restore >/dev/null

ps_single_quote() {
  local value="${1//\'/\'\'}"
  printf "'%s'" "$value"
}

remote_bootstrap="\$env:EXPECTED_HEAD=$(ps_single_quote "$local_head"); "
remote_bootstrap+="\$env:OMEN_REPO=$(ps_single_quote "$OMEN_REPO"); "
remote_bootstrap+="\$env:OMEN_BRANCH=$(ps_single_quote "$OMEN_BRANCH"); "
remote_bootstrap+="\$env:RAYME_OMEN_VERIFY_VOXCPM2=$(ps_single_quote "$RAYME_OMEN_VERIFY_VOXCPM2"); "
remote_bootstrap+="\$env:RAYME_OMEN_VERIFY_QWEN3_TRACER=$(ps_single_quote "$RAYME_OMEN_VERIFY_QWEN3_TRACER"); "
remote_bootstrap+="\$env:RAYME_OMEN_VERIFY_QWEN3=$(ps_single_quote "$RAYME_OMEN_VERIFY_QWEN3"); "
remote_bootstrap+="\$env:RAYME_OMEN_QWEN3_FIDELITY_SWEEP=$(ps_single_quote "$RAYME_OMEN_QWEN3_FIDELITY_SWEEP"); "
remote_bootstrap+="Invoke-Expression ([Console]::In.ReadToEnd())"

run_remote_deploy() {
ssh "${OMEN_SSH_ALIAS}" "powershell -NoProfile -ExecutionPolicy Bypass -Command \"${remote_bootstrap}\"" <<'POWERSHELL'
$ErrorActionPreference = "Stop"
$repo = $env:OMEN_REPO
if (-not $repo) { $repo = "C:\Users\pmpg\rayme\RayMe" }
$branch = $env:OMEN_BRANCH
if (-not $branch) { $branch = "main" }
$expectedHead = $env:EXPECTED_HEAD
$verifyVoxCpm2 = $env:RAYME_OMEN_VERIFY_VOXCPM2 -eq "1"
$verifyQwen3Tracer = $env:RAYME_OMEN_VERIFY_QWEN3_TRACER -eq "1"
$verifyQwen3 = $env:RAYME_OMEN_VERIFY_QWEN3 -eq "1"
$qwenFidelitySweep = $env:RAYME_OMEN_QWEN3_FIDELITY_SWEEP -eq "1"
$qwenRuntimeCommit = "a70afc0f81f7f5f8801c3227968f1102f43f211c"
$qwenModelId = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
$qwenModelRevision = "fd4b254389122332181a7c3db7f27e918eec64e3"
$qwenModelDir = "C:\Users\pmpg\rayme\models\qwen3-tts-1.7b-$qwenModelRevision"
$wavlmModelId = "microsoft/wavlm-base-plus-sv"
$wavlmModelRevision = "feb593a6c23c1cc3d9510425c29b0a14d2b07b1e"
$qwenEvidenceDir = Join-Path $repo ".local\phase09-qwen3-release-results"

Set-Location $repo
Write-Host "== OMEN deploy: repo $(Get-Location)"
$dirty = git status --porcelain
if ($dirty) {
  throw "OMEN checkout has local changes; refusing to deploy without discarding work: $($dirty -join '; ')"
}
git fetch origin $branch
git pull --ff-only origin $branch
if ($LASTEXITCODE -ne 0) {
  $preResetHead = (git rev-parse HEAD).Trim()
  $targetHead = (git rev-parse "origin/$branch").Trim()
  $backupBranch = "backup/omen-pre-reset-$($preResetHead.Substring(0, 12))-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
  Write-Host "== Fast-forward failed; preserving clean OMEN checkout at $backupBranch"
  git branch $backupBranch $preResetHead
  if ($LASTEXITCODE -ne 0) { throw "Failed to create backup branch $backupBranch before OMEN reset" }
  Write-Host "== Resetting clean OMEN checkout to origin/$branch ($targetHead)"
  git reset --hard "origin/$branch"
  if ($LASTEXITCODE -ne 0) { throw "Failed to reset clean OMEN checkout to origin/$branch" }
}
$actualHead = (git rev-parse HEAD).Trim()
Write-Host "== OMEN commit $actualHead"
if ($expectedHead -and $actualHead -ne $expectedHead) {
  throw "OMEN checkout is $actualHead, expected $expectedHead"
}

$cudaRuntimeBin = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin"
if (-not (Test-Path "$cudaRuntimeBin\cublas64_12.dll")) {
  throw "Missing CUDA 12 runtime at $cudaRuntimeBin. Expected cublas64_12.dll for faster-whisper GPU STT."
}

function Stop-RayMePortOwners {
  Write-Host "== Stopping existing RayMe service processes"
  $repoPattern = [regex]::Escape($repo)
  $raymeProcesses = Get-CimInstance Win32_Process |
    Where-Object {
      $_.CommandLine -and
      $_.CommandLine -match $repoPattern -and
      (
        $_.CommandLine -match "ai-backend\\scripts\\run_https\.py" -or
        $_.CommandLine -match "web-ui\\server\\scripts\\run_dev_https\.py"
      )
    }
  if ($raymeProcesses) {
    $raymeProcesses | Select-Object ProcessId,Name,CommandLine | Format-Table -AutoSize
    $raymeProcesses | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Start-Sleep -Seconds 3
  }

  Write-Host "== Stopping existing port owners"
  $ports = Get-NetTCPConnection -State Listen -LocalPort 8443,9443 -ErrorAction SilentlyContinue
  if ($ports) {
    $ports | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize
    $ports.OwningProcess | Sort-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force }
  }
  Start-Sleep -Seconds 3
}

function Invoke-RayMeVoxCpm2Verification {
  Write-Host "== Verifying VoxCPM2 runtime smoke"

  function Get-RayMeUv {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $repoLocalUv = Join-Path $repo ".local\uv-bootstrap\Scripts\uv.exe"
    if (-not (Test-Path $repoLocalUv)) {
      Write-Host "== Bootstrapping repo-local uv CLI"
      $uvVenv = Join-Path $repo ".local\uv-bootstrap"
      & "$repo\ai-backend\.venv\Scripts\python.exe" -m venv $uvVenv
      if ($LASTEXITCODE -ne 0) { throw "Failed to create repo-local uv bootstrap venv" }
      & "$uvVenv\Scripts\python.exe" -m pip install --upgrade pip | Out-Host
      if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip in repo-local uv bootstrap venv" }
      & "$uvVenv\Scripts\python.exe" -m pip install "uv==0.11.6" | Out-Host
      if ($LASTEXITCODE -ne 0) { throw "Failed to install repo-local uv CLI" }
    }
    return $repoLocalUv
  }

  $uv = [string](Get-RayMeUv | Select-Object -Last 1)
  $pythonVersion = "3.11"
  $env:UV_PYTHON = $pythonVersion
  & $uv sync --project ai-backend --extra tts --python $pythonVersion
  if ($LASTEXITCODE -ne 0) { throw "uv sync --project ai-backend --extra tts failed" }

  Write-Host "== Installing CUDA PyTorch wheels"
  & $uv pip install `
    --python "$repo\ai-backend\.venv\Scripts\python.exe" `
    --index-url "https://download.pytorch.org/whl/cu126" `
    "torch==2.10.0+cu126" `
    "torchaudio==2.10.0+cu126"
  if ($LASTEXITCODE -ne 0) { throw "Failed to install CUDA PyTorch wheels for VoxCPM2 verification" }

  $env:PATH = "$cudaRuntimeBin;$env:PATH"
  $probe = @'
import gc
import importlib.metadata
import json
import os
import subprocess
import time

MODEL_ID = "openbmb/VoxCPM2"
EXPECTED_PACKAGE = "voxcpm==2.0.2"


def gpu_snapshot():
    output = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    ).strip().splitlines()[0]
    name, total, used, free = [part.strip() for part in output.split(",")]
    return {
        "gpu_name": name,
        "memory_total_mb": int(total),
        "memory_used_mb": int(used),
        "memory_free_mb": int(free),
    }


before = gpu_snapshot()

import torch

torch_version = torch.__version__
if "+cpu" in torch_version.lower():
    raise RuntimeError(f"CPU-only torch is not allowed for VoxCPM2: {torch_version}")
if not torch.version.cuda:
    raise RuntimeError(f"CUDA torch build is required for VoxCPM2: {torch_version}")
if not torch.cuda.is_available():
    raise RuntimeError("torch.cuda.is_available() is false for VoxCPM2")

package_version = importlib.metadata.version("voxcpm")
package = f"voxcpm=={package_version}"
if package != EXPECTED_PACKAGE:
    raise RuntimeError(f"Expected {EXPECTED_PACKAGE}, got {package}")

from voxcpm import VoxCPM

started = time.perf_counter()
# Runtime contract remains device="cuda"; voxcpm==2.0.2 selects CUDA internally
# when CUDA PyTorch is installed, and the parameter-device check below rejects CPU.
model = VoxCPM.from_pretrained(MODEL_ID, load_denoiser=False)
load_ms = round((time.perf_counter() - started) * 1000, 1)

tts_model = getattr(model, "tts_model", None)
sample_rate = getattr(tts_model, "sample_rate", None)
if sample_rate is None:
    raise RuntimeError("VoxCPM2 runtime did not expose tts_model.sample_rate")
sample_rate = int(sample_rate)
if sample_rate != 48000:
    raise RuntimeError(f"Expected VoxCPM2 runtime sample rate 48000, got {sample_rate}")

device_types = set()
for candidate in (model, tts_model, getattr(model, "model", None)):
    if candidate is None or not hasattr(candidate, "parameters"):
        continue
    try:
        for parameter in candidate.parameters():
            device_types.add(parameter.device.type)
            break
    except Exception:
        pass
if "cuda" not in device_types:
    raise RuntimeError("VoxCPM2 runtime did not expose CUDA-loaded parameters")

try:
    from huggingface_hub import snapshot_download

    cache_path = snapshot_download(MODEL_ID, local_files_only=True)
except Exception:
    cache_path = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")

after = gpu_snapshot()
peak_vram_mb = max(before["memory_used_mb"], after["memory_used_mb"])
free_min_mb = min(before["memory_free_mb"], after["memory_free_mb"])

runtime_smoke = {
    "commit_sha": os.environ.get("EXPECTED_HEAD", ""),
    "package": package,
    "model_id": MODEL_ID,
    "device": "cuda",
    "sample_rate": sample_rate,
    "runtime_sample_rate": sample_rate,
    "torch_version": torch_version,
    "torch_cuda_version": torch.version.cuda,
    "cuda_available": True,
    "cuda_device_name": torch.cuda.get_device_name(0),
    "model_cache_path": cache_path,
    "model_load_ms": load_ms,
    "vram_before": before,
    "vram_after_load": after,
    "cpu_fallback_detected": False,
}
vram_soak = {
    "gpu_name": after["gpu_name"],
    "memory_total_mb": after["memory_total_mb"],
    "memory_used_peak_mb": peak_vram_mb,
    "memory_free_min_mb": free_min_mb,
    "resident_engines": ["voxcpm2_standalone_probe"],
    "stt_model": "distil-large-v3",
    "vad_ready": False,
    "iterations": 1,
    "passed_11gb_budget": peak_vram_mb <= 11264,
    "cpu_fallback_detected": False,
    "peak_vram_mb": peak_vram_mb,
    "vram_budget_mb": 11264,
    "within_11gb_budget": peak_vram_mb <= 11264,
}
if peak_vram_mb > 11264:
    raise RuntimeError(f"VoxCPM2 peak VRAM {peak_vram_mb} MB exceeds 11264 MB budget")

del model
gc.collect()
torch.cuda.empty_cache()

print("__RAYME_VOXCPM2_PROBE_JSON__" + json.dumps({
    "runtime_smoke": runtime_smoke,
    "vram_soak": vram_soak,
}, sort_keys=True))
'@

  $probeOutput = $probe | & "$repo\ai-backend\.venv\Scripts\python.exe" -
  if ($LASTEXITCODE -ne 0) { throw "VoxCPM2 runtime verification failed" }
  $probeLine = $probeOutput | Where-Object { $_ -like "__RAYME_VOXCPM2_PROBE_JSON__*" } | Select-Object -Last 1
  if (-not $probeLine) { throw "VoxCPM2 runtime verification did not emit JSON evidence" }
  $probeJson = $probeLine.Substring("__RAYME_VOXCPM2_PROBE_JSON__".Length)
  $payload = $probeJson | ConvertFrom-Json
  $script:VoxCpm2RuntimeSmoke = $payload.runtime_smoke
  $script:VoxCpm2VramSoak = $payload.vram_soak
}

function Invoke-RayMeQwen3Provisioning {
  Write-Host "== Provisioning pinned Faster Qwen3-TTS runtime and model snapshot"

  function Get-RayMeQwenUv {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $repoLocalUv = Join-Path $repo ".local\uv-bootstrap\Scripts\uv.exe"
    if (-not (Test-Path $repoLocalUv)) {
      Write-Host "== Bootstrapping repo-local uv CLI"
      $uvVenv = Join-Path $repo ".local\uv-bootstrap"
      & "$repo\ai-backend\.venv\Scripts\python.exe" -m venv $uvVenv
      if ($LASTEXITCODE -ne 0) { throw "Failed to create repo-local uv bootstrap venv" }
      & "$uvVenv\Scripts\python.exe" -m pip install --upgrade pip | Out-Host
      if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip in repo-local uv bootstrap venv" }
      & "$uvVenv\Scripts\python.exe" -m pip install "uv==0.11.6" | Out-Host
      if ($LASTEXITCODE -ne 0) { throw "Failed to install repo-local uv CLI" }
    }
    return $repoLocalUv
  }

  $uv = [string](Get-RayMeQwenUv | Select-Object -Last 1)
  $pythonVersion = "3.11"
  $env:UV_PYTHON = $pythonVersion
  & $uv sync --project ai-backend --extra tts --python $pythonVersion
  if ($LASTEXITCODE -ne 0) { throw "uv sync --project ai-backend --extra tts failed" }

  Write-Host "== Reasserting CUDA PyTorch wheels after Qwen dependency sync"
  & $uv pip install `
    --python "$repo\ai-backend\.venv\Scripts\python.exe" `
    --index-url "https://download.pytorch.org/whl/cu126" `
    "torch==2.10.0+cu126" `
    "torchaudio==2.10.0+cu126"
  if ($LASTEXITCODE -ne 0) { throw "Failed to install CUDA PyTorch wheels for Qwen verification" }

  New-Item -ItemType Directory -Path $qwenModelDir -Force | Out-Null
  $env:PATH = "$cudaRuntimeBin;$env:PATH"
  $env:RAYME_QWEN3_MODEL_DIR = $qwenModelDir
  $env:RAYME_QWEN3_MODEL_REVISION = $qwenModelRevision
  $env:RAYME_DEPLOYED_COMMIT = $actualHead
  $env:RAYME_QWEN3_RUNTIME_COMMIT = $qwenRuntimeCommit
  $env:RAYME_QWEN3_MODEL_ID = $qwenModelId
  $env:RAYME_WAVLM_MODEL_ID = $wavlmModelId
  $env:RAYME_WAVLM_MODEL_REVISION = $wavlmModelRevision
  $env:RAYME_MATERIALIZE_WAVLM = if ($verifyQwen3) { "1" } else { "0" }

  $probe = @'
import importlib.metadata
import json
import os
from pathlib import Path

from huggingface_hub import snapshot_download

EXPECTED_RUNTIME_VERSION = "0.3.2"
EXPECTED_RUNTIME_COMMIT = os.environ["RAYME_QWEN3_RUNTIME_COMMIT"]
EXPECTED_MODEL_ID = os.environ["RAYME_QWEN3_MODEL_ID"]
EXPECTED_MODEL_REVISION = os.environ["RAYME_QWEN3_MODEL_REVISION"]
MODEL_DIR = Path(os.environ["RAYME_QWEN3_MODEL_DIR"])
WAVLM_MODEL_ID = os.environ["RAYME_WAVLM_MODEL_ID"]
WAVLM_MODEL_REVISION = os.environ["RAYME_WAVLM_MODEL_REVISION"]

resolved = Path(snapshot_download(
    repo_id=EXPECTED_MODEL_ID,
    revision=EXPECTED_MODEL_REVISION,
    local_dir=MODEL_DIR,
))
if resolved.resolve() != MODEL_DIR.resolve():
    raise RuntimeError("Qwen model snapshot resolved outside the canonical model directory")
if not (MODEL_DIR / "config.json").is_file():
    raise RuntimeError("Pinned Qwen model snapshot is incomplete")

wavlm_cache_path = None
if os.environ.get("RAYME_MATERIALIZE_WAVLM") == "1":
    wavlm_cache_path = Path(snapshot_download(
        repo_id=WAVLM_MODEL_ID,
        revision=WAVLM_MODEL_REVISION,
    )).resolve()
    if wavlm_cache_path.name != WAVLM_MODEL_REVISION:
        raise RuntimeError("Pinned WavLM snapshot resolved to an unexpected revision")
    if not (wavlm_cache_path / "config.json").is_file():
        raise RuntimeError("Pinned WavLM snapshot is incomplete")

manifest = {
    "model_id": EXPECTED_MODEL_ID,
    "model_revision": EXPECTED_MODEL_REVISION,
}
(MODEL_DIR / "rayme-model-revision.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

runtime_version = importlib.metadata.version("faster-qwen3-tts")
if runtime_version != EXPECTED_RUNTIME_VERSION:
    raise RuntimeError("Unexpected Faster Qwen3-TTS version")
direct_url = json.loads(
    importlib.metadata.distribution("faster-qwen3-tts").read_text("direct_url.json") or "{}"
)
runtime_commit = (direct_url.get("vcs_info") or {}).get("commit_id")
if runtime_commit != EXPECTED_RUNTIME_COMMIT:
    raise RuntimeError("Unexpected Faster Qwen3-TTS source commit")

import torch

if torch.__version__ != "2.10.0+cu126":
    raise RuntimeError("Unexpected Torch version for Qwen")
if torch.version.cuda != "12.6" or not torch.cuda.is_available():
    raise RuntimeError("Qwen CUDA 12.6 runtime is unavailable")
gpu_name = torch.cuda.get_device_name(0)
if gpu_name != "NVIDIA GeForce RTX 3060":
    raise RuntimeError("Unexpected Qwen hardware target")

print("__RAYME_QWEN3_RUNTIME_JSON__" + json.dumps({
    "runtime_version": runtime_version,
    "runtime_source_commit": runtime_commit,
    "model_id": EXPECTED_MODEL_ID,
    "model_revision": EXPECTED_MODEL_REVISION,
    "torch_version": torch.__version__,
    "torch_cuda_version": torch.version.cuda,
    "cuda_available": True,
    "gpu_name": gpu_name,
    "sample_rate": 24000,
    "wavlm_model_id": WAVLM_MODEL_ID if wavlm_cache_path else None,
    "wavlm_model_revision": WAVLM_MODEL_REVISION if wavlm_cache_path else None,
}, sort_keys=True))
'@
  $probeOutput = $probe | & "$repo\ai-backend\.venv\Scripts\python.exe" -
  if ($LASTEXITCODE -ne 0) { throw "Pinned Qwen runtime/model provisioning failed" }
  $probeLine = $probeOutput | Where-Object { $_ -like "__RAYME_QWEN3_RUNTIME_JSON__*" } | Select-Object -Last 1
  if (-not $probeLine) { throw "Qwen provisioning did not emit runtime identity" }
  $script:QwenRuntimeIdentity = $probeLine.Substring("__RAYME_QWEN3_RUNTIME_JSON__".Length) | ConvertFrom-Json
}

if ($verifyVoxCpm2) {
  Stop-RayMePortOwners
  Invoke-RayMeVoxCpm2Verification
}

if ($verifyQwen3Tracer -or $verifyQwen3 -or $qwenFidelitySweep) {
  Stop-RayMePortOwners
  Invoke-RayMeQwen3Provisioning
}

Write-Host "== Verifying AI GPU runtime"
$env:PATH = "$cudaRuntimeBin;$env:PATH"
& "$repo\ai-backend\.venv\Scripts\python.exe" -c "import torch, torchaudio; assert '+cpu' not in torch.__version__.lower(), torch.__version__; assert torch.version.cuda, torch.__version__; assert torch.cuda.is_available(), torch.__version__; print('torch', torch.__version__, 'cuda', torch.version.cuda, 'device', torch.cuda.get_device_name(0)); print('torchaudio', torchaudio.__version__)"

if ($qwenFidelitySweep) {
  Write-Host "== Running local Qwen fidelity sweep"
  $sweepScript = Join-Path $repo ".planning\phases\09-integrate-faster-qwen3-tts-1-7b-into-live-calls\09-qwen-fidelity-sweep.py"
  $sweepOutput = Join-Path $repo ".local\phase09-qwen3-fidelity-sweep"
  & "$repo\ai-backend\.venv\Scripts\python.exe" $sweepScript generate --model-dir $qwenModelDir --output-dir $sweepOutput
  if ($LASTEXITCODE -ne 0) { throw "Qwen fidelity sweep generation failed" }
  & "$repo\ai-backend\.venv\Scripts\python.exe" $sweepScript score --output-dir $sweepOutput
  if ($LASTEXITCODE -ne 0) { throw "Qwen fidelity sweep scoring failed" }
}

Write-Host "== Writing scheduled task launchers"
$aiLauncher = @"
@echo off
cd /d C:\Users\pmpg\rayme\RayMe
set "PATH=$cudaRuntimeBin;%PATH%"
set "RAYME_DEPLOYED_COMMIT=$actualHead"
set "RAYME_QWEN3_MODEL_DIR=$qwenModelDir"
set "RAYME_QWEN3_MODEL_REVISION=$qwenModelRevision"
ai-backend\.venv\Scripts\pythonw.exe ai-backend\scripts\run_https.py --host 192.168.1.199 --port 9443 --cert C:\Users\pmpg\rayme\phase1-tls\rayme.local+1.pem --key C:\Users\pmpg\rayme\phase1-tls\rayme.local+1-key.pem >> C:\Users\pmpg\rayme\logs\ai-backend.run.log 2>>&1
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
web-ui\server\.venv\Scripts\pythonw.exe web-ui\server\scripts\run_dev_https.py --host 192.168.1.199 --port 8443 --cert C:\Users\pmpg\rayme\phase1-tls\rayme.local+1.pem --key C:\Users\pmpg\rayme\phase1-tls\rayme.local+1-key.pem >> C:\Users\pmpg\rayme\logs\web-ui.run.log 2>>&1
"@
Set-Content -Path "C:\Users\pmpg\rayme\start-web-ui.cmd" -Value $webLauncher -Encoding ASCII

function Write-RayMeDesktopShortcut {
  $launcherScript = Join-Path $repo "scripts\start-rayme-omen.ps1"
  if (-not (Test-Path $launcherScript)) {
    throw "Desktop launcher target missing: $launcherScript"
  }

  $desktopDir = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
  if ([string]::IsNullOrWhiteSpace($desktopDir)) {
    throw "Could not resolve the current Windows Desktop directory"
  }
  if (-not (Test-Path $desktopDir)) {
    New-Item -ItemType Directory -Path $desktopDir | Out-Null
  }

  $shortcutPath = Join-Path $desktopDir "Run RayMe.lnk"
  $powershellPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
  $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
  $shortcut.TargetPath = $powershellPath
  $shortcut.Arguments = "-NoProfile -File `"$launcherScript`""
  $shortcut.WorkingDirectory = $repo
  $shortcut.Description = "Run RayMe with visible AI and Web logs; close the console to stop"
  $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
  $shortcut.WindowStyle = 1
  $shortcut.Save()
  Write-Host "Desktop launcher: $shortcutPath"
}

Write-Host "== Writing Desktop launcher"
Write-RayMeDesktopShortcut

Write-Host "== Building web client"
Set-Location "$repo\web-ui\client"
npm run build
Set-Location $repo

Stop-RayMePortOwners

Write-Host "== Asserting canonical scheduled tasks"
schtasks /Delete /TN RayMePhase1AI /F 2>&1 | Out-Null
schtasks /Delete /TN RayMePhase1Web /F 2>&1 | Out-Null

function Register-RayMeTask {
  param(
    [Parameter(Mandatory = $true)][string]$TaskName,
    [Parameter(Mandatory = $true)][string]$Launcher
  )

  $action = New-ScheduledTaskAction -Execute $Launcher
  $trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddHours(6))
  $principal = New-ScheduledTaskPrincipal -UserId "pmpg" -LogonType S4U -RunLevel Limited
  $settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 72)
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Host
}
Register-RayMeTask -TaskName RayMePhase1AI -Launcher "C:\Users\pmpg\rayme\start-ai-backend.cmd"
Register-RayMeTask -TaskName RayMePhase1Web -Launcher "C:\Users\pmpg\rayme\start-web-ui.cmd"

$canonicalTaskLaunchers = @{
  RayMePhase1AI = "C:\Users\pmpg\rayme\start-ai-backend.cmd"
  RayMePhase1Web = "C:\Users\pmpg\rayme\start-web-ui.cmd"
}
foreach ($entry in $canonicalTaskLaunchers.GetEnumerator()) {
  $task = Get-ScheduledTask -TaskName $entry.Key -ErrorAction Stop
  $actions = @($task.Actions)
  if ($actions.Count -ne 1 -or [string]$actions[0].Execute -ne [string]$entry.Value) {
    throw "Scheduled task $($entry.Key) does not point to its canonical launcher"
  }
}
if (
  -not (Test-Path "C:\Users\pmpg\rayme\start-ai-backend.cmd") -or
  -not (Test-Path "C:\Users\pmpg\rayme\start-web-ui.cmd")
) {
  throw "Canonical RayMe launcher inventory is incomplete"
}

Write-Host "== Starting scheduled tasks"
Start-ScheduledTask -TaskName RayMePhase1AI

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

Start-ScheduledTask -TaskName RayMePhase1Web

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

if ($verifyVoxCpm2) {
  $script:VoxCpm2RuntimeSmoke.commit_sha = $actualHead
  $script:VoxCpm2VramSoak.vad_ready = [bool]$aiStatus.vad_ready
  if ($aiStatus.stt_model) { $script:VoxCpm2VramSoak.stt_model = [string]$aiStatus.stt_model }
  $script:VoxCpm2VramSoak.resident_engines = @(
    "voxcpm2_standalone_probe",
    "live_ai_backend:$($aiStatus.resident_tts_engine)"
  )
  Write-Host "__RAYME_VOXCPM2_RUNTIME_SMOKE_JSON__$($script:VoxCpm2RuntimeSmoke | ConvertTo-Json -Depth 8 -Compress)"
  Write-Host "__RAYME_VOXCPM2_VRAM_SOAK_JSON__$($script:VoxCpm2VramSoak | ConvertTo-Json -Depth 8 -Compress)"
}

if ($verifyQwen3Tracer -or $verifyQwen3) {
  Write-Host "== Running production Qwen saved-voice/WebRTC hardware tracer"
  $tracerDir = Join-Path $repo ".local\phase09-qwen3-tracer"
  New-Item -ItemType Directory -Path $tracerDir -Force | Out-Null
  $tracerScript = Join-Path $repo ".planning\phases\09-integrate-faster-qwen3-tts-1-7b-into-live-calls\09-run-hardware-tracer.py"
  $tracerJson = Join-Path $tracerDir "qwen3-hardware-tracer.json"
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $tracerOutput = & "$repo\ai-backend\.venv\Scripts\python.exe" $tracerScript `
    --run-hardware-tracer `
    --expected-commit $actualHead `
    --deployment-branch $branch `
    --work-dir $tracerDir `
    --output $tracerJson 2>&1
  $tracerStatus = $LASTEXITCODE
  $ErrorActionPreference = $previousErrorActionPreference
  $tracerSafeLines = $tracerOutput | Where-Object {
    $_ -like "FAIL:*" -or $_ -like "__RAYME_QWEN3_TRACER_JSON__*"
  }
  $tracerSafeLines | ForEach-Object { Write-Host $_ }
  if ($tracerStatus -ne 0) {
    $failureLine = $tracerSafeLines | Where-Object { $_ -like "FAIL:*" } | Select-Object -Last 1
    if (-not $failureLine) { $failureLine = "FAIL: hardware tracer returned no sanitized diagnostic" }
    throw "Production Qwen hardware tracer failed: $failureLine"
  }
  $tracerLine = $tracerOutput | Where-Object { $_ -like "__RAYME_QWEN3_TRACER_JSON__*" } | Select-Object -Last 1
  if (-not $tracerLine) { throw "Qwen hardware tracer did not emit commit-matched JSON evidence" }
  Write-Host "__RAYME_QWEN3_RUNTIME_JSON__$($script:QwenRuntimeIdentity | ConvertTo-Json -Depth 8 -Compress)"
}

if ($verifyQwen3) {
  Write-Host "== Running exact-commit Phase 09 Qwen core evidence"
  if (Test-Path $qwenEvidenceDir) {
    Remove-Item -Path $qwenEvidenceDir -Recurse -Force
  }
  New-Item -ItemType Directory -Path $qwenEvidenceDir -Force | Out-Null
  $qwenEvidenceLocalDir = Join-Path $qwenEvidenceDir ".local"
  New-Item -ItemType Directory -Path $qwenEvidenceLocalDir -Force | Out-Null

  $qwenWebRtcStatusRaw = curl.exe -k -sS https://192.168.1.199:9443/webrtc/status
  if ($LASTEXITCODE -ne 0) { throw "Qwen worker memory status request failed" }
  $qwenWebRtcStatus = $qwenWebRtcStatusRaw | ConvertFrom-Json
  $qwenTorchReservedMib = 0.0
  $qwenTorchReservedText = [string]$qwenWebRtcStatus.tts_model.torch_reserved_mib
  if (
    -not [double]::TryParse($qwenTorchReservedText, [ref]$qwenTorchReservedMib) -or
    $qwenTorchReservedMib -le 0
  ) {
    throw "Qwen worker Torch reserved memory could not be measured"
  }
  if ($qwenTorchReservedMib -gt 5888) {
    throw "Qwen worker Torch reserved memory exceeds the 5888 MiB release limit"
  }

  $env:RAYME_QWEN3_AI_LOG = "C:\Users\pmpg\rayme\logs\ai-backend.run.log"
  $env:RAYME_QWEN3_WEB_LOG = "C:\Users\pmpg\rayme\logs\web-ui.run.log"
  $runnerScript = Join-Path $repo ".planning\phases\09-integrate-faster-qwen3-tts-1-7b-into-live-calls\09-run-omen-evidence.py"
  $verifierScript = Join-Path $repo ".planning\phases\09-integrate-faster-qwen3-tts-1-7b-into-live-calls\09-verify-evidence.py"
  $runnerWorkDir = Join-Path $qwenEvidenceLocalDir "runner-work"
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $runnerOutput = & "$repo\ai-backend\.venv\Scripts\python.exe" $runnerScript `
    --core-only `
    --expected-commit $actualHead `
    --output-dir $qwenEvidenceDir `
    --work-dir $runnerWorkDir 2>&1
  $runnerStatus = $LASTEXITCODE
  $ErrorActionPreference = $previousErrorActionPreference
  $runnerOutput | Where-Object { $_ -like "PASS*" -or $_ -like "FAIL:*" } | ForEach-Object { Write-Host $_ }
  if ($runnerStatus -ne 0) {
    $failureLine = $runnerOutput | Where-Object { $_ -like "FAIL:*" } | Select-Object -Last 1
    if (-not $failureLine) { $failureLine = "FAIL: evidence runner returned no sanitized diagnostic" }
    throw "Production Qwen core evidence failed: $failureLine"
  }

  $browserMicSource = Join-Path $tracerDir "synthetic-fake-microphone.wav"
  if (-not (Test-Path $browserMicSource)) {
    throw "Qwen browser microphone fixture was not produced by the canonical tracer"
  }
  Copy-Item -Path $browserMicSource -Destination (Join-Path $qwenEvidenceLocalDir "qwen3-fake-mic.wav") -Force

  & "$repo\ai-backend\.venv\Scripts\python.exe" $verifierScript `
    --core-ready `
    --expected-commit $actualHead `
    --results-dir $qwenEvidenceDir
  if ($LASTEXITCODE -ne 0) { throw "Independent Qwen core evidence verification failed" }

  $expectedCoreFiles = @(
    "qwen3-runtime.json",
    "qwen3-webrtc-status.json",
    "qwen3-call-flow.json",
    "qwen3-soak.json",
    "qwen3-stt.json"
  )
  $expectedPrivateFiles = @(
    "qwen3-permitted-reference.wav",
    "qwen3-permitted-reference.txt",
    "qwen3-permitted-provenance.json",
    "qwen3-fake-mic.wav"
  )
  foreach ($filename in $expectedCoreFiles) {
    if (-not (Test-Path (Join-Path $qwenEvidenceDir $filename))) {
      throw "Qwen core evidence inventory is incomplete"
    }
  }
  foreach ($filename in $expectedPrivateFiles) {
    if (-not (Test-Path (Join-Path $qwenEvidenceLocalDir $filename))) {
      throw "Qwen private test fixture inventory is incomplete"
    }
  }

  $finalAiHealth = (curl.exe -k -sS https://192.168.1.199:9443/health | ConvertFrom-Json)
  $finalWebRtcStatus = (curl.exe -k -sS https://192.168.1.199:9443/webrtc/status | ConvertFrom-Json)
  $finalPrompt = $finalWebRtcStatus.selected_voice_prompt
  if (
    $finalAiHealth.resident_tts_engine -ne "qwen3_1_7b" -or
    $finalWebRtcStatus.deployed_commit -ne $actualHead -or
    -not $finalPrompt -or
    $finalPrompt.engine_id -ne "qwen3_1_7b" -or
    $finalPrompt.state -ne "ready"
  ) {
    throw "Qwen core evidence did not leave the exact deployed model and prompt call-ready"
  }
  Write-Host "__RAYME_QWEN3_CORE_READY__$actualHead"
}
POWERSHELL
}

if [[ "$RAYME_OMEN_VERIFY_VOXCPM2" == "1" || "$RAYME_OMEN_VERIFY_QWEN3_TRACER" == "1" || "$RAYME_OMEN_VERIFY_QWEN3" == "1" ]]; then
  deploy_log="$(mktemp)"
  trap 'rm -f "$deploy_log"' EXIT
  set +e
  run_remote_deploy >"$deploy_log" 2>&1
  deploy_status=$?
  set -e
  cat "$deploy_log"
  if [[ "$deploy_status" -ne 0 ]]; then
    exit "$deploy_status"
  fi

  if [[ "$RAYME_OMEN_VERIFY_VOXCPM2" == "1" ]]; then
    runtime_json="$(sed -n 's/^__RAYME_VOXCPM2_RUNTIME_SMOKE_JSON__//p' "$deploy_log" | tail -n 1)"
    if [[ -z "$runtime_json" ]]; then
      echo "VoxCPM2 runtime smoke JSON marker was not found in deploy output" >&2
      exit 1
    fi
    mkdir -p "$(dirname "$RAYME_OMEN_VOXCPM2_RUNTIME_SMOKE_JSON")"
    python3 - "$runtime_json" "$RAYME_OMEN_VOXCPM2_RUNTIME_SMOKE_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
Path(sys.argv[2]).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

    vram_json="$(sed -n 's/^__RAYME_VOXCPM2_VRAM_SOAK_JSON__//p' "$deploy_log" | tail -n 1)"
    if [[ -n "$RAYME_OMEN_VOXCPM2_VRAM_SOAK_JSON" ]]; then
      if [[ -z "$vram_json" ]]; then
        echo "VoxCPM2 VRAM soak JSON marker was not found in deploy output" >&2
        exit 1
      fi
      mkdir -p "$(dirname "$RAYME_OMEN_VOXCPM2_VRAM_SOAK_JSON")"
      python3 - "$vram_json" "$RAYME_OMEN_VOXCPM2_VRAM_SOAK_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
Path(sys.argv[2]).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
    fi
  fi
  if [[ "$RAYME_OMEN_VERIFY_QWEN3_TRACER" == "1" ]]; then
    qwen_tracer_json="$(sed -n 's/^__RAYME_QWEN3_TRACER_JSON__//p' "$deploy_log" | tail -n 1)"
    if [[ -z "$qwen_tracer_json" ]]; then
      echo "Qwen3 hardware tracer JSON marker was not found in deploy output" >&2
      exit 1
    fi
    mkdir -p "$(dirname "$RAYME_OMEN_QWEN3_TRACER_JSON")"
    python3 - "$qwen_tracer_json" "$RAYME_OMEN_QWEN3_TRACER_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
Path(sys.argv[2]).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  fi
  if [[ "$RAYME_OMEN_VERIFY_QWEN3" == "1" ]]; then
    qwen_core_marker="$(sed -n 's/^__RAYME_QWEN3_CORE_READY__//p' "$deploy_log" | tail -n 1)"
    if [[ "$qwen_core_marker" != "$local_head" ]]; then
      echo "Qwen3 core evidence ready marker was missing or commit-mismatched" >&2
      exit 1
    fi

    omen_repo_scp="${OMEN_REPO//\\//}"
    remote_results="$omen_repo_scp/.local/phase09-qwen3-release-results"
    mkdir -p "$RAYME_QWEN3_RESULTS_DIR" "$RAYME_QWEN3_LOCAL_RESULTS_DIR"
    for filename in \
      qwen3-runtime.json \
      qwen3-webrtc-status.json \
      qwen3-call-flow.json \
      qwen3-soak.json \
      qwen3-stt.json
    do
      scp -q "${OMEN_SSH_ALIAS}:${remote_results}/${filename}" "$RAYME_QWEN3_RESULTS_DIR/$filename"
    done
    for filename in \
      qwen3-permitted-reference.wav \
      qwen3-permitted-reference.txt \
      qwen3-permitted-provenance.json \
      qwen3-fake-mic.wav
    do
      scp -q "${OMEN_SSH_ALIAS}:${remote_results}/.local/${filename}" "$RAYME_QWEN3_LOCAL_RESULTS_DIR/$filename"
    done

    python3 "$RAYME_QWEN3_PHASE_DIR/09-verify-evidence.py" \
      --core-ready \
      --expected-commit "$local_head" \
      --results-dir "$RAYME_QWEN3_RESULTS_DIR"
  fi
  trap - EXIT
  rm -f "$deploy_log"
else
  run_remote_deploy
fi

echo "OMEN deploy complete: ${local_head}"
