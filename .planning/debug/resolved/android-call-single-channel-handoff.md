---
status: resolved
created: 2026-04-26T12:40:13Z
updated: 2026-04-29T02:39:02Z
closure_reason: superseded by solved Android live-call debug session
handoff_for: next-agent
---

# Handoff: Android Call VAD End-of-Turn Never Fires

## TL;DR

Two independent bugs are blocking the entire call pipeline. Both are fixed locally
but **neither is deployed**. The next agent should commit, push, deploy, then
wait for the user to reproduce on Android Chrome.

**Bug 1 — Logging format crash (committed `9275e36`, deployed):**
`on_datachannel` logger had 3 `%s` placeholders but only 2 args. Crashed the
handler before the data-channel keepalive task could start.

**Bug 2 — VAD `end_of_turn` never fires (uncommitted, NOT deployed):**
Silero's `speech_timestamps()` on the full buffered audio keeps classifying
everything as one continuous speech segment. `_silence_ms` stays 0, so
`vad.end_of_turn` never fires. No STT, no LLM, no TTS. The system appears
"deaf" because the turn never finalizes.

Fix: Added `vad_max_turn_ms` config (default 5000ms) as a safety net — forces
end of turn after continuous speech exceeds the limit.

## Current Deployment State

- Local repo: `/d/Pedro/Repos/Program/RayMe`
- Branch: `main`
- Local HEAD: `9275e36` (logging format fix only)
- OMEN deployed HEAD: `9275e36`
- **Uncommitted changes in working tree:**
  - `ai-backend/app/call/session.py` — VAD max-turn duration + `_speech_start_frame`
  - `ai-backend/app/config.py` — `vad_max_turn_ms` field

## What Was Proven In This Session

Both sessions on `9275e36` (second call, `rtc_0ed2202b...`):

| Boundary | Outcome |
|---|---|
| `offer.received` -> `offer.answered` | OK |
| ICE `checking -> completed` | OK |
| Peer `connecting -> connected` | OK |
| `peer.on_datachannel` (no crash) | OK — logging fix works |
| `track.recv.first_frame sample_rate=48000 samples=960` | OK |
| `turn.started frame_count=1 sample_rate=16000 pcm_bytes=640` | OK |
| `vad.diag frame=1 rms=896.3 peak=2348.0` | OK — audio levels healthy |
| `vad.bufdiag buf_rms=0.0235 buf_peak=0.0829 dur_ms=200` | OK |
| `vad.silero ts_count=0` | OK — initial, expected |
| `vad.speech_start turn_frames=15` | OK — speech detected |
| `track.recv.progress` 50..450 | OK — frames keep flowing |
| `vad.silence` | **NEVER** |
| `vad.end_of_turn` | **NEVER** |
| `stt.begin` / `stt.result` / LLM / TTS | **NEVER** |
| browser `datachannel.open` | OK |
| browser `datachannel.close` | After connection death |
| browser ICE `connected -> disconnected -> failed` | **FAILS** ~5s after connect |

**Root cause of "deaf" behavior:** Silero keeps all buffered audio as one
speech segment. After 450 frames (~9s) the browser hangs up (ICE disconnect),
and the turn never finalizes. No transcription ever runs.

## Uncommitted Changes

### `ai-backend/app/config.py`
- Added `vad_max_turn_ms: int = Field(default=5000, ge=1000)`

### `ai-backend/app/call/session.py`
- Added `self._speech_start_frame: int | None = None` to `__init__`
- In Silero `speech_timestamps` path: tracks `_speech_start_frame`, computes
  `turn_duration_ms = frame_idx * frame_ms`, forces `end_of_turn` when
  `turn_duration_ms >= vad_max_turn_ms`
- In energy-based fallback path: same max-turn safety net
- Reset `_speech_start_frame = None` in `finalize_user_turn()`

## Why 5000ms and not 10000ms?

Browser ICE disconnects at ~9-10s. With a 5s max turn, the turn forces at
~5s, giving ~4s for STT + LLM + TTS to complete before ICE dies. Tight but
workable. If ICE keepalive also works (logging fix), the window opens.

## Immediate Next Step

1. Commit the uncommitted changes
2. Push to GitHub
3. Deploy with `bash scripts/deploy-omen.sh`
4. Tell user to test on Android Chrome, say "go" when done
5. Pull logs and trace:

```bash
ssh rayme-pmpg 'powershell -NoProfile -Command "Get-Content C:\\Users\\pmpg\\rayme\\logs\\ai-backend.hidden.err.log -Tail 500"'
ssh rayme-pmpg 'powershell -NoProfile -Command "Get-Content C:\\Users\\pmpg\\rayme\\logs\\ai-backend.hidden.out.log -Tail 300"'
```

6. Check the first missing boundary in this order:
   1. backend `vad.speech_start`
   2. backend `vad.end_of_turn` (should fire at ~5s max-turn)
   3. backend `stt.begin`
   4. backend `stt.result transcript_len>0`
   5. browser `datachannel.message event_type=user_final`
   6. backend `tts.enqueue`
   7. browser remote audio playback

## Secondary Issue: Browser ICE Disconnect

Android Chrome ICE goes `connected -> disconnected -> failed` ~5s after connect.
This is a separate, ongoing issue. The data-channel keepalive (app-layer) may
help if SCTP traffic counts as DTLS activity — but the logging bug prevented
it from ever running. Now fixed. Watch for:
- `datachannel.close` timing — does it come sooner or later?
- Browser-side ICE state progression in debug events

## Known Open Issues

1. **VAD end-of-turn** — uncommitted fix, needs deploy + test
2. **Browser ICE disconnect** — root cause unknown. May need aiortc ICE keepalive
   config or browser-side `iceTransportPolicy` tuning
3. **Voice reference 409** — previously fixed, shows as warning only

## User Constraints

- Do not run Playwright.
- Do not reintroduce fake or synthetic success paths.
- The user does the Android testing on Chrome (device IP 192.168.1.253).
- Agent reads logs after the user says `go`.

## Recent Commit History

```text
9275e36 fix(03-debug): add missing `ready` arg to on_datachannel logger
faac744 fix(03-debug): add data channel keepalive task
8b6b9e6 fix(03-debug): use single browser-owned call data channel
445c19f fix(03-debug): keep retryable call failures in session
f6054d1 fix(03-debug): disable double-vad on call stt
f144354 fix(03-debug): handle packed stereo inbound audio
785414e fix(03-debug): handle pyav audio frame orientation
```
