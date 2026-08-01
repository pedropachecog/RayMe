---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
reviewed: 2026-08-01T10:21:31Z
depth: standard
files_reviewed: 60
files_reviewed_list:
  - ai-backend/app/api/tts.py
  - ai-backend/app/api/webrtc.py
  - ai-backend/app/call/session.py
  - ai-backend/app/call/tracks.py
  - ai-backend/app/models/engine_metadata.py
  - ai-backend/app/models/model_manager.py
  - ai-backend/app/models/tts_qwen3.py
  - ai-backend/app/models/tts_qwen3_protocol.py
  - ai-backend/app/models/tts_qwen3_worker.py
  - ai-backend/app/models/tts_registry.py
  - ai-backend/pyproject.toml
  - ai-backend/tests/test_call_session.py
  - ai-backend/tests/test_health.py
  - ai-backend/tests/test_model_manager.py
  - ai-backend/tests/test_no_synthetic_production_paths.py
  - ai-backend/tests/test_omen_deploy_contract.py
  - ai-backend/tests/test_tts_qwen3.py
  - ai-backend/tests/test_tts_registry.py
  - ai-backend/tests/test_webrtc_signaling.py
  - ai-backend/uv.lock
  - scripts/deploy-omen.sh
  - web-ui/client/playwright.config.ts
  - web-ui/client/src/lib/api/types.ts
  - web-ui/client/src/lib/api/voices.ts
  - web-ui/client/src/lib/call/turnStream.ts
  - web-ui/client/src/lib/components/EndpointSettingsPanel.svelte
  - web-ui/client/src/lib/components/voice/SynthPreviewPanel.svelte
  - web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte
  - web-ui/client/src/lib/components/voice/VoiceAssignmentSelect.svelte
  - web-ui/client/src/lib/components/voice/VoiceLibraryList.svelte
  - web-ui/client/src/lib/components/voice/VoiceLibraryRow.svelte
  - web-ui/client/src/routes/call/[threadId]/+page.svelte
  - web-ui/client/src/routes/voice-lab/+page.svelte
  - web-ui/client/tests/e2e/call-start.spec.ts
  - web-ui/client/tests/e2e/live-call.spec.ts
  - web-ui/client/tests/e2e/qwen3-readiness.spec.ts
  - web-ui/client/tests/e2e/settings-connection.spec.ts
  - web-ui/client/tests/e2e/voice-lab.spec.ts
  - web-ui/client/tests/unit/character-editor.test.ts
  - web-ui/client/tests/unit/settings.test.ts
  - web-ui/client/tests/unit/turn-stream.test.ts
  - web-ui/client/tests/unit/voice-lab.test.ts
  - web-ui/server/alembic/versions/0003_qwen3_engine_identity.py
  - web-ui/server/alembic/versions/0004_call_turn_idempotency.py
  - web-ui/server/alembic/versions/0005_reconfirm_qwen3_authorization.py
  - web-ui/server/alembic/versions/0006_call_turn_lifecycle.py
  - web-ui/server/alembic/versions/0007_call_turn_ownership.py
  - web-ui/server/app/api/calls.py
  - web-ui/server/app/api/voices.py
  - web-ui/server/app/domain/ai_backend_client.py
  - web-ui/server/app/domain/call_service.py
  - web-ui/server/app/domain/call_tts_segments.py
  - web-ui/server/app/domain/settings_service.py
  - web-ui/server/app/domain/speech_terminal.py
  - web-ui/server/app/domain/voice_service.py
  - web-ui/server/app/storage/models.py
  - web-ui/server/tests/test_call_tts_segments.py
  - web-ui/server/tests/test_calls.py
  - web-ui/server/tests/test_migrations.py
  - web-ui/server/tests/test_voices.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 09: Code Review Report

**Reviewed:** 2026-08-01T10:21:31Z
**Depth:** standard
**Files Reviewed:** 60
**Status:** clean

## Summary

The final Phase 09 implementation was independently re-reviewed at standard depth after commit `4f6efd9`. The review covered the exact 60-file source scope, all 15 plan/summary pairs, the live-call invariants, the complete four-iteration review/fix history, and the production call, prompt-lease, durable-turn, UI recovery, runtime-provenance, and OMEN deployment boundaries.

The spoken barge-in blocker is closed. While the assistant is speaking, normalized microphone PCM now enters a bounded one-second onset buffer, must clear an RMS floor and VAD confirmation over sustained speech, is promoted into the next user turn before cancellation, and invokes the exact `await interrupt(cause="vad_barge_in")` path. That path stops and drains queued playout before waiting for the matching cancellation acknowledgement, suppresses the interrupted turn's normal terminal, preserves speech arriving during cancellation, returns to listening, and leaves later Qwen playback usable. The production-path regression uses non-silent PCM, a real `QueuedAudioOutputTrack`, and delayed cancellation acknowledgement; it also rejects low noise and transient onset.

All reviewed files meet the correctness, security, and robustness bar for this review. No Critical, Warning, or Info findings remain.

## Narrative Findings (AI reviewer)

### Prior finding disposition

All prior review findings are now closed.

| Review area | Disposition | Closing evidence |
|---|---|---|
| Default deployment and authorization migration | Closed | The canonical deploy provisions Qwen by default, upgraded rows require renewed authorization, and authorization remains hash-bound to saved reference content and transcript. |
| Playout proof, hangup atomicity, and cancellation ownership | Closed | Normal persistence requires explicit completed playout, terminal hangup state gates late writes, and cancellation remains bound to the exact active Qwen request. |
| Prompt leases and session lifecycle races | Closed | Shared same-prompt owners are reference-counted, competing prompts fail closed, and prepare/end operations coordinate under the session lifecycle lock. |
| Failure redaction and runtime provenance | Closed | Browser-visible failures are sanitized, and the pinned Faster Qwen source identity is verified before runtime import. |
| Streaming and whole-synthesis fallback | Closed | Live Qwen calls use native incremental generation, first playback begins before a slow stream completes, and the non-streaming synthesis API remains unavailable for this engine. |
| Queued-audio silence during delayed cancellation | Closed | Paced playout is stopped and drained before cancellation acknowledgement is awaited. |
| Durable turn reservation, ownership, and abandoned-work recovery | Closed | Turns are reserved before side effects, owner tokens guard transitions and persistence, stale/dead reservations are terminalized, and duplicate request identities do not duplicate work. |
| Production duplicate-turn UI recovery | Closed | The typed `turn_existing` contract reaches the call page; active duplicates rejoin, completed duplicates restore the canonical assistant message, and failed/cancelled duplicates remain recoverable. |
| Spoken VAD barge-in | Closed | Real inbound PCM during speaking now confirms bounded onset, invokes exact-request interruption, preserves the utterance, prevents stale `ai_done`, and permits a later normal turn. |

### Verification performed

- `uv run --project ai-backend pytest ai-backend/tests -q`: 263 passed.
- Focused AI barge-in/cancellation/slow-stream/whole-synthesis regression: 11 passed.
- `uv run --project web-ui/server pytest` over all four reviewed server test files: 135 passed.
- Focused client unit suite: 37 passed.
- Reviewed browser suite on desktop and mobile Chromium: 78 passed; 2 OMEN-only live tests skipped because live deployment mode was not enabled.
- `npm --prefix web-ui/client run build`: passed.
- `bash -n scripts/deploy-omen.sh`: passed.
- `git diff --check`: passed.

---

_Reviewed: 2026-08-01T10:21:31Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
