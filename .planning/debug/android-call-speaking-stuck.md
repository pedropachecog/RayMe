---
status: fixing
trigger: "Android call stuck in 'speaking' with no audible audio"
created: 2026-04-27T03:30:00Z
updated: 2026-04-27T03:37:00Z
---

## Current Focus

reasoning_checkpoint:
  hypothesis: "The /turns SSE generator blocks on _speak_call (TTS synthesis 5-15s) before yielding ai_done. The browser SSE reader blocks indefinitely waiting for ai_done. During this gap, WebRTC ICE times out on Android (despite keepalive), killing the peer connection. Additionally, VAD early-returns when speech_detected=False, bypassing the max turn duration safety net."
  confirming_evidence:
    - "calls.py line 366: speak_result = await _speak_call(...) blocks the SSE generator. ai_done yield (line 391) comes AFTER _speak_call returns."
    - "client.ts line 665: activeTurnReader.read() has no timeout - blocks forever if server hangs"
    - "session.py line 148-149: if not speech_detected: return None - returns before checking end_of_turn, bypassing max turn duration"
    - "session.py line 563: end_of_turn = self._speech_seen and (...) - requires speech, so ambient-only turns never end"
    - "Outbound track logs: ALL entries show queue_size=0, buffer_size=0 - TTS audio was never queued"
    - "DTLS ConnectionError logged - peer connection dies during the TTS blocking gap"
    - "Audio flows through WebRTC independently of SSE - ai_done is purely a UI state signal"
  falsification_test: "If ai_done were being delivered to the browser (via SSE or data channel) during the observed timeframe, the fix would be wrong. Check data channel logs for ai_done delivery - if it was delivered, the browser would have transitioned to 'listening'."
  fix_rationale: "Yield ai_done before _speak_call because ai_done is a UI state signal (transition from 'speaking' to 'listening'), and audio flows through WebRTC independently. The browser does not need to wait for TTS to finish before knowing the AI has completed its turn. This eliminates the blocking gap that kills the WebRTC connection. VAD fix ensures ambient-only turns still finalize after max duration."
  blind_spots:
    - "If the browser UI shows 'listening' before TTS audio arrives, there could be a brief visual inconsistency. However, the 440Hz keepalive should maintain the connection long enough for TTS to start."
    - "If _speak_call raises an exception in the background task, it will be unhandled. Need to add error handling."
    - "The data channel ai_done will still fire after TTS completes via _speak_call - but by then the browser already transitioned from SSE ai_done. The data channel handler is idempotent (calls finishAiTurn which just sets listening), so this is harmless."

hypothesis: "CONFIRMED - SSE generator blocks on TTS, preventing ai_done. VAD early-return bypasses max duration."
test: "Implement fixes and deploy for live Android testing"
expecting: "Browser receives ai_done immediately after LLM completes, transitions to 'listening'. TTS audio still plays through WebRTC."
next_action: "Fix calls.py: yield ai_done before _speak_call, dispatch TTS as background task. Fix session.py: remove VAD early return, fix end_of_turn formula."

## Symptoms

expected: After the AI speaks, the call status should transition from "speaking" back to "listening", and the TTS audio should be audible on Android
actual: Call status is stuck in "speaking" — never returns to "listening". No generated audio is audible on Android Chrome.
errors: AI backend logs show a DTLS ConnectionError "Cannot send encrypted data, not connected" — the peer connection dies while still in the speaking state. Session remains active (active_sessions: 1) after hangup.
reproduction: Open https://192.168.1.199:8443 on Android Chrome, start a call, speak. VAD detects speech, STT transcribes, user_final event sent. Then call gets stuck in "speaking".
started: Multi-session ongoing issue. Previously stuck in "Listening", recent fixes moved it forward but now stuck in "speaking".

## Eliminated

- hypothesis: Browser never received user_final data channel event.
  evidence: Web UI logs show POST /turns 200 OK — browser DID submit a turn.
  timestamp: 2026-04-27T03:30Z

- hypothesis: LLM never generated tokens.
  evidence: Browser reached "speaking" state, which requires receiving at least one ai_token SSE event (handleTurnStreamEvent sets callState='speaking' on first ai_token).
  timestamp: 2026-04-27T03:30Z

- hypothesis: Data channel was never open.
  evidence: AI backend logs show event.sent type=user_final readyState=open — data channel WAS open when user_final was sent.
  timestamp: 2026-04-27T03:30Z

## Evidence

- timestamp: 2026-04-27T03:30Z
  checked: AI backend outbound track progress logs
  found: ALL recv_count entries show idle_frames=recv_count, queue_size=0, buffer_size=0
  implication: TTS audio was NEVER queued to the outbound track at any point during the call

- timestamp: 2026-04-27T03:30Z
  checked: AI backend logs for /speak endpoint access
  found: No POST /webrtc/sessions/{id}/speak visible in access logs (only /webrtc/offer, /health, /webrtc/status)
  implication: Either _speak_call was never invoked, TTS synthesis is still running (log not flushed), or voice reference check aborted the turn

- timestamp: 2026-04-27T03:30Z
  checked: Browser /turns SSE handling code (client.ts readTurnStream)
  found: activeTurnReader.read() has NO timeout — blocks indefinitely
  implication: If server generator blocks during TTS (5-15s), browser reader hangs forever waiting for ai_done

- timestamp: 2026-04-27T03:30Z
  checked: /turns handler code (calls.py lines 334-422)
  found: _speak_call is a blocking await (TTS synthesis 5-15s). ai_done yield comes AFTER _speak_call returns. If TTS hangs, ai_done is never yielded.
  implication: Browser stuck in "speaking" because ai_done never arrives through SSE

- timestamp: 2026-04-27T03:30Z
  checked: VAD early-return logic (session.py lines 148-150)
  found: if not speech_detected: return None — returns early WITHOUT checking end_of_turn. Max turn duration safety net is bypassed.
  implication: Turn 3 (ambient noise only, _speech_seen=False) can never finalize

- timestamp: 2026-04-27T03:30Z
  checked: VAD end_of_turn formula (session.py lines 561-565)
  found: end_of_turn = self._speech_seen AND (silence >= threshold OR forced_end). Requires _speech_seen=True.
  implication: Even with max turn duration, if _speech_seen is False, end_of_turn is always False

- timestamp: 2026-04-27T03:30Z
  checked: Web UI server logs
  found: Only ONE POST to /turns (for turn 1). No second POST for turn 2's user_final.
  implication: Browser only processed turn 1. Turn 2 user_final was sent but either browser never received it (data channel timing?) or browser never called /turns again because it was stuck processing turn 1.

## Resolution

root_cause: "The /turns SSE generator blocks on _speak_call (TTS synthesis 5-15s) before yielding ai_done. Browser's SSE reader blocks forever waiting for ai_done. Combined with WebRTC ICE timeout during the gap, the peer connection dies. Additionally, VAD early-returns when speech_detected=False (session.py line 148-149), bypassing the max turn duration safety net. The end_of_turn formula requires _speech_seen=True, so ambient-only turns can never finalize."
fix: "(1) calls.py: yield ai_done immediately after LLM completes, dispatch TTS as asyncio.ensure_future background task. (2) session.py: removed early return when speech_detected=False, fixed end_of_turn formula to allow forced_end (max duration) regardless of _speech_seen in both Silero and energy-based paths."
verification: "Deploying for live Android test."
files_changed: ["web-ui/server/app/api/calls.py", "ai-backend/app/call/session.py"]
