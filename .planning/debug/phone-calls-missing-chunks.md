---
status: awaiting_human_verify
created: 2026-04-29T19:18:06Z
updated: 2026-05-01T23:56:36Z
trigger: "Phone calls fail to transcribe the whole content of user speech; RayMe misses whole chunks of long turns."
---

# Debug Session: Phone Calls Missing Speech Chunks

## Current Focus

reasoning_checkpoint:
  hypothesis: "The latest post-`c769afb` freeze loses the recovered first turn because `hangup()` can call `/end` and clear browser media while a reconnect offer/backfill is still pending; the backend may later produce `user_final`, but the data channel and HTTP fallback path are already closed."
  confirming_evidence:
    - "OMEN `call_2fb9a7b8841b47e4b2abaff8148ad933` / `rtc_d4c2b23f435c4d4fa431e60de0ab9082` shows `reconnect_audio.backfill.finalize`, `stt.begin`, and `stt.result transcript_len=461`, followed by `event.skip_channel_not_open type=user_final readyState=closed`."
    - "Browser logs for the same call contain no `datachannel.message ... user_final`; the final `/reconnect-audio` surfaced to the browser as 502 after `/end`, while the AI backend logged the underlying request as 200 after STT."
    - "New Playwright regression failed on current code in both desktop and mobile: after clicking End during reconnect, `backfillCount` stayed 0 while `/end` completed."
  falsification_test: "After the fix, the same regression must show a final reconnect-audio backfill sent before `/end`; if `/end` still occurs first or no backfill is sent, the hypothesis is wrong."
  fix_rationale: "Drain the pending reconnect-audio backfill before ending the call so the final HTTP response can carry and handle any recovered `user_final` before the browser asks the backend to close the session. If a reconnect flush is already running, hangup must await that existing flush instead of starting a duplicate drain over the same PCM window."
  blind_spots: "This does not prove the broader WebRTC churn is solved; it addresses the first durable loss observed in the post-`c769afb` repro and still requires live phone verification before deployment."
next_action: User reruns the same first-turn poem repro on OMEN after the hangup/backfill ordering fix deployment.

## Rollback Anchor

selected_commit: `6607214de3f65a7855e6d6ad4132bc7d66f3b479` (`docs(debug): record reconnect tail deployment`)
runtime_code_commit: `faba4cc4f62e3f0c8ffd4b57b30f02aec934c1f0` (`fix(call): drain reconnect backfill tail`)
selection_basis: User selected `6607214` because it was the commit tested immediately before the "terrible regression" report and is the desired operational return point.
caveat: Rollback is now explicitly requested. Preserve post-snapshot analysis before restoring runtime code to this anchor.

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

## Investigation Evidence

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

root_cause: The post-`c769afb` first-turn poem repro no longer loses audio before STT: backend logs show `reconnect_audio.backfill.finalize`, `stt.begin`, and `stt.result transcript_len=461`. The remaining first durable loss is browser call-end/reconnect ordering: `hangup()` can call `/end` and clear/close media while the final reconnect-audio request is still pending, so the data channel is closed before backend emits `user_final`, and the HTTP fallback response is reported to the browser as a failed reconnect-audio request instead of being handled.
fix: Updated the browser call page so hangup drains the final reconnect-audio backfill before `/api/calls/{call_id}/end`; `flushReconnectAudioBackfill()` can now await the final batch when used for hangup cleanup and avoids duplicate drains by awaiting an already-running flush.
verification: Focused Playwright regressions failed before the first fix and passed after the refined fix in desktop and mobile Chromium. Full `call-start.spec.ts` passed (26 passed), `npm run build` passed, `git diff --check` passed, and OMEN deployed `d7c8d4d` with `/webrtc/status` ready and `active_sessions=0`.
files_changed:
  - web-ui/client/src/routes/call/[threadId]/+page.svelte
  - web-ui/client/tests/e2e/call-start.spec.ts

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
