---
status: resolved
created: 2026-08-01T00:10:00Z
updated: 2026-08-01T00:41:00Z
trigger: "Phase 09 exact-commit OMEN core evidence passed its fifty-turn runner, then the independent verifier rejected message-integrity-punctuation-final-word because caller-side first playback was 1276.2 ms against the 1250 ms bound."
---

# Debug Session: Qwen Live First-Playback Bound

## Current Focus

user_goal_preservation: "Faster Qwen3-TTS 1.7B must be ready for real RayMe calls without the long-call degradation of the old engine, while preserving early playback, bounded backpressure, smooth playout, listening recovery, and barge-in."
hypothesis: "Confirmed in production: the generic 750 ms target quantized Qwen's 320 ms chunks to a 960 ms startup buffer, then a redundant 250 ms synthetic preroll delayed caller nonzero audio. The sole underflow was natural terminal frame padding, and the RTF denominator included intentional downstream playout blocking instead of using the worker's native generation clock."
test: "Completed on exact deployed commit bd71e481f8f90feb4be22d1f308ebf67b281f922."
expecting: "Satisfied: hot hardware-tracer playback was 929.4/997.9 ms, native RTFx was 1.419/1.525, the fifty-turn runner passed, and the independent verifier advanced beyond all timing/stream/backpressure/underflow gates."
next_action: "Closed. Track the later message-integrity WER failure in a separate debug session."

## Symptoms

expected: "Every sustained Qwen live-call scenario begins caller playback before generation completes and normally within 1250 ms, with zero active-playout underflow."
actual: "Seven sustained scenarios began before completion but measured 1276.2-1537.1 ms first playback and underflow_count=1; the verifier stopped at the first 1276.2 ms bound failure."
errors:
  - "FAIL: message-integrity-punctuation-final-word first playback exceeds the bound"
timeline: "Observed on 2026-08-01 during canonical deployment of exact commit 492f197d140ba9b1dc7ec6e8a1c3a2f56013b478."
reproduction: "Run RAYME_OMEN_VERIFY_QWEN3=1 scripts/deploy-omen.sh and independently verify the generated Phase 09 core evidence."

## Evidence

- timestamp: 2026-08-01T00:10:00Z
  checked: "Copied exact-commit OMEN qwen3-call-flow.json."
  found: "The punctuation scenario measured 1276.2 ms first playback, 372.03 ms native first chunk, 6060.7 ms generation completion, RTFx 1.03, and underflow_count 1. The other six sustained scenarios measured 1461.1-1537.1 ms first playback and also underflow_count 1."
  implication: "Early playback is intact, but this is a systematic startup/measurement boundary issue rather than a full-synthesis fallback or isolated 26 ms jitter."

- timestamp: 2026-08-01T00:18:00Z
  checked: "Production startup constants, Qwen native 320 ms chunk shape, and caller first-nonzero measurement."
  found: "The shared 750 ms audio minimum requires three Qwen chunks (960 ms), and the first streamed chunk adds 250 ms of silence even though the WebRTC track already sends silent keepalive frames. Removing one chunk and Qwen-only preroll predicts a 570 ms reduction, enough to move the observed 1248.5-1697.1 ms soak range below 1250 ms."
  implication: "Use an engine-specific two-chunk/600 ms Qwen startup and zero Qwen preroll; leave VoxCPM2's established policy untouched."

- timestamp: 2026-08-01T00:20:00Z
  checked: "QueuedAudioOutputTrack underflow activation and the uniform underflow_count=1 evidence pattern."
  found: "The counter treats a natural final partial 20 ms frame as underflow because measurement remains active until wait_until_idle returns. It does not know that the producer reached natural EOS."
  implication: "Signal natural input completion before draining playout, so terminal padding is excluded while any partial/empty frame before EOS remains a real underflow."

- timestamp: 2026-08-01T00:22:00Z
  checked: "Qwen worker timestamps, unbounded worker-reader queue, capacity-two session bridge, and final RTF calculation."
  found: "Qwen generated_at_ms is stamped in the isolated worker and drained independently by its reader thread, but CallSession divided audio by wall time after paced track admission. The result folded deliberate bounded backpressure into engine RTF."
  implication: "Retain wall generation completion for first-before-completion ordering, but calculate Qwen RTF from the worker-native final generated_at_ms and expose that denominator as terminal evidence."

- timestamp: 2026-08-01T00:28:00Z
  checked: "Local regression suite after the engine-specific startup, EOS accounting, and native timing changes."
  found: "Qwen's slow-stream test starts from exactly two 320 ms chunks/640 ms, target 600 ms, zero preroll, and before producer completion. VoxCPM2 startup tests remain green. Focused call/Qwen/WebRTC tests passed, evidence tests passed 40/40, the full backend passed 241/241, py_compile and git diff checks passed."
  implication: "The repair preserves the live-call invariants locally and is ready for exact-commit OMEN verification."

- timestamp: 2026-08-01T00:41:00Z
  checked: "Canonical deploy and exact-commit OMEN hardware/core evidence for bd71e481f8f90feb4be22d1f308ebf67b281f922."
  found: "The medium and long hardware samples began caller nonzero playback at 929.4 ms and 997.9 ms with 640 ms/two-chunk startup buffers, no Qwen preroll, native RTFx 1.419 and 1.525, and first playback before completion. The full fifty-turn runner returned PASS. Independent verification advanced through streaming, latency, RTF, natural EOS, underflow, capacity, and field-separation checks before stopping later at message-integrity WER."
  implication: "The live first-playback, active-underflow, and native-supply incident is resolved on the exact production deployment."

## Eliminated

- hypothesis: "The verifier failed because Qwen waited for whole synthesis before playback."
  evidence: "Every measured first playback preceded generation completion by several seconds; streaming_used=true and whole_wav_fallback_used=false."

- hypothesis: "One slow evidence sample caused a flaky 26 ms miss."
  evidence: "All seven sustained rows measured 1276.2-1537.1 ms and all fifty soak rows measured 1248.5-1697.1 ms, matching the shared three-chunk plus preroll policy."

## Resolution

root_cause: "Qwen inherited a generic 750 ms startup target that rounded 320 ms native chunks up to 960 ms, plus a redundant 250 ms synthetic preroll on an already-live WebRTC track. Evidence also counted natural terminal frame padding as underflow and used paced admission wall time as the engine RTF denominator."
fix: "Use a Qwen-only 600 ms/two-chunk startup with zero synthetic preroll while retaining the capacity-two bridge and early playback. Mark natural input completion before draining the track so only pre-EOS starvation counts as underflow. Calculate Qwen RTF from the isolated worker's native generated_at clock while keeping wall generation completion for ordering."
verification: "Local Qwen/VoxCPM2 call/WebRTC regressions passed, evidence tests passed 40/40, and full backend passed 241/241. Exact OMEN commit bd71e48 produced hot caller playback at 929.4/997.9 ms and native RTFx 1.419/1.525; the fifty-turn runner passed and independent verification cleared every timing/stream/underflow gate."
files_changed:
  - "ai-backend/app/call/session.py"
  - "ai-backend/app/call/tracks.py"
  - "ai-backend/tests/test_call_session.py"
  - ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py"
  - ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-verify-evidence.py"
