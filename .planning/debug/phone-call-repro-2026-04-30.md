# Phone Call Repro: 2026-04-30

Source: deployed OMEN thread API for
`thread_2fed9f8154424a68af5d4a4e956204ef` after the user's 2026-04-30
reproduction call.

## Call IDs

- Web call: `call_035fe1f98e34495899c911a9acc711b0`
- RTC session: `rtc_5cee6240cccf42079c09a785d6bb6b6b`
- Deployed commit: `ba6057c`

## Persisted User Speech

### Short Turn 1

Hi, how are you doing today?

### Short Turn 2

What can you do for me?

### Long Turn 1

Of course, and now I will tell you a story. The horrible conclusion which had
been gradually obtruding himself upon my confused and reluctant mind was now an
awful certainty. I was lost completely, hopefully lost in the vast and
liberating services of the mammoth cave. Turned as I might in no direction
could my straining visions on any other

### Long Turn 2

Already my torch has begun to expire, soon as I would be enveloped by the total
almost palpable blackness in the bowels of the earth. As I stood in waning and
steady light, I idly wondered over the except circumstances of my coming end. I
remember the accounts which I had heard of the color. Now I couldn't be told
myself. My opportunity for setting to this point it has arrived, provided that
want of food should not bring me to speed a departure from this life. departure
from this life.

## Boundary Summary

The deployed threshold change was active (`threshold_ms=1800`), but both long
turns still finalized early.

- `user-turn-3` finalized with `turn_frames=1211`, `transcript_len=343`.
- `user-turn-4` finalized with `turn_frames=1620`, `transcript_len=490`.
- Both long turns had browser media reconnects mid-turn before VAD finalized.
- After the reoffer, the backend saw new-track silence and finalized on
  `silence_ms=1822`.

## Revised Finding

The first fix improved the cutoff duration but did not handle mid-speech
browser media reconnects. The next fix must preserve an active spoken turn
through reconnect startup silence, instead of treating the reconnect gap as a
real end-of-turn.
