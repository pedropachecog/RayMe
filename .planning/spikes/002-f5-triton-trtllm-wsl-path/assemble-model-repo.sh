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
template=$repo/src/f5_tts/runtime/triton_trtllm/model_repo_f5_tts
model_repo=$workspace/model_repo_cpuipc_18000
ckpt_dir=$repo/ckpts/F5TTS_v1_Base
vocoder_plan=$repo/ckpts/vocos_vocoder.plan

test -f "$ckpt_dir/model_1250000.safetensors"
test -f "$ckpt_dir/vocab.txt"
test -f "$ckpt_dir/trtllm_engine/rank0.engine"
test -f "$vocoder_plan"

mkdir -p "$model_repo"
cp -a "$template/." "$model_repo/"
mkdir -p "$model_repo/vocoder/1"
install -m 0644 "$vocoder_plan" "$model_repo/vocoder/1/vocoder.plan"

sed -i \
  -e 's|${vocab}|/workspace-host/F5-TTS/ckpts/F5TTS_v1_Base/vocab.txt|' \
  -e 's|${model}|/workspace-host/F5-TTS/ckpts/F5TTS_v1_Base/model_1250000.safetensors|' \
  -e 's|${trtllm}|/workspace-host/F5-TTS/ckpts/F5TTS_v1_Base/trtllm_engine|' \
  -e 's|${vocoder}|vocos|' \
  "$model_repo/f5_tts/config.pbtxt"

perl -0pi -e 's|inference_request = pb_utils.InferenceRequest\(\n            model_name="vocoder", requested_output_names=\["waveform"\], inputs=\[input_tensor_0\]\n        \)|inference_request = pb_utils.InferenceRequest(\n            model_name="vocoder",\n            requested_output_names=["waveform"],\n            inputs=[input_tensor_0],\n            preferred_memory=pb_utils.PreferredMemory(\n                pb_utils.TRITONSERVER_MEMORY_CPU,\n                0,\n            ),\n        )|' \
  "$model_repo/f5_tts/1/model.py"

grep -n "preferred_memory" "$model_repo/f5_tts/1/model.py"
sed -n '1,120p' "$model_repo/f5_tts/config.pbtxt"
printf 'model_repo=%s\n' "$model_repo"
WSL
