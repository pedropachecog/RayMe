---
status: investigating
created: 2026-04-26T00:58:20Z
updated: 2026-04-26T00:58:20Z
handoff_for: next-agent
---

# Handoff: Android Call Stuck In Listening After Successful Offer

## User-Visible Symptom

After deploying commit `1be53a7`, the user tested Android Chrome again. The call
still gets stuck in `Listening`. It does not progress to a user transcript, AI
response, or audible TTS. The user hangs up manually.

The user does not want a clearer failure only. The requirement is a real working
call path.

## Current Deployment State

- Local repo: `/d/Pedro/Repos/Program/RayMe`
- Branch: `main`
- Local HEAD: `1be53a7 fix: remove synthetic call facade fallbacks`
- OMEN deployed HEAD verified by SSH: `1be53a7`
- Web URL: `https://192.168.1.199:8443`
- AI URL: `https://192.168.1.199:9443`
- Android client IP in logs: `192.168.1.253`
- Web listener: `192.168.1.199:8443`
- AI listener: `192.168.1.199:9443`
- AI `/webrtc/status` after test:
  - `status: ready`
  - `live_call_ready: true`
  - `media_transport_ready: true`
  - `active_sessions: 0`
- Web `/api/settings` after test:
  - `ai_backend_url: https://192.168.1.199:9443`
  - `endpoint_status: degraded`
  - `resident_tts_engine: f5`

## Important Change From Prior Failure

This is no longer the same Android 502 offer failure.

Latest OMEN web log from Android after deploying `1be53a7`:

```text
INFO: 192.168.1.253:41088 - "POST /api/calls/start HTTP/1.1" 201 Created
INFO: 192.168.1.253:41088 - "POST /api/calls/call_c1e0c4bd0b214a31a1af6d6ffec82c5c/offer HTTP/1.1" 200 OK
INFO: 192.168.1.253:42426 - "POST /api/calls/call_c1e0c4bd0b214a31a1af6d6ffec82c5c/end HTTP/1.1" 200 OK
```

Matching OMEN AI log:

```text
INFO: 192.168.1.199:53595 - "POST /webrtc/offer HTTP/1.1" 200 OK
INFO: 192.168.1.199:55595 - "POST /webrtc/sessions/rtc_b2c3e6bc44eb4f238b155a673157c3a6/end HTTP/1.1" 200 OK
```

Interpretation:

- Browser microphone and call start are not the current blocker.
- Web facade forwarding to AI is not the current blocker.
- AI backend is accepting the WebRTC offer and returning an answer.
- The problem is after offer/answer: media transport, data channel, inbound
  audio processing, VAD/STT finalization, event delivery to browser, or browser
  playback.

## Recent Fixes Already Applied

Commit `6d817dd fix: wire real call audio path`:

- Removed the AI backend fake answer path.
- Added outbound queued audio track support.
- Added browser `connection.ontrack` remote audio playback.
- Removed hidden LLM token shortcut path.
- Added production guard for fake/mock/stub tokens.
- Fixed `scripts/deploy-omen.sh` to restore the `rayme-pmpg` SSH alias before
  deploy.

Commit `27750e9 fix: surface real WebRTC offer failures`:

- Increased WebRTC offer timeout.
- Preserved safer backend offer failure details.
- Added more offer failure handling.

Commit `1be53a7 fix: remove synthetic call facade fallbacks`:

- Removed production web facade branches that returned pretend success when
  backend call methods were missing.
- Missing backend call methods now return `call_backend_client_misconfigured`.
- `end_call` no longer hides a misconfigured backend client.
- Strengthened production guard to reject `answer: None`.

## Do Not Regress

- Do not reintroduce fake or synthetic success paths.
- Do not hide failures by leaving the UI stuck in `Listening`.
- Do not run Playwright E2E; the user explicitly said those always fail.
- Do not spend time re-solving SSH. Use `ssh rayme-pmpg`; deploy script already
  restores the alias.
- Do not mark this resolved until the live Android path is proven end to end.

## Files To Inspect First

- `web-ui/client/src/routes/call/[threadId]/+page.svelte`
- `web-ui/client/src/lib/api/calls.ts`
- `web-ui/client/src/lib/call/client.ts`
- `web-ui/server/app/api/calls.py`
- `web-ui/server/app/domain/ai_backend_client.py`
- `ai-backend/app/api/webrtc.py`
- `ai-backend/app/call/session.py`
- `ai-backend/app/call/tracks.py`
- `ai-backend/app/call/events.py`

## High-Probability Debug Targets

1. Browser may accept the answer but WebRTC ICE/connection state never reaches
   connected on Android.
2. Backend may receive the offer but not receive inbound audio frames.
3. Backend VAD/STT may never emit `user_final` from Android microphone audio.
4. Backend may emit events, but the browser may not subscribe to or handle them.
5. Browser may be listening locally but not sending audio over the peer
   connection.
6. Remote backend TTS track may exist, but no generated audio is ever enqueued
   because no user turn finalizes.

## Immediate Next Steps

1. Add safe structured logs around the WebRTC connection lifecycle on both ends:
   - Browser: `iceconnectionstatechange`, `connectionstatechange`,
     `signalingstatechange`, data channel open/message/close/error, remote
     track received, audio play rejection.
   - AI backend: peer connection state changes, inbound track creation, audio
     frame count, VAD speech start/end, STT final transcript, event publish,
     TTS enqueue.
2. Deploy instrumentation, reproduce once on Android, and read logs.
3. Fix the first real broken boundary.
4. Verify with Android user test:
   microphone -> WebRTC -> backend audio frames -> STT final -> LLM -> TTS ->
   outbound WebRTC audio -> browser playback.

## Commands

From repo root:

```bash
cd /d/Pedro/Repos/Program/RayMe
git status --short
ssh rayme-pmpg 'powershell -NoProfile -Command "Set-Location C:\\Users\\pmpg\\rayme\\RayMe; git rev-parse --short HEAD"'
curl -k -sS https://192.168.1.199:9443/webrtc/status | jq '{status, live_call_ready, media_transport_ready, active_sessions}'
```

Tail logs after Android reproduction:

```bash
ssh rayme-pmpg 'powershell -NoProfile -Command "Get-Content C:\\Users\\pmpg\\rayme\\logs\\web-ui.hidden.out.log -Tail 160; Write-Output AI_LOG; Get-Content C:\\Users\\pmpg\\rayme\\logs\\ai-backend.hidden.out.log -Tail 160; Write-Output AI_ERR; Get-Content C:\\Users\\pmpg\\rayme\\logs\\ai-backend.hidden.err.log -Tail 120"'
```

Deploy:

```bash
git push origin main && scripts/deploy-omen.sh
```

## Verification Already Run Before This Handoff

- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q`
  passed: `24 passed`
- `uv run --project web-ui/server pytest web-ui/server/tests -q`
  passed: `147 passed`
- `uv run --project ai-backend pytest ai-backend/tests -q`
  passed: `63 passed, 1 warning`
- `uv run --project ai-backend pytest ai-backend/tests/test_no_synthetic_production_paths.py -q`
  passed: `1 passed`
- `npm --prefix web-ui/client run check` passed

## Command For Next Agent

```bash
cd /d/Pedro/Repos/Program/RayMe && codex '$gsd-debug continue android-call-offer-502. First read .planning/debug/android-call-listening-stuck-handoff.md. The latest deployed commit is 1be53a7 and Android now gets POST /offer 200 OK but remains stuck in Listening. Do not run Playwright E2E. Do not reintroduce fake or synthetic success. Instrument and fix the real post-offer WebRTC/audio/STT/TTS path until the Android call works end to end.'
```
