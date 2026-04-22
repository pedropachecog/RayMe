#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(
  CDPATH= cd -- "$(dirname -- "$0")"
  pwd
)
REPO_ROOT=$(
  CDPATH= cd -- "$SCRIPT_DIR/../../.."
  pwd
)

WORK_ROOT="/home/pmpg/rayme"

RAYME_SSH_ALIAS=rayme-pmpg RAYME_SSH_USER=pmpg "$REPO_ROOT/scripts/bootstrap-rayme-ssh.sh" restore >/dev/null

ssh rayme-pmpg "wsl -d Ubuntu --cd /home/pmpg -e bash -s -- /home/pmpg/rayme" <<'WSL'
set -euo pipefail

work_root="$1"

mkdir -p "$work_root"

echo "linux_user:$(whoami)"
echo "linux_pwd:$(pwd)"
echo "linux_work_root:$(readlink -f "$work_root")"
ls -ld "$work_root"
grep '^PRETTY_NAME=' /etc/os-release || true

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
elif [ -x /usr/lib/wsl/lib/nvidia-smi ]; then
  /usr/lib/wsl/lib/nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
else
  echo "nvidia_smi:missing"
fi

if command -v python3 >/dev/null 2>&1; then
  python3 --version
  python3 - <<'PY'
import json
import sys

out = {"python_executable": sys.executable}

try:
    import torch

    out["torch_installed"] = True
    out["torch_version"] = torch.__version__
    out["torch_cuda_available"] = bool(torch.cuda.is_available())
    out["torch_cuda_version"] = getattr(torch.version, "cuda", None)
    if torch.cuda.is_available():
        out["torch_device_count"] = torch.cuda.device_count()
        out["torch_device_name"] = torch.cuda.get_device_name(0)
except Exception as exc:
    out["torch_installed"] = False
    out["torch_error"] = str(exc)

print(json.dumps(out, sort_keys=True))
PY
else
  echo "python3:missing"
fi

uname -r

if command -v git >/dev/null 2>&1; then
  git --version
else
  echo "git:missing"
fi

if command -v pip3 >/dev/null 2>&1; then
  pip3 --version
else
  echo "pip3:missing"
fi

if command -v gcc >/dev/null 2>&1; then
  gcc --version | head -n 1
else
  echo "gcc:missing"
fi

if command -v g++ >/dev/null 2>&1; then
  g++ --version | head -n 1
else
  echo "g++:missing"
fi

if command -v cmake >/dev/null 2>&1; then
  cmake --version | head -n 1
else
  echo "cmake:missing"
fi

if command -v ninja >/dev/null 2>&1; then
  ninja --version
else
  echo "ninja:missing"
fi

if [ -e /usr/lib/wsl/lib/libcuda.so ]; then
  echo "libcuda:present"
else
  echo "libcuda:missing"
fi
WSL
