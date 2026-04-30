---
status: awaiting_human_verify
created: 2026-04-29T19:18:06Z
updated: 2026-04-30T12:31:00Z
trigger: "Phone calls fail to transcribe the whole content of user speech; RayMe misses whole chunks of long turns."
---

# Debug Session: Phone Calls Missing Speech Chunks

## Current Focus

reasoning_checkpoint:
  hypothesis: "Phone call transcription loses chunks because `CallSession` finalizes turns too aggressively: false Silero silence lasting ~700 ms is accepted as end-of-turn during continuous speech, and the 30s `vad_max_turn_ms` would force-cut long continuous turns even after false-silence tolerance is fixed."
  confirming_evidence:
    - "OMEN logs show affected turns reach `stt.begin` already short; downstream `user_final` forwarding happens after those short STT inputs."
    - "For latest session `rtc_3acc177ecea14b5493657d3e72f8bd2a`, turn 4 and turn 5 include long pre-speech waits, then only ~4.8s and ~11.4s of speech respectively before `vad.end_of_turn silence_ms=722`."
    - "User clarified they made sure not to pause during the speech, so those 722 ms gaps are false VAD silence, not intentional end-of-turn pauses."
    - "`CallSession._accept_vad_frame` ends on `self._silence_ms >= settings.vad_end_silence_ms` and also force-ends when `turn_duration_ms >= settings.vad_max_turn_ms`."
  falsification_test: "If a test simulating a 700ms false-negative VAD gap during otherwise continuous call speech does not finalize under the new call threshold, and a continuous 32s call turn does not force-finalize, the proposed fix addresses the observed cutoff mechanisms. If real calls still truncate before STT with longer thresholds, the remaining cause is deeper Silero false-negative duration or media capture loss."
  fix_rationale: "Use call-specific VAD finalization thresholds: keep general STT defaults intact, but make live calls tolerate short false VAD gaps and allow long monologues before the safety max forces a chunk."
  blind_spots: "No local reproduction has the user's exact microphone/audio; longer thresholds may add up to ~1.8s response latency after true speech ends, and speech longer than the new max turn still chunks."
next_action: Run another long-passage phone-call verification and confirm `vad.reconnect_grace.*` logs appear without premature `user_final`.
tdd_checkpoint:

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

## Investigation Evidence

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

## Resolution

root_cause: Phone call transcription loses chunks before STT. The first loss mode was overly aggressive live-call VAD finalization (`vad.end_of_turn silence_ms=722`) and a 30s hard max-turn cap. After commit `ba6057c`, the remaining loss mode is mid-speech browser media reconnect: Android Chrome drops/reoffers the WebRTC media path during long speech, the server preserves the in-progress turn, but the replacement track begins with startup silence; VAD treats that reconnect gap as the end of the user's speech and finalizes before the rest of the spoken passage arrives.
fix: Added call-specific VAD settings (`call_vad_end_silence_ms=1800`, `call_vad_max_turn_ms=120000`), updated `CallSession` to use them for live-call turn finalization/windowing, and added regression tests for false Silero silence during continuous speech and continuous speech beyond 30 seconds. Follow-up fix: added `call_media_reconnect_grace_ms=5000`; when a browser reoffer replaces the peer connection during an active spoken turn, `CallSession` arms a short grace window and starts it on the first frame of the new track so reconnect startup silence does not finalize the turn before speech resumes.
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
files_changed:
  - ai-backend/app/config.py
  - ai-backend/app/call/session.py
  - ai-backend/app/api/webrtc.py
  - ai-backend/tests/test_call_session.py
