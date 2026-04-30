# Phone Call Repro After 2360feb: 2026-04-30

Source: OMEN logs and deployed Web UI thread API after the user's latest
post-`2360feb` phone-call reproduction with reconnect audio diagnostics from
`3ce53c7`.

## Runtime

- Local commit: `2360feb` (`docs(debug): record reconnect diagnostics deployment`)
- OMEN deployed checkout: `2360feb` (`docs(debug): record reconnect diagnostics deployment`)
- OMEN remote worktree: clean
- WebRTC status: `status=ready`, `live_call_ready=true`,
  `media_transport_ready=true`, `active_sessions=0`
- Web call: `call_398dbd33e47c4cd9bad0e9196e060c11`
- RTC session: `rtc_312a33e4d8a243aeb0fc521da21e8473`
- Thread: `thread_3be859853d7a4726a5151ca50b6e7940`
- Copied logs:
  `/tmp/rayme-phone-debug-2360feb-2026-04-30/ai-backend.run.log`,
  `/tmp/rayme-phone-debug-2360feb-2026-04-30/web-ui.run.log`
- Note: the thread and log files show this latest substantive call ended at
  `2026-04-30T17:17:34Z`. No later OMEN log/thread writes were observed after
  `2026-04-30T17:19:00Z`.

## Persisted User Speech

### Short Turn

Hey, how is it going?

### Long Turn

Of course, and now I will tell your story. The horrible conclusion which had
been gradually obtruding itself upon my confused and reluctant mind was now an
awful certainty. I was lost completely, hopelessly lost in the vast and the
brink thing, recesses of the mammoth thrown, the victims of similar situations.
I experienced none of these, but stood quiet as soon as I clearly realized the
loss of my my bearings.

## Timeline And IDs

- `2026-04-30T17:15:41Z`: call start persisted for
  `call_398dbd33e47c4cd9bad0e9196e060c11`.
- `2026-04-30T17:15:53Z`: short user speech persisted.
- `2026-04-30T17:17:23Z`: long user speech persisted, already partial.
- `2026-04-30T17:17:34Z`: call end persisted.

## Browser Reconnect Diagnostics

The browser local audio track stayed live and enabled during reconnect:

- Track id `e176adb8-9330-4b48-8da6-4e387964780f`
- `readyState=live`
- `muted=false`
- `enabled=true`
- settings included `sampleRate=48000`, `channelCount=1`,
  `echoCancellation=true`, `noiseSuppression=true`, `autoGainControl=true`

Local mic RMS/peak samples show the user was still producing microphone audio
while the peer connection was failed/reconnecting:

- scheduled/disconnected: `localMicRawRms=0.0457`, `localMicRawPeak=0.0991`
- scheduled/failed: `localMicRawRms=0.0275`, `localMicRawPeak=0.0600`
- interval, `mediaReconnecting=true`, `elapsedMs=1504`:
  `localMicRawRms=0.1205`, `localMicRawPeak=0.3585`
- interval, `mediaReconnecting=true`, `elapsedMs=2005`:
  `localMicRawRms=0.1176`, `localMicRawPeak=0.3044`
- interval, `mediaReconnecting=true`, `elapsedMs=3008`:
  `localMicRawRms=0.0832`, `localMicRawPeak=0.1850`
- interval, `mediaReconnecting=true`, `elapsedMs=3509`:
  `localMicRawRms=0.0556`, `localMicRawPeak=0.2565`
- interval, `mediaReconnecting=true`, `elapsedMs=4010`:
  `localMicRawRms=0.2146`, `localMicRawPeak=0.5383`
- `pc.media_reconnect.ok`, immediate sample:
  `localMicRawRms=0.0001`, `localMicRawPeak=0.0002`
- recovered/connected:
  `localMicRawRms=0.0011`, `localMicRawPeak=0.0035`

Interpretation: this rules out browser capture silence/mute as the first loss.
The browser had live microphone audio during the reconnect outage.

## Backend Reconnect Diagnostics

The long turn starts at backend frame 614. VAD sees speech at turn frame 115.
The old receive track then fails:

- `track.recv.error ... frames=1659 exc=MediaStreamError ice=completed conn=connected`
- peer/data channel close follows
- same-session reoffer arrives for the same RTC session
- reconnect grace arms at `turn_frames=1046 silence_ms=0`
- replacement track starts and first frame arrives

Backend `vad.reconnect_grace.audio` shows the replacement WebRTC path receives
real speech and Silero accepts it:

- diag frame 1: `rms=44.0`, `peak=218.0`, `speech_now=True`, `ts_count=1`
- diag frame 2: `rms=1486.8`, `peak=5190.0`, `speech_now=True`, `ts_count=1`
- diag frame 3: `rms=2140.0`, `peak=6284.0`, `speech_now=True`, `ts_count=1`
- diag frame 7: `rms=3160.8`, `peak=7187.0`, `speech_now=True`, `ts_count=1`
- diag frame 75: `rms=1634.6`, `peak=4777.0`, `speech_now=True`, `ts_count=1`
- diag frame 125: `rms=55.2`, `peak=165.0`, `speech_now=True`, `ts_count=1`

After the grace period, VAD sees real end silence:

- `vad.silence ... silence_ms=830`
- `vad.silence ... silence_ms=1022`
- `vad.silence ... silence_ms=1214`
- `vad.silence ... silence_ms=1406`
- `vad.silence ... silence_ms=1630`
- `vad.reconnect_grace.expired ... silence_ms=1822`
- `vad.end_of_turn ... turn_frames=1612 silence_ms=1822`
- `stt.begin ... frames=1612 pcm_bytes=1031680 rms=1139.7 peak=12332.0`
- `stt.result ... transcript_len=414`

Interpretation: this rules out backend VAD rejection of real post-reconnect
audio. The backend receives VAD-positive speech once the replacement track is
established.

## First Loss Boundary

The first loss boundary is the browser/WebRTC outage during media reconnect.

The browser is capturing microphone audio while `mediaReconnecting=true`, but
the backend old track has already failed and the replacement track has not
started receiving frames yet. Speech spoken during that outage is never
delivered to the backend and is not replayed after reconnect.

Once the replacement track is established, backend frame RMS is nonzero and
Silero reports `speech_now=True`, so the remaining audio path and VAD are
working for the post-reconnect speech that actually arrives.

## Root Cause / Strongest Supported Hypothesis

RayMe does not preserve microphone audio spoken during the multi-second
media-reconnect gap. The current reconnect flow tears down/replaces the peer
connection and keeps the live call going, but it has no browser-side audio
buffer/backfill path for speech captured while the WebRTC sender is failed or
not yet connected.

That produces transcripts that keep the beginning and the later post-reconnect
speech, while dropping the middle spoken during the reconnect outage.

## Fix Recommendation

Code changes are needed if the product requirement is to preserve continuous
speech while the user keeps talking through reconnect.

Focused fix direction:

1. Add a browser-side rolling PCM buffer sourced from the local mic meter/audio
   graph during active calls.
2. When media reconnect is scheduled/started, mark the reconnect-gap start and
   retain mic PCM until the new peer connection reaches connected/recovered.
3. Add a backend endpoint or data-channel message to append that buffered PCM
   to the active `CallSession` turn before normal post-reconnect live frames
   finalize the turn.
4. Keep the current backend reconnect grace, but use it as finalization
   protection while buffered reconnect-gap audio is inserted.

Focused tests:

- Browser unit/E2E test: simulate `pc.connectionstatechange=failed`, feed local
  mic meter samples, assert reconnect-gap buffering starts and a backfill
  request is sent before/around `pc.media_reconnect.ok`.
- Backend unit test: start a spoken turn, mark reconnect grace pending, inject
  buffered PCM for the reconnect gap, then continue replacement-track frames;
  assert a single STT turn receives pre-reconnect + buffered-gap +
  post-reconnect frames in order.
- Regression test: without backfill, a reconnect gap during continuous speech
  yields a partial frame count; with backfill, STT receives the expected full
  frame count and only finalizes after real post-speech silence.
