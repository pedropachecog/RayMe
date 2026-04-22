#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
remote_alias="${1:-rayme-ssh}"
remote_stage_dir="${2:-phase0-probes}"

sample_dest="$repo_root/.planning/phases/00-measurement-gate/results/remote_tts_samples"
json_dest="$repo_root/.planning/phases/00-measurement-gate/results/remote_tts_json"

mkdir -p "$sample_dest" "$json_dest"

scp -r "${remote_alias}:${remote_stage_dir}/fixtures/tts_samples/." "$sample_dest/"
scp -r "${remote_alias}:${remote_stage_dir}/results/." "$json_dest/"

echo "Pulled remote TTS artifacts into:"
echo "  $sample_dest"
echo "  $json_dest"
