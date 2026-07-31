---
status: resolved
created: 2026-07-31T22:26:03Z
updated: 2026-07-31T22:31:21Z
trigger: "Phase 09 Plan 14 canonical OMEN hardware evidence stopped because saved voice creation returned HTTP 422 after exact-commit deployment."
---

# Debug Session: Qwen Saved Voice 422

## Current Focus

user_goal_preservation: "RayMe must be ready for real live-call testing with Faster Qwen3-TTS 1.7B voice cloning, with visible readiness, early playback, listening recovery, interruption, and no fabricated release evidence."
hypothesis: "Confirmed: the hardware tracer nests its authorization values only under metadata.authorization, while the save API requires voice_data_steward, authorization_basis, and use_scope at the request top level before it creates hash-bound stored provenance."
test: "Add a tracer-boundary regression that captures the actual POST /api/voices payload and requires all three canonical top-level authorization fields, then apply the minimal payload fix and run the tracer/evidence plus server authorization suites."
expecting: "The new regression fails on the deployed request shape, passes after the three canonical fields are sent at top level, and existing server tests prove authorization remains hash-bound and fail-closed."
next_action: "Resume Phase 09 Plan 14 from the committed repair and rerun the canonical exact-commit OMEN deployment/evidence gate."

## Symptoms

expected: "After canonical exact-commit deployment, the production hardware tracer creates an authorized saved Qwen voice, prewarms its prompt, and begins the Phase 09 evidence run."
actual: "The canonical deploy succeeded, but the production hardware tracer stopped at saved voice creation with HTTP 422. Qwen never reached saved-voice readiness, so no core release evidence was claimed."
errors:
  - "FAIL: saved voice creation failed with status 422"
  - "Production Qwen hardware tracer failed"
timeline: "First observed on 2026-07-31 during Phase 09 Plan 14 after deploying exact commit e70c4f3ac8c5b3e6041bd704a6c1574d26381d7e to OMEN."
reproduction: "Run the canonical Phase 09 final Qwen deployment/evidence path through scripts/deploy-omen.sh against exact commit e70c4f3ac8c5b3e6041bd704a6c1574d26381d7e; saved voice creation returns 422."

## Evidence

- timestamp: 2026-07-31T22:26:03Z
  checked: "Phase 09 Plan 14 executor result after canonical deployment."
  found: "OMEN remote commit matches local e70c4f3ac8c5b3e6041bd704a6c1574d26381d7e; AI/Web services, STT, and VAD are running; the tracer stopped on saved voice creation status 422; Qwen did not reach saved-voice readiness; no mock evidence or core evidence was substituted."
  implication: "Debug the real saved-voice API request/validation boundary before redeploying or resuming evidence collection."
- timestamp: 2026-07-31T22:31:00Z
  checked: "The exact _create_saved_voice request in 09-run-hardware-tracer.py against VoiceSave and save_voice in web-ui/server/app/api/voices.py plus passing Qwen authorization tests."
  found: "The tracer sends asset_id, name, default_engine, reference_transcript, and metadata.authorization. It omits the three canonical top-level fields voice_data_steward, authorization_basis, and use_scope. VoiceSave accepts those top-level fields and VoiceService rejects their absence for qwen3_1_7b with 422."
  implication: "The 422 is a request-contract mismatch in the tracer. Repair the caller; do not weaken or bypass server authorization validation."
- timestamp: 2026-07-31T22:31:21Z
  checked: "RED/GREEN production-tracer payload regression, full Phase 09 evidence contracts, Qwen server voice authorization suite, full AI backend suite, full Web UI server suite, and git diff checks."
  found: "The new tracer regression failed before the fix with KeyError voice_data_steward and passed after the fix. Phase 09 evidence passed 38/38, voice authorization passed 41/41, AI backend passed 233/233, Web UI server passed 224/224, and git diff --check passed."
  implication: "The caller now satisfies the canonical authorization contract without weakening server validation. The repair is ready for a new exact-commit canonical deployment."

## Eliminated

- hypothesis: "The multipart WAV upload caused FastAPI validation failure."
  evidence: "The asset upload succeeded and returned an opaque asset id; the 422 occurred only on the subsequent JSON saved-voice request."
- hypothesis: "The server's Qwen authorization gate should be relaxed for the release tracer."
  evidence: "Existing server tests prove the gate intentionally requires explicit top-level stewardship, basis, and LAN scope before it computes hash-bound provenance; the tracer alone violated the public contract."

## Resolution

root_cause: "The production Qwen hardware tracer omitted the save API's three top-level authorization fields and placed them only in opaque metadata, so the server correctly rejected saved-voice creation with HTTP 422 before prompt preparation."
fix: "The Phase 09 hardware tracer now sends voice_data_steward, authorization_basis, and use_scope at the top level of POST /api/voices while retaining the sanitized audit metadata block."
verification: "RED tracer payload regression reproduced the omission; GREEN regression passed; Phase 09 evidence 38 passed; server voice authorization 41 passed; full AI backend 233 passed; full Web UI server 224 passed; git diff check passed."
files_changed: ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-hardware-tracer.py, .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/test_phase09_evidence.py"
