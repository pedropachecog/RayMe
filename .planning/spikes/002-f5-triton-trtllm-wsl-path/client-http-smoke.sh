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

docker run --rm \
  -v /home/pmpg/rayme/f5-triton-runtime:/workspace-host \
  soar97/triton-f5-tts:24.12 \
  bash -lc 'python3 - <<'"'"'PY'"'"'
import json
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

wav_path = Path("/workspace-host/F5-TTS/src/f5_tts/infer/examples/basic/basic_ref_en.wav")
out_path = Path("/workspace-host/client_http_out.wav")

waveform, sample_rate = sf.read(wav_path)
assert sample_rate == 24000
waveform = np.asarray(waveform, dtype=np.float32)
lengths = np.array([[len(waveform)]], dtype=np.int32)

payload = {
    "inputs": [
        {
            "name": "reference_wav",
            "shape": [1, len(waveform)],
            "datatype": "FP32",
            "data": waveform.reshape(1, -1).tolist(),
        },
        {
            "name": "reference_wav_len",
            "shape": [1, 1],
            "datatype": "INT32",
            "data": lengths.tolist(),
        },
        {
            "name": "reference_text",
            "shape": [1, 1],
            "datatype": "BYTES",
            "data": [["Some call me nature, others call me mother nature."]],
        },
        {
            "name": "target_text",
            "shape": [1, 1],
            "datatype": "BYTES",
            "data": [["I do not really care what you call me."]],
        },
    ]
}

response = requests.post(
    "http://host.docker.internal:18000/v2/models/f5_tts/infer",
    headers={"Content-Type": "application/json"},
    json=payload,
    params={"request_id": "0"},
    timeout=300,
)
print("status", response.status_code)

try:
    body = response.json()
except Exception:
    print(response.text[:4000])
    raise

if "outputs" not in body:
    print(json.dumps(body, indent=2)[:4000])
    raise SystemExit(1)

audio = np.asarray(body["outputs"][0]["data"], dtype=np.float32)
sf.write(out_path, audio, 24000, "PCM_16")
print(json.dumps({"samples": int(audio.shape[0]), "output_audio": str(out_path)}))
PY'
WSL
