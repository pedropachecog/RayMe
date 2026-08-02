# Phase 09 OMEN Qwen Handoff

RayMe is autonomously release-ready at deployed commit `288c05b4742dda0aac76050658aa12a44041102e`. The remaining work is human acceptance: integrated listening and one physical multi-turn/barge-in/reconnect call on a real device. Neither has been claimed as complete.

## Live OMEN State

| Item | Verified value |
|---|---|
| Web | `https://192.168.1.199:8443` |
| AI health | `https://192.168.1.199:9443/health` |
| WebRTC status | `https://192.168.1.199:9443/webrtc/status` — `ready`, live call ready, media transport ready |
| Deployed commit | `288c05b4742dda0aac76050658aa12a44041102e` |
| Resident engine | `qwen3_1_7b` |
| Selected prompt | `ready` |
| Active sessions | `0` before and after the real browser suite |
| Prepared evidence voice ID | `voice_84a55c199fb74c7f9cf4fa012ba23bf5` |
| Prepared evidence voice name | `RayMe Phase 09 Synthetic Qwen Tracer` |
| Prompt owner key | `voice_84a55c199fb74c7f9cf4fa012ba23bf5` — matches the live ready prompt after final finish-evidence cleanup |

The prepared voice is an explicitly selected mechanical generated non-person transport-evidence fixture. Evidence runs may create additional transient fixture IDs, so identify it by the evidence voice name rather than one ID. It proves transport, streaming, recovery, stability, and privacy; it is not eligible for human likeness judgment and is never an automatic fallback. Before judging likeness or naturalness, upload and save the intended sample with its matching transcript. Uploading a voice sample is assumed authorized; there is no separate policy form, sidecar, status, or gate.

## Release Evidence

All final release evidence below records the same deployed SHA:

- `09-evidence-manifest.json` — frozen runtime, thresholds, privacy policy, and scenario inventory.
- `results/qwen3-runtime.json` — pinned Faster Qwen3-TTS/model/Torch/CUDA and one-hot residency.
- `results/qwen3-webrtc-status.json` — model resident, prompt ready, bounded output, and explicitly selected fixture state.
- `results/qwen3-call-flow.json` — early playback, bounded bridge/track, cancellation, recovery, and no whole-synthesis fallback.
- `results/qwen3-soak.json` — 50-turn non-degradation and memory/throughput stability.
- `results/qwen3-stt.json` — 50-turn spoken-message integrity.
- `results/qwen3-speaker.json` — pinned WavLM early/middle/late and integrated-baseline drift proof.
- `results/qwen3-browser.json` — real canonical desktop/mobile Chromium call proof, 4/4 passed in 2.8 minutes, with two completed cycles and the required `ai_audio_started`, `ai_done`, persistence, and listening-recovery contracts on each device; both fixture-path guards passed.
- `results/qwen3-log-leak-scan.json` — no raw reference audio, transcript, or local-path leakage in structured evidence or service logs.

Raw reference audio, transcripts, embeddings, and scorer audio remain local and uncommitted.

## Canonical Deployment, Review, and Incident Repair Record

- The only deployment command was `RAYME_OMEN_VERIFY_QWEN3=1 scripts/deploy-omen.sh`.
- The canonical deploy passed database schema migration, pinned Faster Qwen3-TTS `v0.3.2`/source/model identity, CUDA RTX 3060 residency, the production streaming tracer, exact 50-turn core evidence, and the independent core verifier.
- The latest mandatory live-call code review is `CLEAN`: 15 files reviewed, 0 findings. Its gate includes the receiver-drain, cancellation telemetry, browser correlation, and evidence-runner changes through `345fe33`.
- The deployed repairs normalize uploaded audio to 16 kHz before alignment, remove retired policy form/save gates, preserve curated evidence diagnostics, correlate duplicate interrupt acknowledgements, require measured zero pending playout, validate bounded drain values, and retain final cancellation telemetry across speech-task teardown.
- The same-commit acoustic/leak finish runner and the real browser suite were rerun after those repairs. All 4 desktop/mobile tests passed in 2.8 minutes, and post-suite status remained live/media ready with `qwen3_1_7b` prompt ready and `active_sessions=0`.
- A deployed 48 kHz stereo sample completed upload → built-in transcription → Qwen save without policy fields → generated test-play. The transcript matched the spoken sample exactly and the temporary verification voice was deleted afterward.

## Automated Gate Commands

Run the semantic verifier first:

```bash
python3 .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-verify-evidence.py --decision-ready --expected-commit "$(python3 .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-verify-evidence.py --print-deployed-commit)"
```

Expected and observed output: `PASS`.

Then run the exact operational gate:

```bash
scripts/operational-check.sh handoff --phase-dir .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls --commit "$(python3 .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-verify-evidence.py --print-deployed-commit)" --tests "PASS: full backend/server/client unit suites, mocked readiness UI, verifier self-test, canonical deploy evidence, deployed Voice Lab 48 kHz upload/transcribe/save/test-play, and deployed Qwen desktop/mobile live-call E2E" --ui-evidence .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-browser.json --live-evidence .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-call-flow.json --gpu-evidence .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-runtime.json
```

Observed result: `operational-check: handoff gate passed` for commit `288c05b4742dda0aac76050658aa12a44041102e`.

## Physical Multi-Turn and Barge-In Acceptance

1. From the physical test device, open `https://192.168.1.199:8443`. In Settings, confirm the AI backend is `https://192.168.1.199:9443` and Qwen3-TTS 1.7B is available.
2. In Voice Lab, upload the intended Qwen sample, use the built-in transcription, and confirm the transcript matches the recording. Uploading a voice sample is assumed authorized; there are no separate policy fields, sidecars, statuses, or automatic fallback. Save it and assign it to the call character. Do not judge likeness with the generated transport fixture listed above.
3. Start the call and confirm the UI reaches `Listening` before speaking.
4. Speak a normal first turn. Confirm audible playback begins while the assistant/TTS stream is still completing; silence until whole-response synthesis is a failure.
5. During a later spoken response, talk over RayMe. Confirm audio stops promptly, the cancelled assistant response is not persisted as completed speech, and the UI returns to `Listening` so the interruption becomes the next turn.
6. Complete at least three user-to-AI turns after recovery, including one longer response. Listen for intelligibility, stable identity, natural joins, and no late-call degradation.
7. End the call and return to the thread. Confirm durable call start/end plus completed user and assistant speech rows, with no completed row for the cancelled response.
8. Start one reconnect call with the same saved voice. Confirm Qwen remains resident, the selected prompt becomes ready, first playback is still early, and listening recovers after speech.
9. Record the two human results separately. Integrated listening covers audible likeness/naturalness/intelligibility/join quality; physical-call acceptance covers the complete real-device multi-turn, interruption, hangup, persistence, and reconnect flow.

## Acceptance Boundary

| Status | Value |
|---|---|
| `autonomous_release_ready` | `pass` |
| `candidate_spike_listening_status` | `accepted_separately` |
| `integrated_human_listening_status` | `pending` |
| `physical_call_status` | `pending` |

The candidate Spike listening result does not count as integrated Phase 09 listening acceptance. Only the builder's actual integrated and physical tests can close the two pending rows.
