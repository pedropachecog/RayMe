---
status: testing
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
source: [09-VERIFICATION.md, 09-OMEN-HANDOFF.md]
started: 2026-08-01T12:57:46Z
updated: 2026-08-01T12:57:46Z
---

## Current Test

number: 1
name: Integrated listening with the intended uploaded real-person Qwen voice
expected: |
  Early, middle, and late call turns are intelligible and natural, retain the
  intended voice consistently, contain no objectionable chunk joins or
  late-call degradation, and begin playing before full generation finishes.
awaiting: user response

## Test Rules

- Keep both tests pending until the builder performs them and records direct observations.
- Do not use the generated non-person evidence fixture for likeness or naturalness acceptance. Evidence runs may rotate its opaque voice ID; that fixture proves automated transport only.
- Uploading the intended sample through Voice Lab is assumed authorized. Confirm its matching transcript; keep private material out of this record and verify deletion/cache behavior through the technical flow.
- Do not paste raw reference audio, its transcript, recordings, credentials, or private local paths into this file. Record only opaque IDs, device details, timestamps, and observations.
- Mark `result: pass` only when every pass condition holds. Otherwise use `result: issue` and fill the failure evidence fields verbatim.

## Tests

### 1. Integrated listening with the intended uploaded real-person Qwen voice

**Procedure:**

1. In Voice Lab, upload and save the intended Qwen3-TTS 1.7B voice with its matching transcript; no policy metadata is required.
2. Confirm this is the intended uploaded voice rather than the generated transport fixture, then assign it to the call character.
3. Start a real OMEN call and listen deliberately to an early response, a middle response, and a later longer response.
4. For each sample, judge intelligibility, naturalness, consistency with the intended sample, chunk joins, and whether playback starts while the response is still being generated.

**Pass conditions:** All three listening points are intelligible and natural; identity remains acceptably consistent; no objectionable joins or late degradation occur; playback is observably early rather than whole-response-delayed.

**Fail conditions:** The generated fixture was used; the transcript is not confirmed; speech is materially unintelligible or unnatural; identity drifts; joins are objectionable; late quality degrades; or playback waits for full generation.

result: [pending]
saved_voice_id: ""
saved_voice_name: ""
intended_sample_confirmed: ""
test_device_and_browser: ""
tested_at: ""
early_turn_observation: ""
middle_turn_observation: ""
late_turn_observation: ""
early_playback_observed: ""
pass_evidence: ""
failure_evidence: ""

### 2. Physical real-device multi-turn, barge-in, hangup, persistence, and reconnect

**Procedure:**

1. On the physical test device, open `https://192.168.1.199:8443`; confirm the AI backend is `https://192.168.1.199:9443`, Qwen3-TTS 1.7B is available, and the intended uploaded real-person saved voice is selected.
2. Start a call. Confirm model/prompt preparation is visible and the UI reaches `Listening` before speaking.
3. Speak a normal turn and confirm audible response playback starts while the assistant/TTS stream is still completing.
4. During a later spoken response, speak over RayMe once. Confirm playout stops promptly, the interruption becomes the next user turn, and the UI returns to `Listening` without ghost audio.
5. Complete at least three user-to-AI turns after recovery, including one longer response.
6. Hang up and inspect the thread. Confirm call start/end and completed user/assistant rows persist, while the cancelled assistant response does not appear as completed speech.
7. Start a new/reconnected call with the same saved voice. Confirm Qwen becomes resident, its prompt becomes ready, early playback still occurs, and listening recovery works on the next turn.

**Pass conditions:** Every step completes on the physical device; early playback is audible; spoken barge-in stops playout and recovers to `Listening`; no cancelled-turn ghost audio/completed persistence appears; hangup records the valid transcript rows; and the reconnect call completes another turn.

**Fail conditions:** Preparation state is hidden/stuck; first playback waits for whole synthesis; spoken interruption fails or loses the user turn; ghost audio continues; UI does not return to `Listening`; cancelled speech persists as completed; hangup loses valid rows; or reconnect cannot complete a turn.

result: [pending]
test_device: ""
browser_and_version: ""
network_path: ""
saved_voice_id: ""
tested_at: ""
preparation_and_listening_observation: ""
early_playback_observation: ""
barge_in_stop_and_user_turn_observation: ""
post_interrupt_listening_observation: ""
post_recovery_turn_count: ""
hangup_and_persistence_observation: ""
reconnect_observation: ""
pass_evidence: ""
failure_evidence: ""

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
