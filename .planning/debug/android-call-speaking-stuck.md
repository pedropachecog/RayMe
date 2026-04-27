---
status: awaiting_human_verify
created: 2026-04-27T03:30:00Z
updated: 2026-04-27T20:30:00Z
---

# Debug Session: Android Call Speaking No Audio

## Current Focus

reasoning_checkpoint:
  hypothesis: The SSE connection on Android Chrome is interrupted during TTS synthesis (10-15s) because the server yields no SSE data during `await _speak_call()`. FastAPI's StreamingResponse closes the HTTP connection when no data flows for the server's idle timeout, which cancels the SSE generator task. This in-flight CancelledError propagates to `_synthesize_speech` -> `run_in_executor` -> F5-TTS, aborting the TTS synthesis. No audio is enqueued, so the browser hears only silence keepalive (speakingRms=0.04).

  confirming_evidence:
    - OMEN logs show `asyncio.exceptions.CancelledError` at `_synthesize_speech` line 667
    - WebRTC disconnects and reconnects during TTS (browser logs show ice=disconnected -> connected cycles)
    - speak_call returns HTTP 500 (CancelledError passes `except Exception` since it inherits BaseException)
    - TTS succeeds later (wav_bytes logged) — the issue is timing, not F5-TTS itself
    - calls.py SSE generator yields zero data during `await _speak_call()` — idle connection
    - The 200 OK for `/turns` confirms the SSE generator eventually completes

  falsification_test: Add SSE keepalive ping during `_speak_call()`. If TTS stops being cancelled, the hypothesis is confirmed.

  fix_rationale: SSE keepalive yields periodic comment-only SSE events during `_speak_call()`, preventing the HTTP idle timeout. CancelledError handling in `speak_session` catches it explicitly (returns 502 instead of 500).

  blind_spots:
    - If the cancellation source is not the SSE idle timeout but something else (e.g., browser closing and reopening the SSE connection)
    - If the browser discards WebRTC connection during SSE gap despite silence keepalive

## Symptoms

expected: AI audio plays during 'speaking' state on Android Chrome
actual: UI reaches 'speaking', shows AI text, but no audio is heard. State transitions to 'listening'.
errors:
  - CancelledError during TTS synthesis (AI backend logs)
  - tts.enqueue after data channel closed
  - track.send.progress queue_size=0 buffer_size=0
  - speak_call.background_failed
reproduction: Start call on Android Chrome, speak, wait for AI response. Text appears but no audio.
started: After commit 8244cb0 (SSE unblock fix)

## Resolution

root_cause:
  Problem A (No AI Audio):
  - The SSE generator in calls.py blocked on await _speak_call() with zero SSE
    output during TTS synthesis (5-15 seconds). FastAPI's StreamingResponse
    timed out the idle HTTP connection, cancelling the SSE generator task.
    CancelledError propagated to _synthesize_speech on the AI backend, aborting
    F5-TTS mid-inference. No audio was enqueued to the outbound WebRTC track.
    Additionally, CancelledError inherits from BaseException (not Exception),
    so the except Exception handler in speak_session did not catch it, resulting
    in HTTP 500 instead of HTTP 502.
  - Browser-side: WebRTC connection dropped during TTS gap because no audio
    was enqueued (only silence keepalive sine wave at 440Hz). Android Chrome
    ICE reconnection timeout (30s) kicked in.

  Problem B (Silence transcribed as "Thank You"):
  - The client's microphone stayed enabled during AI thinking/speaking states.
    Ambient noise flowed through VAD -> STT -> Whisper hallucinated "thank you"
    from room-tone silence.
  - Server-side: handle_inbound_audio_frame only dropped frames when muted or
    state in {"ended", "failed"}. During LLM generation, state was "listening"
    (reset after finalize_user_turn), so audio accumulated.

fix:
  1. SSE keepalive (calls.py): Run _speak_call() as asyncio.create_task().
     While waiting, yield ": keepalive\n\n" SSE comments every 2 seconds to
     keep the HTTP connection alive. After TTS completes, await the task to
     surface any exceptions.

  2. CancelledError handling (webrtc.py): Added explicit except asyncio.CancelledError
     before except Exception to catch task cancellation and return HTTP 502
     with "Speech playback cancelled" message instead of HTTP 500.

  3. Mic gating client-side (+page.svelte): Added disableMicrophone()/enableMicrophone()
     functions called during state transitions in applyCallState(). Mic disabled
     when transitioning from listening to thinking/speaking. Re-enabled when
     returning to listening.

  4. Mic gating server-side (session.py): Extended frame drop condition to include
     "speaking" state. Added "thinking" state guard to drop frames during LLM
     generation. Changed finalize_user_turn to set state to "thinking" instead
     of "listening".

verification:
  - Code deployed to OMEN (commit 9fdb8c2)
  - Both services healthy (F5-TTS resident, VRAM headroom 9.4GB)
  - Pending: Android Chrome test to verify:
    a) AI audio plays during speaking state
    b) No phantom transcriptions from silence
    c) WebRTC connection stays stable through TTS

files_changed:
  - web-ui/server/app/api/calls.py (SSE keepalive)
  - ai-backend/app/api/webrtc.py (CancelledError handling)
  - web-ui/client/src/routes/call/[threadId]/+page.svelte (mic gating)
  - ai-backend/app/call/session.py (frame drop + state transitions)

## Investigation Evidence (2026-04-27T19:00:00Z)

### Problem A: No AI Audio

- checked: Full audio delivery path — TTS synthesis -> _queue_outbound_audio -> QueuedAudioOutputTrack.enqueue -> aiortc RTP -> browser ontrack -> AudioContext -> speakers
- found: Path looks correct. TTS fix (8d20fd2) keeps connection alive. But OMEN logs are sparse after 10:55 AM restart — no speak_call logs visible.
- checked: Client attachRemoteAudio — AudioContext resume() called if suspended, but resume() requires user gesture on Android Chrome
- implication: If AudioContext suspends, resume() silently fails. TTS audio never plays.

### Problem B: Silence Transcribed as "Thank You"

- checked: session.py handle_inbound_audio_frame line 109
- found: Frame drop condition is `if self.muted or self.state in {"ended", "failed"}` — does NOT include "speaking" or "thinking"
- checked: Client +page.svelte — no mic gating during AI turns
- found: Mic tracks never disabled during thinking/speaking states. Audio continuously flows to server.
- implication: Ambient noise gets transcribed during AI thinking/speaking. This is the root cause of "thank you" hallucination.

### Applied Fixes

- Fix A1: SSE keepalive during _speak_call() (calls.py)
- Fix A2: CancelledError handling in speak_session (webrtc.py)
- Fix B1: Server-side frame drop during speaking state (session.py)
- Fix B2: Client-side mic gating — disable mic on thinking/speaking, re-enable on listening (+page.svelte)
- Fix B3: State transition after finalize_user_turn to "thinking" instead of "listening" (session.py)
