---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 15
subsystem: live-call-release
tags: [qwen3-tts, omen, webrtc, browser-e2e, wavlm, privacy, operational-handoff]

requires:
  - phase: 09-14
    provides: Canonical exact-commit OMEN deployment and five independently verified core Qwen evidence artifacts
provides:
  - Same-commit WavLM speaker stability, private-data leak scan, and real desktop/mobile browser-call evidence
  - Decision-ready autonomous Qwen release proof at deployed commit 3501a1a1e2b4371a46d6d65322975134b0d35a5f
  - Exact OMEN operator handoff with the active saved voice and physical multi-turn/barge-in workflow
affects: [omen-operations, qwen3-release, live-call-acceptance, phase-09-verification]

actuals:
  tokens: 46123
  tasks: 2
  commits: 9

tech-stack:
  added: []
  patterns:
    - Exact-commit release evidence is semantic-verifier-first, then operational-shell-gate
    - Boundary-ended speech turns use a synthesis-free terminal marker so Listening recovers without whole-synthesis fallback
    - Canonical WebRTC media ingress is LocalSubnet-only and bound to the base Python executable that owns live port 9443

key-files:
  created:
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-speaker.json
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-browser.json
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-log-leak-scan.json
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-operational-handoff.json
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-OMEN-HANDOFF.md
  modified:
    - web-ui/server/app/domain/ai_backend_client.py
    - ai-backend/app/call/session.py
    - scripts/deploy-omen.sh
    - web-ui/client/tests/e2e/live-call.spec.ts
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-verify-evidence.py

key-decisions:
  - "Autonomous readiness is proven only when the semantic decision-ready verifier and the exact operational handoff command both pass against the same deployed commit."
  - "The live WebRTC UDP rule remains LocalSubnet-only and must target the resolved base Python executable that actually owns port 9443; the deploy script verifies that identity."
  - "Automated release readiness is pass, while integrated human listening and physical-call acceptance remain separate pending judgments; the accepted candidate Spike cannot substitute for either."

requirements-completed: [REQ-22, REQ-45, REQ-46]

coverage:
  - id: D1
    description: "Pinned WavLM scores and the local-only leak scan prove stable same-commit acoustics without committing private reference material."
    requirement: REQ-22
    verification:
      - kind: integration
        ref: "results/qwen3-speaker.json and results/qwen3-log-leak-scan.json"
        status: pass
      - kind: unit
        ref: "test_phase09_evidence.py (48 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The canonical deployed Qwen browser call streams early, completes two cycles, recovers Listening, and persists durable speech on desktop and mobile."
    requirement: REQ-45
    verification:
      - kind: e2e
        ref: "live-call.spec.ts at 3501a1a1e2b4371a46d6d65322975134b0d35a5f (6/6 passed in 11.1m)"
        status: pass
      - kind: integration
        ref: "09-verify-evidence.py --decision-ready"
        status: pass
    human_judgment: false
  - id: D3
    description: "The exact operator handoff names the live saved voice, release evidence, and physical multi-turn/barge-in workflow without fabricating human acceptance."
    requirement: REQ-46
    verification:
      - kind: integration
        ref: "scripts/operational-check.sh handoff with exact Plan 09-15 arguments"
        status: pass
      - kind: human
        ref: "09-OMEN-HANDOFF.md integrated listening and physical-call workflow"
        status: pending
    human_judgment: true

duration: 4h08m
completed: 2026-08-01
status: complete
---

# Phase 09 Plan 15: Same-Commit Qwen Release Handoff Summary

**Faster Qwen3-TTS 1.7B is autonomously release-ready on OMEN at exact commit `3501a1a`, with real browser cycles, stable speaker identity, clean privacy evidence, and an honest physical-call handoff.**

## Performance

- **Duration:** 4h 08m
- **Started:** 2026-08-01T02:32:20Z
- **Completed:** 2026-08-01T06:40:20Z
- **Tasks:** 2
- **Files modified:** 26 implementation and evidence files
- **Deployed implementation:** `3501a1a1e2b4371a46d6d65322975134b0d35a5f`

## Accomplishments

- Recorded pinned CUDA WavLM early/middle/late and integrated-baseline scores. The late median drop is 0.02091 versus early and 0.02472 versus baseline, both inside the 0.05 ceiling; no audio or embeddings were committed.
- Proved the sanitized evidence bundle and AI/Web log streams contain no raw reference audio, transcript, or local reference path content.
- Completed the real canonical `live-call.spec.ts` suite 6/6 across desktop and mobile Chromium in 11.1 minutes. Each device completed two user-to-AI cycles with connected ICE/datachannel, early audio, two `ai_done`/Listening recoveries, and durable speech rows.
- Repaired the production speaking stall with synthesis-free boundary terminalization, preserving early playback, interruption, and the prohibition on whole-synthesis fallback.
- Hardened canonical OMEN deployment so LocalSubnet WebRTC UDP ingress targets the base Python image actually serving port 9443 and is asserted against the live owner.
- Published the active saved Qwen voice, canonical URLs/status, all nine release evidence inputs, exact automated commands, and the builder's physical multi-turn/barge-in/reconnect workflow.

## Task Commits

Task 1 — same-commit acoustic, privacy, and browser gates:

1. `2c41730` — repair acoustic privacy evidence gates
2. `c392d26` — make live browser evidence deterministic
3. `98161b2` — terminalize boundary-ended Qwen turns
4. `bf76a54` — allow canonical WebRTC media UDP
5. `3501a1a` — bind WebRTC UDP rule to live Python
6. `4cc392b` — resolve the speaking-stuck debug record
7. `eedc29c` — record decision-ready Qwen evidence

Task 2 — operational handoff:

1. `c2f5b80` — publish Qwen operational handoff

## Files Created/Modified

- `results/qwen3-speaker.json` — pinned WavLM identity, baseline/early/middle/late scores, and stability gate.
- `results/qwen3-browser.json` — exact-commit real desktop/mobile live-call evidence with pending human statuses.
- `results/qwen3-log-leak-scan.json` — clean structured-evidence and service-log privacy scan.
- `results/qwen3-operational-handoff.json` — machine-readable deployed state, selected saved voice, evidence inventory, gate commands, physical workflow, and acceptance boundary.
- `09-OMEN-HANDOFF.md` — operator-facing handoff for the builder's integrated listening and real-device call.
- `web-ui/server/app/domain/ai_backend_client.py` and `ai-backend/app/call/session.py` — interrupt-safe synthesis-free terminal marker for boundary-ended Qwen turns.
- `scripts/deploy-omen.sh` — canonical LocalSubnet-only WebRTC media rule and exact live-process verification.
- `web-ui/client/tests/e2e/live-call.spec.ts` and `playwright.config.ts` — deterministic repo-root fixtures, serialized GPU projects, and VAD-closing microphone silence.
- `deferred-items.md` — stale speaking blocker superseded with its exact resolution and verified non-blocking validation boundary.

## Decisions Made

- `09-verify-evidence.py --decision-ready` is the semantic release oracle. `scripts/operational-check.sh handoff` follows it and proves exact operator arguments; its standalone artifact-presence check is not used as autonomous proof.
- The live-call invariant remains authoritative: playback begins before stream completion, bounded buffers are permitted, and speaking must recover to Listening with barge-in intact.
- The active evidence voice (`voice_2ff7f9b73a4040648d2d8317b07cf02d`, `Live Call Voice 1785565019627`) is a generated non-person mechanical fixture. It proves the system but is explicitly ineligible for likeness judgment; the builder must save/confirm the intended authorized real-person reference first.
- Human acceptance stays split: `autonomous_release_ready=pass`, `candidate_spike_listening_status=accepted_separately`, `integrated_human_listening_status=pending`, and `physical_call_status=pending`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Environment] Completed acoustic evidence where private state lived**
- **Found during:** Task 1 acoustic finish
- **Issue:** The local checkout could not finish the scorer because the private audio, embeddings, and acquisition state correctly remained on OMEN.
- **Fix:** Ran the checked-in same-commit runner on OMEN and copied back only sanitized named JSON evidence.
- **Verification:** Pinned CUDA WavLM gate, leak scan, and decision-ready verifier passed.
- **Committed in:** `2c41730`, `eedc29c`

**2. [Rule 1 - Evidence Bug] Added the missing speaker critical gate**
- **Found during:** Task 1 decision verifier
- **Issue:** The scorer passed numerically but omitted `critical_gates`, so the independent verifier correctly refused to trust it.
- **Fix:** Added `speaker_stability` to the scorer schema and regression contract.
- **Verification:** 48/48 evidence tests and decision-ready verification passed.
- **Committed in:** `2c41730`

**3. [Rule 2 - Privacy] Removed private text and paths from evidence sources**
- **Found during:** Task 1 leak scan
- **Issue:** The engine-switch probe reused the private reference transcript and the deployment log could expose sensitive reference-path text.
- **Fix:** Substituted public switch text, redacted the canonical deployment log before scanning, and committed only hashes, opaque IDs, scalar scores, and named JSON artifacts.
- **Verification:** `qwen3-log-leak-scan.json` reports zero findings across all release artifacts and both service log streams.
- **Committed in:** `2c41730`

**4. [Rule 3 - Browser Harness] Made the real deployed browser gate deterministic**
- **Found during:** Task 1 live E2E
- **Issue:** Fixture paths followed the client working directory, desktop/mobile projects competed for one GPU runtime, and the fake microphone never supplied the silence needed to close VAD.
- **Fix:** Resolved fixtures from the repository root, serialized live projects, and appended bounded fake-microphone silence.
- **Verification:** Exact deployed live suite passed 6/6 with two full cycles on both device profiles.
- **Committed in:** `c392d26`

**5. [Rule 1 - Product Bug] Recovered Listening after boundary-ended Qwen speech**
- **Found during:** Task 1 real browser call
- **Issue:** When a sentence was emitted at a text boundary and the segmenter tail was empty, the backend omitted the terminal event; the call remained Speaking and discarded live input.
- **Fix:** Added an interrupt-safe, synthesis-free terminal marker so no duplicate audio or whole-response fallback is introduced.
- **Verification:** 4 server regressions, 3 backend interruption regressions, exact deployed 6/6 browser E2E, and decision-ready verifier passed.
- **Committed in:** `98161b2`

**6. [Rule 2 - Network Correctness] Bound WebRTC ingress to the real live process**
- **Found during:** Task 1 canonical deployed browser call
- **Issue:** Windows reported the live UDP owner as the base Python executable, not the virtual-environment redirector initially targeted by the firewall rule.
- **Fix:** The sole canonical deploy script now creates a LocalSubnet-only dynamic UDP rule for the resolved base executable and asserts that port 9443's live owner matches the rule application filter.
- **Verification:** Canonical deploy passed at `3501a1a`; the exact browser suite established ICE/datachannel and completed 6/6 tests.
- **Committed in:** `bf76a54`, `3501a1a`

---

**Total deviations:** 6 auto-fixed groups (3 correctness bugs, 2 missing critical/security contracts, 1 blocking environment placement)

**Impact on plan:** Every change was necessary for truthful exact-commit evidence or the real live call. No alternate deployment path, CPU/model fallback, full-stream buffering, private artifact, or fabricated human acceptance was introduced.

## Authentication Gates

None.

## Issues Encountered

- The first real browser attempt exposed a genuine production stall rather than a flaky assertion. Work paused at the GSD checkpoint, the incident was investigated under `.planning/debug/resolved/qwen-browser-speaking-stuck.md`, and Plan 09-15 resumed only after the exact deployed browser suite and semantic verifier passed.
- The operational shell gate checks arguments and artifact presence. The handoff therefore fixes the order explicitly: semantic decision-ready verification first, operational shell verification second.

## Known Stubs

| File | Line | Stub | Reason |
|---|---:|---|---|
| `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py` | 1028 | `_browser_placeholder` emits `awaiting_real_live_e2e` during acoustic-finish mode | Intentional intermediate artifact: the real `live-call.spec.ts` run overwrites it, and the decision-ready verifier rejects it until that happens. The committed final browser artifact is real and passed. |

This intermediate does not prevent the plan goal: the checked-in `qwen3-browser.json` is `passed_real_live_e2e`, and every autonomous release gate passes. It remains in the broken-windows ledger so a future combined runner can remove the overwrite step.

## Threat Flags

| Flag | File | Description |
|---|---|---|
| threat_flag: network_ingress | `scripts/deploy-omen.sh` | Adds a dynamic UDP media rule at a trust boundary. Exposure is limited to `LocalSubnet`, scoped to the exact base Python executable, and verified against the live port 9443 owner during canonical deployment. |

## Human Acceptance Boundary

- **Autonomous release readiness:** pass.
- **Candidate Spike listening:** accepted separately; it is not integrated acceptance.
- **Integrated human listening:** pending. A person must judge likeness, naturalness, intelligibility, and joins using the intended authorized real-person saved voice.
- **Physical call:** pending. A person must perform the exact multi-turn, barge-in, persistence, hangup, and reconnect workflow in `09-OMEN-HANDOFF.md`.

## User Setup Required

No infrastructure setup is required. Follow `09-OMEN-HANDOFF.md`; save or select the intended authorized real-person Qwen voice before judging likeness, then record integrated listening and physical-call outcomes separately.

## Self-Check: PASSED

All five Plan 09-15 output artifacts and this summary exist. Every implementation, repair, debug-resolution, evidence, and handoff commit listed above is present in git history.
