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

ENV_DIR="/home/pmpg/rayme/.venv-cu121"
CUDA_HOME="/usr/local/cuda-12.1"

RAYME_SSH_ALIAS=rayme-pmpg RAYME_SSH_USER=pmpg "$REPO_ROOT/scripts/bootstrap-rayme-ssh.sh" restore >/dev/null

ssh rayme-pmpg "wsl -d Ubuntu --cd /home/pmpg -e bash -s -- /home/pmpg/rayme/.venv-cu121 /usr/local/cuda-12.1" <<'WSL'
set -euo pipefail

env_dir="$1"
cuda_home="$2"
python_bin="/home/pmpg/miniconda3/bin/python"

mkdir -p /home/pmpg/rayme

if [ ! -d "$env_dir" ]; then
  "$python_bin" -m venv "$env_dir"
fi

export CUDA_HOME="$cuda_home"
export PATH="$cuda_home/bin:$env_dir/bin:$PATH"
export LD_LIBRARY_PATH="$cuda_home/lib64:$env_dir/lib/python3.10/site-packages/torch/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export MAX_JOBS="${MAX_JOBS:-4}"

"$env_dir/bin/pip" install --upgrade pip setuptools wheel packaging psutil ninja cmake
"$env_dir/bin/pip" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
"$env_dir/bin/pip" install "deepspeed==0.18.9"
"$env_dir/bin/pip" install --no-build-isolation "flash-attn==2.8.3"

"$env_dir/bin/python" - <<'PY'
import json
import deepspeed
import flash_attn
import torch
import triton

print(
    json.dumps(
        {
            "deepspeed_version": deepspeed.__version__,
            "cuda_available": bool(torch.cuda.is_available()),
            "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
            "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "flash_attn_version": flash_attn.__version__,
            "torch_cuda_version": torch.version.cuda,
            "torch_version": torch.__version__,
            "triton_version": triton.__version__,
        },
        sort_keys=True,
    )
)
PY
WSL
