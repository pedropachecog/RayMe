#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/operational-check.sh start
  scripts/operational-check.sh handoff --phase-dir DIR --commit SHA --tests TEXT
      [--ui-evidence PATH] [--live-evidence PATH] [--gpu-evidence PATH]

Purpose:
  Guard against repeated handoff failures after context resets. The start check
  verifies that durable operating notes are present. The handoff check verifies
  that a claimed-ready workflow has explicit test/evidence inputs.
EOF
}

fail() {
  echo "operational-check: $*" >&2
  exit 1
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || fail "missing required file: $path"
}

require_contains() {
  local path="$1"
  local pattern="$2"
  if ! grep -Fq "$pattern" "$path"; then
    fail "required text not found in $path: $pattern"
  fi
}

cmd_start() {
  require_file ".planning/PROJECT.md"
  require_file ".planning/STATE.md"
  require_file ".planning/OPERATING-NOTES.md"
  require_file ".planning/LEARNINGS.md"
  require_file ".planning/SESSION-START.md"

  require_contains ".planning/OPERATING-NOTES.md" "pre-handoff verification checklist"
  require_contains ".planning/OPERATING-NOTES.md" "product-owner acceptance"
  require_contains ".planning/OPERATING-NOTES.md" "scripts/deploy-omen.sh"
  require_contains ".planning/OPERATING-NOTES.md" "GPU acceleration is mandatory"
  require_contains ".planning/LEARNINGS.md" "False Assumptions"
  require_contains ".planning/LEARNINGS.md" "Standing Handoff Rule"
  require_contains ".planning/SESSION-START.md" "Required Reads"
  require_contains ".planning/SESSION-START.md" "Handoff Gate"

  echo "operational-check: start gate passed"
  echo "Read next: .planning/PROJECT.md, .planning/STATE.md, .planning/OPERATING-NOTES.md, .planning/LEARNINGS.md"
}

cmd_handoff() {
  local phase_dir=""
  local commit=""
  local tests=""
  local ui_evidence=""
  local live_evidence=""
  local gpu_evidence=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --phase-dir)
        phase_dir="${2:-}"
        shift 2
        ;;
      --commit)
        commit="${2:-}"
        shift 2
        ;;
      --tests)
        tests="${2:-}"
        shift 2
        ;;
      --ui-evidence)
        ui_evidence="${2:-}"
        shift 2
        ;;
      --live-evidence)
        live_evidence="${2:-}"
        shift 2
        ;;
      --gpu-evidence)
        gpu_evidence="${2:-}"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        fail "unknown handoff argument: $1"
        ;;
    esac
  done

  [[ -n "$phase_dir" ]] || fail "--phase-dir is required"
  [[ -d "$phase_dir" ]] || fail "phase directory not found: $phase_dir"
  [[ -n "$commit" ]] || fail "--commit is required"
  [[ "$commit" =~ ^[0-9a-fA-F]{7,40}$ ]] || fail "--commit must be a git SHA"
  [[ -n "$tests" ]] || fail "--tests is required; include command and result"

  if [[ -n "$ui_evidence" ]]; then
    require_file "$ui_evidence"
  fi
  if [[ -n "$live_evidence" ]]; then
    require_file "$live_evidence"
  fi
  if [[ -n "$gpu_evidence" ]]; then
    require_file "$gpu_evidence"
  fi

  if [[ "$tests" != *pass* && "$tests" != *passed* && "$tests" != *PASS* ]]; then
    fail "--tests must include an explicit pass result or the handoff is not ready"
  fi

  echo "operational-check: handoff gate passed"
  echo "phase_dir=$phase_dir"
  echo "commit=$commit"
  echo "tests=$tests"
  [[ -z "$ui_evidence" ]] || echo "ui_evidence=$ui_evidence"
  [[ -z "$live_evidence" ]] || echo "live_evidence=$live_evidence"
  [[ -z "$gpu_evidence" ]] || echo "gpu_evidence=$gpu_evidence"
}

case "${1:-}" in
  start)
    shift
    [[ $# -eq 0 ]] || fail "start takes no arguments"
    cmd_start
    ;;
  handoff)
    shift
    cmd_handoff "$@"
    ;;
  -h|--help|"")
    usage
    ;;
  *)
    usage >&2
    fail "unknown command: $1"
    ;;
esac

