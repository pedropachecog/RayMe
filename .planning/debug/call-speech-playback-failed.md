---
status: local_verified_pending_deploy
trigger: "playback is not working at all. it shows there was an error."
created: "2026-05-25T00:00:00Z"
updated: "2026-05-25T17:30:00Z"
---

# Debug Session: Live Call Speech Playback Failed

## User Goal Preservation

Live-call TTS must begin playing early available assistant audio after a generated response while preserving streaming playback, listening recovery, and interrupt/barge-in behavior; this incident must not be fixed by waiting for the full assistant response or full TTS stream to finish before first playback.

## Symptoms

- Expected behavior: after the user speaks during a live call and the assistant generates a short text response, the TTS audio should play in the call.
- Actual behavior: the call generates visible text but no audio plays.
- Error message: `Call [Notice] Speech playback failed.`
- Timeline: reported 2026-05-25.
- Reproduction: start a live call, speak a short message, observe the UI enter `Rehearsing`, then generated assistant text appears, then playback fails with the notice above.
- Surface: live call, after assistant response generation.

## Current Focus

- hypothesis: VoxCPM2 live-call playback fails because the deployed AI backend has permanently marked `voxcpm2` unavailable after an engine load failure; later calls are allowed to generate text, but `/webrtc/speak` raises `TTS engine unavailable` before any TTS chunk can stream.
- test: local verification passed in the parent session; deployment/real-call verification is required on OMEN.
- expecting: after deploying through `scripts/deploy-omen.sh`, a transient VoxCPM2 load failure should no longer permanently disable live-call TTS until AI backend restart; if the underlying worker load failure is deterministic, logs should now show retry attempts and the engine will fail again rather than stay stale-unavailable.
- next_action: commit the local fix, deploy through `scripts/deploy-omen.sh`, then verify OMEN health and the original live-call playback flow.
- reasoning_checkpoint:
    hypothesis: "A single VoxCPM2 load failure makes live-call playback fail persistently because ModelManager marks the engine unavailable with reason `engine load failed` and never retries that transient worker-load state."
    confirming_evidence:
      - "OMEN `/health` reports `voxcpm2` as `available=false`, `state=unavailable`, `unavailable_reason=engine load failed` while F5 is resident."
      - "Failing OMEN call logs show voice reference OK and LLM done, then `/webrtc/speak` returns 502 with no preceding `tts.enqueue` or `ai_audio_started`."
      - "AI backend logs for VoxCPM2 preview show `ValueError: TTS engine unavailable` from `ModelManager.switch_tts_engine`."
    falsification_test: "If `switch_tts_engine('voxcpm2')` can retry and successfully load an adapter after a prior load failure, the permanent-unavailable mechanism is removed; if calls still fail before chunks with the engine available, this hypothesis is incomplete."
    fix_rationale: "Allowing retries only for sanitized load-failure unavailable states lets the supervised worker recover from transient native/load failures without restarting the backend, while preserving startup self-test unavailability for missing packages/unsupported engines."
    blind_spots: "The original worker load exception is sanitized and not present in the public response; if the current OMEN load failure is deterministic, the retry will expose/fail it again rather than make VoxCPM2 playable until the runtime issue is fixed."
- tdd_checkpoint:

## Evidence

- timestamp: 2026-05-25T16:48:28Z
  checked: Required context
  found: Loaded AGENTS.md, .planning/LIVE-CALL-INVARIANTS.md, gsd-debug instructions, debugger references, common bug patterns, and the active debug file.
  implication: Investigation and any fix must preserve live-call early playback, streaming TTS, listening recovery, and interrupt/barge-in behavior.
- timestamp: 2026-05-25T16:49:10Z
  checked: Project skill discovery and code search
  found: No `.codex/skills` or `.agents/skills` project skills were present. `rg` found `Speech playback failed` and `call_tts_failed` in `ai-backend/app/call/session.py`, `ai-backend/app/api/webrtc.py`, `web-ui/server/app/api/calls.py`, and related tests.
  implication: The visible notice is produced by an existing call TTS failure contract; investigation should trace upstream from generated text to TTS stream/playback handling.
- timestamp: 2026-05-25T16:51:05Z
  checked: Live-call failure flow
  found: `web-ui/server/app/api/calls.py` streams visible AI text, then calls `_speak_call`; `ai-backend/app/api/webrtc.py` returns HTTP 502 when `CallSession.speak_text()` emits `failed/call_tts_failed`; `CallSession.speak_text()` emits that failure if streaming TTS raises before successful playback.
  implication: The user-visible notice is a sanitized downstream symptom; root cause is likely inside backend TTS streaming or outbound audio enqueue before the `ai_audio_started` event.
- timestamp: 2026-05-25T16:53:12Z
  checked: VoxCPM2 streaming and outbound track implementation
  found: The live VoxCPM2 path uses `adapter.stream()` via a worker/subprocess path, buffers only bounded startup audio, enqueues chunks to `QueuedAudioOutputTrack`, and raises `VoxCPM2 streaming synthesis failed` if no chunks are produced or the worker emits an error.
  implication: A zero-chunk or worker-error stream would exactly surface as `Speech playback failed`; tests are needed to distinguish a runtime stream failure from a web proxy propagation bug.
- timestamp: 2026-05-25T16:54:35Z
  checked: Focused regression tests
  found: `uv run pytest tests/test_call_session.py -k "voxcpm2 or queued_audio_output_track"` passed 10 tests; `uv run pytest tests/test_webrtc_signaling.py -k "voxcpm2 or call_tts_failed or ai_audio_started"` passed 5 tests; `uv run pytest tests/test_calls.py -k "voxcpm2 or call_tts_failed or ai_audio_started or streaming_audio_started"` passed 4 tests.
  implication: Covered streaming, first-playback, public-error, and SSE propagation paths work in tests; the failing path is likely an uncovered runtime/config branch rather than the normal propagation code.
- timestamp: 2026-05-25T17:02:20Z
  checked: Related GSD debug evidence and model/voice routing code
  found: Prior active debug files document two relevant VoxCPM2 incidents: worker isolation fixed native backend crashes, and the current call profile was capped to timesteps 4/normalize off/denoise off because timesteps 10 generated slower than realtime. Model manager marks engines unavailable on load failures; call voice reference is loaded before LLM generation, so missing voice blobs would fail before visible AI text.
  implication: The current symptom of visible AI text followed by `Speech playback failed` is unlikely to be a missing voice sample; it is either a backend VoxCPM2 stream/load failure or a stream error after some chunks that current buffering discards before first playback.
- timestamp: 2026-05-25T17:08:10Z
  checked: Read-only OMEN AI/web log tails
  found: OMEN is on commit `26b4871`. Latest failing calls show voice reference OK, LLM first token/done, browser state entering `rehearsing`, then AI backend `POST /webrtc/sessions/.../speak` returns 502. There are no `tts.enqueue`, `track.enqueue`, `track.send.first_nonzero`, or `ai_audio_started` lines before the 502; outbound track only sends idle silence.
  implication: The real failure occurs before first audio chunk enqueue, so the earlier uncovered "discard chunk after first chunk" branch is not the observed incident. Need expose and fix the backend pre-first-chunk runtime/load/stream failure.
- timestamp: 2026-05-25T17:14:30Z
  checked: OMEN health and VoxCPM2 error logs
  found: `GET /health` reports `voxcpm2` unavailable with `unavailable_reason: engine load failed`; F5 is resident and the backend is degraded. AI logs for VoxCPM2 preview show `ValueError: TTS engine unavailable` raised from `ModelManager.switch_tts_engine` after the engine was marked unavailable.
  implication: Playback cannot start because the selected call engine is rejected before TTS streaming begins. A transient worker/load failure permanently disables VoxCPM2 until process restart/deploy, and call turns discover it only after generating text.
- timestamp: 2026-05-25T17:18:05Z
  checked: Red regression for transient VoxCPM2 load failure retry
  found: Added `test_transient_voxcpm2_load_failure_can_retry_on_later_switch`. Focused run failed as expected because `ModelManager.switch_tts_engine("voxcpm2")` raises `ValueError("TTS engine unavailable")` after the first load failure instead of retrying the adapter.
  implication: The permanent-unavailable mechanism is reproduced locally and can be fixed with a targeted model-manager state transition.
- timestamp: 2026-05-25T17:20:00Z
  checked: Model-manager retry fix and focused WebRTC regressions
  found: Updated `ModelManager.switch_tts_engine()` to retry engines whose unavailable reason is a sanitized load failure, while keeping non-load unavailable reasons blocked. Focused verification passed: model-manager retry/degrade tests 3 passed; WebRTC VoxCPM2/call_tts_failed/ai_audio_started tests 5 passed.
  implication: A transient VoxCPM2 worker/load failure no longer permanently disables live-call TTS until process restart, and the public WebRTC error contract remains sanitized.
- timestamp: 2026-05-25T17:23:20Z
  checked: Broader local verification
  found: Passed focused live-call/TTS suites: call-session VoxCPM2/queued audio 10 passed, VoxCPM2 stream/worker/fallback 6 passed, model-manager 7 passed, web call VoxCPM2/error/audio-started 4 passed. Full AI backend suite passed: 140 passed, 3 dependency warnings. `git diff --check` passed.
  implication: The local fix preserves the live-call streaming invariants covered by tests, including first playback before slow stream completion and no whole-synthesis fallback on the VoxCPM2 streaming path.
- timestamp: 2026-05-25T17:30:00Z
  checked: Parent-session verification after adding non-retry guard
  found: Added `test_startup_self_test_failure_remains_unavailable_without_retry` so the retry path remains limited to load failures. Parent-run checks passed: model-manager suite 8 passed, call-session VoxCPM2/queued audio 10 passed, WebRTC VoxCPM2/failure/audio-started 5 passed, web call VoxCPM2/error/audio-started 4 passed, full AI backend suite 141 passed with 3 dependency warnings, and `git diff --check` passed.
  implication: The patch fixes stale transient load-failure state without retrying startup self-test failures, and preserves the required live-call streaming regressions.

## Eliminated

- hypothesis: The web SSE proxy fails to surface nested `ai_audio_started_event`, causing a false playback failure after successful backend audio.
  evidence: Existing web test `test_turn_yields_ai_audio_started_event_when_nested_inside_speak_result_event` was included in the focused run and passed.
  timestamp: 2026-05-25T16:54:35Z

- hypothesis: The current VoxCPM2 streaming call-session implementation waits for full stream completion before first playback.
  evidence: Existing backend test `test_voxcpm2_slow_stream_starts_playback_before_stream_completion` was included in the focused run and passed.
  timestamp: 2026-05-25T16:54:35Z

- hypothesis: The observed incident is caused by a late stream error after some audio was already enqueued, with only the UI failing to surface `ai_audio_started`.
  evidence: OMEN AI logs for the failing sessions show `/webrtc/speak` returning 502 without any preceding `tts.enqueue`, `track.enqueue`, or `ai_audio_started` event.
  timestamp: 2026-05-25T17:08:10Z

## Specialist Review

## Resolution

- root_cause: VoxCPM2 was in a permanent `engine load failed` unavailable state on the AI backend. `ModelManager.switch_tts_engine()` rejects unavailable engines without retry, so live-call `/webrtc/speak` fails before producing any TTS chunks even though the web call already generated visible assistant text.
- fix: `ModelManager.switch_tts_engine()` now retries engines marked unavailable specifically by `engine load failed` / `default engine load failed`, clearing the stale unavailable state before attempting load again; load failures are logged server-side with a sanitized class name and still mark the engine unavailable if the retry fails.
- verification: "Local verification passed in parent session: focused live-call/TTS/model-manager/web-call tests, full AI backend tests (141 passed, 3 dependency warnings), and `git diff --check`. OMEN deployment and live-call verification remain pending."
- files_changed: ai-backend/app/models/model_manager.py, ai-backend/tests/test_model_manager.py
