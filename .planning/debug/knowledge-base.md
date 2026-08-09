# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## qwen-core-invalid-json — Canonical deploy launched new ORM code against an unmigrated OMEN database
- **Date:** 2026-08-01
- **Error patterns:** RayMe runtime returned invalid JSON, POST /api/threads 500, table messages has no column named call_id
- **Root cause(s):** Canonical `scripts/deploy-omen.sh` did not run Alembic before launching services; OMEN retained revision `0002_voice_storage` while deployed code mapped schema through `0007_call_turn_ownership`.
- **Fix:** Run fail-closed Alembic `upgrade head` against OMEN's exact persistent web database before canonical launchers/services are written or started.
- **Files changed:** scripts/deploy-omen.sh, ai-backend/tests/test_omen_deploy_contract.py
- **Why not caught:** Deployment tests covered provisioning/runtime identity but not migration execution, while route tests created fresh current-schema databases and could not expose retained-schema skew.
- **Recurrence guard:** Regression test `ai-backend/tests/test_omen_deploy_contract.py::test_omen_deploy_upgrades_persistent_web_schema_before_launch` plus retained revision-0002-to-head migration tests.
---

## qwen-call-never-listening — Looping fake mic self-interrupted every Qwen reply and stranded prompt ownership
- **Date:** 2026-08-01
- **Error patterns:** Voice preparation failed, aiDoneEvents stayed zero, Speech playback failed, qwen3_prompt_leased, active_sessions=1, vad.barge_in, speak.cancelled
- **Root cause(s):** Phase-09 finish lifecycle prepared Qwen without explicit `/end`; the browser fake microphone left only 3.44 seconds of closing silence, so Chromium loop restart triggered valid barge-in 140–420 ms after every `ai_audio_started`; closed remote peers were not terminalized, retaining the capacity-one prompt lease and blocking the subsequent mobile call.
- **Fix:** Add explicit finish-session `/end` cleanup; expand the canonical synthetic fake-mic trailing response window to 12000 ms; terminalize unended sessions on `connectionState=closed` so prompt leases release.
- **Files changed:** .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py, .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/test_phase09_evidence.py, .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-hardware-tracer.py, ai-backend/app/call/session.py, ai-backend/tests/test_call_session.py
- **Why not caught:** Finish lifecycle tests stopped at readiness; the fake-mic test asserted only enough silence to close VAD rather than a complete loop-safe AI-response window; connection tests covered `failed` but not remote `closed`.
- **Recurrence guard:** `test_phase09_evidence.py` finish lifecycle cleanup tests and `test_hardware_tracer_fake_microphone_has_loop_safe_response_window`; `ai-backend/tests/test_call_session.py::test_closed_connection_ends_session_and_releases_prompt_lease`.
---

## qwen-voice-transcript-reject — Historical: Non-16-kHz Qwen alignment mismatch and unbounded receiver-side cancellation tail
- **Date:** 2026-08-01
- **Error patterns:** The transcript does not appear to match the voice sample, qwen3_transcript_mismatch, retired policy fields, unexpected selection keyword, Audible Qwen frames arrived after cancellation acknowledgement, post-ack RTP, receiver drain
- **Root cause(s):** Voice Lab transcription canonicalized uploads to mono 16 kHz but save-time Qwen alignment passed source-rate ndarray audio into faster-whisper's 16-kHz ndarray path; obsolete product/evidence policy fields were duplicated across UI/API/persistence/runtime; the exact-core evidence caller retained an obsolete saved-voice keyword and ordinary exceptions escaped its sanitized boundary; WebRTC retained already-sent RTP after correct server queue cancellation while the browser lacked a bounded receiver mute/drain and the tracer used an unrelated fixed 100-ms grace without independent zero-pending-audio evidence.
- **Fix:** Reuse canonical 16-kHz decoding for Qwen alignment; remove obsolete policy fields/metadata because upload is assumed authorized; repair the exact-core caller and sanitize unexpected ordinary failures; advertise a shared 250-ms receiver drain across event/control APIs, mute/unmute the browser through that bound, and make the hardware tracer distinguish bounded transport tail from forbidden post-bound audio while requiring explicit zero server pending audio.
- **Files changed:** ai-backend/app/models/model_manager.py, ai-backend/app/call/session.py, ai-backend/app/api/webrtc.py, web-ui/server/app/api/voices.py, web-ui/server/app/api/calls.py, web-ui/server/app/domain/voice_service.py, web-ui/server/app/domain/call_service.py, web-ui/server/alembic/versions/0008_remove_qwen3_authorization.py, web-ui/client/src/routes/voice-lab/+page.svelte, web-ui/client/src/routes/call/[threadId]/+page.svelte, web-ui/client/src/lib/call/audio.ts, web-ui/client/src/lib/api/calls.ts, web-ui/client/src/lib/api/types.ts, Phase 09 hardware/core evidence runners and their regression suites
- **Why not caught:** No gate compared Voice Lab transcription and Qwen alignment using a non-16-kHz sample representation; tests covered server queue cancellation but not real browser audibility after manual/automatic interruption; the tracer conflated post-ack delivery with post-cancel production; exact-core tests did not exercise every saved-voice caller or unexpected ordinary exception type.
- **Recurrence guard:** This historical entry is superseded by `.planning/REFERENCE-AUTHORIZATION-PROHIBITION.md`: removed product/evidence policy fields, gates, and metadata-driven fallback must remain absent. Preserve the transcript-resampling guard `ai-backend/tests/test_model_manager.py::test_qwen_alignment_resamples_uploaded_reference_like_voice_lab_transcription`; `web-ui/client/tests/unit/call-audio.test.ts`; `web-ui/client/tests/e2e/call-toolbar.spec.ts`; `test_phase09_evidence.py::test_hardware_tracer_distinguishes_bounded_transport_drain_from_late_audio`; `test_phase09_evidence.py::test_hardware_tracer_requires_explicit_zero_pending_audio_metric`; canonical OMEN Qwen hardware tracer plus deployed desktop/mobile live-call acceptance.
---

## keep-screen-awake-during-call — Active phone calls allowed idle screen-off and could spin on denied wake locks
- **Date:** 2026-08-09
- **Error patterns:** phone screen turns off after idle timeout, active call becomes unreliable until the screen wakes, Screen Wake Lock rejected, fallback notice
- **Root cause(s):** The active browser call lifecycle originally never requested a Screen Wake Lock, so mobile devices used ordinary idle timeout; the first repair also re-requested from `finally` after every rejection, which creates a tight retry loop when a browser or platform persistently denies the lock.
- **Fix:** Added a route-owned, feature-detected Screen Wake Lock lifecycle that requests only for active visible calls, releases on call teardown, and reacquires on eligible visibility recovery. Rejections now report a deduplicated non-blocking toolbar notice and never self-retry; a later explicit activation or visibility event may request again.
- **Files changed:** web-ui/client/src/lib/call/wakeLock.ts, web-ui/client/src/routes/call/[threadId]/+page.svelte, web-ui/client/tests/unit/call-wake-lock.test.ts, web-ui/client/tests/e2e/call-mobile.spec.ts
- **Why not caught:** No existing unit, mobile browser, or physical-phone acceptance gate covered the Screen Wake Lock lifecycle, persistent rejected-request behavior, or a visible fallback notice.
- **Recurrence guard:** `web-ui/client/tests/unit/call-wake-lock.test.ts` covers `bounds persistent rejections until a new visible lifecycle event requests again`; `web-ui/client/tests/e2e/call-mobile.spec.ts` covers successful acquisition and `explains when the browser cannot keep the screen awake without ending the call`; both passed before deployed Android acceptance.
---
