---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
verified: 2026-08-01T12:53:38Z
status: human_needed
score: 47/47 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Integrated listening with the intended, explicitly authorized real-person saved voice"
    expected: "Early, middle, and late call turns remain intelligible, natural, recognizably consistent with the authorized reference, and free of objectionable chunk joins while playback begins before full generation finishes."
    why_human: "The committed release fixture is a generated non-person SAPI voice and is explicitly ineligible for likeness or naturalness acceptance; hashes, WER, and WavLM trend scores cannot replace listening."
  - test: "Physical multi-turn call on the builder's real desktop/mobile device, including spoken barge-in, hangup, and reconnect"
    expected: "Model and prompt preparation stay visible; speech begins early; a spoken interruption silences playout promptly, preserves the user's utterance, returns to Listening, emits no ghost audio or normal ai_done/persistence for the cancelled turn, and a later/reconnected turn succeeds."
    why_human: "The real-browser suite proves deployed WebRTC wiring with a generated microphone fixture, but cannot prove physical-device audio routing, acoustic VAD behavior, or lived call feel."
---

# Phase 09: Faster Qwen3-TTS 1.7B Live-Call Integration Verification Report

**Phase Goal:** Make `faster-qwen3-tts==0.3.2` with `Qwen/Qwen3-TTS-12Hz-1.7B-Base` a first-class saved-voice engine for real OMEN calls, with visible loading/prewarm, transcript alignment, bounded early streaming, barge-in cancellation, and no whole-synthesis fallback.

**Verified:** 2026-08-01T12:53:38Z  
**Status:** human_needed  
**Re-verification:** No — initial verification

## Verification Basis

- Deployed production commit: `2721a4ef3ddfadf9cbc47acb0522cb41bc62fbae`.
- Current reconciliation commit: `d7e2486ceec69d837576d0b5c3db5fd3f44113cb`.
- The deployed commit is an ancestor of HEAD. `git diff --quiet 2721a4e..HEAD -- ai-backend web-ui scripts` exits 0, so the production code inspected here is the deployed production code; later changes are planning/evidence records only.
- No earlier `09-VERIFICATION.md` existed.
- SUMMARY claims were not used as proof. Evidence below comes from production source, focused tests rerun by this verifier, raw committed OMEN result files, and the independent evidence verifier rerun in this verification.

## Goal Achievement

### Roadmap Contract

| # | Observable truth | Status | Evidence |
|---|---|---|---|
| 1 | Qwen3-TTS 1.7B is visible as a saved-voice engine; saving/using it requires a matching transcript and authorized reference, with sanitized failures. | ✓ VERIFIED | `tts_registry.py` publishes `qwen3_1_7b` with transcript/streaming metadata. `voice_service.py` hashes and binds reference/transcript authorization, contains blob paths, and derives an opaque owner key. The migration maps only `qwen3_0_6b` to the canonical id and resets authorization to `needs_confirmation`. Client Voice Lab/readiness tests and server authorization tests exercise the user-visible and trust-boundary paths. |
| 2 | OMEN runs the pinned package/model on CUDA through one-hot residency, exposes loading/resident state, and prewarms the selected prompt before a call turn. | ✓ VERIFIED | Worker pins model revision `fd4b254…`, rejects non-CUDA/model substitution, and uses the native runtime. `model_manager.py` unloads the previous resident engine, exposes `loading_engine`/`resident_tts_engine`, validates alignment, prewarms one prompt, and leases it to the call. Raw runtime evidence records RTX 3060, Torch `2.10.0+cu126`, CUDA 12.6, one resident `qwen3_1_7b`, no CPU fallback, and prompt-cache capacity/high-water 1/1. |
| 3 | Calls use bounded native streaming, start playback before generation completes on slow streams, separate immediate/final metrics, and never fall back to whole synthesis (including VoxCPM2 guards). | ✓ VERIFIED | `Qwen3TtsAdapter.synthesize()` raises; the worker calls only `generate_voice_clone_streaming`. `CallSession` uses a capacity-2 bridge and the paced track caps pending audio at 1.5 s. Focused early-playback/backpressure/no-fallback tests pass. Deployed short playback starts at 1021.5 ms before 2505.5 ms completion; slow-stream playback starts at 754.1 ms before 7944.0 ms completion with bridge 2/2, track 1500/1500 ms, positive producer blocking, zero underflow, and no fallback. |
| 4 | Barge-in, hangup, and engine switch cancel the exact generation, discard queued/late audio, suppress normal completion/persistence, and recover to listening. | ✓ VERIFIED | `cancel_ai_turn()` begins exact-request cancellation, silences paced playout before awaiting the worker terminal, retains cancellation guards through drain, and clears pending speech completion. Focused request-scoped cancellation, spoken-VAD barge-in, and persistence-suppression tests pass. Deployed cancel/hangup/switch scenarios show 52.9–116.1 ms acknowledgements, zero late audio/enqueue, zero normal `ai_done`, zero cancelled persistence, and recovery true. |
| 5 | Local regressions, canonical deployment verification, post-deploy status, and a real deployed browser call flow are complete and ready for physical user acceptance. | ✓ VERIFIED | Contracts-only, 33 adversarial verifier mutations, decision-ready recomputation, and the exact operational handoff command all pass here. Final browser evidence is non-mocked at canonical OMEN URLs: desktop and mobile each complete two user→AI cycles; 6/6 tests pass in 3.4 minutes; active sessions return to zero; no browser errors. Human listening and physical-device acceptance remain honestly pending. |

### Plan Must-Have Ledger

The five roadmap criteria above are the contract wording. The fifteen plans refine those criteria into 47 unique, testable must-haves; none reduce roadmap scope.

| Plan | Truths | Result | Independent evidence |
|---|---:|---|---|
| 09-01 | 3/3 | ✓ VERIFIED | Immutable runtime source lock, canonical `qwen3_1_7b` roster identity, truthful transcript/streaming metadata. |
| 09-02 | 3/3 | ✓ VERIFIED | Versioned IPC, supervised CUDA worker, native stream lifecycle and exact-request cancellation. |
| 09-03 | 3/3 | ✓ VERIFIED | One-hot readiness/prewarm, early live playback, separate immediate/final metrics. |
| 09-04 | 5/5 | ✓ VERIFIED | Sole deploy seam, authorized deterministic fixture selection, real CUDA hardware tracer and pinned runtime attestation. |
| 09-05 | 3/3 | ✓ VERIFIED | Alignment, prompt identity, output ceilings, sanitized failure containment, streaming-only adapter. |
| 09-06 | 2/2 | ✓ VERIFIED | Saved-voice delete invalidates only the matching opaque prompt and safely handles active use/failure. |
| 09-07 | 4/4 | ✓ VERIFIED | Exact legacy-id migration, provenance binding, contained authorized sample access, stale authorization rejection. |
| 09-08 | 3/3 | ✓ VERIFIED | Voice Lab and call UI expose model/prompt readiness, retry/error states, and gate start until ready. |
| 09-09 | 3/3 | ✓ VERIFIED | Mocked readiness acceptance plus opt-in, exact-commit, real deployed WebRTC acceptance contract. |
| 09-10 | 3/3 | ✓ VERIFIED | Natural-boundary incremental segmentation, first viable segment before LLM completion, bounded 60-word requests. |
| 09-11 | 3/3 | ✓ VERIFIED | Capacity-2 bridge, 1.5-second paced-track credit, producer blocking, cancellation drain, metric truthfulness. |
| 09-12 | 4/4 | ✓ VERIFIED | Locked 20-scenario manifest, pinned local WavLM trend scorer, independent threshold recomputation, human/automated separation. |
| 09-13 | 3/3 | ✓ VERIFIED | Production runner owns exact 20-scenario/50-turn runtime, STT, cancellation, and boundedness capture. |
| 09-14 | 2/2 | ✓ VERIFIED | Canonical deployment produced same-commit core evidence and preserved existing regressions/no-fallback guards. |
| 09-15 | 3/3 | ✓ VERIFIED | Same-commit acoustic/leak/browser decision gates and exact operational handoff pass while human acceptance remains pending. |

**Score:** 47/47 truths verified (0 present-but-behavior-unverified)

## Required Artifacts

All 30 distinct PLAN-declared artifacts exist. Every source artifact is substantive and wired; every result artifact is consumed by the independent verifier, the handoff gate, or both.

| Artifact group | Expected | Status | Details |
|---|---|---|---|
| Runtime identity and worker (`uv.lock`, registry, protocol, worker, adapter) | Pinned package/model, supervised CUDA-native streaming, typed terminals | ✓ VERIFIED | 402–5,426 lines per source/lock artifact; imports and runtime call path are live. Non-streaming Qwen synthesis is explicitly disabled. |
| Residency, alignment, and call pipeline (`model_manager.py`, `api/tts.py`, `session.py`, `tracks.py`) | One-hot load/prewarm, alignment, bounded early playout, terminal-safe cancellation | ✓ VERIFIED | Production source, named state-transition tests, and raw OMEN measurements agree. |
| Saved-voice lifecycle and migration (`voice_service.py`, migration 0003) | Provenance/authorization, contained blob use, exact legacy migration, deletion invalidation | ✓ VERIFIED | Hash-bound authorization is checked again at use time; opaque prompt keys carry no private clone content. |
| Client readiness and call surface (four Svelte/unit artifacts) | Visible model/prompt/loading/error states and honest call-start gate | ✓ VERIFIED | Components are used by the Voice Lab/settings/call routes; readiness state comes from server/backend status rather than hardcoded values. |
| Browser and segmentation contracts (four test/segmenter artifacts) | Incremental safe segments and mocked/real acceptance contracts | ✓ VERIFIED | Server focused slow-LLM test passes; final live browser result is non-mocked and same-commit. |
| Canonical deployment and hardware trace (`deploy-omen.sh`, tracer, hard-gate JSON) | Sole install/launcher/task/evidence seam and real CUDA proof | ✓ VERIFIED | Script writes only canonical launchers, registers tasks to those launchers, pins Torch/CUDA/runtime/model, and invokes the committed tracer/verifier. |
| Release evidence system (manifest, speaker scorer, verifier, OMEN runner) | Raw-sample capture and non-circular, adversarial release decision | ✓ VERIFIED | Contracts-only and all 33 named mutation self-tests pass; decision-ready recomputes thresholds instead of trusting stored overall flags. |
| Final release results and handoff (`qwen3-call-flow.json`, `qwen3-browser.json`, handoff) | Exact-commit deployed behavior and physical-test instructions | ✓ VERIFIED | Final evidence records commit `2721a4e…`; exact operational handoff command exits 0. |

## Key Link Verification

`gsd-tools query verify.key-links` was run against every PLAN. All 34 declared links verified.

| Link group | Count | Status | Details |
|---|---:|---|---|
| 09-01 through 09-04: lock/registry → adapter/worker → manager/session → deploy/tracer | 6/6 | ✓ WIRED | Runtime identity reaches the real worker and canonical OMEN evidence path. |
| 09-05 through 09-07: API/alignment → prompt identity → delete invalidation → migration/provenance | 8/8 | ✓ WIRED | Operations cannot bypass authorization, containment, alignment, or prompt ownership. |
| 09-08 through 09-10: backend readiness → server → UI/tests; token stream → segmenter → call TTS | 8/8 | ✓ WIRED | Visible state is sourced from live readiness; incremental text reaches live speech submission. |
| 09-11 through 09-13: native stream → bounded bridge/track → raw runner → verifier/scorer | 9/9 | ✓ WIRED | Backpressure and cancellation metrics flow into independent release thresholds. |
| 09-14 through 09-15: canonical deploy → final evidence → real browser/handoff | 3/3 | ✓ WIRED | Same-commit final evidence and exact handoff command close the automated release path. |

## Data-Flow Trace (Level 4)

| Dynamic artifact | Data variable | Source | Produces real data | Status |
|---|---|---|---|---|
| Voice Lab / saved-voice rows | engine metadata, transcript, authorization, preparation state | Saved DB rows + contained voice blob + backend `/tts` readiness/preparation APIs | Yes; server hashes and validates the stored sample/transcript at use time | ✓ FLOWING |
| Call preparation panel | model and prompt states | AI model-manager status via server call preparation polling | Yes; `loading`/`resident` and `prewarming`/`ready` are runtime state | ✓ FLOWING |
| Live call audio | incremental assistant segments | LLM token stream → `CallTtsSegmenter` → server speech turn → `CallSession` → Qwen worker native chunks → bounded track → WebRTC | Yes; deployed result contains real chunk/timing/backpressure measurements | ✓ FLOWING |
| Interrupt/hangup/switch state | exact turn/request id and cancellation terminal | VAD/UI/control event → `cancel_ai_turn()` → adapter/worker cancel → queue drain → listening recovery | Yes; deployed control scenarios record acknowledgement and zero late effects | ✓ FLOWING |
| Release decision | raw runtime/call/soak/STT/speaker/browser/leak values | Canonical OMEN runner result bundle | Yes; verifier recomputes identities, capacities, timing, drift, cancellation, and leaks | ✓ FLOWING |

## Behavioral Spot-Checks

Only named checks were run; no server or external service was started and no state was mutated.

| Behavior | Command | Result | Status |
|---|---|---|---|
| Slow Qwen stream starts before completion | `pytest ...::test_qwen_slow_stream_starts_playback_before_stream_completion -q` | 1 passed | ✓ PASS |
| Capacity-2 bridge blocks rather than drops | `pytest ...::test_qwen_capacity_two_bridge_blocks_producer_without_dropping_chunks -q` | 1 passed | ✓ PASS |
| Cancellation causes are request-scoped, terminal-safe, recoverable | `pytest ...::test_qwen_control_causes_are_request_scoped_terminal_safe_and_recoverable -q` | 6 passed | ✓ PASS |
| Spoken VAD barge-in preserves mic turn and silences real playout | `pytest ...::test_qwen_spoken_vad_barge_in_preserves_mic_turn_and_silences_real_playout -q` | 1 passed | ✓ PASS |
| VoxCPM2 stream crash does not use generate fallback | `pytest ...::test_voxcpm2_worker_stream_crash_is_recoverable_without_generate_fallback -q` | 1 passed | ✓ PASS |
| Slow LLM submits first safe segment before completion | `pytest ...::test_qwen_slow_llm_submits_first_safe_segment_before_stream_completion -q` | 1 passed | ✓ PASS |
| Cancelled Qwen turn emits no normal done/persistence | `pytest ...::test_cancelled_qwen_turn_never_persists_complete_speech_or_normal_done -q` | 2 passed | ✓ PASS |
| Deleting a Qwen voice invalidates only its matching prompt owner | `pytest ...::test_qwen_delete_invalidates_matching_owner_and_leaves_unrelated_voice_usable -q` | 1 passed | ✓ PASS |

## Probe Execution

| Probe | Command | Result | Status |
|---|---|---|---|
| Evidence contracts | `python3 09-verify-evidence.py --contracts-only` | `PASS` | ✓ PASS |
| Adversarial verifier self-test | `python3 09-verify-evidence.py --self-test` | 33 named corruptions rejected; final `PASS` | ✓ PASS |
| Final decision gate | `python3 09-verify-evidence.py --decision-ready --expected-commit 2721a4e…` | `PASS` | ✓ PASS |
| Operational handoff | `scripts/operational-check.sh handoff ... --commit 2721a4e…` | `operational-check: handoff gate passed` | ✓ PASS |

## Deployed Evidence Spot-Checks

- Runtime: `faster-qwen3-tts==0.3.2` at source commit `a70afc0…`; exact 1.7B model revision `fd4b254…`; RTX 3060; Torch `2.10.0+cu126`; CUDA 12.6; one-hot residency; CPU fallback false.
- Early/bounded streaming: short playback 1021.5 ms < generation 2505.5 ms; slow-backpressure playback 754.1 ms < generation 7944.0 ms; bridge high-water/capacity 2/2; track high-water/capacity 1500/1500 ms; queue blocking 3206.6 ms; zero underflow/fallback.
- Soak: 50 turns; turn 1/50 TTFA 358.229/363.269 ms, first playback 799.5/826.8 ms, RTFx 1.276/1.269, reserved memory 5702/5702 MiB, WER 0/0, natural EOS true, no underflow/fallback.
- Cancellation: cancel-before/after and hangup/switch acknowledge in 52.9–116.1 ms; each records zero late audio/enqueue, zero normal `ai_done`, zero cancelled persistence, and recovery true.
- Speaker trend: pinned local CUDA WavLM scorer; early median 0.968300, late 0.947390, late-minus-early -0.020910 and late-minus-baseline -0.024717, both inside the frozen 0.05 maximum drop. This is stability evidence, not human likeness acceptance.
- Real browser: live E2E enabled, mocked false, desktop/mobile two-cycle flows pass, 6/6 tests pass, active sessions return to zero, and no browser errors are recorded.
- Privacy: the committed leak scan covers seven release artifacts and AI/web logs with zero findings; the verifier independently rejects private paths, full transcripts, base64 audio, tokens, and audio extensions.

## Requirements Coverage

| Requirement | Source plans | Description | Status | Evidence |
|---|---|---|---|---|
| REQ-22 | 09-01 through 09-10, 09-12 through 09-15 | Saved Qwen voice uses the pinned 1.7B runtime/model and matching transcript; old identity is compatibility-only. | ✓ SATISFIED | Registry/lock/worker pins, hash-bound saved-voice authorization, exact migration, readiness UI, and deployed CUDA identity. |
| REQ-45 | 09-02 through 09-05, 09-07 through 09-15 | Natural bounded chunk planning/native streaming starts from the first viable chunk and records timing/join metrics. | ✓ SATISFIED | Incremental segmenter, streaming-only adapter, capacity-2 bridge, paced track, immediate/final metrics, no-fallback tests, and deployed early-playback results. |
| REQ-46 | 09-03/04, 09-08 through 09-15 | End-to-end turn latency target, explicitly a design budget rather than blocking acceptance. | ✓ SATISFIED | Turn 1/50 first playback 799.5/826.8 ms and native TTFA about 358–363 ms are recorded honestly; the verifier does not falsely convert the non-blocking target into a release gate. |

No additional requirement is mapped to Phase 09 in `REQUIREMENTS.md`; there are no orphaned Phase 09 requirements.

## Anti-Patterns Found

| File | Pattern | Severity | Impact |
|---|---|---|---|
| Production files changed by Phase 09 | `TBD` / `FIXME` / `XXX` | None | No blocker debt markers found in production code. |
| `.planning/ROADMAP.md` | Three `Plans: TBD` markers | ℹ️ Info | Each belongs to an explicitly named later roadmap phase, not unfinished Phase 09 work. |
| `09-run-omen-evidence.py` | Deliberate browser placeholder in the intermediate acoustic-only mode | ℹ️ Info | Final `qwen3-browser.json` is real, non-mocked, and same-commit; decision-ready validation rejects missing/placeholder browser acceptance. |
| `09-VALIDATION.md` | Still marked draft / non-Nyquist | ⚠️ Warning | Documentation lag only. The named tests, real deployed evidence, adversarial verifier, and decision gate were independently rerun and pass; no goal artifact or wiring depends on this stale status page. |

## Human Verification Required

### 1. Integrated listening with the intended authorized saved voice

**Test:** Save or reconfirm the intended authorized real-person Qwen voice, start a real OMEN call, and listen deliberately to early, middle, and late turns, including a longer response.

**Expected:** Speech is intelligible and natural, retains the intended voice consistently, has no objectionable chunk joins or degradation late in the call, and begins while synthesis is still streaming.

**Why human:** The autonomous bundle intentionally used a generated non-person SAPI fixture. WER and WavLM trends prove message/stability properties but cannot prove likeness, naturalness, or subjective join quality.

### 2. Physical real-device multi-turn/barge-in/reconnect call

**Test:** Follow `09-OMEN-HANDOFF.md` on the builder's actual desktop/mobile device: complete several turns, interrupt RayMe by speaking during playout, continue afterward, hang up, and reconnect/start another turn.

**Expected:** Loading/model/prompt state stays visible; audio begins promptly; spoken barge-in stops playout, preserves the user's utterance, and returns to Listening; no ghost audio, normal `ai_done`, or completed persistence appears for the cancelled turn; the later/reconnected turn works.

**Why human:** Automated live E2E verifies deployed browser/WebRTC control flow with generated media, but cannot validate physical audio routing, room acoustics, real speech VAD behavior, or perceived call feel.

## Gaps Summary

No implementation, artifact, wiring, data-flow, behavioral-test, deployment, or evidence gap was found. The automated phase goal is achieved at deployed commit `2721a4e…`.

The phase is **human_needed**, not passed, because both acceptance decisions above remain explicitly pending in the release evidence. That boundary is honest and intentional; it must not be inferred from automated browser, WER, or speaker-trend results.

---

_Verified: 2026-08-01T12:53:38Z_  
_Verifier: the agent (gsd-verifier)_
