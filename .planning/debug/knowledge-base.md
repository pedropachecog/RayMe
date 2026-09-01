# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## same-thread-refusal-recurrence — Swipe retries persisted generic refusals outside the guard's semantic grammar
- **Date:** 2026-09-01
- **Error patterns:** I can't help with that request, explicit description, explicit content, refusal persisted, swipe alternate selected, upstream_complete
- **Root cause(s):** Exact-context provider outputs used sentence-leading first-person refusal verbs aimed directly at request/description/content objects, but the shared guard required separate identity/policy/apology/redirect vocabulary. Omitted direct-object structures therefore finished as accepted text and the swipe route persisted and selected them.
- **Fix:** Added bounded direct-request and terminal direct-object refusal structures with punctuation versus true-upstream-completion disambiguation, plus explicit-subject request-to-describe handling. Preserved in-world until-continuations and quoted dialogue.
- **Files changed:** web-ui/server/app/domain/refusal_guard.py, web-ui/server/tests/fixtures/phase091_refusal_corpus.json, web-ui/server/tests/test_message_actions.py
- **Why not caught:** Earlier tests represented individual policy phrases but did not exercise the real swipe API/storage boundary with terse direct-object refusals or incremental fragments ending temporarily at `request`, `description`, or `content`.
- **Recurrence guard:** `web-ui/server/tests/test_message_actions.py::test_swipe_route_retries_explicit_description_refusal_before_selecting_alternate` covers 16 real refusal forms and persistence/selection; `web-ui/server/tests/test_refusal_guard.py` runs 524 lifecycle/fragmentation checks with direct-object continuation and quotation neighbors; final production replay used ten byte-identical exact-context swipes with zero refusal rows persisted.
---

## last-chat-refusal-recovery — Sentence-boundary refusal escaped before its identity cue arrived
- **Date:** 2026-08-31
- **Error patterns:** cannot fulfill that request, AI assistant, helpful and harmless, sentence-boundary streaming, generic refusal persisted
- **Root cause(s):** `PrefixRefusalGuard._should_release()` released a sentence-boundary prefix that already matched `_REFUSAL_VERB_RE` when its generic identity/policy cue arrived in the next chunk; irreversible passthrough then emitted and persisted the complete refusal.
- **Fix:** Block early safe-sentence release while `_REFUSAL_VERB_RE` already matches the held prefix; add the exact production-form corpus case, benign neighbor, and end-to-end shared-stream retry/persistence regression.
- **Files changed:** web-ui/server/app/domain/refusal_guard.py, web-ui/server/tests/fixtures/phase091_refusal_corpus.json, web-ui/server/tests/test_chat_stream.py
- **Why not caught:** The corpus lacked a multi-sentence refusal whose secondary generic cue begins after an independently releasable first sentence.
- **Recurrence guard:** `web-ui/server/tests/test_chat_stream.py::test_sentence_boundary_identity_refusal_retries_without_reaching_chat_or_persistence` plus the frozen corpus's `observed_omen_sentence_boundary_identity_refusal` and `in_world_fulfill_negation` cases.
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

## chat-continue-prefix-replaced — Edit → Continue discarded the committed assistant prefix
- **Date:** 2026-08-10
- **Error patterns:** Continue, composer_text empty, edited assistant prefix absent, whole-message replacement, assistant prefill
- **Root cause(s):** Continue previously persisted raw model output; its first repair passed supplied text as a user instruction instead of assistant prefill; its Edit → Continue path then ignored the selected edited assistant content when the global composer was empty, re-entering the whole-message replacement path.
- **Fix:** Preserve raw explicit composer text or resolve an empty composer to the selected assistant target, prefill it as the final assistant turn, and persist it exactly once before generated suffix text.
- **Files changed:** web-ui/client/src/routes/chat/[threadId]/+page.svelte, web-ui/client/tests/unit/chat.test.ts, web-ui/server/app/api/messages.py, web-ui/server/app/domain/message_actions.py, web-ui/server/app/domain/prompt_builder.py, web-ui/server/tests/test_message_actions.py, web-ui/server/tests/test_phase1_acceptance.py, web-ui/server/tests/test_prompt_builder.py
- **Why not caught:** Existing Continue tests covered nonempty composer input and did not model the separate Edit → empty-composer Continue workflow, so the UI/API contract gap escaped automated and initial physical verification.
- **Recurrence guard:** `web-ui/server/tests/test_message_actions.py::test_continue_uses_edited_assistant_text_as_prefix_when_composer_is_empty` performs PATCH → empty-composer Continue against real SQL and asserts the returned/displayed selected alternate and persisted content retain the prefix once despite contradictory backend output.
---

## message-edit-update-fails — Message edits lost persistence/branch identity and stale-user regeneration omitted its correction
- **Date:** 2026-08-10
- **Error patterns:** RayMe could not update this message, optimistic-user PATCH 404, assistant edit marked downstream stale, final AI repeated prior assistant, edited stale user omitted from regenerate context
- **Root cause(s):** Successful streams left a client-only optimistic user ID in editable state; user edits did not regenerate their immediate AI response and regenerated rows stayed stale; server/client edit paths marked downstream rows stale for assistant-only corrections; an already-stale edited user was not reactivated, so final-AI regeneration excluded the correction and could repeat the preceding assistant.
- **Fix:** Refresh thread state after successful streaming; regenerate the immediate AI response after a user edit; limit stale propagation to user edits; reactivate the edited user branch point before prompt construction; retain exact-ID assistant edit projection.
- **Files changed:** web-ui/client/src/routes/chat/[threadId]/+page.svelte, web-ui/client/src/lib/api/chat.ts, web-ui/server/app/domain/message_actions.py, web-ui/client/tests/e2e/chat-stream.spec.ts, web-ui/client/tests/unit/chat.test.ts, web-ui/server/tests/test_message_actions.py
- **Why not caught:** Existing message-action tests covered fresh user edits and direct assistant edits, but not an already-stale user followed by automatic regeneration or assistant edits with later stale AI identity/alternate preservation.
- **Recurrence guard:** `web-ui/server/tests/test_message_actions.py::test_editing_a_previously_stale_user_reactivates_its_regeneration_context`; `web-ui/server/tests/test_message_actions.py::test_assistant_edit_isolated_from_later_stale_ai_record`; client unit and rendered stale-AI isolation coverage in `web-ui/client/tests/unit/chat.test.ts` and `web-ui/client/tests/e2e/chat-stream.spec.ts`.
---
