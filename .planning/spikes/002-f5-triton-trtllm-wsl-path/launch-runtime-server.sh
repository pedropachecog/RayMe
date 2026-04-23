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

RAYME_SSH_ALIAS=rayme-pmpg RAYME_SSH_USER=pmpg "$REPO_ROOT/scripts/bootstrap-rayme-ssh.sh" restore >/dev/null

ssh rayme-pmpg "wsl -d Ubuntu --cd /home/pmpg -e bash -s" <<'WSL'
set -euo pipefail

container_name=f5-triton-safe-18000
model_repo=/home/pmpg/rayme/f5-triton-runtime/model_repo_cpuipc_18000

if docker ps -a --format '{{.Names}}' | grep -Fx "$container_name" >/dev/null 2>&1; then
  docker rm -f f5-triton-safe-18000 >/dev/null
fi

docker run -d \
  --name f5-triton-safe-18000 \
  --gpus all \
  --ipc=host \
  --pid=host \
  --shm-size=2g \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -p 18000:8000 \
  -p 18001:8001 \
  -p 18002:8002 \
  -v /home/pmpg/rayme/f5-triton-runtime:/workspace-host \
  soar97/triton-f5-tts:24.12 \
  bash -lc 'pip install --quiet rjieba >/dev/null && tritonserver --model-repository=/workspace-host/model_repo_cpuipc_18000' >/dev/null

for _ in $(seq 1 120); do
  if curl -sf http://127.0.0.1:18000/v2/health/ready >/dev/null; then
    echo "ready"
    docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
    exit 0
  fi
  sleep 2
done

docker logs --tail 200 f5-triton-safe-18000
exit 1
WSL
