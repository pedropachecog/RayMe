# Phone Calls Post-Snapshot Audit

created: 2026-05-01T15:46:17Z
selected_snapshot: `6607214de3f65a7855e6d6ad4132bc7d66f3b479`
snapshot_runtime_code: `faba4cc4f62e3f0c8ffd4b57b30f02aec934c1f0`
current_bad_head_before_rollback: `a0d5d173810b638bb43e146c346aff68553256c0`

## Purpose

The user requested a rollback to the selected recovery snapshot, but only after
recording what changed after that snapshot and which hypotheses/fixes failed to
restore the phone-call behavior.

The selected snapshot is `6607214`, a docs commit over runtime commit `faba4cc`.
That snapshot was not proven to fully solve long-text transcription. It is the
user-selected operational return point because it was tested immediately before
the later "terrible regression" state.

## Baseline At Snapshot

Runtime code at the snapshot was `faba4cc` (`fix(call): drain reconnect backfill tail`).

Known behavior at/around that point:

- The original bug was missing chunks in long turns. The system could get some
  long speech through, but long passages were truncated or compressed.
- The reconnect-tail fix attempted to send an initial browser PCM backfill
  batch plus a final tail batch, and held replacement-track live frames until
  the final marker arrived.
- The snapshot still had risk around reconnect/backfill lifecycle. It had not
  been proven by product-owner acceptance to fully preserve long passages.

## Commit Ledger After Snapshot

These commits exist after `6607214`:

1. `6f63de0` - `fix(call): release reconnect final markers`
   - Runtime change.
   - Changed backend reconnect held-frame release and final-marker handling.
   - Changed browser reconnect backfill IDs from a single batch namespace to
     separate `batch` and `final` namespaces.
   - Added backend unit tests and a Playwright reconnect assertion.

2. `21bc46e` - `docs(debug): record final-marker deployment`
   - Documentation/debug note only.
   - Recorded that `6f63de0` was deployed to OMEN through
     `scripts/deploy-omen.sh`.

3. `d764cc4` - `docs(debug): record post-deploy call regression`
   - Documentation/debug note only.
   - Recorded the user's post-`21bc46e` report: a long poem call froze, one
     start failed, and a delayed-speech second turn froze.

4. `ec2f769` - `docs(debug): select rollback anchor`
   - Documentation/debug note only.
   - Recorded the user-selected rollback anchor as `6607214`, with runtime code
     `faba4cc`.

5. `9136024`, `067c560`, `81f8f7f`
   - AGENTS/workflow docs only.
   - Added rules requiring the debug session-manager workflow to run inline and
     forbidding nested agent CLI workarounds.

6. `2de5f02`, `b9d9585`
   - Documentation/debug note only.
   - Refocused the session away from rollback and toward fix-forward analysis of
     the two failing post-`21bc46e` calls.

7. `a0d5d17` - `fix(call): preserve turn artifacts across reconnect`
   - Runtime change.
   - Added pending backend data-channel replay for durable `user_final` events.
   - Made replacement data channels flush queued events.
   - Made browser hangup drain reconnect backfill before `/end` and before
     local media cleanup.
   - Added backend and Playwright tests.

## Hypotheses And Fixes Since Snapshot

### Hypothesis 1: duplicate empty final markers left held audio unreleased

Observed after the snapshot on calls `call_3294...` and `call_f0fb...`:

- Browser local mic RMS was nonzero.
- Backend accepted non-silent reconnect backfill PCM.
- Backend VAD saw speech.
- A final empty reconnect marker reused a previous non-final `backfill_id`.
- `CallSession.backfill_reconnect_audio()` deduped the marker before it could
  release held replacement-track frames.
- Held-frame release also ignored VAD `end_of_turn`, so released frames could
  fail to trigger STT immediately.

Implemented in `6f63de0`:

- Empty `final:true` markers became release signals even when their ID matched a
  prior batch.
- Held-frame release began returning whether VAD saw `end_of_turn`.
- `handle_inbound_audio_frame()` and `backfill_reconnect_audio()` could
  immediately call `finalize_user_turn()` after releasing held frames.
- Browser final marker IDs were namespaced separately from non-final batch IDs.

Result:

- Local tests passed and OMEN deployment succeeded.
- User verification after deployment still failed.
- The next observed state was worse than the selected snapshot: calls could
  freeze after the first short turn, second long turns could fail to persist,
  and at least one call-start attempt failed.

Risk introduced right after the snapshot:

- `6f63de0` made final-marker and held-frame release paths actively finalize
  turns. Before this, reconnect-held frames were appended but release did not
  itself drive STT/user-final emission.
- This increased coupling between reconnect/backfill cleanup and turn
  finalization. In real phone calls, the data channel and peer connection were
  often not stable when these finalization paths ran.
- The post-`21bc46e` logs showed the second long turn could reach STT but then
  lose `user_final` because the data channel was already closed.

Inference:

- `6f63de0` is the most important post-snapshot regression candidate. It was the
  first runtime change after `6607214`, and the next product-owner report
  described the severe frozen-call state.
- The exact root is not proven to be one line, but the dangerous shift was:
  reconnect cleanup markers became allowed to force turn finalization while
  transport/data-channel recovery was still unstable.

### Hypothesis 2: backend dropped `user_final` while the data channel was closed

Observed after `6f63de0`/`21bc46e` on call
`call_5152493ffa72481ab60f1fc5b16eba9c` /
`rtc_2892320a439f4ef59830af9df3cdd296`:

- First short turn persisted normally.
- Second long turn began and backend VAD saw speech.
- Peer/data channel closed mid-turn.
- Reconnect/backfill applied multiple batches, including non-silent final PCM.
- Backend eventually ran STT for `user-turn-2` and got a transcript.
- Delivery failed with `event.skip_channel_not_open type=user_final
  readyState=closed`.
- SQLite had no long-turn row.

Implemented in `a0d5d17`:

- Added a bounded pending data-channel queue for durable `user_final` events.
- Added `attach_data_channel()` and `flush_pending_data_channel_events()`.
- Replaced direct `session.data_channel = channel` assignments with
  `session.attach_data_channel(channel)`.
- Tried to replay pending `user_final` when a replacement channel opened.

Result:

- Local backend tests passed.
- User verification after deployment still failed.
- The fix did not restore real phone-call behavior.

### Hypothesis 3: browser hangup/reconnect cleanup discarded pending PCM

Observed after `6f63de0`/`21bc46e` on call
`call_e3e46602b0e340f098b2549aa04a3765` /
`rtc_fd075194886f46569ba1ba921440e62f`:

- First short turn persisted normally.
- After AI playback, the second listening turn started.
- Backend did not see second-turn `vad.speech_start`, `stt.begin`, or
  `user_final`.
- Browser started reconnect backfill and created a replacement offer.
- `/end` and media cleanup raced before the answer was applied.
- `setRemoteDescription` failed because the peer connection was already closed.
- No backend `reconnect_audio.backfill.applied` occurred for that session.

Implemented in `a0d5d17`:

- Added `drainReconnectAudioBackfillBeforeHangup()`.
- Made hangup await a final reconnect-audio drain before `/api/calls/{call_id}/end`.
- Added Playwright ordering coverage that the final backfill POST precedes
  `/end` during a mocked in-flight reconnect.

Result:

- Local browser test passed.
- User verification after deployment still failed.
- The fix did not restore real phone-call behavior.

## What Did Not Solve The Frozen Problem

None of the post-snapshot runtime fixes solved the real phone-call frozen state:

- `6f63de0` did not fix the post-snapshot frozen/no-response behavior.
- `a0d5d17` did not fix the frozen/no-response behavior.
- The passing unit and mocked Playwright tests were insufficient because they
  tested isolated reconnect paths, not the real Android/phone long-turn flow
  with live WebRTC transport instability.

## Current Rollback Plan

Rollback should not use `git reset --hard` or a detached deployment.

Use a normal revert/restore commit that returns runtime files to the selected
snapshot state while preserving this audit note and other debug documentation.
Then deploy to OMEN only with `scripts/deploy-omen.sh`.

Runtime files to restore to the snapshot state:

- `ai-backend/app/api/webrtc.py`
- `ai-backend/app/call/session.py`
- `ai-backend/tests/test_call_session.py`
- `web-ui/client/src/routes/call/[threadId]/+page.svelte`
- `web-ui/client/tests/e2e/call-start.spec.ts`

Expected post-rollback state:

- Runtime code matches `faba4cc` for the changed files.
- Documentation notes remain available for future debugging.
- OMEN is deployed through the canonical script from the rollback commit.

