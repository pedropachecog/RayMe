---
status: resolved
created: 2026-07-31T23:39:00Z
updated: 2026-08-01T00:08:00Z
trigger: "Phase 09 exact-commit OMEN core evidence completed the fifty-turn audio run but rejected reset-seed anchors as non-identical."
---

# Debug Session: Qwen Deterministic Anchor Input Mismatch

## Current Focus

user_goal_preservation: "The long-run suite must distinguish actual Qwen voice degradation or nondeterminism from differences caused by intentionally different spoken text, while keeping the mixed fifty-turn workload and strict anchor equality gate."
hypothesis: "Confirmed: the corrected equal-input run produced distinct remote-capture hashes because the comparison sat after WebRTC/Opus transport, while the exact Qwen source chunks were deterministic."
test: "Completed on exact deployed commit 492f197d140ba9b1dc7ec6e8a1c3a2f56013b478."
expecting: "Satisfied: all six source hashes matched and the remote captures remained distinct."
next_action: "Closed. Track the independent first-playback performance gate in a separate debug session."

## Symptoms

expected: "Turns 1, 10, 20, 30, 40, and 50 reset the evidence RNG and produce byte-identical WAVs for a controlled repeatability probe."
actual: "All fifty WAVs were captured, then bind_and_validate_actual_anchor_hashes rejected the six anchor WAVs as non-identical."
errors:
  - "Reset-seed anchor WAVs are not bit-identical; release evidence failed"
timeline: "Observed on 2026-07-31 during canonical deployment of exact commit f5b99d54ae7546f392029ef93665e6a6909c4bf6."
reproduction: "Run the Phase 09 core evidence soak and compare target selection for manifest anchor_turns against the three-phrase turn modulo rotation."

## Evidence

- timestamp: 2026-07-31T23:39:00Z
  checked: "Canonical deploy output and remote runner audio inventory."
  found: "The runner captured 57 WAVs including soak-turn-48, soak-turn-49, and soak-turn-50, then failed only at the reset-seed anchor equality gate."
  implication: "Generation completed; the failure is in the controlled repeatability input contract or actual determinism, requiring input hashes to distinguish them."

- timestamp: 2026-07-31T23:40:46Z
  checked: "Anchor turn numbers against the runner's modulo-three target selection."
  found: "Turns 1, 10, and 40 selected the short phrase; 20 and 50 selected the medium phrase; 30 selected the long phrase. The six anchors therefore had three distinct target inputs despite sharing the reset seed."
  implication: "The equality gate was invalid until target text was held constant; audio mismatch could not diagnose engine nondeterminism."

- timestamp: 2026-07-31T23:40:46Z
  checked: "Refactored soak target selection and Phase 09 evidence contracts."
  found: "All anchors now resolve to SOAK_ANCHOR_TARGET_TEXT; non-anchor turns still span all three workload phrases. All 40 evidence tests and git diff validation passed."
  implication: "The local deterministic probe now controls seed and text; real CUDA output equality remains the verification gate."

- timestamp: 2026-07-31T23:52:00Z
  checked: "Canonical exact-commit c9957f80cf9104974797d7efc65f85c5db14e042 run with equal seed and equal anchor text."
  found: "All fifty turns completed, but the six remote-capture WAVs still had distinct hashes. Each anchor capture had the identical 329,776-frame/6.87-second shape, while its WAV and PCM hashes differed."
  implication: "Inputs and output length are controlled, but the current hash sits after real-time WebRTC transport/Opus decode and cannot yet isolate model-source repeatability."

- timestamp: 2026-07-31T23:54:00Z
  checked: "Standalone Torch 2.10 CUDA-graph RNG replay on the same OMEN RTX 3060."
  found: "Resetting torch.cuda.manual_seed_all(91000) before each replay produced the same captured multinomial result eight out of eight times."
  implication: "A generic CUDA-graph RNG reset failure is not sufficient to explain the remote WAV mismatch; test the exact pre-transport source boundary next."

- timestamp: 2026-07-31T23:57:34Z
  checked: "Release-only source-chunk hash implementation and focused regressions."
  found: "The live CallSession now incrementally hashes validated Qwen source WAV chunks with length framing before WebRTC, exposes the digest only in release final metrics, and keeps remote WAV hashes for quality scoring. Call/WebRTC tests passed 99/99; evidence contracts passed 40/40; diff validation passed."
  implication: "The next exact CUDA run will distinguish source nondeterminism from transport capture variation without bypassing production streaming."

- timestamp: 2026-08-01T00:08:00Z
  checked: "Canonical exact-commit 492f197d140ba9b1dc7ec6e8a1c3a2f56013b478 OMEN release run and copied qwen3-soak.json."
  found: "The full fifty-turn runner passed. Turns 1, 10, 20, 30, 40, and 50 all reported the identical pre-WebRTC source_audio_sha256 and anchor_sha256 7ce0c81abadb2c2d8150b9688aaf0ef34d7b2b5bd1935c34dfd2d4e5eebda85c, while their remote capture audio_sha256 values remained distinct."
  implication: "The Faster Qwen source is repeatable under controlled seed and text. WebRTC capture variation is transport evidence, not model nondeterminism; the source-bound anchor is the correct release gate."

## Eliminated

- hypothesis: "The first failed equality result proves Faster Qwen3-TTS is nondeterministic under reset seed."
  evidence: "The compared requests had three different target texts, so different WAVs were the required semantic outcome regardless of RNG behavior."

- hypothesis: "The second failed remote-WAV equality result alone proves Qwen source generation is nondeterministic."
  evidence: "The hash was taken after paced WebRTC/Opus transport and capture, not at the validated Qwen source boundary; all six captures had equal duration but distinct decoded PCM."

## Resolution

root_cause: "The original anchor workload varied target text, and after controlling text the equality comparison was still made after paced WebRTC/Opus capture. That boundary introduced transport/resampling variation unrelated to Qwen source determinism."
fix: "Hold all declared anchor turns to one explicit target while retaining the mixed non-anchor workload, then incrementally hash length-framed validated Qwen source WAV chunks before WebRTC. Bind the release anchor to that source digest and keep remote hashes for acoustic/STT evidence."
verification: "Local call/WebRTC tests passed 99/99, evidence tests passed 40/40, the full backend passed 240/240, and the exact deployed OMEN fifty-turn runner passed with six identical source hashes across turns 1/10/20/30/40/50."
files_changed:
  - "ai-backend/app/call/session.py"
  - "ai-backend/tests/test_call_session.py"
  - ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py"
  - ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-verify-evidence.py"
  - ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-evidence-manifest.json"
