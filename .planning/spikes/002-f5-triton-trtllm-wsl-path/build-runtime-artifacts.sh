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

workspace=/home/pmpg/rayme/f5-triton-runtime
repo=$workspace/F5-TTS
runtime_dir=$repo/src/f5_tts/runtime/triton_trtllm
ckpt_dir=$repo/ckpts/F5TTS_v1_Base

test -d "$runtime_dir"

run_stage() {
  local stage=$1
  docker run --rm \
    --gpus all \
    --shm-size=2g \
    -v /home/pmpg/rayme/f5-triton-runtime:/workspace-host \
    soar97/triton-f5-tts:24.12 \
    bash -lc "cd /workspace-host/F5-TTS/src/f5_tts/runtime/triton_trtllm && $stage"
}

if [ ! -f "$ckpt_dir/model_1250000.safetensors" ] || [ ! -f "$ckpt_dir/vocab.txt" ]; then
  run_stage 'bash run.sh 0 0 F5TTS_v1_Base'
fi

if [ ! -f "$ckpt_dir/trtllm_engine/rank0.engine" ]; then
  run_stage 'bash run.sh 1 1 F5TTS_v1_Base'
fi

if [ ! -f "$repo/ckpts/vocos_vocoder.plan" ]; then
  run_stage 'pip install --quiet vocos >/dev/null && bash run.sh 2 2 F5TTS_v1_Base'
fi

du -sh "$ckpt_dir"
ls -lh "$ckpt_dir/trtllm_engine"
ls -lh "$repo/ckpts/vocos_vocoder.onnx" "$repo/ckpts/vocos_vocoder.plan"
WSL
