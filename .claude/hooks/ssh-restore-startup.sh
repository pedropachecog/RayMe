#!/usr/bin/env bash
# SessionStart hook: auto-restore SSH access to OMEN-PC on every new session.
# Keys live in .local/phase0-ssh/ (repo bind mount, persists across container restarts).
# This copies them to ~/.ssh/ and writes config so SSH just works.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/bootstrap-rayme-ssh.sh"

[[ -f "$SCRIPT" ]] || exit 0

# Restore both aliases silently
bash "$SCRIPT" restore 2>/dev/null || true
RAYME_SSH_ALIAS=rayme-pmpg RAYME_SSH_USER=pmpg bash "$SCRIPT" restore 2>/dev/null || true

exit 0
