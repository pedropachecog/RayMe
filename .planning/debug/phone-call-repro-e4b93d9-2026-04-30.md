# Phone Call Repro After e4b93d9: 2026-04-30

Source: OMEN logs and deployed Web UI thread API after the user's latest
post-`e4b93d9` phone-call reproduction.

## Runtime

- Deployed commit: `e4b93d9` (`fix(call): preserve speech through media reconnect`)
- Web call: `call_df8ae118f4d04187ad95a08aace6f8e5`
- RTC session: `rtc_2f157017837a4ee4b307bb08cb2630e0`
- Thread: `thread_3be859853d7a4726a5151ca50b6e7940`
- Copied logs: `/tmp/rayme-phone-debug-e4b93d9/ai-backend.run.log`,
  `/tmp/rayme-phone-debug-e4b93d9/web-ui.run.log`

## Persisted User Speech

### Short Turn

Hi, how are you doing today?

### Long Turn

Of course, and I will tell you a story. The horrible conclusion which had been
gradually obtruding itself upon my confused and reluctant mind was now an awful
certainty. I was lost completely, hopefully lost in the vast and laboring
recesses of the mammoth cave. Turned as I might in no direction could my strait
as soon as I clearly realized the loss of my bearings.

## Boundary Summary

- Backend long turn started at frame 727 and VAD saw speech at turn frame 67.
- The old track then hit `track.recv.error ... exc=MediaStreamError
  ice=completed conn=connected` at frame 1737, followed by closed peer/data
  channel state.
- Browser logs show `pc.iceconnectionstatechange disconnected`,
  `pc.connectionstatechange failed`, and `pc.media_reconnect.start`.
- Backend accepted a same-session reoffer for the same RTC session.
- Expected `vad.reconnect_grace.pending`, `.start`, and `.hold` logs are absent.
- After the replacement track started, VAD treated startup silence as normal
  end-of-turn silence: `vad.end_of_turn ... turn_frames=1258 silence_ms=1822`.
- STT began with only `frames=1258` and produced `transcript_len=367`, matching
  the persisted long turn length.

## First Loss Point

The persisted transcript is already short because STT received a short frame
buffer. The loss occurs before STT, when a failed-then-reoffered media reconnect
does not arm reconnect grace and VAD finalizes the active turn on replacement
track startup silence.

## Code-Level Finding

`CallSessionManager.create_session()` recovered `failed/connection_failed`
sessions after calling `existing.mark_media_reconnect_pending()`. Since
`mark_media_reconnect_pending()` requires `existing.state == "listening"`, the
failed-then-reoffered path did not set `_media_reconnect_grace_pending`.

