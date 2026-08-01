---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
reviewed: 2026-08-01T17:06:11Z
depth: deep
files_reviewed: 15
files_reviewed_list:
  - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-hardware-tracer.py
  - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/test_phase09_evidence.py
  - ai-backend/app/api/webrtc.py
  - ai-backend/app/call/session.py
  - ai-backend/tests/test_call_session.py
  - ai-backend/tests/test_webrtc_signaling.py
  - web-ui/client/src/lib/api/calls.ts
  - web-ui/client/src/lib/api/types.ts
  - web-ui/client/src/lib/call/audio.ts
  - web-ui/client/src/routes/call/[threadId]/+page.svelte
  - web-ui/client/tests/e2e/call-toolbar.spec.ts
  - web-ui/client/tests/e2e/helpers/acceptance.ts
  - web-ui/client/tests/unit/call-audio.test.ts
  - web-ui/server/app/api/calls.py
  - web-ui/server/tests/test_calls.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 09: Code Review Report

**Reviewed:** 2026-08-01T17:06:11Z
**Depth:** deep
**Files Reviewed:** 15
**Status:** clean

## Summary

The complete `3bc3100..345fe33` receiver-drain implementation is clean under deep adversarial review. All four prior findings are closed:

- CR-01: one session/turn-scoped generation owns the immediate mute and visual-state timers; matching HTTP/data-channel acknowledgements cannot restart them, newer turns supersede them, teardown invalidates them, reconnect attachment preserves the active mute, and automatic VAD remains functional.
- CR-02: the hardware tracer observes through the later interrupted-event receive boundary while classifying audible frames against the declared HTTP-acknowledgement drain boundary.
- CR-03: cancellation captures the exact request's metrics callback before speech-task teardown, samples it immediately after outbound playout is drained, and only then waits for worker acknowledgement. The event retains measured exact-zero telemetry even when the speech task has already cleared its active fields.
- WR-01: the Web and browser boundaries accept only integer drain values from 1 through 500 and use the safe 250 ms default for missing, fractional, boolean, string, negative, and oversized values.

The bounded receiver mute remains separate from TTS startup behavior. Qwen and VoxCPM2 still begin live playback before slow stream completion, automatic barge-in still silences queued playout and preserves the microphone turn, cancelled turns reject late audio/normal completion, and the VoxCPM2 streaming path still rejects whole-synthesis fallback.

All reviewed files meet quality standards. No issues found.

## Narrative Findings (AI reviewer)

No findings.

## Verification

- Independent production-class delayed-ack reproduction: passed. The speech task completed and cleared `_active_tts_metrics_snapshot` before acknowledgement; the eventual interrupted event still reported `track_metrics_present=True`, positive admission capacity, exact `track_pending_samples=0`, and `track_pending_audio_ms=0.0`.
- Focused early-playback, exact-request cancellation, all control causes, automatic VAD/barge-in, signaling, and VoxCPM2 no-whole-synthesis-fallback gate: 15 passed.
- Phase 09 evidence contracts, including delayed-event capture and stored exact-zero validation: 68 passed.
- Focused Web interrupt propagation/defaulting contracts: 7 passed.
- Client call-audio unit tests: 9 passed.
- Desktop/mobile delayed-response call-toolbar acceptance: 2 passed.
- SvelteKit sync check: passed.
- Python AST parsing for all 8 reviewed Python files: passed.
- `git diff --check`: passed.
- Conflict-marker scan across all 15 reviewed files: none found.
- Reviewed diff fingerprint: `239765f71a397302a7c2128b90d88a32259df72f626c1c1ab2c062723fdc8c44`.

---

_Reviewed: 2026-08-01T17:06:11Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
