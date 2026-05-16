# Live Call Invariants

RayMe's core product is a live phone call with an AI. Every call, TTS, STT,
VAD, WebRTC, reconnect, and call UI change must preserve that product shape.

## Non-Negotiables

- NEVER wait for full assistant response generation or full TTS stream completion before first playback in a live call, unless the user explicitly asks for a named non-live mode.
- Live-call playback must begin from early available audio and continue while
  later audio is produced.
- Smoothness fixes may use bounded jitter/startup buffering only. The buffer
  must have an explicit upper bound and tests that prove it does not become
  full-response generate-then-play.
- Calls must remain interruptible. Barge-in, hangup, mute, and reconnect fixes
  must not strand the UI in fake `Listening`, endless `Rehearsing`, or a dead
  call surface.
- Immediate first-audio metrics and final playback metrics must stay separate.
  First-audio evidence cannot stand in for smooth-playback evidence.

## Required Tests

Any live-call TTS change must include focused tests proving:

- first playback starts before stream completion for a deliberately slow stream,
- the VoxCPM2 live-call streaming path does not call whole synthesis fallback,
- final-only timing fields are not copied into the immediate `ai_audio_started`
  event,
- interrupt after first audio prevents late chunks from continuing as a normal
  completed turn.

## GSD Rule

Always GSD for non-trivial product changes, incident repair, regressions, and
deployments. That means:

- create or update the phase/plan/debug/learning/evidence artifact first,
- write the user-goal preservation sentence before implementation,
- run local tests before deployment,
- deploy OMEN only through `scripts/deploy-omen.sh`,
- verify the deployed commit and health before asking for product-owner
  acceptance.

Quick fixes are acceptable only for genuinely trivial local edits that do not
touch product behavior, live calls, AI runtime, deployment, or user-visible
workflows.
