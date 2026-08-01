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
