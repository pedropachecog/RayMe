---
status: verifying
created: 2026-04-29T19:18:06Z
updated: 2026-05-14T22:06:00Z
trigger: "Phone calls fail to transcribe the whole content of user speech; RayMe misses whole chunks of long turns."
---

# Debug Session: Phone Calls Missing Speech Chunks

## Current Focus

user_goal_preservation: "The user must still be able to see and hear the generated response for a recovered long turn; the fix must keep the call live long enough for that response instead of cancelling, hiding, dropping, rejecting, or enqueueing it onto a dead media path."
hypothesis: "The latest Android stall at deployed commit `bfa294f` is still a backend replacement-media activation bug plus UI state ambiguity. STT, LLM, and TTS complete, but the backend accepts the replacement peer/track before the replacement media is actually connected, so TTS can queue onto a track with `recv_count=0`. The UI also reports `Composing` during TTS and can look fake-listening during long reconnect/STT work."
test: "`uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q`, `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q`, `npm run test:unit -- call-state.test.ts`, `npm run test:e2e -- call-visualizer.spec.ts`, `npm run test:e2e -- call-start.spec.ts --workers=1`, `npm run build`, and `git diff --check`."
expecting: "Before the backend fix, an answered replacement `/offer` immediately makes the backend candidate authoritative. After the fix, replacement peer/track/data-channel objects stay pending until the replacement connection reaches connected/completed or receives its first audio frame; only then does it replace the active media path. The UI now separates `Composing` text generation from `Rehearsing` TTS generation and shows `Understanding` during reconnect backfill/STT instead of fake-listening."
next_action: "Commit, deploy through `scripts/deploy-omen.sh`, then physical Android Chrome retest at `https://192.168.1.199:8443`: two short exchanges, the long poem/message, verify live response text and voice playback, verify hangup/Return to Thread do not return to a dead call, and verify the poem transcript has no omitted span of 3+ normalized words."
reasoning_checkpoint:
  hypothesis: "Terminal reconnect cleanup ends the call too early because `failTerminalMediaReconnect()` always runs `cleanupTerminalFailedCall()` and applies failed UI even when `activeTurnAbort`/`activeTurnReader` indicate an in-flight `/turns` response."
  confirming_evidence:
    - "The RED Playwright test holds `/api/calls/*/turns` before `ai_audio_started`/`ai_done` and observes `/api/calls/*/end` already posted (`endCount=1`)."
    - "`submitUserTurn()` starts an `AbortController` and stream reader for `/turns`; `failTerminalMediaReconnect()` and `cleanupTerminalFailedCall()` do not consult that state before ending."
    - "The forensic report and OMEN logs show the recovered long-turn transcript reached `/turns`, LLM generation began, then terminal reconnect cleanup posted `/end` before the response could play/show live."
  falsification_test: "If the focused Playwright test still posts `/end` before the gated `/turns` stream delivers, or if the response is not visible after releasing the gate, this hypothesis/fix is wrong."
  fix_rationale: "Delay terminal `/end` and failed UI while a turn response stream is active, and make browser reconnect replacement transactional so a failed `/offer` does not close the last answered peer/audio path. This addresses the premature state transition and playback path instead of suppressing post-end work."
  blind_spots: "The browser test mocks media and SSE timing; real Android/OMEN verification is still required after deployment, but the regression now covers both no-premature-end and keeping an answered peer open."
tdd_checkpoint:
  test_file: "web-ui/client/tests/e2e/call-start.spec.ts"
  test_name: "keeps recovered turn response live when terminal reconnect offer fails before audio starts"
  command: "npm run test:e2e -- call-start.spec.ts -g \"keeps recovered turn response live when terminal reconnect offer fails before audio starts\""
  status: "green"
  failure_output: "Expected counters.endCount to be 0 before live response delivery; received 1 at call-start.spec.ts:570 in both desktop-chromium and mobile-chromium."
  green_output: "Focused test passed after client liveness guard, transactional browser reconnect replacement, and SSE fixture framing correction: 2 passed in desktop-chromium and mobile-chromium. Full serialized call-start spec passed: 36 passed."
checkpoint:
  type: android-acceptance-needed
  rollback_commit: `7929e703fcc82eba5017d85aaf0ca98bfe16c03b`
  deployed_commit: `51e672ff4624b1d6aba2183829d0c4b285668e6c`
  forensics_report: `.planning/forensics/report-20260513-163852.md`
  guardrail: "Symptom-suppression patches cannot satisfy call-liveness acceptance."
  verification_required: "Physical Android Chrome must confirm live response delivery, clean hangup/thread return, and no omitted 3+ word poem transcript spans; local/browser mocks are not final acceptance."

## Rollback Anchor

selected_commit: `6607214de3f65a7855e6d6ad4132bc7d66f3b479` (`docs(debug): record reconnect tail deployment`)
runtime_code_commit: `faba4cc4f62e3f0c8ffd4b57b30f02aec934c1f0` (`fix(call): drain reconnect backfill tail`)
selection_basis: User selected `6607214` because it was the commit tested immediately before the "terrible regression" report and is the desired operational return point.
caveat: Rollback is now explicitly requested. Preserve post-snapshot analysis before restoring runtime code to this anchor.

## Possible Rollback Targets

- `47f41c764eacfab2b4107f87df1d887485c67ee6` (`docs(debug): record hangup backfill deployment`) — previous deployed commit before the post-`9e50387` no-STT regression; runtime code is `d7c8d4df3a54219f6e110a3d70c93fda458ba6f3`.
- `6607214de3f65a7855e6d6ad4132bc7d66f3b479` (`docs(debug): record reconnect tail deployment`) — earlier user-selected recovery snapshot; runtime code is `faba4cc4f62e3f0c8ffd4b57b30f02aec934c1f0`.

## Current Unresolved Failure

primary_target: Superseded by explicit rollback request after `a0d5d17` failed user verification.
poem_freeze_call: `call_5152493ffa72481ab60f1fc5b16eba9c` / `rtc_2892320a439f4ef59830af9df3cdd296` reached STT for the second long turn, but `user_final` was skipped because the data channel was already closed.
delayed_speech_freeze_call: `call_e3e46602b0e340f098b2549aa04a3765` / `rtc_fd075194886f46569ba1ba921440e62f` accepted the first short turn, then the second delayed turn never reached backend VAD/STT/backfill before transport close.
debugger_instruction: Historical post-`21bc46e` fix-forward target. Superseded by explicit rollback request after `a0d5d17` failed user verification.

## Symptoms

expected: RayMe phone calls should transcribe the whole spoken turn content. Minor word-level errors from accent are acceptable; dropping whole spans is not.
actual: Long speech turns are heavily truncated or compressed. Turn 2 loses most content after the Mammoth Cave setup. Turn 3 stops around the consumptives/grotto passage. Turn 4 truncates after "prevent any". Turn 5 appears to preserve only the opening phrase and ending phrase, skipping most of the middle.
errors:
  - No explicit user-facing error reported.
  - User asked debugger to inspect logs for the last call.
timeline: Observed in the last phone call on 2026-04-29. Previous issue where RayMe froze after the user took more than 5 seconds to start or finish speaking was solved.
reproduction: Start a phone call, speak multi-sentence passages, include around 10 seconds of pause before some turns, then compare the user's intended text with RayMe's transcribed `user_final` content.
evidence_files:
  - .planning/debug/phone-call-transcript-comparison.md
  - .planning/debug/phone-call-repro-e4b93d9-2026-04-30.md
  - .planning/debug/phone-call-repro-1239588-2026-04-30.md
  - .planning/debug/phone-calls-post-snapshot-audit.md
  - .planning/debug/phone-call-expected-poem-2026-05-02.md

## Investigation Evidence

- timestamp: 2026-05-14T21:34:33Z
  checked: Independent verification of latest Android Chrome repro after deployed commit `bfa294fcaed8148961ad7654cfba6e838df80e44`.
  found: Copied OMEN `rayme.sqlite3`, `web-ui.run.log`, and `ai-backend.run.log` to `/tmp/rayme-phone-debug-bfa294f-android-latest-20260514T213433Z/`. Latest call is `call_194c47dbb71b41a1a9f8f8b842b688b3` / `rtc_e167f32fca64468096e10f56b012c795` on `thread_52544a9c8441431e9ffc4b1208fb8f37`. SQLite persisted two successful short exchanges, then the long poem `user_speech` at sequence 6, an AI response at sequence 7, late user speech `Okay. Okay.` at sequence 8, a second AI response at sequence 9, and `call_end` at sequence 10.
  implication: The user report is independently confirmed. The long-turn response was generated and persisted, but it was not delivered live as audible call playback.

- timestamp: 2026-05-14T21:34:33Z
  checked: Playback/media boundary for latest call `call_194c47dbb71b41a1a9f8f8b842b688b3`.
  found: Web logs show reconnect backfill and a replacement reconnect attempt, then `mic.keep_live prevState=listening nextState=thinking`. The server generated the long response quickly (`llm.first_token` around 698 ms, `llm.done` around 4165 ms). The backend enqueued TTS (`wav_bytes=1378796`) but logged `track.wait_until_idle.timeout recv_count=0 queue_size=1 buffer_size=0`; data-channel `user_final` and `ai_audio_started` were skipped because the channel was closed. The browser received `ai_audio_started` via the turn stream with `speakingRms=0`, entered `speaking`, then returned to `listening`, so the UI treated the response as delivered while no receiver consumed the audio.
  implication: The remaining live-delivery bug is not "no generated response"; it is generated audio being queued onto a replacement media path that the browser is not consuming.

- timestamp: 2026-05-14T21:34:33Z
  checked: Poem transcript fidelity with normalized word-to-word comparison against `.planning/debug/phone-call-expected-poem-2026-05-02.md`.
  found: Expected normalized word count is 153; latest actual normalized word count is 141. The transcript omits a contiguous expected 12-word phrase around `waiting / as for a gift / snow to begin / which it...`. Misheard individual words remain acceptable under the user's accent tolerance, but this omitted 3+ word span fails acceptance.
  implication: Transcript completeness remains a separate acceptance gate. Future verification must compare normalized words to normalized words, not LLM tokens.

- timestamp: 2026-05-14T22:06:00Z
  checked: Local fix and verification for pending-media activation plus state-label ambiguity.
  found: Backend WebRTC replacement offers now leave candidate peer/track/data-channel objects pending after answer negotiation and only activate them when the candidate reaches connected/completed or receives its first audio frame; pending failures are discarded without stealing the active outbound track. Frontend reconnect now waits for replacement browser media to connect before closing the previous browser peer, preserves `Understanding` while final reconnect backfill/STT is pending, restores `Listening` when recovery is canceled/no turn is produced, and introduces distinct `Composing` (text generation) and `Rehearsing` (TTS generation) states before `Speaking`. Verification passed: backend call/session signaling suite 74 passed, web call facade suite 43 passed, unit call-state suite 6 passed, visualizer e2e 2 passed, full serialized call-start e2e 40 passed, client production build passed, and `git diff --check` passed.
  implication: The latest proven media activation and UI-state mechanisms are fixed locally. Commit, canonical OMEN deployment, and physical Android acceptance remain required.

- timestamp: 2026-05-13T17:05:28Z
  checked: Focused TDD RED baseline before product-code changes.
  found: `npm run test:e2e -- call-start.spec.ts -g "keeps recovered turn response live when terminal reconnect offer fails before audio starts"` failed in both desktop and mobile Chromium at `call-start.spec.ts:570`; expected `counters.endCount` to be `0`, received `1`.
  implication: The current client still posts `/end` while the recovered long-turn `/turns` response stream is gated before `ai_audio_started`/`ai_done`; the green fix must change the terminal reconnect liveness path.

- timestamp: 2026-05-13T17:09:58Z
  checked: First GREEN attempt after adding the active turn response guard.
  found: The focused test no longer failed at the premature `/end` assertion. It advanced to response delivery, then failed waiting for `Live response after recovery.`; the page snapshot showed the terminal failed panel. The test route currently serializes multiple SSE events as adjacent `data:` lines without blank-line event separators, so the client sees one malformed event instead of `ai_audio_started`, `ai_token`, and `ai_done`.
  implication: The product-code liveness guard moved the failure past the original boundary. The test fixture must emit valid SSE frames before the response-delivery assertion can verify the fix.

- timestamp: 2026-05-13T17:12:18Z
  checked: Focused GREEN verification after correcting mocked SSE framing.
  found: `npm run test:e2e -- call-start.spec.ts -g "keeps recovered turn response live when terminal reconnect offer fails before audio starts"` passed in both mobile and desktop Chromium: 2 passed. The test verified no `/end` and no alert while `/turns` was gated, then showed `Live response after recovery.` and observed `call.ai_audio_started`.
  implication: The active turn response liveness guard satisfies the RED boundary without cancelling or suppressing the response.

- timestamp: 2026-05-13T17:15:38Z
  checked: Adjacent browser reconnect/hangup regression verification and client build hygiene.
  found: Adjacent Playwright command for terminal reconnect limit, terminal queued-turn recovery, pending/in-flight/stalled reconnect backfill hangup cases passed: 10 passed across desktop and mobile Chromium. `npm run build` from `web-ui/client` passed. `git diff --check` passed.
  implication: The client liveness guard did not regress existing terminal reconnect cleanup or user hangup backfill behavior, and the Svelte production build accepts the change.

- timestamp: 2026-05-13T17:22:12Z
  checked: Strengthened playback-path regression after reviewing the first GREEN diff.
  found: Added an assertion to `keeps recovered turn response live when terminal reconnect offer fails before audio starts` requiring at least one already-answered peer to remain open while the recovered `/turns` stream is gated. The test failed in both desktop and mobile Chromium with that assertion false.
  implication: The first GREEN attempt was insufficient for the user's full goal. It kept `/end` from firing but `reconnectBrowserMedia()` had already closed the last answered peer/audio path before the replacement `/offer` failed, risking visible text without playable voice.

- timestamp: 2026-05-13T17:25:44Z
  checked: Focused GREEN verification after transactional browser reconnect replacement.
  found: `connectBrowserMedia()` now supports preserving the existing peer until a replacement answer is applied; `reconnectBrowserMedia()` uses that path and restores the previous peer/data channel if the replacement `/offer` fails. The strengthened focused test passed in both desktop and mobile Chromium: 2 passed.
  implication: Terminal reconnect failure no longer wins while the active response is in flight, and a failed replacement offer no longer destroys the last answered media path before the response can show/play.

- timestamp: 2026-05-13T17:30:54Z
  checked: Full browser route regression verification after the stronger fix.
  found: Adjacent reconnect/hangup grep passed: 14 passed across desktop and mobile Chromium. Full serialized `npm run test:e2e -- call-start.spec.ts --workers=1` passed: 36 passed. `npm run build` from `web-ui/client` passed. `git diff --check` passed.
  implication: The transactional reconnect plus active response liveness guard is stable across call startup, reconnect, backfill, hangup, error, and mobile route coverage; runtime deployment is the next step.

- timestamp: 2026-05-13T17:36:31Z
  checked: Commit, push, canonical OMEN deployment, and post-deploy readiness for the valid call-liveness fix.
  found: Committed and pushed `56c4ab7fdff91ec337a446fed676e967fa78cbd1` (`fix(call): keep recovered response live through reconnect failure`). `scripts/deploy-omen.sh` fast-forwarded OMEN to that commit, built the web client, recreated canonical `RayMePhase1AI` and `RayMePhase1Web` scheduled tasks, and reported `OMEN deploy complete`. Post-deploy OMEN checkout is `56c4ab7fdff91ec337a446fed676e967fa78cbd1` with no git status output. `/webrtc/status` returned `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, `active_sessions=0`. Scheduled tasks are running and point to `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`.
  implication: The valid upstream liveness fix is live on OMEN through the approved deployment path. Physical Android Chrome acceptance is now required; generic `/health` remains degraded because resident TTS is `f5`, but call-specific WebRTC readiness is green.

- timestamp: 2026-05-13T18:05:08Z
  checked: Independent verification of the latest Android Chrome stall after deployed commit `56c4ab7fdff91ec337a446fed676e967fa78cbd1`.
  found: Latest failed call is `call_3cb73bcce25a436fa84e3ac7c8efc1cd` / `rtc_ab6a07203ed449228aaf106fd4497000` on `thread_27fab4e0328c4eb2a953cad0d2f0688a`. SQLite persisted two successful short exchanges, then `call_end`, then a partial long-turn `user_speech` of length 260 ending with `...`, then an `ai_speech` of length 192. The ellipsis was stored content, not just UI truncation. Web logs show the replacement `/offer` for the long-turn reconnect returned 502 after `pc.media_reconnect.start`, leaving `callState=listening`; no retry attempt followed. AI logs show `offer.received` for the replacement offer but no `offer.answered`; the backend then finalized reconnect audio, queued `user_final` on a closed data channel, generated TTS, and skipped `ai_audio_started`/`ai_done` because the channel was closed. `/events/recover` returned 502 during hangup, `/api/calls/.../end` returned 200 in the Web UI, but no matching backend `/webrtc/sessions/.../end` appears for that session and `/webrtc/status` later reported `active_sessions=1`.
  implication: The user report is confirmed independently. The first live failure is not LLM generation or TTS synthesis; it is a reconnect-offer failure/cancellation boundary that leaves the browser inert and the backend session active without a live data/audio path. The post-hangup transcript/AI response is a late artifact, not the success path.

- timestamp: 2026-05-13T18:15:48Z
  checked: RED/GREEN implementation for latest reconnect-offer cancellation/retry boundary.
  found: Added browser regression `retries when the first replacement offer fails during media reconnect`; it failed in desktop and mobile Chromium because `offerCount` stayed at 2 instead of retrying to 3. Added backend regression `test_cancelled_reconnect_offer_preserves_existing_session_media`; it failed because cancelled replacement negotiation left `session.peer_connection` on the replacement peer. Fixed browser retry scheduling for nonterminal replacement-offer failure and added a terminal-state guard in `reconnectBrowserMedia()`. Fixed backend `asyncio.CancelledError` handling in `/webrtc/offer` so the previous peer/track/session state is restored and the abandoned replacement peer is closed before re-raising cancellation. Focused tests now pass.
  verification: "`ai-backend/tests/test_webrtc_signaling.py`: 26 passed, 3 warnings; `ai-backend/tests/test_call_session.py`: 47 passed; serialized `web-ui/client` `call-start.spec.ts`: 38 passed; `npm run build`: passed; `git diff --check`: passed."
  implication: The latest proven stall mechanism is fixed locally without suppressing generation or post-end visibility. Physical Android Chrome acceptance is still required after canonical OMEN deployment.

- timestamp: 2026-05-13T18:19:54Z
  checked: Push, canonical OMEN deployment, and post-deploy readiness for reconnect-offer cancellation/retry fix.
  found: Pushed `51e672ff4624b1d6aba2183829d0c4b285668e6c` (`fix(call): retry cancelled reconnect offers`) to `origin/main`. `scripts/deploy-omen.sh` fast-forwarded OMEN to that commit, verified the CUDA runtime, built the web client, recreated the canonical `RayMePhase1AI` and `RayMePhase1Web` scheduled tasks, and reported `OMEN deploy complete`. Post-deploy OMEN checkout is `51e672ff4624b1d6aba2183829d0c4b285668e6c` with no git status output. `/webrtc/status` returned `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, `active_sessions=0`. Scheduled tasks are running and point to `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`.
  implication: The fix for the latest verified Android stall boundary is live through the approved deployment path. Generic `/health` remains degraded because resident TTS is `f5`, but call-specific WebRTC readiness is green.

- timestamp: 2026-05-14T00:16:36Z
  checked: Independent verification of latest Android Chrome repro after deployed commit `51e672ff4624b1d6aba2183829d0c4b285668e6c`.
  found: Copied OMEN `rayme.sqlite3`, `web-ui.run.log`, and `ai-backend.run.log` to `/tmp/rayme-phone-debug-51e672f-android-latest-20260514T001636Z/`. OMEN `/webrtc/status` reported `active_sessions=1`, confirming a leaked/still-active backend session. Latest call is `call_51e671a6f7d246a588388e7273b7b707` / `rtc_cda2132f1f5a447b88d13b64338793a8` on `thread_27fab4e0328c4eb2a953cad0d2f0688a`. SQLite persisted two successful short user/AI exchanges, then the long `user_speech` at sequence 30 and AI `ai_speech` at sequence 31, then `call_end` at sequence 32, then a late user `Stop it.` and AI response at sequences 33-34 after call end.
  implication: The user report is independently confirmed. The long turn did reach STT, LLM, TTS, and persistence, but it was not delivered live. Audio was still being recovered/captured around and after call end, so this is multiple bugs rather than one missing-generation bug.

- timestamp: 2026-05-14T00:16:36Z
  checked: Transport and playback boundary for latest call `call_51e671a6f7d246a588388e7273b7b707`.
  found: First replacement offer during long-turn reconnect succeeded and reconnect backfill finalized STT with `transcript_len=835`. A second replacement `/offer` started while the long-turn response path was active; the Web UI saw `502 Bad Gateway` for that offer, and the AI backend logged `offer.received` without a matching `offer.answered`. Backend still generated and enqueued TTS, but `ai_audio_started`/`ai_done` were skipped because the data channel was closed, and the outbound audio track timed out with `recv_count=0` and `queue_size=1`. Browser debug also recorded `call.ai_audio_started` from the turn stream with `speakingRms=0`, so the client believed the response had been delivered while no live receiver was playing it.
  implication: The first live failure is not STT, LLM, or TTS generation. It is the candidate replacement media path becoming authoritative before the replacement offer is successfully answered, leaving generated audio queued to a dead track/channel.

- timestamp: 2026-05-14T00:16:36Z
  checked: Poem transcript fidelity against `.planning/debug/phone-call-expected-poem-2026-05-02.md`.
  found: Expected poem normalized word count was 154; the latest STT transcript normalized word count was 146. Misheard words are present and acceptable under the user's accent tolerance, but the diff includes at least one omitted/contracted 3-word expected span and one omitted/contracted 6-word expected span. This fails the user's threshold that an omitted span of 3+ words is not acceptable.
  implication: Transcript fidelity remains a separate unresolved acceptance item even if transport/playback is fixed. Current evidence does not yet prove whether those omissions are caused by STT recognition under accent/noise or by subtle audio loss before STT; acceptance must compare the full poem transcript after the transport fix.

- timestamp: 2026-05-14T00:33:40Z
  checked: Local fix and focused verification for latest multi-bug repro.
  found: Backend WebRTC replacement offers now stage peer/track/data-channel objects as pending and only swap `session.peer_connection`/`outbound_audio_track` after negotiation succeeds; failed or cancelled candidates are discarded and cannot steal the active media path. Frontend call state now ignores nonterminal state transitions while ending or already terminal, so late data-channel events cannot revive an ended/failed call UI. Added backend regression `test_inflight_reconnect_offer_does_not_steal_active_session_media` and frontend regression `does not revive an ended call when a late data channel state event arrives`. Focused backend command passed: 3 passed, 24 deselected. Full `ai-backend/tests/test_webrtc_signaling.py` passed: 27 passed, 3 warnings. Focused Playwright command passed in desktop and mobile Chromium: 2 passed. Full serialized `call-start.spec.ts` passed: 40 passed.
  implication: The latest proven live-delivery and dead-call-UI mechanisms are fixed locally. Production build, diff hygiene, commit/deploy, and physical Android acceptance are still pending.

- timestamp: 2026-05-14T00:38:53Z
  checked: Commit, push, canonical OMEN deployment, and post-deploy readiness for the replacement-media transaction fix.
  found: `npm run build` from `web-ui/client` passed and `git diff --check` passed. Committed and pushed `bfa294fcaed8148961ad7654cfba6e838df80e44` (`fix(call): stage replacement media until answered`). `scripts/deploy-omen.sh` fast-forwarded OMEN to that runtime fix, verified CUDA runtime, built the web client, recreated canonical `RayMePhase1AI` and `RayMePhase1Web` scheduled tasks, and reported `OMEN deploy complete`. Post-deploy `/webrtc/status` returned `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, and `active_sessions=0`; OMEN checkout was clean at `bfa294fcaed8148961ad7654cfba6e838df80e44`. Generic `/health` remained `degraded` because resident TTS is `f5`.
  implication: The latest runtime fix is live on OMEN through the approved deployment path. Physical Android Chrome acceptance is the remaining gate, including live response playback, clean hangup/thread return, and full poem transcript comparison.

- timestamp: 2026-05-13T17:00:36Z
  checked: Upstream RED browser regression for the active product bug.
  found: Added `keeps recovered turn response live when terminal reconnect offer fails before audio starts` in `web-ui/client/tests/e2e/call-start.spec.ts`. The test starts a call, successfully reconnects once, emits a recovered long-turn `user_final` through the live data channel so `/turns` begins, holds the `/turns` SSE before `ai_audio_started`/`ai_done`, then forces the next reconnect `/offer` to return 502. Focused Playwright failed in both desktop and mobile Chromium because `counters.endCount` was already `1` while the response stream was still gated.
  implication: The RED test proves the correct upstream boundary. Current client cleanup ends the call before the recovered response can show/play live; a valid green fix must delay or gate terminal `/end`/failed UI around the active response stream, not suppress generation after end.

- timestamp: 2026-05-13T16:40:37Z
  checked: Process failure after user challenged `6faf893` as solving the wrong problem.
  found: User correctly identified that the patch cancelled/rejected work after the call had already ended instead of making the call not fail. Reverted `6faf893` with `3800391b9a445963f4d1d2aefefbed5f2a5e482f`, pushed it, and deployed it through `scripts/deploy-omen.sh`. Wrote `.planning/forensics/report-20260513-163852.md` and added guardrails to `.planning/OPERATING-NOTES.md` and `.planning/LEARNINGS.md`.
  implication: The active product target returns to the upstream premature terminal-cleanup race. Do not reapply `6faf893`; future fixes must first add a RED test proving `/end`/failed UI do not win while a recovered long-turn response is in flight.

- timestamp: 2026-05-13T14:04:02Z
  checked: Fresh OMEN runtime baseline and artifact snapshot after failed Android Chrome retest of `2d00461`.
  found: `ssh rayme-pmpg whoami` returned `omen-pc\pmpg`. OMEN checkout is `2d00461f6d233338fb6562446874a466945e1b9b` with no reported git status output. Scheduled tasks `RayMePhase1AI` and `RayMePhase1Web` are running and point to canonical `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`. `GET https://192.168.1.199:9443/webrtc/status` returns ready/live-call-ready/media-transport-ready with `active_sessions=1`. Copied `rayme.sqlite3`, `ai-backend.run.log`, and `web-ui.run.log` to `/tmp/rayme-phone-debug-2d00461-android-delivery-fail-20260513T140311Z/`.
  implication: The failed Android retest ran against the intended deployed code and canonical launchers. A backend session remains active after the visible failure, so session cleanup/drain lifetime is a live suspect while analyzing the copied artifacts.

- timestamp: 2026-05-13T14:05:31Z
  checked: Fresh OMEN SQLite and logs for latest physical Android failed call.
  found: Latest failed call is `call_2018a74d029c467eb173f6a012719663` / `rtc_127ff57be7024045b1c8ac3307afbbde` on `thread_27fab4e0328c4eb2a953cad0d2f0688a`. SQLite persisted short turns, then the long `user_speech` at length 855, then `call_end`, then the final `ai_speech` at length 913 after `call_end`. Web UI logs show recovered `user_final` reached `/turns`, `llm.first_token` began, then a second `/offer` returned 502, browser terminal cleanup drained two events, posted `/end`, and entered failed state before `llm.done`. AI backend logs show reconnect backfill finalized the long turn, `stt.result transcript_len=855`, recover drained the queued `user_final`, `/end` succeeded, then `/speak` still enqueued a 41.6s TTS response on a closed session; `ai_audio_started` and `ai_done` were skipped because the data channel was closed, and `track.wait_until_idle.timeout` completed false.
  implication: The first failed boundary is not STT, LLM, or persistence. It is terminal media cleanup racing with in-flight recovered turn generation: the call is ended before the assistant response is ready, but the server still persists and attempts TTS after the media path is closed.

- timestamp: 2026-05-13T14:10:44Z
  checked: Focused RED regressions for post-end turn generation and TTS.
  found: Added `test_end_cancels_server_generation_before_call_end`; it fails because `/api/calls/{call_id}/end` returns 200 but the fake active turn has `cancel_calls=0`. Added `test_webrtc_speak_rejects_ended_session_without_synthesis`; it fails because `/webrtc/sessions/{session_id}/speak` after `/end` returns 200 instead of 502.
  implication: The OMEN mechanism is reproduced locally at both server boundaries: Web UI end does not cancel in-flight generation, and the AI backend allows late TTS on retained ended sessions.

- timestamp: 2026-05-13T14:12:00Z
  checked: Focused post-fix regressions.
  found: Implemented Web UI `/end` cancellation for `_ACTIVE_LLM_TURNS[call_id]` and an AI backend `/speak` guard that rejects ended/failed retained sessions before TTS synthesis. The focused Web UI regression now passes: 1 passed, 43 deselected. The focused AI backend regression now passes: 1 passed, 25 deselected.
  implication: The confirmed post-end generation/TTS race is fixed locally at the two reproduced boundaries; broader adjacent verification is required before commit/deploy.

- timestamp: 2026-05-13T14:23:00Z
  checked: Broader post-fix regression verification.
  found: `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` passed: 44 passed. `uv run --project ai-backend pytest ai-backend/tests/test_webrtc_signaling.py -q` passed: 26 passed, 3 warnings. `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` passed: 47 passed. `npm run test:e2e -- call-start.spec.ts` from `web-ui/client` had one desktop concurrent reconnect timing assertion fail while the same test passed on mobile; the exact focused desktop rerun passed. Serialized full `npm run test:e2e -- call-start.spec.ts --workers=1` passed: 34 passed. `npm run build` from `web-ui/client` passed. `git diff --check` passed.
  implication: The scoped fix is stable across adjacent Web UI call routes, AI backend session/signaling behavior, browser call-start/reconnect flows, and client production build. The one default-worker Playwright failure is a pre-existing/concurrent timing flake in client-only reconnect scheduling, not caused by the server/backend-only code change.

- timestamp: 2026-05-13T14:23:45Z
  checked: Atomic runtime fix commit.
  found: Committed `6faf89378bc55943c4588d31ec0b303a3607ffa3` (`fix(call): stop post-end response playback`) with only `ai-backend/app/api/webrtc.py`, `ai-backend/tests/test_webrtc_signaling.py`, `web-ui/server/app/api/calls.py`, and `web-ui/server/tests/test_calls.py`. Local dirty files are this debug session and the pre-existing Phase 03.1 evidence notes.
  implication: The runtime fix is isolated and ready to push/deploy through the canonical OMEN script.

- timestamp: 2026-05-13T14:28:30Z
  checked: Push, canonical OMEN deployment, and post-deploy readiness for post-end response playback fix.
  found: Pushed `6faf89378bc55943c4588d31ec0b303a3607ffa3` to `origin/main`. `scripts/deploy-omen.sh` fast-forwarded OMEN from `2d00461f6d233338fb6562446874a466945e1b9b` to `6faf89378bc55943c4588d31ec0b303a3607ffa3`, rebuilt the web client, recreated the canonical scheduled tasks, restarted both services, and reported `OMEN deploy complete`. Post-deploy OMEN git status is clean at `6faf89378bc55943c4588d31ec0b303a3607ffa3`. `GET https://192.168.1.199:9443/webrtc/status` returned `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, `active_sessions=0`. `RayMePhase1AI` and `RayMePhase1Web` are running and point to `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`.
  implication: The scoped runtime fix is live on OMEN through the approved deployment path and is ready for physical Android Chrome verification.

- timestamp: 2026-05-13T14:00:05Z
  checked: Physical Android Chrome human verification after deployed fix `2d00461f6d233338fb6562446874a466945e1b9b`.
  found: User reports a couple of short exchanges worked. During a long message, the call appeared frozen for about 1.5 minutes and then failed with a connection-dropped style message. After the failure, the transcript showed the whole poem and the AI had generated a whole response, but that response was never displayed or heard in the live call.
  implication: The prior fix is not accepted. The first failed user-visible boundary has moved downstream from missing transcript/hangup deadlock to live response delivery after delayed long-turn recovery; the next investigation must correlate fresh OMEN logs and SQLite for the latest Android call before applying any new fix.

- timestamp: 2026-05-13T13:12:02Z
  checked: Session rehydration before fresh Android failure investigation.
  found: Loaded the active debug session, Phase 03.1 evidence/results, post-snapshot do-not-retry guard, project operating notes/learnings, session-start protocol, and 03.1-07 plan. Local branch is `main` at `57ea978357673b040c8258aed378878482640453`; pre-existing dirty files are this debug session and `03.1-EVIDENCE.md`, containing the Android failure notes from the checkpoint. No project-local `.claude/skills` or `.agents/skills` were found.
  implication: Investigation must treat the new Android failure as unresolved live evidence on top of the existing Phase 03.1 proof, preserve the existing uncommitted evidence updates, and avoid the forbidden post-snapshot reconnect/final-marker/data-channel replay stack.

- timestamp: 2026-05-13T13:12:49Z
  checked: Debug knowledge base and OMEN SSH aliases.
  found: `.planning/debug/knowledge-base.md` is absent, so there is no prior resolved-pattern candidate to test first. `ssh rayme-pmpg whoami` returned `omen-pc\pmpg`; `ssh rayme-ssh whoami` returned `omen-pc\rayme-ssh`.
  implication: Proceed with fresh evidence collection through the required OMEN alias `rayme-pmpg`; no known-pattern shortcut is available.

- timestamp: 2026-05-13T13:13:34Z
  checked: OMEN runtime baseline after failed Android acceptance.
  found: OMEN checkout is `85bbacc919c83d1b486883e616156b2d8778c3f5` with no reported repo dirt. `GET /webrtc/status` returns `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, and `active_sessions=2`. Scheduled tasks `RayMePhase1AI` and `RayMePhase1Web` are running and point to canonical `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`.
  implication: The failed Android call ran against the intended deployed commit and canonical launchers. The two still-active backend sessions are fresh evidence for a cleanup/session-lifetime boundary and must be correlated with latest call rows/logs.

- timestamp: 2026-05-13T13:17:13Z
  checked: Copied OMEN artifact snapshot for the failed Android acceptance.
  found: Copied `rayme.sqlite3`, `ai-backend.run.log`, and `web-ui.run.log` to `/tmp/rayme-phone-debug-85bbacc-android-fail-2026-05-13/`. The newest primary failed call is `call_9c6f0bf7e12a469882374f3ab570937e` / `rtc_49587f27d43244e6b6d78a69fb1e56f1` on `thread_27fab4e0328c4eb2a953cad0d2f0688a`; a later reload/start attempt is `call_7e1daa08075f4ca3984c1a13d568a14a` / `rtc_b2a8b7e5a0404d80bfef4eee8f8543b6`. SQLite persisted the primary `call_start`, first short `user_speech` (`Hey, can you hear me?`), and first `ai_speech`, but no long second-turn `user_speech` and no `call_end` for either May 13 call.
  implication: The user report maps to durable storage: the first short turn succeeded, the longer turn did not reach persisted transcript, and hangup/end cleanup did not persist.

- timestamp: 2026-05-13T13:17:13Z
  checked: Web UI and browser debug events for primary Android call `call_9c6f0bf7e12a469882374f3ab570937e`.
  found: Browser logs show `/start`, initial `/offer`, datachannel open, remote audio unmuted, first `user_final` received, `/turns` persisted, and AI audio played with nonzero remote-audio samples. During the second long user turn, the peer/datachannel failed. The browser sent reconnect-audio backfill batches covering approximately `-48..55242ms` with speech-level RMS through batch 5 and lower RMS batch 6, all with `final=false`; the sixth browser fetch failed with `TypeError Failed to fetch`. There is no `/api/calls/call_9c6f0bf7e12a469882374f3ab570937e/events/recover` and no `/api/calls/call_9c6f0bf7e12a469882374f3ab570937e/end` in the Web UI log.
  implication: Audio capture and reconnect backfill transmission progressed much further than the previously fixed offset-gap failure, but terminal recovery/end did not run for the primary Android failure.

- timestamp: 2026-05-13T13:17:13Z
  checked: AI backend logs for primary Android session `rtc_49587f27d43244e6b6d78a69fb1e56f1`.
  found: Backend VAD/STT handled the first short turn and emitted `user_final`. For the second turn, VAD saw speech before media failure, then accepted reconnect backfill batches through `turn_frames=3862`. The final accepted batch logged `speech_seen=True` and `silence_ms=8398`, but `final=false`; no `vad.end_of_turn`, no `stt.begin`, and no `user_final` followed. Later `/events/drain` returned only a queued `failed` event, and no backend `/webrtc/sessions/rtc_49587f27d43244e6b6d78a69fb1e56f1/end` was logged.
  implication: The first proven boundary is after backend received substantial second-turn audio but before terminal finalization/end: without a final marker or `/end`, backend retained non-final VAD state and the UI stayed stuck.

- timestamp: 2026-05-13T13:21:46Z
  checked: Client and backend reconnect/hangup code paths.
  found: `hangup()` calls `drainReconnectAudioBackfillBeforeHangup()` before `/end`; that drain awaits `flushReconnectAudioBackfill(..., { awaitFinal: true })` with no timeout. Terminal reconnect cleanup has the same await before recover/end. Separately, backend `_should_finalize_after_reconnect_backfill()` returns `False` whenever `final` is false, even if VAD has speech and `_silence_ms` is already above the call end threshold. Existing browser tests cover successful/failed completed backfill, but not a stalled final backfill; existing backend tests cover final reconnect backfill, but not non-final backfill containing enough silence to end the turn.
  implication: The Android log shape has a concrete mechanism to test locally: a final reconnect backfill that never completes can deadlock browser hangup before `/end`, and the backend will not finalize the already received long-turn audio without that final marker.

- timestamp: 2026-05-13T13:26:31Z
  checked: Focused RED regressions for the fresh Android failure mechanism.
  found: Added a browser regression where the second/final reconnect-audio request is held open and the user clicks End Call; `npm run test:e2e -- call-start.spec.ts -g "ends when the final reconnect backfill request stalls during hangup"` fails in desktop and mobile Chromium with `endCount=0`. Added backend regression `test_nonfinal_reconnect_backfill_with_extended_silence_finalizes_turn`; `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q -k "nonfinal_reconnect_backfill_with_extended_silence"` fails with `KeyError: 'event'`.
  implication: The code-level mechanism is confirmed: browser cleanup can deadlock before `/end` on a stalled final backfill, and backend reconnect backfill cannot produce a transcript from non-final audio even after long terminal silence.

- timestamp: 2026-05-13T13:29:26Z
  checked: Focused post-fix regressions.
  found: Implemented a bounded browser terminal reconnect-backfill wait and backend non-final reconnect-backfill extended-silence finalization. The previously RED browser test now passes in desktop and mobile Chromium: `2 passed`. The previously RED backend test now passes: `1 passed, 46 deselected`.
  implication: The proven local failure boundaries are fixed. Broader call lifecycle/reconnect regression coverage is required before committing and deploying.

- timestamp: 2026-05-13T13:33:16Z
  checked: Broader post-fix regression verification.
  found: `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` passed: 47 passed. `uv run --project ai-backend pytest ai-backend/tests/test_webrtc_signaling.py -q` passed: 25 passed, 3 warnings. `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q -k "recover or reconnect_audio or end"` passed: 21 passed, 22 deselected. Full `npm run test:e2e -- call-start.spec.ts` passed: 34 passed. `npm run build` passed. `git diff --check` passed.
  implication: The fix is stable across adjacent backend session lifecycle, WebRTC signaling, Web UI call facade, browser reconnect/hangup flows, and Svelte production build; it is ready for atomic commit and canonical OMEN deployment.

- timestamp: 2026-05-13T13:34:20Z
  checked: Atomic code commit.
  found: Committed `2d00461f6d233338fb6562446874a466945e1b9b` (`fix(call): finalize stalled reconnect backfill`) with only `ai-backend/app/call/session.py`, `ai-backend/tests/test_call_session.py`, `web-ui/client/src/routes/call/[threadId]/+page.svelte`, and `web-ui/client/tests/e2e/call-start.spec.ts`. The only remaining local dirty files are this debug session and pre-existing Phase 03.1 evidence notes.
  implication: The verified fix is isolated in one code/test commit and ready to push/deploy through the canonical OMEN path.

- timestamp: 2026-05-13T13:38:56Z
  checked: Push, canonical OMEN deployment, and post-deploy readiness.
  found: Pushed `main` from `85bbacc` to `2d00461`. `scripts/deploy-omen.sh` fast-forwarded OMEN to `2d00461f6d233338fb6562446874a466945e1b9b`, verified CUDA runtime (`torch 2.10.0+cu126`, CUDA 12.6, NVIDIA GeForce RTX 3060), built the web client, recreated canonical `RayMePhase1AI` / `RayMePhase1Web` scheduled tasks, started listeners on `192.168.1.199:9443` and `192.168.1.199:8443`, and reported `OMEN deploy complete`. Read-only post-deploy checks show OMEN checkout at `2d00461` with no git status output, `/webrtc/status` returns `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, `active_sessions=0`, and scheduled tasks are running with `Task To Run` set to `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`.
  implication: The fix is deployed through the only approved path and ready for physical Android Chrome product-owner acceptance. Generic `/health` remains `status=degraded` because the current resident TTS engine is `f5`, but call-specific WebRTC readiness is green.

- timestamp: 2026-05-13T13:09:05Z
  checked: Android product-owner acceptance after Phase 03.1 OMEN live dual-engine evidence.
  found: User reports the physical Android Chrome call listened to a short message, then froze on a longer message of about one minute. After choosing to hang up, the call remained stuck in the call UI. The long-turn freeze is a regression against this session's missing-chunks target; the hangup freeze is a new hang-up deadlock failure mode unless logs prove the exact path existed before.
  implication: Phase 03.1 plan `03.1-07` must remain incomplete. Android acceptance is failed, not approved. The next investigation must inspect fresh OMEN artifacts from deployed commit `85bbacc919c83d1b486883e616156b2d8778c3f5` and must not mark the phase complete until long-turn and hangup cleanup pass on the physical device.

- timestamp: 2026-05-02T17:11:52Z
  checked: Canonical OMEN deployment and post-deploy readiness for `b71fcdd`.
  found: Pushed `main` from `74450da` to `b71fcdd`. `scripts/deploy-omen.sh` fast-forwarded OMEN to `b71fcddc59e787a7a117be49b25d4785b98b4e77`, verified the CUDA runtime, built the web client, recreated and started `RayMePhase1AI` / `RayMePhase1Web`, and reported `OMEN deploy complete`. OMEN checkout is `b71fcdd` with no reported repo dirt. `/webrtc/status` returns `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, and `active_sessions=0`. Scheduled tasks are running and point to `C:\Users\pmpg\rayme\start-ai-backend.cmd` / `C:\Users\pmpg\rayme\start-web-ui.cmd`.
  implication: The delayed reconnect-tail fix is live through the only approved deployment path and ready for the user to rerun the clean phone-call repro.

- timestamp: 2026-05-02T17:09:57Z
  checked: Runtime fix commit.
  found: Committed `b71fcdd` (`fix(call): preserve delayed reconnect backfill tail`) with `web-ui/client/src/lib/call/reconnectBackfill.ts`, `web-ui/client/src/routes/call/[threadId]/+page.svelte`, and `web-ui/client/tests/unit/reconnect-backfill.test.ts`.
  implication: The verified code fix is ready to push and deploy through the canonical OMEN script.

- timestamp: 2026-05-02T17:08:36Z
  checked: Local fix and verification for delayed reconnect-tail selection.
  found: Implemented a client reconnect-backfill selector helper. Initial reconnect selection still applies the 30s pre-roll cap, but tail selection now resumes from `reconnectAudioBackfillLastEndMs` without reapplying the latest-window cap. Increased the rolling local microphone PCM buffer to 180s so delayed tail selection can still access the contiguous unsent span. Verification passed: `npm run test:unit -- reconnect-backfill.test.ts` (2 passed), focused reconnect Playwright (10 passed), `npm run build`, full `npm run test:e2e -- call-start.spec.ts` (30 passed), full `npm run test:unit` (90 passed), and `git diff --check`.
  implication: The reproduced selector boundary is fixed locally and adjacent call reconnect/end/recovery flows still pass.

- timestamp: 2026-05-02T17:01:45Z
  checked: RED client regression for delayed reconnect-tail selection.
  found: Added focused Vitest coverage for reconnect backfill selection. `npm run test:unit -- reconnect-backfill.test.ts` failed as expected: the delayed tail test expected `selection.startMs` to be `35000`, but current code returned `69000`; the initial capped pre-roll test passed.
  implication: The latest OMEN gap is reproduced locally at the selector boundary. The fix should change tail selection, not backend STT or Web UI persistence.

- timestamp: 2026-05-02T16:58:49Z
  checked: Latest OMEN runtime and artifact snapshot after failed human verification of `74450da`.
  found: OMEN checkout is `74450da2c961e76f5cef0a5973a2e37833d62b5f` with no reported repo dirt. `/webrtc/status` is ready with `live_call_ready=true`, `media_transport_ready=true`, and `active_sessions=0`. Scheduled tasks are running and point to `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`. Active logs and SQLite were copied to `/tmp/rayme-phone-debug-74450da-failed-2026-05-02/`.
  implication: The failed repro ran against the intended deployed code and canonical OMEN task/launcher setup; deployment drift is not the current boundary.

- timestamp: 2026-05-02T16:58:49Z
  checked: Latest persisted call after `74450da`.
  found: Newest repro is `call_54dc73bdeb1144549c77667b557ce2a6` / `rtc_db972418f201449c88667141c6fafda6` on `thread_c23ed9dfdcd64f23b007f7f8e75045dc`. SQLite stores `call_start` at `2026-05-02 16:47:20`, `user_speech` at `16:50:48` with length 607, `ai_speech` at `16:50:50`, and `call_end` at `16:51:08`. The user transcript stops after "faithful beyond all our expressions of faith" and omits the final expected poem section beginning "our deepest prayers."
  implication: Persistence contains the same partial transcript the user saw. The missing ending was already absent before durable `/turns` storage.

- timestamp: 2026-05-02T16:58:49Z
  checked: Browser reconnect-backfill debug events for `call_54dc73...`.
  found: The browser selected and sent reconnect backfill chunks covering offsets `5226-15226`, `15226-25226`, `25226-35226`, and `35226-35256` with speech-level RMS. Later, after reconnect work continued, it selected only offsets `69467-79467`, `79467-89467`, and `89467-99412`, all near silence. No browser request covered the contiguous `35256-69467` span.
  implication: The first loss boundary is client-side reconnect backfill selection. A middle microphone-buffer span is dropped before the AI backend can append it or send it to STT.

- timestamp: 2026-05-02T16:58:49Z
  checked: AI backend logs for `rtc_db972...`.
  found: Backend backfill application exactly matches the browser gap: speech batches 1-4, then near-silent batches 5-7. It finalized after the final silent batch, trimmed trailing silence, and ran STT on `frames=2509`, producing `transcript_len=607`. The data channel was closed, but `/events/drain` returned the queued `user_final`, and Web UI `/turns` persisted it.
  implication: Backend STT, recoverable event drain, and Web UI persistence worked on the audio they received. They could not recover the omitted `35256-69467` microphone span.

- timestamp: 2026-05-02T16:54:00Z
  checked: Resume setup after failed human verification of `74450da`.
  found: Required debug file and repo rules were read. No project-local skill directories or debug knowledge base are present. Common bug pattern scan points first to Async/Timing, State Management, and Data Shape/API Contract boundaries because the call fails before a delayed partial transcript is persisted and playback remains user-visible.
  implication: Prior transactional reoffer diagnosis must be treated as eliminated for the live workflow. The next test must use fresh OMEN evidence and identify the current first failed boundary before any fix.

- timestamp: 2026-05-02T16:52:16Z
  checked: User live verification after OMEN deployment of `74450da2c961e76f5cef0a5973a2e37833d62b5f`.
  found: User repeated the repro and reports it worked the same: the top of the call says it failed right before the transcription appears; the transcription is still partial; the transcription takes about two minutes, which is far too long.
  implication: The transactional reoffer fix did not resolve the live failure. The active target is no longer just inaudible AI playback; the call still enters failed state before delayed/partial transcript recovery completes.

- timestamp: 2026-05-02T16:34:05Z
  checked: Resume baseline after latest human verification.
  found: SSH works as `omen-pc\rayme-ssh` and `omen-pc\pmpg`. Local checkout is `028bb0ff4351c7ce2254cc97a93262af55b22d48` with only this debug file dirty.
  implication: The continuation is on the deployed fix commit locally, and remote artifact collection can proceed without first repairing SSH or local checkout drift.

- timestamp: 2026-05-02T16:36:04Z
  checked: OMEN runtime state after the latest post-`028bb0f` repro.
  found: OMEN checkout is `028bb0ff4351c7ce2254cc97a93262af55b22d48` with no repo dirt. `GET /webrtc/status` returns `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, and `active_sessions=0`. `RayMePhase1AI` and `RayMePhase1Web` are running and point to `C:\Users\pmpg\rayme\start-ai-backend.cmd` / `start-web-ui.cmd`; those launchers cd into `C:\Users\pmpg\rayme\RayMe` and run the repo scripts.
  implication: The latest repro ran against the intended deployed code and canonical launcher/task setup; deployment drift is not the current first failed boundary.

- timestamp: 2026-05-02T16:35:09Z
  checked: Latest copied OMEN artifact snapshot at `/tmp/rayme-phone-debug-028bb0f-post-audio-fail/`.
  found: Newest repro call is `call_5a5ea16d3e8345898b8a90f40d21fc70` / `rtc_25f8427bdfa74337a056a78e9783ec73` on `thread_c23ed9dfdcd64f23b007f7f8e75045dc`. SQLite persisted `call_start` at `2026-05-02 16:24:46`, a `user_speech` row at `16:28:10`, an `ai_speech` row at `16:28:12`, and `call_end` at `16:28:31`. Web UI logs show `/turns` returned 200 and emitted `call.ai_audio_started` with about 10.8s of audio, but `speakingRms=0`. AI backend logs show the media peer/data channel had already closed, `/speak` enqueued 11.055s of TTS audio to the track, `event.skip_channel_not_open type=ai_audio_started`, then `track.wait_until_idle.timeout recv_count=0 queue_size=1`, `tts.playback_wait.done completed=False`, and `event.skip_channel_not_open type=ai_done`.
  implication: The first failed boundary has moved beyond transcript persistence and AI generation. The current failure is that TTS/audio playback is attempted after the WebRTC output path is already dead, so generated audio is accepted but not actually delivered audibly to the caller.

- timestamp: 2026-05-02T16:38:22Z
  checked: Focused failed-reoffer regression.
  found: Added `test_failed_reconnect_offer_preserves_existing_session_media`. It failed on current code because a simulated second `/webrtc/offer` negotiation failure left `session.peer_connection` pointing at the new failed peer instead of the original peer. After the transactional reoffer fix, the same test passed: 1 passed, 16 deselected.
  implication: The OMEN audio failure mechanism is now reproduced locally and fixed at the media-session mutation boundary.

- timestamp: 2026-05-02T16:42:11Z
  checked: Regression verification after transactional reoffer fix.
  found: `uv run --project ai-backend pytest ai-backend/tests/test_webrtc_signaling.py -q` passed: 17 passed, 3 warnings. `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` passed: 39 passed. Full `uv run --project ai-backend pytest ai-backend/tests -q` passed: 101 passed, 3 warnings. Focused Web UI call facade checks passed: 22 passed, 6 deselected. `git diff --check` passed.
  implication: The fix covers the reproduced boundary and does not regress adjacent backend call lifecycle, WebRTC signaling, TTS playout, event recovery, reconnect-audio, `/turns`, or `/end` behavior.

- timestamp: 2026-05-02T16:43:18Z
  checked: Code commit and push.
  found: Committed `74450da` (`fix(call): preserve media on failed reconnect offer`) with `ai-backend/app/api/webrtc.py`, `ai-backend/app/call/session.py`, and `ai-backend/tests/test_webrtc_signaling.py`; pushed `main` from `028bb0f` to `74450da`. The debug session file remains the only expected local dirty file.
  implication: The verified fix is available for OMEN deployment through the canonical script.

- timestamp: 2026-05-02T16:45:06Z
  checked: Canonical OMEN deployment and post-deploy readiness.
  found: `scripts/deploy-omen.sh` fast-forwarded OMEN from `028bb0f` to `74450da2c961e76f5cef0a5973a2e37833d62b5f`, verified CUDA/GPU runtime, built the web client, recreated and started `RayMePhase1AI` / `RayMePhase1Web`, and reported `OMEN deploy complete`. OMEN checkout is `74450da` with no repo dirt. `/webrtc/status` returns `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, and `active_sessions=0`. Scheduled tasks are running and point to `C:\Users\pmpg\rayme\start-ai-backend.cmd` / `start-web-ui.cmd`; launchers cd into `C:\Users\pmpg\rayme\RayMe` and run the repo command lines.
  implication: The transactional reoffer fix is live through the only approved deployment path and ready for a real phone-call repro.

- timestamp: 2026-05-02T16:30:51Z
  checked: User live verification after OMEN deployment of `028bb0ff4351c7ce2254cc97a93262af55b22d48`.
  found: User repeated the repro. They are not sure whether the whole poem was transcribed, but they now see some transcript content. After about two minutes, the AI generated text, but the user could not hear it because it was not played in the call; then the call failed.
  implication: The backend post-end retention fix likely improved transcript recovery, but the remaining first user-visible failure has moved downstream to assistant response delivery: durable AI text generation may be happening while TTS/audio playback or terminal media recovery still fails.

- timestamp: 2026-05-02T12:56:21Z
  checked: Local/OMEN baseline after latest checkpoint response.
  found: Local and OMEN checkouts are both `330e0f216f505cc9ae9feb86da572bf672a349f3` (`fix(call): recover terminal reconnect failures`), with only this debug file dirty locally. SSH works as `omen-pc\rayme-ssh` and `omen-pc\pmpg`. Scheduled tasks `RayMePhase1AI` and `RayMePhase1Web` are running and point to canonical `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`. The launchers run the repo scripts written by `scripts/deploy-omen.sh`. `/webrtc/status` is ready with `active_sessions=0`.
  implication: Deployment drift, noncanonical launchers, and stale active backend sessions are not the first explanation for the latest post-`330e0f2` failure.

- timestamp: 2026-05-02T12:57:39Z
  checked: Copied OMEN DB/log snapshot at `/tmp/rayme-phone-debug-330e0f2-latest/` for the latest clean repro.
  found: Newest post-`330e0f2` call is `call_39aa8c2ad9e34503b961444f224d567e` / `rtc_4708d47d025a430ca4eead1aea298c9a` on `thread_c23ed9dfdcd64f23b007f7f8e75045dc`. SQLite has `call_start` at `2026-05-02 12:47:16.032015` and `call_end` at `2026-05-02 12:50:44.299209`, with no `user_speech` or `ai_speech` rows for that call window. Backend accepted six reconnect backfill batches, finalized on batch 6, started STT with `frames=2553`, drained one queued `failed` event, then `/end` succeeded. After `/end`, STT completed with `transcript_len=504`, queued `user_final`, and the following `/events/drain` returned `404 Not Found`. Browser/Web UI logs match: final `/reconnect-audio` surfaced as 502, recovery drained one event (`failed`), second recovery drained zero events, `/end` returned 200, and retry recovery failed with 502. No `/turns` request occurred for the call.
  implication: The previous fix moved the boundary forward but still races: terminal cleanup ends/removes the backend session while final backfill STT is still in flight, so the transcript is generated after the only successful recovery drains and after the session is no longer recoverable.

- timestamp: 2026-05-02T13:00:36Z
  checked: Full client/server/backend call cleanup and recovery paths.
  found: The Svelte terminal cleanup awaits the final reconnect backfill promise, recovers missed events, then posts `/end`; when the final backfill request itself surfaces as 502, that await only confirms the Web UI facade request finished, not that backend STT has stopped running. Web UI `/events/recover` maps backend drain 404 to a browser-visible 502. AI backend `/webrtc/sessions/{id}/end` calls `session.end(...)` and immediately removes the session from `CallSessionManager._sessions`; `CallSession.finalize_user_turn()` can still finish afterward, queue recoverable `user_final`, and currently does not preserve terminal `ended` state if that completion happens after `/end`.
  implication: The remaining first-loss boundary is backend session lifetime. The existing browser retry recovery would have had a chance to persist the transcript if the ended session remained drainable for a short grace window after `/end`.

- timestamp: 2026-05-02T13:00:56Z
  checked: RED backend route regression `test_webrtc_events_drain_returns_late_user_final_after_end`.
  found: The test creates a call session, posts `/webrtc/sessions/{id}/end`, queues a recoverable `user_final` on the still-running session object, then posts `/events/drain`. Current code returns `404 Not Found` instead of the queued event.
  implication: This directly reproduces the latest OMEN failure mechanism locally: `/end` makes late STT output unreachable even though the `CallSession` can still queue it.

- timestamp: 2026-05-02T13:02:00Z
  checked: Post-fix focused backend route regression.
  found: `uv run --project ai-backend pytest ai-backend/tests/test_webrtc_signaling.py -q -k "late_user_final_after_end"` passed: 1 passed, 15 deselected.
  implication: The ended session remains drainable for a late recoverable `user_final` while the manager still reports zero active sessions.

- timestamp: 2026-05-02T13:02:43Z
  checked: Focused AI backend lifecycle regression coverage.
  found: `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` passed: 39 passed. `uv run --project ai-backend pytest ai-backend/tests/test_webrtc_signaling.py -q` passed: 16 passed, 3 warnings.
  implication: The fix does not regress existing call-session state handling, WebRTC control routes, reconnect backfill, or event drain behavior.

- timestamp: 2026-05-02T13:03:29Z
  checked: Full AI backend regression suite and whitespace check.
  found: `uv run --project ai-backend pytest ai-backend/tests -q` passed: 100 passed, 3 warnings. `git diff --check` passed.
  implication: The backend retention fix is stable under the full AI backend test suite and introduces no whitespace errors.

- timestamp: 2026-05-02T13:04:10Z
  checked: Web UI server facade coverage and final diff inspection.
  found: `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q -k "recover or reconnect_audio or end"` passed: 18 passed, 10 deselected. Final code diff is limited to AI backend `/end` routing, `CallSessionManager` post-end retention/state preservation, and the new backend route regression.
  implication: The Web UI call facade contract remains compatible; the patch is ready to commit and deploy via `scripts/deploy-omen.sh`.

- timestamp: 2026-05-02T13:04:37Z
  checked: Code commit and push.
  found: Committed `028bb0f` (`fix(call): keep ended sessions recoverable briefly`) with `ai-backend/app/api/webrtc.py`, `ai-backend/app/call/session.py`, and `ai-backend/tests/test_webrtc_signaling.py`; pushed `main` from `330e0f2` to `028bb0f`. The active debug file remains uncommitted.
  implication: The verified backend fix is available for the canonical OMEN deployment script to pull from `origin/main`.

- timestamp: 2026-05-02T13:06:02Z
  checked: Canonical OMEN deployment.
  found: `scripts/deploy-omen.sh` fast-forwarded OMEN from `330e0f2` to `028bb0ff4351c7ce2254cc97a93262af55b22d48`, verified the GPU runtime, built the web client, recreated `RayMePhase1AI` and `RayMePhase1Web`, started listeners on `192.168.1.199:9443` and `192.168.1.199:8443`, and reported `OMEN deploy complete: 028bb0f...`. Generic `/health` reported `status=degraded`, so call-specific readiness still needs direct verification.
  implication: The fix is deployed through the only approved script. A direct `/webrtc/status` check is needed before the human retest checkpoint.

- timestamp: 2026-05-02T13:06:42Z
  checked: OMEN post-deploy runtime verification.
  found: OMEN checkout is `028bb0ff4351c7ce2254cc97a93262af55b22d48` with no reported repo dirt. Scheduled tasks `RayMePhase1AI` and `RayMePhase1Web` point to canonical `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`; launcher contents are the canonical repo command lines written by `scripts/deploy-omen.sh`. `GET https://192.168.1.199:9443/webrtc/status` returned `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, and `active_sessions=0`. Local checkout is also `028bb0f`, with only this debug file dirty.
  implication: The fix is live on OMEN and ready for the user to repeat the clean phone-call repro.

- timestamp: 2026-05-02T12:53:47Z
  checked: User live verification after OMEN deployment of `330e0f216f505cc9ae9feb86da572bf672a349f3`.
  found: User repeated the same clean poem repro. The call still did not transcribe. About two minutes and a few seconds after the user stopped speaking, the call failed by itself. The visible thread log now shows both `call_start` and `call_end`.
  implication: The deployed terminal reconnect cleanup changed the durable failure boundary: `/end` now reaches persistence, but the transcript still does not. The next investigation should focus on the remaining gap between backend STT/recoverable `user_final` production and Web UI `/turns` persistence during terminal failure cleanup.

- timestamp: 2026-05-02T04:05:44Z
  checked: Continuation baseline after the clean repro checkpoint.
  found: SSH works as `omen-pc\rayme-ssh` and `omen-pc\pmpg`. Local and OMEN checkouts are both `d8c38d5800c8b57e3d71d1b09f4b4ca9ab0f1668` (`fix(call): recover user final after reconnect`), with only this debug file dirty locally. Scheduled tasks `RayMePhase1AI` and `RayMePhase1Web` are running and point to the canonical `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`. `/webrtc/status` is ready and reports `active_sessions=2`.
  implication: The clean repro ran against the intended deployed commit and canonical launchers. The two active backend sessions after the failed call are direct evidence that cleanup/end did not complete for all post-checkpoint sessions.

- timestamp: 2026-05-02T04:08:48Z
  checked: Clean repro Web UI SQLite, web logs, browser debug events, and AI backend logs copied to `/tmp/rayme-phone-debug-clean-2026-05-02/`.
  found: The only new durable call after the ambiguous `03:09`/`03:10` sequence is `call_a5502db31dce4a879066617fce01e92c` / `rtc_f926d6a174b8484c98189ec251236453` on `thread_c23ed9dfdcd64f23b007f7f8e75045dc`, with SQLite `call_start` at `2026-05-02 03:56:40.209161` and no later `call_end`, `user_speech`, or `ai_speech`. Browser logs show no `/events/recover`, no `/turns`, and no `/end` for this call. Backend logs show live speech reached VAD, reconnect backfill batches reached the backend, final backfill triggered `stt.begin ... frames=3400`, `stt.result ... transcript_len=602`, then `event.skip_channel_not_open type=user_final readyState=closed` and `event.queued_undelivered ... pending=2`. Browser logs show reconnect attempt 2 failed with `/api/calls/call_a550.../offer` returning `502`, then `mic.keep_live prevState=listening nextState=failed`, data channel close, Return-to-Thread navigation, and final backfill fetch failure.
  implication: STT and backend recovery queuing worked. The current first durable loss boundary is browser terminal reconnect failure: the client never drained the queued backend event and never ended the active call after giving up.

- timestamp: 2026-05-02T04:11:17Z
  checked: RED Playwright regression for terminal reconnect failure cleanup.
  found: Added `recovers queued turn and ends when terminal media reconnect fails` to `web-ui/client/tests/e2e/call-start.spec.ts`, simulating a first successful reconnect, a second `/offer` 502, and a queued recoverable `user_final`. `npm run test:e2e -- call-start.spec.ts -g "recovers queued turn and ends when terminal media reconnect fails"` failed in both desktop and mobile Chromium because `counters.recoverCount` stayed `0`.
  implication: This directly reproduces the clean repro boundary in the browser: terminal reconnect failure abandons queued recoverable events instead of calling `/events/recover`, and therefore cannot post `/turns` or `/end`.

- timestamp: 2026-05-02T04:14:43Z
  checked: Local fix for terminal media reconnect failure cleanup.
  found: Updated the call page so terminal reconnect failure calls a shared cleanup path before showing the failed panel. Cleanup waits for any pending final reconnect backfill promise, drains `/events/recover`, lets recovered `user_final` events use the existing `/turns` path, and posts `/end` with reason `connection_failed`. Also updated the existing reconnect give-up test so it no longer encodes the broken no-end behavior. The RED test now passes in desktop and mobile Chromium: 2 passed.
  implication: The exact browser-side loss boundary from `call_a550...` is covered locally. Broader reconnect and build verification is still required before deployment.

- timestamp: 2026-05-02T04:16:22Z
  checked: Focused reconnect cleanup regression coverage.
  found: `npm run test:e2e -- call-start.spec.ts -g "recovers queued turn and ends when terminal media reconnect fails|recovers and ends after the reconnect attempt limit gives up"` passed in desktop and mobile Chromium: 4 passed.
  implication: Both terminal reconnect paths now recover queued events and end the call in focused browser coverage.

- timestamp: 2026-05-02T04:19:22Z
  checked: Broader client verification after terminal reconnect cleanup fix.
  found: Full `npm run test:e2e -- call-start.spec.ts` passed: 30 passed. `npm run build` passed. `git diff --check` passed.
  implication: The focused fix does not regress existing call start/reconnect/end browser coverage, and the Svelte client still builds.

- timestamp: 2026-05-02T04:21:18Z
  checked: Commit, push, canonical OMEN deployment, and post-deploy readiness.
  found: Committed `330e0f216f505cc9ae9feb86da572bf672a349f3` (`fix(call): recover terminal reconnect failures`) with only `web-ui/client/src/routes/call/[threadId]/+page.svelte` and `web-ui/client/tests/e2e/call-start.spec.ts`, pushed `main`, and deployed via `scripts/deploy-omen.sh`. OMEN fast-forwarded to `330e0f2`, rebuilt the web client, rewrote canonical scheduled task launchers, recreated/started `RayMePhase1AI` and `RayMePhase1Web`, and reported `OMEN deploy complete`. Post-deploy OMEN checkout is `330e0f2`; `/webrtc/status` is ready with `active_sessions=0`; scheduled tasks are running and point to `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`.
  implication: The fix is live on OMEN through the only approved deployment path and ready for user verification.

- timestamp: 2026-05-02T03:18:56Z
  checked: User report from another structured poem repro after the latest recovery work.
  found: User reports the call failed again. It froze, then after almost two minutes the call failed by itself; the user did not need to end it manually. The poem was again not transcribed.
  implication: The prior fix is not user-verified. The next investigation must treat this as fresh live evidence, verify the exact deployed/runtime commit first, and inspect the newest call/session/log artifacts before assuming the previous `event.skip_channel_not_open` mechanism is still the only boundary.

- timestamp: 2026-05-02T03:20:09Z
  checked: Local and SSH baseline before inspecting OMEN.
  found: `ssh rayme-ssh whoami` returned `omen-pc\rayme-ssh`; `ssh rayme-pmpg whoami` returned `omen-pc\pmpg`. Local checkout is `d8c38d5800c8b57e3d71d1b09f4b4ca9ab0f1668`, with only `.planning/debug/phone-calls-missing-chunks.md` modified.
  implication: OMEN is reachable for read-only inspection, and local source changes have not yet confounded runtime evidence.

- timestamp: 2026-05-02T03:21:41Z
  checked: OMEN checkout and scheduled task targets.
  found: OMEN repo at `C:\Users\pmpg\rayme\RayMe` is `d8c38d5800c8b57e3d71d1b09f4b4ca9ab0f1668` (`fix(call): recover user final after reconnect`). Scheduled tasks `RayMePhase1AI` and `RayMePhase1Web` are running and their `Task To Run` values are the canonical `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`.
  implication: The latest user repro ran against the intended post-recovery commit and canonical launchers; deployment-target drift is not the first explanation.

- timestamp: 2026-05-02T03:22:59Z
  checked: OMEN runtime launchers and AI backend status.
  found: Canonical launchers run AI backend via `ai-backend\scripts\run_https.py` bound to `192.168.1.199:9443` and Web UI via `web-ui\server\scripts\run_dev_https.py` bound to `192.168.1.199:8443`, appending to `C:\Users\pmpg\rayme\logs\ai-backend.run.log` and `C:\Users\pmpg\rayme\logs\web-ui.run.log`. `GET https://192.168.1.199:9443/webrtc/status` returned `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, and `active_sessions=1`.
  implication: The newest failed repro likely left a live/stale backend session after the browser-visible call failure. The first current boundary may involve session failure/cleanup or reconnect-state hang, not only closed-channel `user_final` delivery.

- timestamp: 2026-05-02T03:26:55Z
  checked: User correction about latest repro sequence.
  found: User clarified there was only one structured repro in the latest window. Before it, there was one failed call where the user reloaded the `Return to Thread` dialog; the call page always resumes/creates a new call after reload, and the user clicked Back. That earlier call should be treated as reload/back noise and likely stale-session source, not as a second structured repro.
  implication: The structured repro under investigation is `call_6552125159374c8090432bd0d1e7daa2` / `rtc_b9c682d948384f3fbf8a4db34188c9cb`. Any active-session leak from the earlier 03:09 reload/back call is secondary unless logs show it interfered with this repro.

- timestamp: 2026-05-02T03:29:20Z
  checked: User clarification after reloading again.
  found: User initially reported the last repro yielded no thread transcript, only `call started` and `call ended`, then reloaded again and saw that a transcript may have appeared despite the call UI saying the call failed and no audio being heard.
  implication: This sequence is ambiguous: delayed event recovery can persist a `user_final`/AI response after the call UI has already entered a failed transport state. A clean repro with no reload/back during the call is needed to identify the current first boundary without conflating recovery timing, failed UI state, and thread persistence.

- timestamp: 2026-05-02T04:02:53Z
  checked: User clean repro response after debugger checkpoint.
  found: User opened a fresh repro as requested. The same failure happened: the poem was not transcribed, and after about two minutes the call failed by itself. The visible log shows `call_start` but not `call_end`.
  implication: This is the clean target window for the next investigation. Inspect only calls created after the checkpoint, and pay special attention to why `call_end` is absent after the UI self-failure.

- timestamp: 2026-05-02T02:12:18Z
  checked: OMEN read-only state, Web UI API, and SQLite after `e201a67` / runtime `9e50387`.
  found: OMEN checkout is `e201a674c0cb49ded7bfbf9b04fc35ff28917e9d` and `/webrtc/status` is ready with `active_sessions=0`. The newest two post-deploy calls are `call_4cf61efa73ee499ca2b58fe0333c7bf8` / `rtc_0782b6f8e8ca4ae080a5b60d794b0e84` on `thread_c23ed9dfdcd64f23b007f7f8e75045dc`, from `2026-05-02T01:48:10.918381` to `2026-05-02T01:52:24.011747`; and `call_dddb0772457d454f95692a9f9d26c5b2` / `rtc_1871897e998c4e8d8aae17757b7881ae` on the same thread, from `2026-05-02T01:52:42.762162` to `2026-05-02T01:56:05.401756`. API and SQLite contain only `call_start`/`call_end` rows for both calls, with no `user_speech` or `ai_speech`.
  implication: The user-visible "STT never worked" symptom is real at persistence/UI level, but persistence alone does not prove backend STT failed.

- timestamp: 2026-05-02T02:12:18Z
  checked: AI backend logs for the two newest post-`9e50387` sessions.
  found: `rtc_0782b6f8e8ca4ae080a5b60d794b0e84` had `vad.speech_start`, applied reconnect backfill batch 1 with `duration_ms=29944`, `bytes=958230`, `rms=2286.9`, `peak=24183.0`, `speech_seen=True`, `overlap_trimmed_frames=0`, finalized after reconnect grace, then ran `stt.begin ... frames=2510` and `stt.result ... transcript_len=602`; immediately after, backend logged `event.skip_channel_not_open ... type=user_final readyState=closed`. `rtc_1871897e998c4e8d8aae17757b7881ae` had the same shape: `vad.speech_start`, backfill batch 1 `duration_ms=29944`, `bytes=958230`, `rms=1656.4`, `peak=19047.0`, `overlap_trimmed_frames=0`, then `stt.begin ... frames=2534`, `stt.result ... transcript_len=630`, and `event.skip_channel_not_open ... type=user_final readyState=closed`.
  implication: The first durable loss boundary is after STT, at `user_final` delivery on a closed data channel. Backend overlap-only trimming did not remove the turn, and VAD/finalization starvation did not prevent STT.

- timestamp: 2026-05-02T02:12:18Z
  checked: Web logs and browser debug events for reconnect-audio and data-channel behavior.
  found: For `call_4cf61efa73ee499ca2b58fe0333c7bf8`, the browser sent two real-speech reconnect backfill batches around `29945ms` each (`samples=479115`); both browser-facing `/reconnect-audio` requests failed with `RayMe API request failed: 502 Bad Gateway`, while backend accepted only the first batch before STT and later skipped `state=thinking` requests. For `call_dddb0772457d454f95692a9f9d26c5b2`, the same pattern repeated: two `29945ms` real-speech batches failed as browser-facing 502s, backend accepted only batch 1, and later state=thinking backfills were skipped. Browser data-channel diagnostics for both calls contain only `ping` events and no `user_final`.
  implication: `9e50387` is strongly implicated as the regression trigger: it widened browser reconnect backfill to 30s chunks and raised backend/web request caps, and both post-deploy calls hit the new large-upload 502/reconnect-churn pattern. This is not a hard body-size rejection because the decoded backend payload was accepted and below the new cap; it is likely timeout/transport churn around large reconnect uploads exposing the existing lack of durable `user_final` delivery when the channel closes.

- timestamp: 2026-05-02T02:27:11Z
  checked: Local fix for post-STT `user_final` loss and large reconnect backfill 502s.
  found: Browser reconnect backfill now splits selected mic PCM into <=10s batches while preserving a final marker on the last tail batch. AI backend queues recoverable `user_final`/`failed` events when the data channel is missing, closed, or send fails, and exposes a drain endpoint. Web UI exposes `/api/calls/{call_id}/events/recover`; the browser calls it immediately and once more after reconnect-audio failure, and also before hangup. Duplicate `user_final` handling remains guarded by turn id.
  implication: The known post-`9e50387` loss boundary is directly covered: large 30s requests are avoided, and a closed data channel no longer makes STT output unrecoverable.

- timestamp: 2026-05-02T02:27:11Z
  checked: Local verification for the recovery/chunking fix.
  found: Focused AI backend event recovery tests passed. Focused Web UI server recovery/reconnect tests passed. Focused browser reconnect recovery tests passed: 6 passed. Full `uv run --project ai-backend pytest ai-backend/tests -q` passed: 99 passed, 3 warnings. Full `uv run --project web-ui/server pytest web-ui/server/tests -q` passed: 153 passed. `npm run build` passed. Full `npm run test:e2e -- call-start.spec.ts` passed: 28 passed. `git diff --check` passed.
  implication: The fix is ready to commit and deploy for live repro validation.

- timestamp: 2026-05-02T01:58:01Z
  checked: User report after OMEN deployed `e201a67` / runtime `9e50387`.
  found: User ran one structured first-turn poem repro and STT never worked despite waiting two minutes before ending the call. User repeated an identical second repro and STT again did not work. User asked to note the previous commit as a possible future rollback target.
  implication: This is a worse post-`9e50387` regression than partial poem truncation. Record `47f41c7` as the immediate pre-regression rollback candidate, with `6607214` still preserved as the earlier recovery snapshot.

- timestamp: 2026-05-02T00:39:38Z
  checked: Local fix for the post-`47f41c7` poem truncation mechanism.
  found: Browser reconnect backfill now keeps a 35s rolling mic buffer and selects up to 30s before/through reconnect instead of 250ms. The inactive start sentinel changed from `0` to `-1` because `0ms` is a valid widened backfill start shortly after page load. Web UI and AI backend reconnect-audio request limits now accept the wider payload. Backend `CallSession` trims reconnect backfill overlap against already-received live turn frames before appending, and trims long trailing silence before STT while retaining about 400ms of tail.
  implication: The fix targets the newly proven first-loss boundary without reintroducing the failed post-`6607214` reconnect stack. It also addresses the phantom ending by avoiding STT on a long silent tail.

- timestamp: 2026-05-02T00:39:38Z
  checked: Local regression and integration verification for the wider reconnect backfill fix.
  found: `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` passed: 38 passed. `uv run --project web-ui/server pytest web-ui/server/tests -q` passed: 152 passed. `uv run --project ai-backend pytest ai-backend/tests -q` passed: 97 passed, 3 warnings. `npm run build` passed. Focused reconnect Playwright passed: 8 passed. Full `npm run test:e2e -- call-start.spec.ts` passed: 26 passed. `git diff --check` passed.
  implication: The local patch is ready for commit/deployment. Live verification still requires OMEN deployment through the canonical script and another structured poem repro.

- timestamp: 2026-05-02T00:42:33Z
  checked: Canonical OMEN deployment and post-deploy readiness for `9e50387`.
  found: Committed and pushed `9e50387` (`fix(call): widen reconnect speech backfill`), then deployed with `scripts/deploy-omen.sh`. OMEN fast-forwarded to `9e50387af584f0e1f284230fdfa8ffac6dedf6c8`, rebuilt the web client, rewrote the canonical launchers, recreated/started scheduled tasks `RayMePhase1AI` and `RayMePhase1Web`, and reported `OMEN deploy complete`. `GET https://192.168.1.199:9443/webrtc/status` returned `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, and `active_sessions=0`. Scheduled tasks point to `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`. SQLite remained present at `C:\Users\pmpg\rayme\RayMe\web-ui\server\data\rayme.sqlite3`, length `856064`.
  implication: The wider reconnect backfill fix is live on OMEN. The next evidence needed is the user's repeated first-turn poem repro.

- timestamp: 2026-05-02T00:19:40Z
  checked: OMEN deployed state and readiness after user tested deployed `47f41c7`.
  found: Local and OMEN checkouts are `47f41c764eacfab2b4107f87df1d887485c67ee6` (`docs(debug): record hangup backfill deployment`). `GET https://192.168.1.199:9443/webrtc/status` returned `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, and `active_sessions=0`. Active logs were copied read-only to `/tmp/rayme-phone-debug-47f41c7-2026-05-02/`.
  implication: The user repro ran against the intended deployed snapshot and no active call was left running.

- timestamp: 2026-05-02T00:19:40Z
  checked: Newest post-`47f41c7` call/session/thread and persisted transcript through API and copied SQLite.
  found: Newest valid repro is `call_1c544ed3b58d4976a883fdd2cb7faab1` / `rtc_88142006de7d42d7bb54874b4ac9db4b` on `thread_c23ed9dfdcd64f23b007f7f8e75045dc`. SQLite/API store `call_start` at `2026-05-02T00:08:12.000021`, `user_speech` at `2026-05-02T00:10:03.069035` with length 391, `ai_speech` at `2026-05-02T00:10:08.583636`, and `call_end` at `2026-05-02T00:10:25.018512`.
  implication: Persistence is not hiding a fuller transcript. The visible user row is exactly the partial STT result for this call.

- timestamp: 2026-05-02T00:19:40Z
  checked: Backend logs for `rtc_88142006de7d42d7bb54874b4ac9db4b`.
  found: Backend received live audio until `track.recv.error ... frames=1038`, armed reconnect grace, then applied reconnect backfill batch 1 with real speech (`frames=346`, `duration_ms=6910`, `rms=1541.3`, `peak=17296.0`). Final batch 2 was near-silent (`frames=598`, `duration_ms=11943`, `rms=0.3`, `peak=3.0`) and pushed `silence_ms=12177`, causing `reconnect_audio.backfill.finalize`, `stt.begin ... frames=1982`, and `stt.result ... transcript_len=391`. The data channel was closed at `user_final`, but the reconnect-audio HTTP response returned 200 and the Web UI persisted via `/turns`.
  implication: The first durable loss is before STT and before persistence. Backend STT was only given an incomplete turn with a long silent tail; the phantom `thank you` is consistent with STT hallucination from that trailing silence.

- timestamp: 2026-05-02T00:19:40Z
  checked: Browser/Web UI logs for `call_1c544ed3b58d4976a883fdd2cb7faab1`.
  found: Browser logged local mic speech during reconnect (`localMicRawRms` roughly 0.11-0.13 at reconnect start, later 0.037-0.040 around 3-3.5s and 5.5s). It sent backfill batch 1 with `durationMs=6910`, `rms=1541.28`, `peak=17296`, and received `status=accepted`. It then sent final batch 2 with `durationMs=11944`, `rms=0.29`, `peak=3`, and received `status=accepted`. Web UI then posted `/api/calls/call_1c544.../turns` successfully. No 502 or timeout occurred for this newest call; later reconnect-audio requests during `state=thinking` were skipped by backend and reported as skipped, not failures.
  implication: The previous post-`c769afb` delivery failure is not the current first boundary. HTTP fallback/persistence worked; the missing poem content was absent from the audio handed to STT.

- timestamp: 2026-05-02T00:19:40Z
  checked: Expected poem comparison against actual persisted transcript.
  found: Expected text has 153 words; persisted actual has 68 words. The opening through the winter/afternoon/time section is mostly preserved with substitutions, and the final doorway/boots/hands/stars ending is partly preserved. The large middle span from around "slowly like the still unhurried wind" through the faith/prayers and return-home sections is absent, collapsed to a single "slow" before the ending fragment. Actual also appends phantom "Thank you."
  implication: This is a contiguous mid-poem loss plus hallucinated tail, not merely accent substitutions. The loss matches the backend evidence that only a partial speech buffer plus long near-silence reached STT.

- timestamp: 2026-05-02T00:12:38Z
  checked: User report after testing deployed `47f41c7`.
  found: User says RayMe heard the poem and took about one minute to process, but the resulting transcript still omitted parts of the poem and appended a phantom `thank you`. Saved the user-provided expected poem to `.planning/debug/phone-call-expected-poem-2026-05-02.md`.
  implication: The frozen/no-delivery regression is improved, but the original truncation/hallucinated-tail problem remains. The next investigation must compare newest OMEN STT/persisted transcript against the saved expected poem and identify the first current loss boundary.

- timestamp: 2026-05-01T22:51:03Z
  checked: Post-redeploy OMEN state and latest call after user reported redeploy did not fix the problem.
  found: OMEN remained on `6cbc48782f8c9ed4f20270ed7b9d1661928f6d0c` with WebRTC ready and `active_sessions=0` after restart. The latest call `call_836cbfd6abf84c2ca47282e35b830be6` / `rtc_7d3353a02035475985a0d7c60b8674cb` reached `user_final` for `user-turn-3` (`stt.result transcript_len=149`), LLM completed (`llm.done chars=430`), and TTS started a long playback (`duration_ms=26420`). Backend then logged repeated `inbound.dropped ... state=speaking`; later the speak request was cancelled when the call ended, returning a `Speech playback cancelled` processing error.
  implication: The verified restored snapshot is running. This fresh trace does not look like the post-`6607214` no-throughput regression; it points to the known snapshot behavior where the server rejects inbound user audio while AI playback is active. The next action should be a controlled repro to separate "long user speech while listening" from "user speaks while AI is still speaking" before applying another fix.

- timestamp: 2026-05-01T23:17:17Z
  checked: User clarified that the prior inspected call was not a structured repro, then performed two new first-turn poem calls. The second/latest call is the valid repro because the user waited about one minute before ending it.
  found: Latest valid repro is `call_e8464de2aeea413ebe3feb83247f0a33` / `rtc_20158f17ebad4f34b37d8c371135b76b` on `thread_c23ed9dfdcd64f23b007f7f8e75045dc`. It detected speech (`vad.speech_start turn_frames=125`) but the peer failed at frame 994 before `vad.end_of_turn`. Reconnect backfill applied real speech (`batch-1 rms=1316 peak=10767`, `batch-2 rms=1440 peak=19508`) and later long mostly-silent tail batches, but no `vad.end_of_turn`, `stt.begin`, or `user_final` was emitted. The thread persisted only call start/end events.
  implication: Root cause is now code-level and narrower than the failed post-snapshot stack: `backfill_reconnect_audio()` calls `_append_turn_frame()` but ignores the returned VAD `end_of_turn`, so final backfill cannot finish the user turn if no later live frame arrives. Implemented a backend finalization path for final reconnect backfill/held frames plus a browser fallback that handles a `user_final` event returned by the reconnect-audio HTTP response, with duplicate turn-id protection.

- timestamp: 2026-05-01T23:32:57Z
  checked: Newest OMEN evidence after `c769afb` deployment and the repeated first-turn poem repro.
  found: OMEN is on `c769afb` (`fix(call): finalize reconnect backfill turns`), `/webrtc/status` reports `active_sessions=0`, and the latest post-deploy call is `call_2fb9a7b8841b47e4b2abaff8148ad933` / `rtc_d4c2b23f435c4d4fa431e60de0ab9082` on `thread_c23ed9dfdcd64f23b007f7f8e75045dc`. Backend logs show the previous loss boundary is no longer first: `reconnect_audio.backfill.finalize` appears after final batch 2, then `event.sent type=state`, `stt.begin ... turn=user-turn-1 frames=3035`, and `stt.result ... transcript_len=461`. The browser log contains no `datachannel.message ... event_type="user_final"` for this call; Web UI thread API stores only `call_start` and `call_end` rows for the call at `2026-05-01T23:26:03.826011` and `2026-05-01T23:28:43.541569`.
  implication: `c769afb` fixed the missing `reconnect_audio.backfill.finalize`/STT boundary. The first durable loss is now after STT result generation: `event.skip_channel_not_open type=user_final readyState=closed` prevented delivery/persistence, and the browser did not receive a user_final over the data channel.

- timestamp: 2026-05-01T23:32:57Z
  checked: Browser/Web UI reconnect response evidence for `call_2fb9a7b8841b47e4b2abaff8148ad933`.
  found: Browser sent real reconnect backfill batches before the finalization (`batch-1 rms=1445.3 peak=14062`, `batch-2 rms=2189.3 peak=20365`) and received accepted responses for the first reconnect. During a later reconnect, backend accepted a mostly silent batch 1 and then final batch 2 triggered STT, but the browser issued `/api/calls/call_2fb9.../end` while a replacement `/offer` and final `/reconnect-audio` request were still in flight. The replacement offer returned `502 Bad Gateway`; the final reconnect-audio request also surfaced to the browser as `mic.reconnect_backfill.failed ... RayMe API request failed: 502 Bad Gateway`, despite the AI backend eventually logging the corresponding `/webrtc/sessions/rtc_d4.../reconnect-audio` as `200 OK` after `stt.result`.
  implication: The browser did not handle a successful reconnect-audio HTTP response carrying the fallback `user_final`; it saw the facade request as failed after `/end` closed the call. The remaining mechanism to inspect is end/reconnect ordering and whether the facade/client abandons the final STT response.

- timestamp: 2026-05-01T23:38:01Z
  checked: RED regression for ending while reconnect backfill is pending.
  found: Added `drains pending reconnect backfill before ending during reconnect` in `web-ui/client/tests/e2e/call-start.spec.ts`. On current `c769afb`, `npm run test:e2e -- call-start.spec.ts -g "drains pending reconnect backfill before ending during reconnect"` failed in both desktop and mobile Chromium because `counters.backfillCount` remained `0` after clicking End during a delayed reconnect offer.
  implication: This directly reproduces the browser-side ordering bug: current `hangup()` can call `/end` before the final reconnect-audio backfill is sent/drained, matching the newest OMEN loss boundary.

- timestamp: 2026-05-01T23:40:06Z
  checked: Local client fix for the post-`c769afb` browser hangup/backfill ordering bug.
  found: Updated `web-ui/client/src/routes/call/[threadId]/+page.svelte` so `flushReconnectAudioBackfill()` can await its final batch, and `hangup()` now calls `drainReconnectAudioBackfillBeforeHangup()` before `/api/calls/{call_id}/end` or media cleanup. The RED regression now passes in both desktop and mobile Chromium.
  implication: Local evidence supports the narrow fix for the newest first-loss boundary. Broader call E2E/build verification is still required before this can be offered for deployment.

- timestamp: 2026-05-01T23:46:36Z
  checked: Local verification for the post-`c769afb` browser hangup/backfill ordering fix.
  found: `npm run test:e2e -- call-start.spec.ts -g "drains pending reconnect backfill before ending during reconnect"` passed after the fix in desktop and mobile Chromium. Full `npm run test:e2e -- call-start.spec.ts` initially had one desktop timing failure in an existing reconnect snapshot assertion, that exact failed test passed on immediate targeted rerun, and a full-file rerun then passed: 24 passed. `npm run build` passed. `git diff --check` passed.
  implication: The fix is locally verified. OMEN has not been deployed, so real phone-call verification is still pending and must use `scripts/deploy-omen.sh` if/when deployment is requested.

- timestamp: 2026-05-01T23:53:44Z
  checked: Parent review of the local browser hangup/backfill fix.
  found: Tightened the fix so hangup awaits any already-running reconnect backfill flush instead of starting a duplicate drain. Added `awaits in-flight reconnect backfill before ending without duplicate drain`, covering a slow first backfill batch followed by End Call. Focused Playwright tests for both hangup/reconnect cases passed in desktop and mobile Chromium. Full `npm run test:e2e -- call-start.spec.ts` passed: 26 passed. `npm run build` passed. `git diff --check` passed.
  implication: The local patch now covers both observed hangup-before-backfill and in-flight-backfill variants before OMEN deployment.

- timestamp: 2026-05-01T23:56:36Z
  checked: Canonical OMEN deployment and post-deploy readiness for the hangup/backfill ordering fix.
  found: Committed and pushed `d7c8d4d` (`fix(call): drain reconnect backfill before hangup`), then deployed with `scripts/deploy-omen.sh`. OMEN fast-forwarded to `d7c8d4df3a54219f6e110a3d70c93fda458ba6f3`, rebuilt the web client, restarted canonical scheduled tasks, and reported `OMEN deploy complete`. `GET https://192.168.1.199:9443/webrtc/status` returned `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, and `active_sessions=0`. Scheduled tasks point to `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`. SQLite remained present at `C:\Users\pmpg\rayme\RayMe\web-ui\server\data\rayme.sqlite3`, length `856064`.
  implication: The fix is live on OMEN. The next evidence needed is the user's repeated first-turn poem repro.

- timestamp: 2026-04-30T21:24:13Z
  checked: Fresh post-`dff6545` investigation setup.
  found: Created `.planning/debug/phone-call-repro-dff6545-2026-04-30.md`, loaded prior repro files, and confirmed local checkout is `dff6545`.
  implication: Latest evidence should be preserved separately from prior `2360feb` and `adb035c` findings.

- timestamp: 2026-04-30T21:46:00Z
  checked: OMEN deployed state, status, logs, Web UI thread API, and direct SQLite copy after the user's post-`dff6545` report.
  found: OMEN checkout is `dff6545`; `/webrtc/status` is ready with `active_sessions=0`. The latest persisted call is `call_0daee780dd904a08a8fb69b4d8a68ca2` / `rtc_43b7b92a1b844471979bf0fed4adc8c3` on `thread_3be859853d7a4726a5151ca50b6e7940`. It starts at `2026-04-30T20:03:22.542447Z`, stores the long user speech at `2026-04-30T20:04:58.822295Z`, and ends at `2026-04-30T20:05:08.949981Z`. No later persisted thread message or call log was found.
  implication: The latest retrieved call is the failed repro being reported; there is no newer hidden call/thread to inspect after it.

- timestamp: 2026-04-30T21:46:00Z
  checked: Persisted transcript through Web UI API and direct SQLite.
  found: The latest long user speech row is 376 characters: `Of course, and now I will tell your story. The horrible conclusion which had been gradually uprooting itself upon my confused and reluctant mind was now an awful certainty. I was lost completely, hopelessly lost in the vast and at a very thin recesses of the mammoth cave. Turnus, I have frequently rid of the wild, frances into which were thrown the victims of the Thank you.`
  implication: The full expected Mammoth Cave passage is not hidden in persistence. Web UI API, SQLite, backend `stt.result transcript_len=376`, and `event.sent type=user_final` all agree.

- timestamp: 2026-04-30T21:46:00Z
  checked: Browser reconnect backfill logs for latest call.
  found: Browser logged `mic.reconnect_backfill.start` with backfill ID `call_0daee780dd904a08a8fb69b4d8a68ca2-1777579476539-uy2z19qt`, then no `.sent`; it logged `mic.reconnect_backfill.failed ... durationMs=5631 samples=90090 ... RayMe API request failed: 502 Bad Gateway`. Browser local mic diagnostics still showed live mic audio during reconnect, including RMS about `0.0418` at elapsed `2508ms`, `0.0775` at `6522ms`, and `0.0309` at `7023ms`.
  implication: The browser attempted backfill but perceived it as failed. The user was still producing local mic audio during the reconnect/backfill wait.

- timestamp: 2026-04-30T21:46:00Z
  checked: Backend reconnect backfill and VAD logs for latest call.
  found: Backend applied the same backfill ID despite the browser-side 502: `reconnect_audio.backfill.applied ... frames=282 duration_ms=5630 bytes=180180 rms=1079.3 peak=8269.0 turn_frames=1353 speech_seen=True silence_ms=0`. Replacement-track grace then started, but sampled replacement frames had near-zero current energy (`rms=0.1 peak=1.0`) while `speech_now=True` came from the recent VAD window containing the backfilled speech. VAD finalized at `turn_frames=1477 silence_ms=2334`; STT began with only those frames and returned `transcript_len=376`.
  implication: Backfill is partially working, but the active turn still misses audio after the selected backfill batch and before live replacement audio resumes. The first loss remains before STT.

- timestamp: 2026-04-30T21:46:00Z
  checked: Reconnect/backfill code path in `web-ui/client/src/routes/call/[threadId]/+page.svelte` and Web UI AI backend client.
  found: `connectBrowserMedia()` awaits `beforeRemoteDescription`, and reconnect passes `flushReconnectAudioBackfill()` there. `flushReconnectAudioBackfill()` selects the PCM once, posts it, and clears the backfill window in `finally`, before `setRemoteDescription`. `AiBackendClient.backfill_call_audio()` uses the generic 5 second timeout rather than the WebRTC/control timeout.
  implication: Audio captured while the backfill POST is in flight can be excluded from the already-selected batch and cannot travel via replacement WebRTC until after remote description is applied. The 5 second proxy timeout likely explains the browser `502` despite backend application.

- timestamp: 2026-04-30T21:50:49Z
  checked: Local fix and regression verification for the post-`dff6545` partial-backfill loss.
  found: Implemented ordered reconnect backfill batches. The browser now sends an initial batch before replacement answer application, then sends a final tail batch for PCM captured while the first request was in flight; the backend holds replacement-track live frames until the final marker so live silence cannot finalize ahead of the tail. The Web UI proxy now uses the WebRTC timeout for reconnect backfill. Added focused backend, proxy, and Playwright regression coverage. Verification passed: focused Python tests, `npm run build`, `npm run test:e2e -- call-start.spec.ts` (22 passed), full `ai-backend` tests (94 passed), full `web-ui/server` tests (152 passed), and `git diff --check`.
  implication: Local evidence supports the debugger's root cause and fix. Live verification still requires canonical OMEN deployment and another user repro.

- timestamp: 2026-04-30T21:53:27Z
  checked: Canonical OMEN deployment and post-deploy WebRTC readiness.
  found: Committed and pushed `faba4cc` (`fix(call): drain reconnect backfill tail`). `scripts/deploy-omen.sh` fast-forwarded OMEN to `faba4cc4f62e3f0c8ffd4b57b30f02aec934c1f0`, rebuilt the web client, recreated the canonical scheduled tasks, restarted both services, and reported `OMEN deploy complete`. `GET https://192.168.1.199:9443/webrtc/status` returned `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, `active_sessions=0`.
  implication: The reconnect tail fix is live on OMEN and ready for another user repro.

- timestamp: 2026-04-30T21:22:55Z
  checked: User live verification after deploying reconnect-gap backfill (`dff6545`, code fix in `adb035c`).
  found: User repeated the same long-passage repro and RayMe still did not transcribe the whole content. The last turn read by the user was the same Mammoth Cave passage saved in `.planning/debug/phone-call-transcript-comparison.md`: it begins `Of course, and now I will tell you a story. The horrible conclusion which had been gradually obtruding itself...` and ends `...as soon as I clearly realised the loss of my bearings.`
  implication: The debug session is reopened. The next debugger must inspect the latest live evidence with fresh eyes, including `mic.reconnect_backfill.*`, `reconnect_audio.backfill.*`, `vad.reconnect_grace.*`, `stt.begin/result`, Web UI thread API, and OMEN database state. If a call transcript is not visible in one source, that is not acceptable as a stopping point; query the other persistence/log sources.

- timestamp: 2026-04-30T17:20:13Z
  checked: Start of fresh post-`2360feb` debugger pass.
  found: Session focus reset to compare the newly deployed reconnect audio diagnostics against the latest user repro after `2026-04-30T17:19:00Z`.
  implication: The next finding must be based on current browser/backend diagnostics rather than assuming the previous replacement-track-silence hypothesis.

- timestamp: 2026-04-30T17:21:05Z
  checked: Linked repro evidence files and project skill discovery.
  found: Prior repro files show the recurring loss happened before persistence and before STT; the post-`1239588` file specifically left the boundary unresolved between browser capture, WebRTC send/receive silence, and backend VAD rejection. No project-local `.claude/skills` or `.agents/skills` were present.
  implication: The post-`2360feb` pass should focus on the newly added RMS/peak and VAD diagnostic events, not downstream transcript handling.

- timestamp: 2026-04-30T17:23:47Z
  checked: Latest OMEN checkout, logs, `/webrtc/status`, and thread API after the user's post-`2360feb` repro.
  found: Local and OMEN checkouts both report `2360feb` (`docs(debug): record reconnect diagnostics deployment`) with clean remote worktree. `/webrtc/status` is ready. The newest substantive call in persisted data is `call_398dbd33e47c4cd9bad0e9196e060c11` / `rtc_312a33e4d8a243aeb0fc521da21e8473` on `thread_3be859853d7a4726a5151ca50b6e7940`; it starts at `2026-04-30T17:15:41Z`, stores the long user speech at `2026-04-30T17:17:23Z`, and ends at `2026-04-30T17:17:34Z`. No OMEN log/thread writes were observed after `2026-04-30T17:19:00Z`.
  implication: The latest available repro evidence is the post-`2360feb` call ending at `17:17:34Z`, immediately before the debug note was recorded; there is no later persisted call to inspect.

- timestamp: 2026-04-30T17:23:47Z
  checked: Persisted Web UI thread data for latest call `call_398dbd33e47c4cd9bad0e9196e060c11`.
  found: The long user speech row is 414 characters: `Of course, and now I will tell your story...but stood quiet as soon as I clearly realized the loss of my my bearings.`
  implication: Persistence still stores the same partial transcript produced by STT; the new loss boundary remains before or at live audio capture/transport/VAD, not UI storage.

- timestamp: 2026-04-30T17:23:47Z
  checked: Browser `mic.reconnect_diag` events for latest call.
  found: During reconnect, the local audio track stayed live, unmuted, and enabled. Local mic raw RMS/peak were nonzero before reconnect and high during the outage, including `elapsedMs=1504 localMicRawRms=0.120 peak=0.358`, `elapsedMs=2005 rms=0.118 peak=0.304`, `elapsedMs=3008 rms=0.083 peak=0.185`, and `elapsedMs=4010 rms=0.215 peak=0.538` while `mediaReconnecting=true`.
  implication: The browser microphone was capturing speech during the failed/reconnecting interval; this rules out local mic mute/capture silence as the first loss boundary.

- timestamp: 2026-04-30T17:23:47Z
  checked: Backend `vad.reconnect_grace.audio` events for latest call.
  found: The old track fails at backend frame 1659, same-session reoffer starts reconnect grace at turn frame 1046, and the replacement track receives real VAD-positive audio: diagnostic frames 2-10 have RMS roughly 1487-3161 and `speech_now=True`; later samples at diag frames 25/50/75/100/125 also have `speech_now=True`. After grace, audio becomes VAD-silent for `silence_ms=1822`, then `stt.begin frames=1612` and `stt.result transcript_len=414`.
  implication: Once the replacement WebRTC path exists, backend receive and Silero VAD both accept speech. The missing middle spans were spoken while no backend track was receiving frames during the reconnect gap; they are not backend VAD rejection of real received audio.

- timestamp: 2026-04-30T17:24:30Z
  checked: Latest repro evidence preservation.
  found: Saved `.planning/debug/phone-call-repro-2360feb-2026-04-30.md` with deployed commit, call/session/thread IDs, persisted user speech, browser/backend reconnect diagnostics, first-loss boundary, and focused fix/test recommendation.
  implication: The post-`2360feb` diagnostic pass can be reloaded without re-querying OMEN logs.

- timestamp: 2026-04-30T17:38:16Z
  checked: Reconnect-gap audio backfill fix.
  found: Added browser rolling 16 kHz PCM buffering from the local mic graph, started reconnect-gap selection when browser media reconnect is scheduled/started, and posted the selected gap to the Web UI before applying the replacement peer answer. Added Web UI and AI backend routes to forward/apply reconnect audio backfill. `CallSession.backfill_reconnect_audio()` splits PCM into 20 ms frames, appends them to the active turn, runs VAD bookkeeping, preserves reconnect grace for the first replacement-track frame, and deduplicates by backfill ID.
  implication: Speech captured by the browser during the WebRTC reconnect outage is no longer intentionally discarded; the live verification target is whether the new browser route emits `mic.reconnect_backfill.sent` and backend logs `reconnect_audio.backfill.applied` during the same long-passage repro.

- timestamp: 2026-04-30T17:38:16Z
  checked: Regression tests for reconnect-gap audio backfill.
  found: `uv run --project ai-backend pytest ai-backend/tests -q` passed: 93 passed, 3 warnings. `uv run --project web-ui/server pytest web-ui/server/tests -q` passed: 151 passed. `npm run build` passed. `npm run test:e2e -- call-start.spec.ts` passed: 20 passed. `git diff --check` passed.
  implication: The fix is covered at backend call-session, AI backend signaling route, Web UI facade route, and existing call reconnect E2E levels.

- timestamp: 2026-04-30T17:41:07Z
  checked: Reconnect-gap backfill deployment to OMEN.
  found: Committed and pushed `adb035c` (`fix(call): backfill speech during media reconnect`), then deployed with `scripts/deploy-omen.sh`. OMEN checkout reported `adb035c`; `/webrtc/status` returned `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, and `active_sessions=0`. Generic `/health` remains `degraded` for the known non-F5 TTS engine availability reason while STT/VAD are ready and F5 is resident.
  implication: The next user phone-call repro will run against the reconnect-gap backfill fix.

- timestamp: 2026-04-30T17:19:00Z
  checked: User live verification after deploying reconnect audio diagnostics (`2360feb`, instrumentation from `3ce53c7`).
  found: User repeated the same phone-call repro as before. RayMe still did not transcribe the whole long text.
  implication: The next debugger pass should inspect the newly added `mic.reconnect_diag` browser events and `vad.reconnect_grace.audio` backend events from the latest call, without assuming the prior hypothesis is correct.

- timestamp: 2026-04-30T15:56:08Z
  checked: User live verification after deploying commit `1239588`.
  found: User repeated the same repro as the previous failed call. RayMe still did not transcribe the whole long text.
  implication: The debug session is reopened. Prior VAD and reconnect-grace fixes are insufficient, or the latest live failure is a different loss mode. The next debugger should inspect the newest OMEN logs and persisted thread data with fresh eyes.

- timestamp: 2026-04-30T15:57:53Z
  checked: Local and SSH access before latest OMEN inspection.
  found: Local checkout is at commit `1239588`. SSH works as `omen-pc\rayme-ssh` and `omen-pc\pmpg`.
  implication: The latest repro can be investigated against the intended local commit and live OMEN runtime without changing deployment state.

- timestamp: 2026-04-30T16:00:23Z
  checked: Latest OMEN deployment, active logs, thread API, and call/session IDs after the user's post-`1239588` repro.
  found: OMEN checkout is deployed at commit `1239588`. Active logs are `C:\Users\pmpg\rayme\logs\ai-backend.run.log` and `web-ui.run.log`. The latest substantive repro is `call_fc27939a380549f2a1a7a0ea38be2ec6` / `rtc_03a72711f2044c55a73cfc184e2151c5` on `thread_3be859853d7a4726a5151ca50b6e7940`; the later `call_0e9421d52da44cd4b5199f4237abfd65` / `rtc_f1a6d6121d764f618351866fb1238d4a` starts and ends immediately with no speech.
  implication: The live failure happened on the intended fixed commit. The newest no-speech call should not be treated as the truncation repro.

- timestamp: 2026-04-30T16:00:23Z
  checked: Persisted Web UI thread data for `thread_3be859853d7a4726a5151ca50b6e7940`.
  found: The latest substantive call persisted user speech `Hey, how are you doing?` followed by a long user row of 448 characters: `Of course, and now I will tell you a story... but stood quite as soon as I clearly realized the loss of my bearings.`
  implication: Persistence/UI are not the first loss boundary; the thread stores the same already-short transcript that came through `user_final`.

- timestamp: 2026-04-30T16:00:23Z
  checked: Backend and browser logs for `rtc_03a72711f2044c55a73cfc184e2151c5`.
  found: The long turn starts at backend frame 1062, VAD sees speech at turn frame 129, the old track fails at frame 2045, browser logs `pc.connectionstatechange failed`, `pc.iceconnectionstatechange disconnected`, and `pc.media_reconnect.start`, backend accepts a same-session reoffer, `vad.reconnect_grace.pending/start` are present, but the replacement track produces no post-reconnect `vad.speech_start`; it logs silence through `silence_ms=1822`, `vad.reconnect_grace.expired`, `vad.end_of_turn turn_frames=1645`, then `stt.begin frames=1645` and `stt.result transcript_len=448`.
  implication: The prior failed-state grace-ordering bug is fixed in live logs. The current first-loss boundary is still before STT, at media reconnect/VAD: the backend receives a replacement track but only silence/no VAD-positive speech before finalizing the partial turn.

- timestamp: 2026-04-30T16:01:50Z
  checked: Latest repro evidence preservation.
  found: Saved `.planning/debug/phone-call-repro-1239588-2026-04-30.md` with deployed commit, call/session/thread IDs, persisted user speech, log boundary summary, first-loss boundary, and the next instrumentation experiment.
  implication: The post-`1239588` failure can be reloaded without re-querying OMEN logs.

- timestamp: 2026-04-30T16:10:20Z
  checked: Instrumentation-only patch for the next live experiment.
  found: Added backend `vad.reconnect_grace.audio` logs with per-frame RMS/peak, Silero timestamp counts, speech flags, silence counters, and grace remaining time while reconnect grace is active. Added browser `mic.reconnect_diag` logs with local microphone RMS/peak, track state/settings, call state, reconnect phase, attempt count, and interval samples around media reconnect. Added an E2E assertion that reconnect emits scheduled/start/ok mic diagnostics.
  implication: The next repro should distinguish browser capture silence, WebRTC send/receive silence, and backend VAD rejection without changing call behavior.

- timestamp: 2026-04-30T16:10:20Z
  checked: Regression tests for instrumentation patch.
  found: `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` passed: 32 passed. `uv run --project ai-backend pytest ai-backend/tests -q` passed: 90 passed, 1 warning. `npm run build` passed. `npm run test:e2e -- call-start.spec.ts` passed: 20 passed. `git diff --check` passed.
  implication: The instrumentation patch is safe to commit and deploy for the next diagnostic call.

- timestamp: 2026-04-30T16:12:22Z
  checked: Instrumentation deployment to OMEN.
  found: Committed and pushed `3ce53c7` (`chore(call): instrument reconnect audio diagnostics`), then deployed with `scripts/deploy-omen.sh`. OMEN checkout is at `3ce53c7`; `/webrtc/status` reports `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, and `active_sessions=0`. Generic `/health` remains `degraded` because only F5-TTS is implemented/resident while other listed engines are unavailable.
  implication: The next phone-call repro should produce the targeted browser/backend diagnostics needed for the next debugger pass.

- timestamp: 2026-04-30T13:31:00Z
  checked: Fresh OMEN runtime state after the user's post-`e4b93d9` repro.
  found: SSH works as `omen-pc\pmpg`. Local and deployed checkouts both report commit `e4b93d9` (`fix(call): preserve speech through media reconnect`). Active log files are `web-ui.run.log` (last write 2026-04-30 09:25:17 local) and `ai-backend.run.log` (last write 2026-04-30 09:23:44 local). Latest visible call/session in the log tail is `call_df8ae118f4d04187ad95a08aace6f8e5` / `rtc_2f157017837a4ee4b307bb08cb2630e0`, with thread `thread_3be859853d7a4726a5151ca50b6e7940`.
  implication: The repro ran on the intended deployed commit. The latest session is identifiable and can be traced end-to-end without relying on the earlier `ba6057c` diagnosis.
- timestamp: 2026-04-30T13:43:00Z
  checked: Persisted thread data for `thread_3be859853d7a4726a5151ca50b6e7940` via `GET /api/threads/{thread_id}`.
  found: The latest call persisted one short user speech row (`Hi, how are you doing today?`, length 28) and one long user speech row beginning `Of course...` with length 367. The long row ends at `as soon as I clearly realized the loss of my bearings.` and is much shorter than the expected first long passage in `.planning/debug/phone-call-transcript-comparison.md`.
  implication: The web UI database contains the same short text that the call received; there is no later full transcript hidden behind the UI or persistence layer.
- timestamp: 2026-04-30T13:43:00Z
  checked: Full backend and browser logs copied to `/tmp/rayme-phone-debug-e4b93d9` and filtered for `rtc_2f157017837a4ee4b307bb08cb2630e0`.
  found: The long turn starts at backend frame 727, sees speech at turn frame 67, then the old receive loop hits `track.recv.error ... exc=MediaStreamError ice=completed conn=connected` at frame 1737 followed by a closed connection. Browser logs show `pc.iceconnectionstatechange disconnected`, `pc.connectionstatechange failed`, and `pc.media_reconnect.start`. A same-session reoffer arrives, but backend logs contain no `vad.reconnect_grace.pending`, `.start`, or `.hold` lines. After the new track starts, VAD accumulates silence to `silence_ms=1822`, emits `vad.end_of_turn turn_frames=1258`, starts STT with only `frames=1258`, and produces `transcript_len=367`.
  implication: The first observed loss is still before STT, at turn finalization after media reconnect. Unlike the intended `e4b93d9` behavior, reconnect grace did not arm for this real failed-then-reoffered path.
- timestamp: 2026-04-30T13:50:00Z
  checked: Focused regression test `test_existing_failed_session_reoffer_marks_in_progress_turn_for_reconnect_grace`.
  found: The test failed on current code: the same-session reoffer recovered `state == "listening"`, cleared `end_reason`, and cleared `ended_at`, but `_media_reconnect_grace_pending` remained `False`.
  implication: The live failure has a confirmed code-level mechanism: failed-state recovery happens too late for the reconnect-grace guard.
- timestamp: 2026-04-30T13:57:00Z
  checked: Focused regression test after moving failed-state recovery before `mark_media_reconnect_pending()`.
  found: `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q -k failed_session_reoffer_marks` passed: 1 passed, 31 deselected.
  implication: The targeted fix corrects the confirmed state-ordering bug.
- timestamp: 2026-04-30T14:02:00Z
  checked: Adjacent call-session regression suite.
  found: `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` passed: 32 passed in 8.10s.
  implication: Existing call session behavior still passes with the failed-state reconnect-grace fix and new regression test.
- timestamp: 2026-04-30T14:10:00Z
  checked: Full AI backend regression suite and diff whitespace check.
  found: `uv run --project ai-backend pytest ai-backend/tests -q` passed: 90 passed, 1 warning in 23.74s. `git diff --check` passed with no output.
  implication: The fix is covered by the focused regression test and does not break existing AI backend tests.
- timestamp: 2026-04-30T14:16:00Z
  checked: Latest repro evidence preservation.
  found: Saved `.planning/debug/phone-call-repro-e4b93d9-2026-04-30.md` with deployed commit, call/session/thread IDs, persisted user speech, backend/browser boundary summary, first loss point, and code-level finding.
  implication: The latest post-`e4b93d9` failure can be reloaded without re-querying OMEN logs.
- timestamp: 2026-04-30T14:20:00Z
  checked: `scripts/deploy-omen.sh`.
  found: The canonical deploy script computes local `git rev-parse HEAD`, fetches/pulls `origin/main` on OMEN, and throws if the OMEN checkout does not match local HEAD. The current fix is uncommitted local work, so running the script now would not deploy this patch.
  implication: Live verification requires committing and pushing this fix before running the canonical deploy script.

- timestamp: 2026-04-29T19:18:06Z
  checked: User-provided expected-versus-actual transcript for the latest phone call.
  found: Turn 1 was correct, but longer turns dropped large contiguous spans. This points beyond ordinary accent-based substitutions and toward audio capture, VAD segmentation, STT input duration/chunking, timeout, or transcript persistence/truncation.
  source: .planning/debug/phone-call-transcript-comparison.md
- timestamp: 2026-04-29T19:19:51Z
  checked: Prior resolved call/VAD debug sessions.
  found: Previous fixes established that WebRTC audio delivery, Silero VAD silence calculation, SSE/TTS keepalive, and mic gating had all been recent failure boundaries. The current symptom is different: turns finalize and produce `user_final`, but long turns lose contiguous middle/end spans.
  source: .planning/debug/resolved/android-call-vad-silence-handoff.md; .planning/debug/resolved/android-call-speaking-stuck.md
- timestamp: 2026-04-29T19:21:18Z
  checked: OMEN SSH, deployment commit, and log directory.
  found: SSH to `rayme-pmpg` works as `omen-pc\\pmpg`. OMEN repo is at commit `1db1e93`. The active logs are `ai-backend.run.log` and `web-ui.run.log` from 2026-04-28; hidden logs are stale/empty from 2026-04-27.
  source: `ssh rayme-pmpg whoami`; OMEN `C:\Users\pmpg\rayme\logs`
- timestamp: 2026-04-29T19:23:17Z
  checked: Tail of OMEN `ai-backend.run.log`.
  found: Latest visible call session is `rtc_3acc177ecea14b5493657d3e72f8bd2a`. Tail shows user turn processing completed, AI TTS was generated and played, then a new listening turn started before hangup. Need full-session log extraction to locate each user turn boundary.
  source: OMEN `C:\Users\pmpg\rayme\logs\ai-backend.run.log`
- timestamp: 2026-04-29T19:28:44Z
  checked: Full OMEN logs copied to `/tmp/rayme-phone-debug` and filtered for session `rtc_3acc177ecea14b5493657d3e72f8bd2a`.
  found: Truncation occurs before downstream forwarding: each affected turn reaches `stt.begin` already short. Turn 2 speech starts at frame 79 and ends at frame 1215 (~22.7s of speech) with transcript_len=374; turn 3 starts at frame 93 and ends at 1139 (~20.9s); turn 4 starts at frame 863 after the user's long pause and ends at 1105 (~4.8s of speech); turn 5 starts at frame 896 and ends at 1467 (~11.4s of speech). These durations are far shorter than the saved expected passages.
  source: `/tmp/rayme-phone-debug/ai-backend.run.log`
- timestamp: 2026-04-29T19:33:12Z
  checked: User clarification during investigation.
  found: User explicitly reports they did not pause during the affected speech. Therefore the ~722 ms VAD silence gaps in logs are false silence detections during continuous speech, not expected end-of-turn pauses.
  source: user message 2026-04-29
- timestamp: 2026-04-29T19:37:02Z
  checked: `CallSession._accept_vad_frame` and `AiBackendSettings`.
  found: Call finalization uses `settings.vad_end_silence_ms` (default 700 ms) as the sole post-speech silence threshold, and `settings.vad_max_turn_ms` (default 30000 ms) as a hard force-end. After finalization, `finalize_user_turn` sets state to `understanding` then `thinking`; `handle_inbound_audio_frame` drops inbound frames during `understanding`, `thinking`, and `speaking`.
  source: `ai-backend/app/call/session.py`; `ai-backend/app/config.py`
- timestamp: 2026-04-29T19:42:11Z
  checked: `WhisperSttAdapter`.
  found: Call STT writes the collected PCM frames to a temp WAV and calls faster-whisper with `apply_vad_filter=False`; there is no downstream 30-second transcript slicing in RayMe code. The earliest observed truncation is the VAD-selected frame buffer passed to STT.
  source: `ai-backend/app/models/stt.py`; `ai-backend/app/call/session.py`
- timestamp: 2026-04-30T12:06:37Z
  checked: User's post-deploy reproduction call after commit `ba6057c`.
  found: The deployed threshold change was active (`threshold_ms=1800`) and improved the duration before cutoff, but the two long passages were still truncated. Persisted transcripts are saved in `.planning/debug/phone-call-repro-2026-04-30.md`.
  source: OMEN thread API; `.planning/debug/phone-call-repro-2026-04-30.md`
- timestamp: 2026-04-30T12:18:00Z
  checked: Full call boundary logs for `rtc_5cee6240cccf42079c09a785d6bb6b6b`.
  found: Both long turns had browser media reconnects mid-turn. After the reoffer, the backend saw new-track silence and finalized on `silence_ms=1822`, producing already-short STT inputs (`user-turn-3` frames=1211, transcript_len=343; `user-turn-4` frames=1620, transcript_len=490).
  source: OMEN `ai-backend.run.log`; OMEN `web-ui.run.log`

- timestamp: 2026-05-01T00:56:35Z
  checked: Post-`6607214` persisted Web UI/SQLite transcript rows copied from OMEN.
  found: The latest post-deploy thread is `thread_3be859853d7a4726a5151ca50b6e7940`. Persisted calls after `2026-05-01T00:37:00Z` are `call_3294c6a6ccd94631b1fbc85f04142c17`/`rtc_25ab1948e65c4e0eb58269b8a78a38da`, `call_f0fb95ca621f4fdb95978b47c4e8f5bd`/`rtc_328930b782da4e1396538f02aa4a4425`, and `call_de275daf80454bc4b7395cac6a338cda`/`rtc_f584bd114a5b4b7799468b0667d80b66`. SQLite stored only short user turns: `Hi, how are you doing?`, `How are you today? Hi.`, `Hi, how are you today?`, and `I'm doing well, thank you. How are you doing?`, with matching AI replies and call_end rows. No post-`6607214` long Mammoth Cave passage was visible in SQLite, Web UI logs, or AI backend logs.
  implication: Persistence is not hiding a later full long transcript. The latest data directly confirms delayed-speech/no-response failures on short calls; it does not yet contain a fresh long-text repro after `6607214`.

- timestamp: 2026-05-01T00:56:35Z
  checked: Backend/browser boundary for affected call `call_3294c6a6ccd94631b1fbc85f04142c17` / `rtc_25ab1948e65c4e0eb58269b8a78a38da`.
  found: The first short turn finalized normally (`stt.begin frames=525`, `stt.result transcript_len=22`, `event.sent type=user_final`). During the next spoken turn, backend VAD saw speech (`vad.speech_start turn_frames=157`), then the track failed at frame 2615 while the browser still logged local mic RMS around `0.063` to `0.094` during `mediaReconnecting=true`. Backend accepted backfill batches with real audio, including `frames=278 rms=1930.4 peak=17481` and `frames=546 rms=798.7 peak=13249`, then a second reconnect started. One replacement live frame was held, a later backfill added `frames=602 rms=472.0 peak=10318`, and the browser sent an empty `final:true` marker using the same batch ID as the prior non-final batch. Backend logged `reconnect_audio.backfill.duplicate` for that final marker; no `reconnect_audio.live_release`, `stt.begin`, or `user_final` followed for the second spoken turn.
  implication: The first loss is after browser capture and backend VAD/backfill acceptance, but before STT. The active turn remains unfinalized because the final empty marker is deduped before it can release held live frames.

- timestamp: 2026-05-01T00:56:35Z
  checked: Backend/browser boundary for affected call `call_f0fb95ca621f4fdb95978b47c4e8f5bd` / `rtc_328930b782da4e1396538f02aa4a4425`.
  found: The first turn finalized normally (`stt.begin frames=539`, `stt.result transcript_len=22`). During the next turn, backend VAD saw speech (`vad.speech_start turn_frames=104`) and the track failed at frame 2112. Backfill then appended real audio (`frames=278 rms=1306.5 peak=8933`, then `frames=542 rms=1381.2 peak=13965`). A second reconnect held one live frame, appended another non-final backfill (`frames=598 rms=542.9 peak=11179`), then logged `reconnect_audio.backfill.duplicate` for the empty final marker with the same batch ID. No later `stt.begin`/`user_final` occurred for that turn.
  implication: This independently repeats the same first-loss boundary as `call_3294...`: capture and VAD are present, but duplicate final-marker handling prevents release/finalization.

- timestamp: 2026-05-01T00:56:35Z
  checked: Control call `call_de275daf80454bc4b7395cac6a338cda` / `rtc_f584bd114a5b4b7799468b0667d80b66`.
  found: Two user turns finalized and persisted, including a delayed second turn where speech started at `turn_frames=847` and produced `stt.result transcript_len=45`. A later reconnect happened mostly while idle/listening; that session ended through `/webrtc/sessions/rtc_f584bd114a5b4b7799468b0667d80b66/end` and a final empty backfill after end returned 404.
  implication: Waiting before speech is not generally broken in VAD or STT. The regression appears when delayed or continued speech intersects a reconnect/backfill hold/final-marker sequence.

- timestamp: 2026-05-01T00:56:35Z
  checked: Current reconnect backfill code in `ai-backend/app/call/session.py` and browser backfill emission in `web-ui/client/src/routes/call/[threadId]/+page.svelte`.
  found: `CallSession.backfill_reconnect_audio()` returns early for duplicate `backfill_id` before it handles an empty `final:true` marker, so a duplicate final marker cannot call `_release_reconnect_live_frames(reason="final_empty_backfill")`. `_release_reconnect_live_frames()` replays held frames via `_append_turn_frame()` but ignores the returned `end_of_turn`, so a released held frame that crosses the silence threshold cannot itself trigger `finalize_user_turn()` unless another live frame later arrives. Browser logs show the empty final marker can reuse a previous non-final batch ID during aborted/end-call reconnect paths.
  implication: The log pattern has a code-level mechanism. The final marker side effect is not idempotent, and the hold-release path has no immediate finalization path.

- timestamp: 2026-05-01T01:06:26Z
  checked: Local post-`6607214` regression fix.
  found: Updated `CallSession.backfill_reconnect_audio()` so empty `final:true` reconnect markers can release held live frames even if their `backfill_id` duplicates a prior non-final batch. Updated reconnect held-frame release to return VAD `end_of_turn` and finalize the user turn immediately when released frames cross the turn boundary. Updated browser reconnect backfill IDs to use `batch` vs `final` namespaces so final markers cannot collide with non-final batch IDs even if a reconnect path reuses a batch index. Added backend regressions for duplicate empty final markers releasing held frames and held-frame release reaching STT. Tightened an existing Playwright reconnect assertion to wait for the replacement answer before snapshotting the new peer.
  implication: The no-response mechanism found in post-`6607214` logs is fixed locally and covered by tests.

- timestamp: 2026-05-01T01:09:37Z
  checked: Canonical OMEN deployment after post-`6607214` fix.
  found: Committed and pushed `6f63de0` (`fix(call): release reconnect final markers`). `scripts/deploy-omen.sh` fast-forwarded OMEN to `6f63de035989a53c0a20e5e85002a5e115fede26`, rebuilt the web client, recreated the canonical scheduled tasks, restarted both services, and reported `OMEN deploy complete`. `GET https://192.168.1.199:9443/webrtc/status` returned `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, `active_sessions=0`.
  implication: The final-marker release fix is live on OMEN and ready for user repro.

- timestamp: 2026-05-01T02:02:32Z
  checked: User post-`21bc46e` repro report and rollback-anchor request.
  found: User reports three latest calls failed after the latest deployment. Oldest of the three: user sent a short first message and RayMe responded, then user read a long poem and the call froze. Middle call: the call could not start and showed call failed. Latest call: user sent a short first message and RayMe responded, then waited more than 10 seconds and spoke; the call froze. User asks to record the commit that last worked so the project can return to it if needed.
  implication: Reopen the session. The debugger should inspect the last three calls with fresh evidence, and should separately identify a rollback anchor. Do not apply fixes before the call-start/freeze boundaries and rollback candidate are recorded.

- timestamp: 2026-05-01T02:05:13Z
  checked: Project-local skills, debug knowledge base, local/OMEN commit, canonical runtime, and readiness before the post-`21bc46e` log pass.
  found: No `.claude/skills`, `.agents/skills`, or `.planning/debug/knowledge-base.md` exists. Local `main` and OMEN are both at `21bc46e0a3095fec8c9f8fc00e44fbd4a4493a19` (`docs(debug): record final-marker deployment`). OMEN scheduled tasks `RayMePhase1AI` and `RayMePhase1Web` are running and point only to `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`. The launchers point at `C:\Users\pmpg\rayme\RayMe`; the Web UI launcher uses `sqlite+aiosqlite:///C:/Users/pmpg/rayme/RayMe/web-ui/server/data/rayme.sqlite3`. `/webrtc/status` returned ready with `live_call_ready=true`, `media_transport_ready=true`, and `active_sessions=1`; `/api/settings` reached the AI backend with STT/VAD ready and resident F5, while generic endpoint status remained degraded only because non-F5 engines are unavailable. Copied active logs and SQLite to `/tmp/rayme-phone-debug-21bc46e-2026-05-01/`.
  implication: The repro window is on the intended deployed commit and canonical OMEN launch path. Further analysis can use the copied logs/database without changing source or deployment state.

- timestamp: 2026-05-01T02:11:44Z
  checked: SQLite messages and Web UI `/api/calls/start` events after the `21bc46e` deployment.
  found: The latest post-deploy thread is `thread_3be859853d7a4726a5151ca50b6e7940`. Persisted/logged 201-created calls after `01:50Z` are `call_22a4f02eddda4624847d57bdf1a0cb6a`/`rtc_837425d25e51420e82659d46c8a81390` at about `01:54:32Z`, `call_5152493ffa72481ab60f1fc5b16eba9c`/`rtc_2892320a439f4ef59830af9df3cdd296` at about `01:55:21Z`, and `call_e3e46602b0e340f098b2549aa04a3765`/`rtc_fd075194886f46569ba1ba921440e62f` at about `01:58:07Z`. SQLite stores only short user turns for those calls: `Hey there.`, `Always there, Mike.`, and `I use the air.` plus AI replies for the latter two. A separate `/api/calls/start` returned 500 between `call_515...` and `call_e3...`.
  implication: The two user-described calls that started then froze are `call_515...` and `call_e3...`; the long/delayed second turns are absent from SQLite/API persistence. `call_22a4...` is an additional logged short call, not the failed long-turn repro.

- timestamp: 2026-05-01T02:11:44Z
  checked: User correction about the failed-to-start attempt.
  found: User clarified that the observed `AiBackendUnavailable` 500 was another failed start they did not mention, and that the call that failed completely in their report does not appear to be logged. The copied Web UI access log has no additional `/api/calls/start` failure after the 500 and no durable call/session row for another failed attempt.
  implication: The user-reported failed-to-start call has no recoverable `call_id` or `rtc_session_id` in these server-side artifacts. Its first loss boundary is before durable Web UI call/session creation, possibly before the start request reached the server or before browser debug telemetry was posted.

- timestamp: 2026-05-01T02:11:44Z
  checked: Poem/freeze call `call_5152493ffa72481ab60f1fc5b16eba9c` / `rtc_2892320a439f4ef59830af9df3cdd296`.
  found: The first short turn persisted normally: backend `vad.speech_start`, `stt.begin`, `stt.result transcript_len=19`, and `event.sent type=user_final`; Web UI stored `Always there, Mike.` and an AI reply. The second long turn began (`vad.speech_start turn_frames=206`) but the peer closed mid-turn at backend `track.recv.error frames=1508`. Reconnect/backfill applied multiple batches, including non-silent final PCM, and backend eventually ran `stt.begin user-turn-2 frames=3004` then `stt.result transcript_len=446`, but `event.skip_channel_not_open type=user_final readyState=closed` prevented delivery to the browser/Web UI. SQLite has no long-turn row.
  implication: For the poem call, the first instability boundary is WebRTC/datachannel closure during the second turn; the first durable persistence loss boundary is skipped `user_final` after STT because the data channel was already closed.

- timestamp: 2026-05-01T02:11:44Z
  checked: Latest delayed-speech freeze call `call_e3e46602b0e340f098b2549aa04a3765` / `rtc_fd075194886f46569ba1ba921440e62f`.
  found: The first short turn persisted normally: backend `stt.result transcript_len=14` and `event.sent type=user_final`; Web UI stored `I use the air.` and the AI response. After AI playback, the second listening turn started at backend frame `953`, but no second-turn `vad.speech_start`, `stt.begin`, or `user_final` occurred. Backend closed at `track.recv.error frames=1923`; browser logged `pc.iceconnectionstatechange disconnected`, `pc.connectionstatechange failed`, `mic.reconnect_backfill.start`, then user/end raced with reconnect and `setRemoteDescription` failed because the peer connection was already closed. No `reconnect_audio.backfill.applied` was observed for this session.
  implication: For the latest delayed-speech call, the user's second speech did not reach backend VAD/STT before the transport closed, and no reconnect backfill reached the backend before call end.

- timestamp: 2026-05-01T02:11:44Z
  checked: Superseded rollback-anchor evidence across resolved/prior debug history and git history.
  found: A debugger originally suggested `1db1e93` (`fix(call): reconnect on ice-only media loss`) as a possible older rollback candidate, but this was superseded by the user's explicit selection of `6607214`. No objectively confirmed-good commit exists for complete long-poem transcription.
  implication: Historical context only. Do not treat `1db1e93` as the active anchor, and do not let rollback analysis distract from the current fix-forward target.

- timestamp: 2026-05-01T02:17:55Z
  checked: User-selected rollback anchor after clarification.
  found: User clarified they want `6607214` selected as the anchor, because it is the exact commit tested immediately before the "terrible regression" report. `6607214` is a docs commit over runtime code commit `faba4cc`.
  implication: Future rollback work should treat `6607214de3f65a7855e6d6ad4132bc7d66f3b479` as the selected operational anchor. The previous `1db1e93` debugger recommendation remains historical context only, not the selected anchor.

- timestamp: 2026-05-01T02:35:46Z
  checked: Local git rollback anchor verification before returning checkpoint.
  found: Current local `main`/`origin/main` is `81f8f7f4d173be184408d4303b5a4f33aa49913f` (`docs(agents): name canonical debug manager file`). The selected rollback anchor `6607214de3f65a7855e6d6ad4132bc7d66f3b479` resolves to `docs(debug): record reconnect tail deployment`, is an ancestor of current `HEAD`, and only changed `.planning/debug/phone-calls-missing-chunks.md`. Its runtime code commit remains `faba4cc4f62e3f0c8ffd4b57b30f02aec934c1f0` (`fix(call): drain reconnect backfill tail`). The only local dirty file is this debug session file.
  implication: This verifies the insurance anchor only. It must not replace the active fix-forward investigation into `call_515...` and `call_e3...`.

- timestamp: 2026-05-01T02:39:19Z
  checked: Debug-session focus correction after user reported the debugger fixated on rollback.
  found: The previous Current Focus incorrectly framed rollback as the only operational decision. The active evidence to investigate is the two started calls: `call_515...`, where the long turn reached STT but `user_final` was skipped because the data channel was closed, and `call_e3...`, where the delayed second speech never reached backend VAD/STT/backfill before transport close.
  implication: Next debugger pass should ignore rollback except as insurance and should continue root-cause/fix work on the transport/data-channel closure around the second user turn.

- timestamp: 2026-05-01T02:51:22Z
  checked: Fresh OMEN log filtering for post-`21bc46e` calls `call_5152493ffa72481ab60f1fc5b16eba9c` / `rtc_2892320a439f4ef59830af9df3cdd296` and `call_e3e46602b0e340f098b2549aa04a3765` / `rtc_fd075194886f46569ba1ba921440e62f`.
  found: In the poem call, backend accepted reconnect backfills and reached `stt.result ... turn=user-turn-2 transcript_len=446`, but the current data channel had closed during a later reconnect (`datachannel.close` before STT finished), so `event.skip_channel_not_open type=user_final readyState=closed` dropped the turn. In the delayed-speech call, the browser started reconnect backfill (`mic.reconnect_backfill.start`) and created a replacement offer, but `/api/calls/.../end` ran before the answer was applied; `pc.media_reconnect.failed` then reported `setRemoteDescription` on a closed peer connection, and there was no `mic.reconnect_backfill.sending`/backend `reconnect_audio.backfill.applied` for that session.
  implication: The current failure is not explained by STT, VAD, or persistence truncation. It is a reconnect lifecycle bug: successful backend STT has no durable/queued delivery path when the data channel is temporarily closed, and browser hangup/reconnect cleanup can discard pending local PCM before the backend receives it.

- timestamp: 2026-05-01T03:00:26Z
  checked: Red regression attempts for the two confirmed mechanisms.
  found: Added `test_user_final_waits_for_replacement_data_channel_when_closed`; it fails on current code with `AttributeError: 'CallSession' object has no attribute 'attach_data_channel'`, confirming no pending data-channel replay API exists. Added browser E2E coverage for ending during an in-flight reconnect offer; the targeted single-test Playwright command timed out starting its configured web server before reaching the test body.
  implication: Backend regression reproduces the missing pending-event delivery directly. Browser regression is written but needs post-implementation execution through the stable Playwright command path.

- timestamp: 2026-05-01T03:13:24Z
  checked: Fix implementation, regression verification, commit, and OMEN deployment.
  found: Implemented pending backend data-channel replay for durable `user_final` events, wired replacement data channels to flush pending events, and made browser hangup await a final reconnect-audio drain before `/end` and media cleanup. Verification passed: backend red regression now passes; browser ordering regression passes and asserts reconnect audio POST precedes `/end`; `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q` passed (52 passed, 3 warnings); `uv run --project ai-backend pytest ai-backend/tests -q` passed (97 passed, 3 warnings); `npm run build` passed; `npm run test:e2e -- call-start.spec.ts` passed (24 passed); `git diff --check` passed. Committed and pushed `a0d5d17` (`fix(call): preserve turn artifacts across reconnect`). `scripts/deploy-omen.sh` deployed `a0d5d17` to OMEN and `/webrtc/status` returned `status=ready`, `live_call_ready=true`, `media_transport_ready=true`, `active_sessions=0`.
  implication: The two confirmed log mechanisms are fixed in code and live on OMEN. Final resolution still requires the user to verify the real phone-call workflow.

- timestamp: 2026-05-01T15:46:17Z
  checked: User verification after `a0d5d17` and post-snapshot audit request.
  found: User reports `a0d5d17` does not work at all: calls remain frozen and messages longer than about 5 to 10 seconds do not go through. User requested returning OMEN to selected snapshot `6607214`, but first recording every post-snapshot change, hypothesis, and attempted solution, with special attention to the immediate post-snapshot change that likely made the calls worse. Created `.planning/debug/phone-calls-post-snapshot-audit.md`.
  implication: Stop fix-forward work. Restore runtime files to the selected snapshot state and deploy through `scripts/deploy-omen.sh` only.

- timestamp: 2026-05-01T15:51:43Z
  checked: Durable prevention guard before deployment.
  found: Updated `.planning/debug/phone-calls-post-snapshot-audit.md` and `.planning/LEARNINGS.md` with an explicit guard not to retry the exact post-`6607214` `6f63de0` plus `a0d5d17` reconnect/final-marker/data-channel replay patch stack. Also recorded that `AGENTS.md` must be kept and is intentionally outside the runtime rollback.
  implication: Future debugging should not resurrect that patch combination as a small fix. Reconnect architecture requires a fresh plan and live OMEN/phone evidence.

## Eliminated

- hypothesis: The latest post-`74450da` partial transcript is caused by the failed reconnect offer replacing the active backend media track before negotiation succeeds.
  evidence: In the latest `call_54dc73...` repro, the first missing-content boundary occurs earlier in the browser: reconnect backfill requests cover `5226-35256ms` and `69467-99412ms`, leaving `35256-69467ms` unsent. The backend then faithfully transcribes the partial audio it received and Web UI persists the recovered `user_final`.
  timestamp: 2026-05-02T16:58:49Z

- hypothesis: Downstream forwarding, persistence, or UI display truncates a full STT transcript.
  evidence: OMEN AI backend logs show affected turns reach `stt.begin` with already-short frame buffers and produce short `stt.result` lengths before `event.sent type=user_final`; the first loss point is before STT, not after `user_final`.
  timestamp: 2026-04-29T19:58:21Z

- hypothesis: Missing chunks are caused by intentional pauses during user speech.
  evidence: User explicitly clarified they made sure not to pause; observed `vad.end_of_turn silence_ms=722` entries must be false VAD silence or hard cutoff behavior, not real turn endings.
  timestamp: 2026-04-29T19:58:21Z

- hypothesis: The post-`1239588` failure is still caused by failed-state reoffers not arming backend reconnect grace.
  evidence: Latest live backend logs for `rtc_03a72711f2044c55a73cfc184e2151c5` show `vad.reconnect_grace.pending` and `vad.reconnect_grace.start`, proving the grace-ordering fix is active in this repro.
  timestamp: 2026-04-30T16:01:50Z

- hypothesis: The latest truncation happens in STT result forwarding, persistence, or UI display after a full `user_final`.
  evidence: Latest backend logs show `stt.begin` received only `frames=1645` for the long turn and `stt.result transcript_len=448`; the Web UI thread API stores the same 448-character user speech row.
  timestamp: 2026-04-30T16:01:50Z

## Resolution

root_cause: In the fresh Android acceptance failure at deployed commit `2d00461`, the latest failed call `call_2018a74d029c467eb173f6a012719663` / `rtc_127ff57be7024045b1c8ac3307afbbde` recovered and persisted the full long user turn, but terminal media cleanup posted `/end` while `/turns` LLM generation was still in flight. The active product defect was earlier than post-end generation: `failTerminalMediaReconnect()` ended the call and showed failed UI without checking whether a recovered long-turn response stream was active, and browser reconnect offer failure could close the last answered peer/audio path before a replacement answer existed.
fix: Added a client-side active turn response guard in `web-ui/client/src/routes/call/[threadId]/+page.svelte`. Terminal reconnect cleanup now waits for any active `/turns` stream before recovering/ending, waits again after recovery in case recovered events start a turn, and holds terminal cleanup through a bounded response-visible/playback grace based on `ai_audio_started` duration. Browser reconnect replacement is also transactional: the existing answered peer/data channel stays in place until a replacement answer is applied, and a failed replacement offer restores the previous peer instead of destroying the live playback path. The fix does not abort or suppress the response stream.
verification: Focused TDD test passed after the fix: `npm run test:e2e -- call-start.spec.ts -g "keeps recovered turn response live when terminal reconnect offer fails before audio starts"` returned 2 passed across desktop and mobile Chromium. Strengthened playback-path assertion first failed when no answered peer remained open, then passed after transactional reconnect. Adjacent reconnect/hangup grep passed: 14 passed. Full serialized `npm run test:e2e -- call-start.spec.ts --workers=1` passed: 36 passed. `npm run build` from `web-ui/client` passed. `git diff --check` passed. OMEN deployed commit `56c4ab7fdff91ec337a446fed676e967fa78cbd1` via `scripts/deploy-omen.sh`; `/webrtc/status` is ready with `active_sessions=0`. Physical Android Chrome acceptance remains pending.
files_changed:
  - web-ui/client/src/routes/call/[threadId]/+page.svelte
  - web-ui/client/tests/e2e/call-start.spec.ts
  - .planning/debug/phone-calls-missing-chunks.md

## Prior Fix History

prior_root_causes: Earlier confirmed causes included overly aggressive live-call VAD finalization, a 30s hard max-turn cap, failed-state reoffers that did not arm reconnect grace, reconnect outages that needed browser PCM backfill, and post-`6607214` reconnect final markers/held frames that prevented some turns from reaching STT. These are historical fixes, not the current unresolved failure.
prior_fixes: Added call-specific VAD settings (`call_vad_end_silence_ms=1800`, `call_vad_max_turn_ms=120000`), added reconnect grace, recovered failed sessions before marking reconnect grace, added browser PCM backfill for media reconnect gaps, drained ordered reconnect backfill tails, made empty `final:true` markers idempotent, and allowed held-frame release to finalize turns.
prior_verification:
  - `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` failed: 28 passed, 1 failed. Failure was `test_silero_silence_gap_finalizes_turn_even_with_loud_ambient_noise`, because the test implicitly expected the old 700 ms call threshold; it now needs to set `call_vad_end_silence_ms=700` explicitly to preserve that regression scenario.
  - `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` passed: 29 passed in 8.28s.
  - `uv run --project ai-backend pytest ai-backend/tests -q` passed: 87 passed, 1 warning in 34.92s.
  - Inspected `scripts/deploy-omen.sh`; it deploys git HEAD from `origin/main` after resetting OMEN checkout. Because the fix is currently uncommitted local work, deployment was not run.
  - `git diff --check` passed with no whitespace errors.
  - Post-deploy user repro on 2026-04-30 still failed under commit `ba6057c`; persisted user speech rows and boundary logs saved in `.planning/debug/phone-call-repro-2026-04-30.md`.
  - `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` passed after reconnect-grace follow-up: 31 passed in 10.56s.
  - `uv run --project ai-backend pytest ai-backend/tests -q` passed after reconnect-grace follow-up: 89 passed, 1 warning in 33.04s.
  - `git diff --check` passed after reconnect-grace follow-up.
  - `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q -k failed_session_reoffer_marks` failed before the post-`e4b93d9` fix, then passed after reordering failed-state recovery before reconnect-grace marking.
  - `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` passed after the post-`e4b93d9` fix: 32 passed in 8.10s.
  - `uv run --project ai-backend pytest ai-backend/tests -q` passed after the post-`e4b93d9` fix: 90 passed, 1 warning in 23.74s.
  - `git diff --check` passed after the post-`e4b93d9` fix.
  - Live verification still requires deploying via `scripts/deploy-omen.sh` only, then repeating the phone-call passage.
  - Post-deploy user repro on 2026-04-30 still failed under commit `1239588`; persisted user speech rows and boundary logs saved in `.planning/debug/phone-call-repro-1239588-2026-04-30.md`.
  - Post-deploy user repro on 2026-04-30 still failed under commit `2360feb`; persisted user speech rows and browser/backend reconnect diagnostics saved in `.planning/debug/phone-call-repro-2360feb-2026-04-30.md`. Diagnostics isolate browser/WebRTC reconnect outage as the first-loss boundary.
  - `uv run --project ai-backend pytest ai-backend/tests -q` passed after reconnect-gap backfill: 93 passed, 3 warnings in 30.81s.
  - `uv run --project web-ui/server pytest web-ui/server/tests -q` passed after reconnect-gap backfill: 151 passed in 29.79s.
  - `npm run build` passed after reconnect-gap backfill.
  - `npm run test:e2e -- call-start.spec.ts` passed after reconnect-gap backfill: 20 passed.
  - `git diff --check` passed after reconnect-gap backfill.
  - `scripts/deploy-omen.sh` deployed reconnect-gap backfill commit `adb035c`; post-deploy `/webrtc/status` was ready.
  - `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q -k 'reconnect_audio_backfill or reconnect_live_frame_release or reconnect_grace'` passed after the post-`6607214` fix: 7 passed, 30 deselected in 3.32s.
  - `npm run test:e2e -- call-start.spec.ts` passed after the post-`6607214` fix: 22 passed.
  - `uv run --project ai-backend pytest ai-backend/tests -q` passed after the post-`6607214` fix: 96 passed, 3 warnings in 40.90s.
  - `uv run --project web-ui/server pytest web-ui/server/tests -q` passed after the post-`6607214` fix: 152 passed in 27.62s.
  - `npm run build` passed after the post-`6607214` fix.
  - `git diff --check` passed after the post-`6607214` fix.
  - `scripts/deploy-omen.sh` deployed post-`6607214` fix commit `6f63de0`; post-deploy `/webrtc/status` was ready with `active_sessions=0`.
prior_files_changed:
  - ai-backend/app/config.py
  - ai-backend/app/call/session.py
  - ai-backend/app/api/webrtc.py
  - ai-backend/tests/test_call_session.py
  - ai-backend/tests/test_webrtc_signaling.py
  - web-ui/client/src/lib/api/calls.ts
  - web-ui/client/src/routes/call/[threadId]/+page.svelte
  - web-ui/client/tests/e2e/call-start.spec.ts
  - web-ui/server/app/api/calls.py
  - web-ui/server/app/domain/ai_backend_client.py
  - web-ui/server/tests/test_calls.py
  - .planning/debug/phone-call-repro-e4b93d9-2026-04-30.md
  - .planning/debug/phone-call-repro-1239588-2026-04-30.md
  - .planning/debug/phone-call-repro-2360feb-2026-04-30.md
