---
status: resolved
trigger: "Call work was claimed before the implementation proved end-to-end microphone, turn generation, and audio playback behavior."
created: 2026-04-26T00:14:20Z
updated: 2026-04-29T02:39:02Z
closure_reason: call-working incident criteria satisfied by final live-call fix and user acceptance
---

# Debug Incident: Call Working Criteria Failure

## What Went Wrong

- The implementation treated call setup and UI state as progress toward a
  working call, even though a working call requires end-to-end media and turn
  behavior.
- The backend had inbound microphone frame handling, STT finalization, LLM turn
  streaming, and a TTS control route, but it did not attach a real outbound
  WebRTC audio track to the peer connection before answering.
- The browser call route negotiated an answer but did not attach a remote audio
  stream to an audio element for playback.
- Tests accepted call startup and visible UI state without requiring server
  outbound media wiring or browser remote playback wiring.
- Deployment tooling depended on an ambient SSH alias instead of restoring the
  repo-persisted SSH configuration before use.

## Correct Standard Going Forward

- Do not claim calls work unless all of these are true:
  - browser obtains microphone permission from a user gesture;
  - browser sends real microphone media over WebRTC;
  - backend receives audio frames and emits `user_final`;
  - web server streams AI text for that exact user turn;
  - backend synthesizes TTS for the AI turn;
  - synthesized audio is queued onto a WebRTC outbound audio track;
  - browser receives a remote audio track and attempts playback;
  - hangup/mute/interrupt operate against the same live session.
- Production code must not invent successful media answers, placeholder call
  behavior, or hidden shortcuts to satisfy tests.
- Tests may use doubles, but production behavior must be guarded by tests that
  assert real wiring boundaries rather than labels or visual state alone.
- Deploy scripts must restore the documented SSH configuration before invoking
  SSH; a missing ambient alias is a tooling defect, not an acceptable blocker.

## Fixes In Progress

- AI backend now creates a queued outbound audio track and attaches it to the
  peer connection before SDP negotiation.
- Call TTS output is queued into that outbound track.
- Browser call route now attaches remote WebRTC audio tracks to an autoplay
  audio element.
- WebRTC offer failures no longer produce synthetic SDP success.
- Deploy script restores the `rayme-pmpg` SSH alias before use.

## Verification Required Before Closing

- Backend tests proving outbound track queueing and WebRTC session wiring.
- Client check and call browser test.
- Live OMEN deployment through `scripts/deploy-omen.sh`.
- Non-mocked live call evidence, then Android product-owner acceptance.
