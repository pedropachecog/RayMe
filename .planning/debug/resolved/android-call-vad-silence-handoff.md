---
status: resolved
created: 2026-04-26T01:30:00Z
updated: 2026-04-29T02:39:02Z
closure_reason: superseded by solved Android live-call debug session
handoff_for: next-agent
---

# Handoff: Android Call VAD Silence Fix Awaiting Verification

## TL;DR

Previous root cause (VAD never finalizing the turn) was identified and fixed.
Fix is committed and deployed. **Awaiting one more Android Chrome reproduction
to confirm the call now reaches STT → LLM → TTS end to end.** User asked for
handoff because they were running out of tokens; do NOT re-investigate from
scratch.

## Current Deployment State

- Local repo: `/d/Pedro/Repos/Program/RayMe`
- Branch: `main`
- Local HEAD: `0bc6f9d fix(03-debug): drive call VAD silence from Silero, not RMS energy`
- OMEN deployed HEAD: `0bc6f9d` (verified by `scripts/deploy-omen.sh` output)
- Web URL: `https://192.168.1.199:8443`
- AI URL: `https://192.168.1.199:9443`
- Android client IP in logs: `192.168.1.253`
- Listeners after deploy:
  - `192.168.1.199:9443` PID 13612
  - `192.168.1.199:8443` PID 35884
- Health endpoint reports `degraded` with `resident_tts_engine: f5` (expected,
  matches prior runs that worked at the transport layer).

## What Was Already Confirmed Working (Boundary Trace)

Captured in commit `70a175d` (logging-handler fix) Android Chrome reproduction:

| Boundary | Status |
|---|---|
| `offer.received` → `offer.answered` (5030 ms) | OK |
| `iceconnectionstatechange: checking → completed` | OK |
| `connectionstatechange: connecting → connected` | OK |
| `peer.on_datachannel rayme-events readyState=open` | OK |
| `track.recv.first_frame sample_rate=48000 samples=960` | OK |
| `turn.started` (post-resample 16 kHz, 1280 PCM bytes) | OK |
| `vad.speech_start turn_frames=1` | fires on frame 1 |
| `track.recv.progress` 50 → 350 | audio flowing ~7 s |
| `vad.silence` | **NEVER (the bug)** |
| `vad.end_of_turn` / `stt.begin` / LLM / TTS | NEVER reached |
| User hangs up → `MediaStreamError` → cleanup | OK |

WebRTC transport, ICE, data channel, audio track delivery, sample-rate
normalization — all proven working.

## Root Cause That Was Fixed

`CallSession._accept_vad_frame` (`ai-backend/app/call/session.py:463`) had a
real `SileroVadAdapter` loaded but only used its boolean "any speech ever?"
result. `_silence_ms` was driven entirely by an RMS-energy comparator with
threshold = `vad_threshold * 1000` = **500 RMS for int16**. Browser audio
(WebRTC AGC) keeps every frame above that, so:

- Frame 1: energy ≥ 500 → `_speech_seen = True`, `_silence_ms = 0`
- Every subsequent frame: energy ≥ 500 → `_silence_ms = 0` (reset every frame)
- `end_of_turn = _speech_seen and _silence_ms >= 700` → permanently false
- Turn held open forever → no STT → no LLM → no TTS → UI stuck in Listening

## Fix Applied (commit 0bc6f9d)

In `ai-backend/app/call/session.py:463-508`:

When the adapter exposes `speech_timestamps` (the Silero path), derive
`_silence_ms` from the gap between the last speech timestamp's `end` sample
and the buffered sample count, using the adapter's `sampling_rate`. Skip the
energy heuristic entirely on this path.

Energy-only branch kept as fallback when no adapter is present (mostly tests).

Regression test added:
`ai-backend/tests/test_call_session.py::test_silero_silence_gap_finalizes_turn_even_with_loud_ambient_noise`
feeds loud constant-amplitude PCM through a Silero-mimic adapter and asserts
the turn finalizes once silence gap exceeds `vad_end_silence_ms`.

`uv run --project ai-backend pytest ai-backend/tests -q` → **65 passed**.

## Pending: User Reproduction

The user has been asked to reproduce on Android Chrome:

1. `https://192.168.1.199:8443` → ThickGiant thread → phone icon → Allow mic
2. Wait until UI shows **Listening**
3. Speak: "hello, can you hear me", then pause ~2 seconds
4. Wait for AI response (or for it to fail audibly/visibly)
5. Tap End call
6. Reply **"go"**

When user says "go", read OMEN logs immediately:

```bash
ssh rayme-pmpg 'powershell -NoProfile -Command "Get-Content C:\\Users\\pmpg\\rayme\\logs\\ai-backend.hidden.err.log -Tail 300"'
ssh rayme-pmpg 'powershell -NoProfile -Command "Get-Content C:\\Users\\pmpg\\rayme\\logs\\ai-backend.hidden.out.log -Tail 200"'
ssh rayme-pmpg 'powershell -NoProfile -Command "Get-Content C:\\Users\\pmpg\\rayme\\logs\\web-ui.hidden.out.log -Tail 200"'
```

## Expected New Trace If Fix Works

```text
[rayme-call] vad.speech_start session=... turn_frames=1
[rayme-call] track.recv.progress session=... frames=50 state=listening
[rayme-call] vad.silence session=... silence_ms=200 threshold_ms=700
[rayme-call] vad.silence session=... silence_ms=400 threshold_ms=700
[rayme-call] vad.silence session=... silence_ms=600 threshold_ms=700
[rayme-call] vad.end_of_turn session=... turn_frames=N silence_ms=700
[rayme-call] stt.begin session=... turn=user-turn-1 frames=N pcm_bytes=...
[rayme-call] stt.result session=... turn=user-turn-1 transcript_len>0 language=en
[rayme-call] event.sent session=... type=user_final
... LLM streaming events on web-ui side ...
... TTS synth + outbound audio frames ...
[rayme-call] event.sent session=... type=ai_final
```

## If Fix Did Not Work — Diagnostic Next Steps

Walk through the boundary table above against the new trace. The **first**
log line that should appear but does not is the new boundary to fix. Likely
follow-on issues if they materialize:

1. **vad.end_of_turn fires but stt.result transcript is empty** → Whisper
   model not warm or wrong sample rate. Check `_transcribe_turn` in
   `ai-backend/app/call/session.py:508` and `WhisperSttAdapter`.
2. **stt.result fires but no LLM tokens** → Web-ui orchestration not picking
   up `user_final` event. Check `web-ui/server/app/api/calls.py` event
   forwarding and `/turns` SSE in `web-ui/server/app/api/turns.py`.
3. **LLM tokens flow but no TTS audio** → Check `_synthesize_speech` and
   F5-TTS adapter. Look for `[rayme-call] tts.*` logs (may need to add).
4. **TTS frames generated but no browser playback** → Check
   `outbound_audio_track.enqueue` and browser `connection.ontrack` handler in
   `web-ui/client/src/lib/call/client.ts`.
5. **Silero is over-triggering even when user isn't speaking** → User says
   "Listening" never transitions to a finished turn. Check
   `vad_threshold` / `vad_end_silence_ms` in `ai-backend/app/config.py`
   (default 0.5 / 700 ms). May need to tune.
6. **Silero raises an exception on the first frame** → `track.recv.exception`
   would fire early. The `except` in `_receive_audio_track` calls
   `session.fail("connection_failed")`. Check err log for Silero traceback.

## Do Not Regress

- Do not reintroduce fake or synthetic success paths (handoff doc explicitly
  forbade this; commits `1be53a7` removed them).
- Do not run Playwright E2E (user said those always fail).
- Do not hide failures by leaving the UI stuck in `Listening`.
- Do not undo the logging-handler fix in `ai-backend/scripts/run_https.py`
  (`build_log_config()`) — without it, all `[rayme-call]` instrumentation is
  silently discarded by uvicorn's default LOGGING_CONFIG.
- Do not change the `accept_audio_frame` adapter branch in
  `_accept_vad_frame` — existing tests rely on it.

## Files Touched In This Session

- `ai-backend/app/call/session.py` (the fix)
- `ai-backend/tests/test_call_session.py` (regression test +
  `ScriptedSileroVadAdapter` helper class)
- `.planning/debug/android-call-offer-502.md` (root-cause section appended)

## Recent Commit History

```
0bc6f9d fix(03-debug): drive call VAD silence from Silero, not RMS energy   <-- THIS FIX
70a175d fix(03-debug): wire app.* loggers to uvicorn handler                <-- visibility
6751631 chore(03-debug): instrument post-offer call lifecycle               <-- logging
94150d4 docs: replace Android call handoff
1be53a7 fix: remove synthetic call facade fallbacks
27750e9 fix: surface real WebRTC offer failures
6d817dd fix: wire real call audio path
03d2f34 docs(debug): capture Android call offer failure
```

## Verification Already Run

- `uv run --project ai-backend pytest ai-backend/tests -q` → **65 passed**
- `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` → **13 passed**
- Push: `0bc6f9d` on `origin/main` (verified by `git push` output)
- Deploy: `OMEN deploy complete: 0bc6f9dcacf645d1e4c84d4d79fd289c05100d3a`

## Useful Commands

```bash
cd /d/Pedro/Repos/Program/RayMe

# Confirm OMEN is on the right commit
ssh rayme-pmpg 'powershell -NoProfile -Command "Set-Location C:\\Users\\pmpg\\rayme\\RayMe; git rev-parse --short HEAD"'

# AI backend status
curl -k -sS https://192.168.1.199:9443/webrtc/status | jq '{status, live_call_ready, media_transport_ready, active_sessions}'

# Tail logs after Android reproduction
ssh rayme-pmpg 'powershell -NoProfile -Command "Get-Content C:\\Users\\pmpg\\rayme\\logs\\ai-backend.hidden.err.log -Tail 300"'
ssh rayme-pmpg 'powershell -NoProfile -Command "Get-Content C:\\Users\\pmpg\\rayme\\logs\\ai-backend.hidden.out.log -Tail 200"'
ssh rayme-pmpg 'powershell -NoProfile -Command "Get-Content C:\\Users\\pmpg\\rayme\\logs\\web-ui.hidden.out.log -Tail 200"'

# Re-deploy if needed
git push origin main && scripts/deploy-omen.sh
```

## SSH Note

If `ssh rayme-pmpg` fails with "Could not resolve hostname":

```bash
RAYME_SSH_ALIAS=rayme-pmpg RAYME_SSH_USER=pmpg \
  scripts/bootstrap-rayme-ssh.sh restore
```

`scripts/deploy-omen.sh` already runs this automatically.

## Command For Next Agent

```bash
cd /d/Pedro/Repos/Program/RayMe && codex '$gsd-debug continue android-call-offer-502. First read .planning/debug/android-call-vad-silence-handoff.md. The VAD silence fix is deployed at commit 0bc6f9d. The user has been asked to reproduce one more time on Android Chrome. When they reply "go", read the OMEN logs and confirm vad.silence -> vad.end_of_turn -> stt.begin -> stt.result -> LLM -> TTS chain completes. If a new boundary fails, fix it without reintroducing synthetic paths and without running Playwright.'
```
