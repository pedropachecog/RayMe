---
status: investigating
trigger: "Android Chrome Phase 3 live call: microphone permission is granted and Android shows mic listening, then the RayMe call UI still fails or becomes unusable."
created: 2026-04-25T23:36:09Z
updated: 2026-04-25T23:36:09Z
---

# Debug Session: Android Call Offer 502

## Symptoms

- Expected behavior: on Android Chrome, starting a call to `ThickGiant` asks for
  microphone permission, enters `Listening`, shows visible microphone activity,
  accepts user speech, transcribes the turn, generates an AI response, and plays
  F5 speech.
- Actual behavior reported by product-owner testing:
  - Initial deploy: Android did not ask for microphone permission, UI showed no
    activity, and hangup showed `Failed`.
  - After `3226fd5`: Android asked for microphone permission, then failed after
    one or two seconds.
  - After `a325c35`: Android showed that the microphone was listening, then
    still failed.
  - After `66e2850`: not yet manually retested by product owner at the time this
    debug file was written.
- Android device/client IP seen in OMEN logs: `192.168.1.253`.
- Developer desktop/browser smoke IP seen in OMEN logs: `192.168.1.190`.

## Current Focus

- hypothesis: Android Chrome's real SDP offer is rejected, times out, or fails
  in the Web UI to AI backend `/webrtc/offer` forwarding path. The user-visible
  failure has been reduced, but the underlying live media path is still not
  proven working.
- test: reproduce with a real or captured Android SDP offer against
  `POST https://192.168.1.199:8443/api/calls/{call_id}/offer` and then directly
  against `POST https://192.168.1.199:9443/webrtc/offer`, while capturing
  backend exceptions and response status.
- expecting: the web facade returns `502` with public code
  `webrtc_offer_failed` or `unreachable`, and the AI backend either receives no
  `/webrtc/offer` request or rejects the Android SDP inside aiortc negotiation.
- next_action: instrument the Web UI call offer facade and AI backend WebRTC
  offer route with safe structured diagnostics for status, elapsed time, and
  exception class; then reproduce on Android and inspect
  `C:\Users\pmpg\rayme\logs\*.hidden.*.log`.
- reasoning_checkpoint: do not keep patching the UI blindly. The permission and
  local microphone symptoms are already fixed. The remaining root cause is in
  the WebRTC offer/answer or aiortc media negotiation path.
- tdd_checkpoint: add regression coverage only around confirmed failure mode;
  avoid tests that merely assert the UI hides backend failure.

## Evidence

- timestamp: 2026-04-25T22:33Z
  observation: Commit `3226fd5` fixed the first startup defect.
  details:
    - `web-ui/client/src/routes/call/[threadId]/+page.svelte` now calls
      `navigator.mediaDevices.getUserMedia` before starting the call.
    - The browser now posts `/api/calls/{call_id}/offer`.
    - Android correctly asks for microphone permission after this commit.

- timestamp: 2026-04-25T22:44Z
  observation: Commit `a325c35` fixed the opaque client-side post-permission
  failure path.
  details:
    - Local mic metering starts immediately after microphone permission.
    - The call UI reaches `Listening` before WebRTC remote answer application.
    - `setRemoteDescription` failures no longer force the generic `Failed`
      panel.

- timestamp: 2026-04-25T23:00Z
  observation: OMEN hidden web logs captured the Android real failure.
  exact_lines:
    - `INFO: 192.168.1.253:41462 - "POST /api/calls/start HTTP/1.1" 201 Created`
    - `INFO: 192.168.1.253:41462 - "POST /api/calls/call_7348bdbc558449e09ea44a6d8e696802/offer HTTP/1.1" 502 Bad Gateway`
  interpretation: Android got past permission and call creation. The failing
  boundary was offer forwarding, not mic permission or thread loading.

- timestamp: 2026-04-25T23:00Z
  observation: AI backend hidden logs did not show a corresponding
  `/webrtc/offer` access line for the Android 502.
  details:
    - AI log tail showed health/status requests only.
    - `/webrtc/status` reported `active_sessions: 2`.
  interpretation: either the web facade timed out/failed before the request was
  logged by uvicorn, or the logging tail did not capture the request. This needs
  targeted instrumentation.

- timestamp: 2026-04-25T23:20Z
  observation: Commit `66e2850` was deployed to OMEN.
  details:
    - Deployed commit: `66e2850c32f6dc8a988941960899689eb5835672`.
    - Web listener: `192.168.1.199:8443`, pid `30876` before this handoff.
    - AI listener: `192.168.1.199:9443`, pid `36408` before this handoff.
    - Live desktop smoke after deploy reached `Listening`, posted
      `/api/calls/start` and `/api/calls/{id}/offer`, and had no browser errors.
  limitation: this smoke uses fake media on desktop Chromium and does not prove
  Android SDP, Android media transport, STT, LLM, or F5 playback.

## Eliminated

- hypothesis: Android Chrome did not receive or load the newest client bundle.
  evidence: hidden logs show Android loaded hashed bundle assets
  `start.DGM4CIoX.js` / `app.BSrKBRPv.js` after the `a325c35` deploy, and later
  deployments changed hashes again.

- hypothesis: microphone permission is the remaining blocker.
  evidence: product owner reports Android shows mic listening, and server logs
  show Android reaches `/api/calls/start` and `/api/calls/{id}/offer`.

- hypothesis: the Web UI cannot create call records on OMEN.
  evidence: Android got `201 Created` from `/api/calls/start`.

- hypothesis: the AI backend process is down.
  evidence: `/health` responds with `status: degraded`, `stt_model:
  distil-large-v3`, `vad_ready: True`, `resident_tts_engine: f5`; listeners are
  up on `8443` and `9443`.

## Code Changes Already Applied

- `e77b0e4 fix(03-11): support OMEN Python typing`
  - Fixed Python 3.10 `typing.NotRequired` import crash on OMEN.

- `3226fd5 fix(03-11): request mic and negotiate call session`
  - Added explicit microphone request.
  - Added browser WebRTC offer posting from the call route.

- `a325c35 fix(03-11): keep Android call UI alive after mic grant`
  - Added local mic meter.
  - Kept UI alive when remote SDP application fails.

- `66e2850 fix(03-11): keep call active when Android offer fails`
  - Client no longer fails the whole call if `/api/calls/{id}/offer` returns an
    error.
  - Server `end_call` records a local call end even if backend session control
    fails.

## Verification Already Run

- `npm --prefix web-ui/client run check` passed.
- `npm --prefix web-ui/client run build` passed.
- `npm --prefix web-ui/client run test:e2e -- tests/e2e/call-start.spec.ts --project=desktop-chromium --workers=1`
  passed: `4 passed`.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q`
  passed: `17 passed`.
- OMEN deployment via `scripts/deploy-omen.sh` completed at `66e2850`.

## Important Files For Debugger

- `web-ui/client/src/routes/call/[threadId]/+page.svelte`
- `web-ui/client/src/lib/api/calls.ts`
- `web-ui/server/app/api/calls.py`
- `web-ui/server/app/domain/ai_backend_client.py`
- `ai-backend/app/api/webrtc.py`
- `ai-backend/app/call/session.py`
- `ai-backend/app/call/tracks.py`
- `web-ui/server/tests/test_calls.py`
- `ai-backend/tests/test_webrtc_signaling.py`
- `.planning/phases/03-first-working-call-mvp/OMEN-PC-LIVE-EVIDENCE.md`

## Operational Notes

- Use `ssh rayme-pmpg`, not raw hostnames.
- Deploy with `scripts/deploy-omen.sh`; do not hand-deploy.
- Push commits before deploy so OMEN can fast-forward pull.
- OMEN checkout: `C:\Users\pmpg\rayme\RayMe`.
- OMEN logs:
  - `C:\Users\pmpg\rayme\logs\web-ui.hidden.out.log`
  - `C:\Users\pmpg\rayme\logs\web-ui.hidden.err.log`
  - `C:\Users\pmpg\rayme\logs\ai-backend.hidden.out.log`
  - `C:\Users\pmpg\rayme\logs\ai-backend.hidden.err.log`
- Live URLs:
  - Web: `https://192.168.1.199:8443`
  - AI health: `https://192.168.1.199:9443/health`
  - AI WebRTC status: `https://192.168.1.199:9443/webrtc/status`

## Recommended Next Debug Steps

1. Add structured, safe logging around `web-ui/server/app/api/calls.py`
   `create_call_offer`:
   - call id
   - stored session id
   - offer SDP length
   - whether SDP includes `m=audio`, `a=ice-ufrag`, `a=fingerprint`
   - elapsed time for `backend.create_webrtc_offer`
   - sanitized exception class/code on failure
2. Add structured logging around `ai-backend/app/api/webrtc.py`
   `create_webrtc_offer_answer`:
   - session id
   - offer SDP length/features
   - whether aiortc peer connection was created
   - exception class from `_negotiate_answer`
3. Reproduce from Android and inspect hidden logs.
4. If aiortc rejects Android SDP, build a fixture from a sanitized Android SDP
   sample and add an `ai-backend/tests/test_webrtc_signaling.py` regression.
5. Only after offer negotiation succeeds, debug media track ingestion, VAD/STT,
   LLM turn generation, and F5 playback.

## Resolution

- root_cause:
- fix:
- verification:
- files_changed:
