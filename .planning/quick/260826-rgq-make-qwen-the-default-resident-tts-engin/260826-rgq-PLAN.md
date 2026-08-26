---
quick_task: 260826-rgq
status: complete
description: "Make Qwen the default resident TTS engine on OMEN startup and verify the OMEN Desktop launcher works as intended"
date: 2026-08-26
---

# Quick Plan: Qwen-Resident OMEN Startup And Desktop Launcher

## Goal

Every canonical OMEN startup must load `qwen3_1_7b` as the one resident TTS
engine, while the Desktop `Run RayMe.lnk` path remains the visible foreground
launcher: one console, AI/Web logs, the LAN URL, and close-to-stop behavior.

User-goal preservation: the user must still be able to start RayMe from the
OMEN Desktop, see honest startup state and logs, open the printed URL, make live
calls with early streamed playback, and stop both services by closing the
console. Changing startup residency must not add whole-response buffering,
CPU fallback, a second resident TTS engine, or hidden background launchers.

## Task 1: Lock Canonical OMEN Startup To Qwen Residency

**Files:**

- `ai-backend/app/config.py`
- `ai-backend/tests/test_model_manager.py`
- `scripts/deploy-omen.sh`
- `ai-backend/tests/test_omen_deploy_contract.py`

**Action:** Add an explicit, validated AI-backend environment override for the
startup TTS engine. Have the deploy-generated AI launcher set it to
`qwen3_1_7b`, and make canonical deploy health gates require Qwen one-hot
residency through both direct AI health and the Web UI bridge. Preserve F5 as
the generic/local fallback when the OMEN environment override is absent.

**Verify:** Focused config/model-manager and deploy-contract tests fail before
the implementation and pass afterward. Shell syntax remains valid.

**Done:** A normal OMEN deploy and every later scheduled-task start load Qwen
resident without an evidence-only flag or manual engine switch.

## Task 2: Restore Desktop Foreground Launcher Runtime Parity

**Files:**

- `scripts/start-rayme-omen.ps1`
- `ai-backend/tests/test_omen_desktop_launcher_contract.py`
- `scripts/deploy-omen.sh`

**Action:** Make the repo-owned foreground launcher consume the same deployed
Qwen model revision, service credential, CA bundle, deployed commit, CUDA path,
and Qwen startup-engine setting as the scheduled launchers. Keep the existing
visible console/log/URL/close-to-stop contract. Extend deploy-time shortcut
attestation so drift in target, arguments, window style, description, or
working directory fails deployment.

**Verify:** Static launcher/shortcut contract tests pass; PowerShell parses the
foreground script; no hidden/minimized/browser-auto-open mechanism appears.

**Done:** The Desktop shortcut points only at the repo launcher and the exact
shortcut command can start authenticated AI/Web services with Qwen resident.

## Task 3: Deploy And Prove The Real Launcher Lifecycle

**Files:**

- `.planning/quick/260826-rgq-make-qwen-the-default-resident-tts-engin/260826-rgq-LIVE-EVIDENCE.md`

**Action:** Run relevant backend tests and invariant regressions, commit and
push the implementation, deploy only through `scripts/deploy-omen.sh`, verify
the exact deployed commit, Qwen one-hot CUDA residency, authenticated Web UI
bridge, and HTTP readiness. On OMEN, inspect `Run RayMe.lnk`, run its exact
target/arguments in a foreground session, capture visible AI/Web/URL markers,
stop that session, prove ports close, then restore the canonical scheduled
services and confirm Qwen is resident again.

**Verify:** Saved evidence records commands, commit, shortcut fields, runtime
markers, shutdown result, restored task/listener state, health, and GPU status.

**Done:** RayMe is left running on OMEN at the new commit with Qwen resident,
and both scheduled and Desktop startup paths are verified.
