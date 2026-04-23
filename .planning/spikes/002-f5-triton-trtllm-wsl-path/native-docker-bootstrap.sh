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

ssh rayme-pmpg "wsl -d Ubuntu -u root -e bash -s" <<'WSL'
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io nvidia-container-toolkit

mkdir -p /home/pmpg/rayme/docker-native/data
mkdir -p /home/pmpg/rayme/docker-native/exec
mkdir -p /home/pmpg/rayme/docker-native/log

cat > /home/pmpg/rayme/docker-native/daemon.json <<'JSON'
{
  "data-root": "/home/pmpg/rayme/docker-native/data",
  "exec-root": "/home/pmpg/rayme/docker-native/exec",
  "hosts": ["unix:///home/pmpg/rayme/docker-native/docker.sock"],
  "default-runtime": "nvidia",
  "runtimes": {
    "nvidia": {
      "path": "/usr/bin/nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}
JSON

if ! pgrep -f 'dockerd.*docker-native/docker.sock' >/dev/null 2>&1; then
  nohup /usr/bin/dockerd --config-file /home/pmpg/rayme/docker-native/daemon.json >/home/pmpg/rayme/docker-native/log/dockerd.log 2>&1 &
fi

sleep 5
DOCKER_HOST=unix:///home/pmpg/rayme/docker-native/docker.sock docker info
WSL
