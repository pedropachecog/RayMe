# Phase 09 OMEN Qwen Handoff

RayMe is autonomously release-ready at deployed commit `2721a4ef3ddfadf9cbc47acb0522cb41bc62fbae`. The remaining work is human acceptance: integrated listening and one physical multi-turn/barge-in/reconnect call on a real device. Neither has been claimed as complete.

## Live OMEN State

| Item | Verified value |
|---|---|
| Web | `https://192.168.1.199:8443` |
| AI health | `https://192.168.1.199:9443/health` |
| WebRTC status | `https://192.168.1.199:9443/webrtc/status` — `ready`, live call ready, media transport ready |
| Deployed commit | `2721a4ef3ddfadf9cbc47acb0522cb41bc62fbae` |
| Resident engine | `qwen3_1_7b` |
| Selected prompt | `ready` |
| Active sessions | `0` before and after the real browser suite |
| Prepared evidence voice ID | `voice_4770e0117d35481fa1fb595eef7939ff` |
| Prepared evidence voice name | `RayMe Phase 09 Synthetic Qwen Tracer` |
| Prompt owner key | `voice_4770e0117d35481fa1fb595eef7939ff` — matches the live ready prompt after final finish-evidence cleanup |

The prepared voice is a mechanical generated non-person evidence fallback (`authorization_basis=generated_non_person_fixture`, scope `rayme_lan_call_testing`). Evidence runs may create additional transient fixture IDs, so identify the fallback by its authorization basis rather than by one ID. It proves transport, streaming, recovery, stability, and privacy; it is not eligible for human likeness judgment. Before judging likeness or naturalness, save or select the intended real-person reference with the speaker/data steward's actual authorization, the matching transcript, the LAN-test scope, and agreed retention/deletion terms.

## Release Evidence

All final release evidence below records the same deployed SHA:

- `09-evidence-manifest.json` — frozen runtime, thresholds, privacy policy, and scenario inventory.
- `results/qwen3-runtime.json` — pinned Faster Qwen3-TTS/model/Torch/CUDA and one-hot residency.
- `results/qwen3-webrtc-status.json` — model resident, prompt ready, bounded output, and authorized fixture state.
- `results/qwen3-call-flow.json` — early playback, bounded bridge/track, cancellation, recovery, and no whole-synthesis fallback.
- `results/qwen3-soak.json` — 50-turn non-degradation and memory/throughput stability.
- `results/qwen3-stt.json` — 50-turn spoken-message integrity.
- `results/qwen3-speaker.json` — pinned WavLM early/middle/late and integrated-baseline drift proof.
- `results/qwen3-browser.json` — real canonical desktop/mobile Chromium call proof, 6/6 passed in 3.4 minutes, with two completed cycles, two `ai_audio_started` events, two `ai_done` events, and two listening recoveries per device; provenance and fixture-path guards passed.
- `results/qwen3-log-leak-scan.json` — no raw reference audio, transcript, or local-path leakage in structured evidence or service logs.

Raw reference audio, transcripts, embeddings, and scorer audio remain local and uncommitted.

## Canonical Deployment, Review, and Incident Repair Record

- The only deployment command was `RAYME_OMEN_VERIFY_QWEN3=1 scripts/deploy-omen.sh`.
- The canonical deploy passed database schema migration, pinned Faster Qwen3-TTS `v0.3.2`/source/model identity, CUDA RTX 3060 residency, the production streaming tracer, exact 50-turn core evidence, and the independent core verifier.
- The mandatory Phase 09 code review is `CLEAN`: 60 files reviewed, 0 findings.
- Three post-review incident repairs are included in the deployed SHA: `2ed38e3` runs the OMEN database migration before launch, `f7feb6c` releases the finish-session prompt lease, and `2721a4e` makes the fake microphone loop-safe while cleaning up closed peers so the real browser suite preserves Qwen reply completion.
- The same-commit acoustic/leak finish runner and the real browser suite were rerun after those repairs. The desktop two-cycle test passed in 1.5 minutes, the mobile two-cycle test passed in 1.6 minutes, all 6 tests passed in 3.4 minutes, and the pre/post status remained live/media ready with `qwen3_1_7b` prompt ready and `active_sessions=0`.

## Automated Gate Commands

Run the semantic verifier first:

```bash
python3 .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-verify-evidence.py --decision-ready --expected-commit "$(python3 .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-verify-evidence.py --print-deployed-commit)"
```

Expected and observed output: `PASS`.

Then run the exact operational gate:

```bash
scripts/operational-check.sh handoff --phase-dir .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls --commit "$(python3 .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-verify-evidence.py --print-deployed-commit)" --tests "PASS: full backend/server/client unit suites, mocked readiness UI, verifier self-test, canonical deploy evidence, and deployed Qwen live-call E2E" --ui-evidence .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-browser.json --live-evidence .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-call-flow.json --gpu-evidence .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-runtime.json
```

Observed result: `operational-check: handoff gate passed` for commit `2721a4ef3ddfadf9cbc47acb0522cb41bc62fbae`.

## Physical Multi-Turn and Barge-In Acceptance

1. From the physical test device, open `https://192.168.1.199:8443`. In Settings, confirm the AI backend is `https://192.168.1.199:9443` and Qwen3-TTS 1.7B is available.
2. In Voice Lab, save or select the intended real-person Qwen reference. Confirm its steward/speaker authorization, `rayme_lan_call_testing` scope, matching transcript, and retention/deletion terms. Assign that saved voice to the call character. Do not judge likeness with the generated fallback listed above.
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
