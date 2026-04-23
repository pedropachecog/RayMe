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

mkdir -p /home/pmpg/rayme/docker-config-public
cat > /home/pmpg/rayme/docker-config-public/config.json <<'JSON'
{}
JSON

export DOCKER_HOST=unix:///home/pmpg/rayme/docker-native/docker.sock
export DOCKER_CONFIG=/home/pmpg/rayme/docker-config-public

docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
WSL
