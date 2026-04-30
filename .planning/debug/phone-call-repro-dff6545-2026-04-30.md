# Phone Call Repro After dff6545: 2026-04-30

Source: fresh investigation after the user's post-`dff6545` phone-call
reproduction report at `2026-04-30T21:22:55Z`.

## Current Focus

hypothesis: The latest failure is not "no reconnect backfill"; it is a partial
backfill/ordering gap. The browser selected and posted one reconnect PCM
backfill before applying the replacement peer answer, but the Web UI proxy
returned `502`, the selection covered only 5.63 seconds, and later local mic
audio captured while the backfill request was in flight was neither backfilled
nor delivered by the replacement WebRTC track.
test: Compare Web UI thread API, direct SQLite rows, browser reconnect events,
AI backend backfill/VAD/STT logs, and local/remote commit state for the latest
call.
expecting: Persistence should match `stt.result`; browser should show whether
backfill was attempted/sent/failed; backend should show whether PCM was applied
to the active turn; the first-loss boundary should be before STT.
next_action: Recommend a focused fix/test; do not commit, push, or deploy.

## Known Prior Context Loaded

- `.planning/debug/phone-calls-missing-chunks.md`
- `.planning/debug/phone-call-transcript-comparison.md`
- `.planning/debug/phone-call-repro-2026-04-30.md`
- `.planning/debug/phone-call-repro-e4b93d9-2026-04-30.md`
- `.planning/debug/phone-call-repro-1239588-2026-04-30.md`
- `.planning/debug/phone-call-repro-2360feb-2026-04-30.md`

## Runtime

- Local commit observed at start: `dff6545`
- OMEN deployed checkout: `dff6545`
- Code fix deployed by prior turn: `adb035c`
- WebRTC status: `status=ready`, `live_call_ready=true`,
  `media_transport_ready=true`, `active_sessions=0`
- Web call: `call_0daee780dd904a08a8fb69b4d8a68ca2`
- RTC session: `rtc_43b7b92a1b844471979bf0fed4adc8c3`
- Thread: `thread_3be859853d7a4726a5151ca50b6e7940`
- Copied logs:
  `/tmp/rayme-phone-debug-dff6545-2026-04-30/ai-backend.run.log`,
  `/tmp/rayme-phone-debug-dff6545-2026-04-30/web-ui.run.log`
- Persisted data checked through Web UI API and direct SQLite copy:
  `/tmp/rayme-phone-debug-dff6545-2026-04-30/rayme.sqlite3`
- No later persisted thread message or log call was found after this call. The
  latest persisted call starts at `2026-04-30T20:03:22.542447Z`, persists the
  long user speech at `2026-04-30T20:04:58.822295Z`, and ends at
  `2026-04-30T20:05:08.949981Z`. The user's report was later, at
  `2026-04-30T21:22:55Z`.

## Persisted User Speech

Checked via:

- `GET https://192.168.1.199:8443/api/threads/thread_3be859853d7a4726a5151ca50b6e7940`
- Direct SQLite query of `web-ui/server/data/rayme.sqlite3`
- Web log `datachannel.message ... event_type=user_final`
- AI backend `stt.result ... transcript_len=376` and `event.sent type=user_final`

Latest short turn:

> Hey, how are you doing?

Latest long turn, persisted as `message_kind=user_speech`, sequence 29,
length 376:

> Of course, and now I will tell your story. The horrible conclusion which had been gradually uprooting itself upon my confused and reluctant mind was now an awful certainty. I was lost completely, hopelessly lost in the vast and at a very thin recesses of the mammoth cave. Turnus, I have frequently rid of the wild, frances into which were thrown the victims of the Thank you.

There is no fuller transcript in the Web UI thread API or SQLite rows. The
persisted row matches the backend STT result length.

## Reconnect Backfill Evidence

- Browser scheduled media reconnect on `iceConnectionState=disconnected` and
  started backfill:
  `mic.reconnect_backfill.start ... backfillId=call_0daee780dd904a08a8fb69b4d8a68ca2-1777579476539-uy2z19qt startOffsetMs=250 bufferedChunks=176`.
- Browser later upgraded to failed-state reconnect and sent a new offer:
  `pc.media_reconnect.start ... attempt=1`.
- Browser local mic diagnostics show the local mic stayed live, unmuted, and
  enabled. During reconnect it captured nonzero audio, including
  `localMicRawRms=0.0418` at `elapsedMs=2508`,
  `localMicRawRms=0.0775` at `elapsedMs=6522`, and
  `localMicRawRms=0.0309` at `elapsedMs=7023`.
- Browser did not log `mic.reconnect_backfill.sent`. It logged
  `mic.reconnect_backfill.failed ... durationMs=5631 samples=90090 ...
  message="RayMe API request failed: 502 Bad Gateway"`.
- The Web UI log confirms
  `POST /api/calls/call_0daee780dd904a08a8fb69b4d8a68ca2/reconnect-audio`
  returned `502 Bad Gateway`.
- The AI backend nevertheless applied the same backfill ID:
  `reconnect_audio.backfill.applied ... frames=282 duration_ms=5630
  bytes=180180 rms=1079.3 peak=8269.0 turn_frames=1353 speech_seen=True
  silence_ms=0 reason=disconnected attempt=1 started_turn=False`.
- No backend `reconnect_audio.backfill.skip` or `.duplicate` was found for this
  latest call.

## First Loss Boundary

Text boundary:

- Expected after `mammoth cave.`: `Turn as I might, in no direction could my
  straining vision seize on any object capable of serving as a guidepost...`
- Persisted transcript after `mammoth cave.`: `Turnus, I have frequently rid of
  the wild, frances into which were thrown the victims of the Thank you.`

Technical boundary:

- The old backend receive track collected the active turn until
  `track.recv.error ... frames=1789`.
- Same-session reoffer armed reconnect grace at `turn_frames=1071`.
- Backend applied 282 backfill frames, bringing the active turn to
  `turn_frames=1353`.
- The replacement track then delivered near-silent frames:
  `vad.reconnect_grace.audio ... rms=0.1 peak=1.0` through sampled frames, while
  `speech_now=True` was driven by the recent VAD analysis window containing the
  backfilled speech, not by current-frame energy.
- VAD then accumulated post-backfill silence, held once for reconnect grace, and
  finalized at `turn_frames=1477 silence_ms=2334`.
- STT began with only `frames=1477` (`pcm_bytes=944980`) and produced
  `transcript_len=376`, which is exactly what was persisted.

The first loss is still before STT and persistence. It now sits between the
browser mic PCM buffer and the backend active turn after the first 5.63 seconds
of backfilled reconnect audio. Audio captured while the browser was awaiting
the backfill request/remote-description path appears not to be included in the
active turn, and live replacement WebRTC frames arrive as silence until VAD
ends the turn.

## Root Cause / Strongest Supported Hypothesis

Strongest supported hypothesis:

The reconnect backfill implementation is one-shot and flushes before
`setRemoteDescription`. Because `connectBrowserMedia()` awaits
`beforeRemoteDescription`, the browser selects a backfill window, posts it, and
waits for the Web UI/AI backend route before the replacement peer can connect.
In this repro, that proxy request returned `502` to the browser after the AI
backend had already applied 5.63 seconds of PCM. While that request was in
flight, browser mic diagnostics still showed speech, but that later audio was
not part of the already-selected backfill and could not reach the backend over
the replacement WebRTC track because the remote description had not been
applied yet.

The separate proxy/observability bug is that the browser reports the backfill as
failed even though the AI backend applied it. The likely mechanism is the Web UI
AI backend client using the generic 5 second `_timeout` for
`backfill_call_audio()` instead of a WebRTC/control timeout, causing a false
`502` when the backend applies the audio but the proxy gives up.

## Fix Recommendation

Code changes are needed.

Focused fix direction:

1. Make reconnect backfill drain all PCM captured before the replacement peer is
   allowed to receive live frames. Do not clear the reconnect backfill window
   after the first selected batch if the call is still reconnecting; send a
   second tail batch, or loop/drain until no chunks remain, immediately before
   `setRemoteDescription`.
2. Keep ordering: all backfilled PCM must be appended before live replacement
   track frames can finalize the turn. If live frames may arrive first, add a
   backend reconnect gate/sequence so backfill can still be inserted before
   finalization.
3. Fix the Web UI proxy timeout/observability path so successful backend
   application is surfaced as `mic.reconnect_backfill.sent`, not browser
   `failed`. `AiBackendClient.backfill_call_audio()` should use a WebRTC/control
   timeout instead of the generic 5 second timeout.
4. Improve diagnostics by logging the selected backfill `startMs/endMs` (or
   relative offsets), not only duration, so future runs can prove whether tail
   PCM was selected.

Focused tests:

- Browser/unit or E2E: simulate reconnect, resolve `sendCallOffer`, make the
  first backfill POST take several seconds while mic PCM chunks continue, and
  assert a tail batch is sent before `setRemoteDescription`.
- Web UI server: AI backend backfill request taking more than 5 seconds but less
  than the WebRTC/control timeout returns `200` to the browser.
- Backend/session: applying multiple ordered backfill batches before
  replacement-track silence yields one STT turn with pre-reconnect + all
  backfilled frames, and VAD grace does not finalize before the tail batch is
  inserted.
