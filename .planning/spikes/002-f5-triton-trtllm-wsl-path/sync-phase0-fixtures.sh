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

src_dir=/mnt/c/Users/rayme-ssh.OMEN-PC/phase0-probes/fixtures
dst_dir=/home/pmpg/rayme/f5-triton-runtime/phase0-fixtures

test -f "$src_dir/short_ref_audio.wav"
test -f "$src_dir/short_ref_transcript.txt"

mkdir -p "$dst_dir"
cp "$src_dir/short_ref_audio.wav" "$dst_dir/short_ref_audio.wav"
cp "$src_dir/short_ref_transcript.txt" "$dst_dir/short_ref_transcript.txt"

ls -l "$dst_dir/short_ref_audio.wav" "$dst_dir/short_ref_transcript.txt"
WSL
