---
status: fixing
created: 2026-04-29T19:18:06Z
updated: 2026-04-30T17:38:16Z
trigger: "Phone calls fail to transcribe the whole content of user speech; RayMe misses whole chunks of long turns."
---

# Debug Session: Phone Calls Missing Speech Chunks

## Current Focus

hypothesis: Post-`2360feb` diagnostics show the first lost speech is the multi-second browser/WebRTC outage during media reconnect, not browser mic mute and not backend VAD rejection. The browser captures speech while the peer connection is failed/reconnecting; the backend receives no frames until the reoffer completes, then receives VAD-positive speech again.
test: Implement browser-side reconnect-gap PCM buffering and backend active-turn backfill, preserving ordering by posting the buffered gap after the backend accepts the reoffer but before the browser applies the answer and starts replacement-track media.
expecting: STT should receive one ordered turn containing pre-reconnect frames, buffered reconnect-gap PCM, and replacement-track frames. Reconnect diagnostics should show `mic.reconnect_backfill.sent` and backend `reconnect_audio.backfill.applied`.
next_action: Commit, push, deploy with `scripts/deploy-omen.sh`, then ask user to repeat the long-passage repro.

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

## Investigation Evidence

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

root_cause: Phone call transcription loses chunks before STT. Prior confirmed root causes were overly aggressive live-call VAD finalization, a 30s hard max-turn cap, and failed-state reoffers that did not arm reconnect grace. As of deployed commit `2360feb`, the latest diagnostics isolate the remaining loss: browser media reconnect creates a multi-second WebRTC outage during continuous speech. The browser local mic remains live and captures nonzero/high RMS while `mediaReconnecting=true`, but the backend old track has failed and the replacement track has not started receiving frames yet. When the replacement track starts, backend RMS is nonzero and Silero reports `speech_now=True`, so backend VAD is not rejecting real post-reconnect audio. Speech spoken during the outage is never delivered or replayed.
fix: Added call-specific VAD settings (`call_vad_end_silence_ms=1800`, `call_vad_max_turn_ms=120000`), updated `CallSession` to use them for live-call turn finalization/windowing, and added regression tests for false Silero silence during continuous speech and continuous speech beyond 30 seconds. Follow-up fix: added `call_media_reconnect_grace_ms=5000`; when a browser reoffer replaces the peer connection during an active spoken turn, `CallSession` arms a short grace window and starts it on the first frame of the new track so reconnect startup silence does not finalize the turn before speech resumes. Post-`e4b93d9` follow-up: recover `failed/connection_failed` sessions before marking reconnect grace so failed-then-reoffered mid-turn calls actually arm the grace window. Post-`2360feb` follow-up: add browser-side rolling 16 kHz PCM buffering and active-turn backend backfill for media reconnect gaps, sent after backend reoffer acceptance but before replacement peer answer application so STT sees pre-reconnect + gap + post-reconnect audio in order.
verification:
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
files_changed:
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
