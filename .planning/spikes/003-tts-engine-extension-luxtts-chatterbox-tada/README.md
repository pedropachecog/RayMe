---
spike: 003
name: tts-engine-extension-luxtts-chatterbox-tada
type: standard
validates: "Given the Phase 0 TTS probe host on OMEN-PC, when LuxTTS, Chatterbox Turbo, and TADA 1B are integrated using Voicebox-compatible installs, then their warm-model latency, VRAM fit, quality risks, and acceleration levers are known."
verdict: PARTIAL
related: [002]
tags: [tts, luxtts, chatterbox, tada, benchmark, quality]
---

# Spike 003: TTS Engine Extension - LuxTTS, Chatterbox Turbo, TADA 1B

## Current Verdict

Current verdict: `PARTIAL`

The new warm-model benchmark invalidates the earlier narrow `Hey, got it.` readout for LuxTTS. Once model load and warmup are excluded, LuxTTS is the most interesting new engine for RayMe-style "LLM answer is ready, now speak it" requests.

The verdict stays `PARTIAL` because objective latency is not enough. Manual listening on 2026-04-23 found that the `chatterbox_turbo` long samples are pure gibberish, and some generated samples across the set are subjectively unacceptable. Do not promote any new engine until manual quality scoring is recorded.

Important correction: the current XTTS long-form rows are not acceptable as final model measurements. The harness discovered XTTS's `inference_stream` 400-token limit but did not segment long text before calling it. That means XTTS long-form streaming was under-tested and the fallback full-render numbers are inflated relative to the streaming path RayMe should actually use.

Broader correction: best-in-class chunking is required for every model, not just XTTS. Engines without true streaming still need sentence-aware, token-aware, latency-aware chunking so RayMe can start playback early, stitch chunks cleanly, and avoid model-specific context limits. Future benchmarks must compare raw whole-generation, native streaming where available, and the best chunked runtime path for each engine.

## What Changed

Initial probe:

- Extended `tts_ttfa.py` and `vram_soak.py` to add `luxtts`, `chatterbox_turbo`, and `tada_1b`.
- Added `requirements-tts-experimental.txt` using the Voicebox-compatible dependency strategy so the Phase 0 torch/CUDA baseline stayed intact.
- Measured the old short-utterance path and found LuxTTS looked slower than F5/XTTS there.

Corrected probe:

- Added `tts_scenario_matrix.py` and `tts_runtime_matrix_v2.py`.
- Measured warm-model request time separately from `model_load_ms` and `warmup_ms`.
- Tested both native Windows and WSL.
- Tested both `baseline` and `optimized` profiles.
- Generated listenable WAV samples for every measured row.
- Repaired F5 rows after the first full matrix exposed a bad F5 invocation path.

## Artifacts

Primary JSON:

- `.planning/phases/00-measurement-gate/results/tts_runtime_matrix_v2.json`
- `.planning/phases/00-measurement-gate/results/tts_scenario_matrix_windows_native.json`
- `.planning/phases/00-measurement-gate/results/tts_scenario_matrix_wsl_python.json`

Listening roots:

- `.planning/phases/00-measurement-gate/results/tts_scenario_audio/windows_native/`
- `.planning/phases/00-measurement-gate/results/tts_scenario_audio/wsl_python/`

Probe code:

- `.planning/phases/00-measurement-gate/probes/tts_scenario_matrix.py`
- `.planning/phases/00-measurement-gate/probes/tts_runtime_matrix_v2.py`
- `.planning/phases/00-measurement-gate/probes/test_tts_scenario_matrix.py`

Manual quality template:

- `.planning/spikes/003-tts-engine-extension-luxtts-chatterbox-tada/MANUAL-QUALITY.csv`

Full measured matrix:

- `.planning/spikes/003-tts-engine-extension-luxtts-chatterbox-tada/RESULT-MATRIX.csv`

## Warm-Model Results

These metrics exclude model load and warmup. They measure request-time behavior after the model is already resident.

Streaming caveat:

- `XTTS` native streaming was measured for `short_reply` and `medium_reply` on both Windows and WSL, for both baseline and optimized profiles.
- `XTTS` `long_reply` did not stream. `inference_stream` hit XTTS's 400-token limit and the harness fell back to full-render timing, so long XTTS rows are not streaming TTFA and must be remeasured.
- `F5` optimized rows use simulated streaming through chunked generation. They are not true incremental model streaming, but they do measure first generated chunk timing.
- `Qwen3` rows use simulated text streaming semantics with `non_streaming_mode=False`, not real audio streaming.
- `LuxTTS`, `Chatterbox Turbo`, and `TADA 1B` rows are whole-generation timings. Their `request_ttfa_ms` equals `request_total_ms` in this harness.
- For non-streaming engines, those whole-generation rows are only raw baselines. They do not represent the best RayMe runtime path until a chunked playback strategy is implemented and measured.

Best optimized winners:

| Scenario | Metric | Winner | Runtime | Value | Sample |
|---|---|---|---|---:|---|
| `short_reply` | request TTFA | `luxtts` | WSL | 289.8 ms | `wsl_python/luxtts__optimized__short_reply.wav` |
| `short_reply` | request total | `luxtts` | WSL | 289.8 ms | `wsl_python/luxtts__optimized__short_reply.wav` |
| `medium_reply` | request TTFA | `xtts` | WSL | 439.6 ms | `wsl_python/xtts__optimized__medium_reply.wav` |
| `medium_reply` | request total | `luxtts` | Windows | 508.3 ms | `windows_native/luxtts__optimized__medium_reply.wav` |
| `long_reply` | request TTFA | `f5` | WSL | 980.6 ms | `wsl_python/f5__optimized__long_reply.wav` |
| `long_reply` | request total | `luxtts` | Windows | 1678.6 ms | `windows_native/luxtts__optimized__long_reply.wav` |

Optimized medium reply, sorted by request TTFA:

| Runtime | Engine | Status | TTFA ms | Total ms | RTF | Notes |
|---|---|---|---:|---:|---:|---|
| WSL | `xtts` | measured | 439.6 | 9861.1 | 0.552 | fastest medium first audio |
| Windows | `xtts` | measured | 455.6 | 9694.4 | 0.591 | native streamer, slow full render |
| Windows | `luxtts` | measured | 508.3 | 508.3 | 0.043 | best medium total time |
| WSL | `luxtts` | measured | 519.4 | 519.4 | 0.044 | near-Windows parity |
| Windows | `f5` | measured | 846.8 | 2637.1 | 0.098 | strong chunked behavior |
| WSL | `f5` | measured | 1033.8 | 2614.6 | 0.097 | strong chunked behavior |
| WSL | `tada_1b` | measured | 3233.4 | 3233.4 | 0.194 | valid on WSL only |
| WSL | `chatterbox_turbo` | measured | 6483.6 | 6483.6 | 0.433 | manual long-form quality failed |
| Windows | `chatterbox_turbo` | measured | 7012.2 | 7012.2 | 0.482 | manual long-form quality failed |
| WSL | `qwen3` | measured | 47050.1 | 47050.1 | 2.970 | too slow |
| Windows | `qwen3` | measured | 47060.4 | 47060.4 | 2.723 | too slow |
| Windows | `tada_1b` | failed | n/a | n/a | n/a | CUDA failure during warmup/generation |

## Optimization Findings

Baseline vs optimized changes:

| Engine | Useful optimization | Result |
|---|---|---|
| `luxtts` | cached prompt state | Large short-reply gain: Windows `999.1 -> 352.6 ms`, WSL `827.9 -> 289.8 ms` |
| `xtts` | cached conditioning latents | Consistent TTFA gain: WSL medium `596.2 -> 439.6 ms` |
| `f5` | cached prep plus chunked generation | Large medium/long TTFA gain: WSL long `11257.0 -> 980.6 ms` |
| `chatterbox_turbo` | cached conditionals | Small gains only |
| `tada_1b` | cached prompt state | WSL medium/long improved, WSL short regressed badly |
| `qwen3` | cached prompt plus FA2 fallback logic | No useful gain in this environment |

Engine notes:

- `LuxTTS` is now a serious candidate for an experimental fast path. It has extremely low warm total latency, but quality must be judged manually before product use.
- `XTTS` remains valuable for earliest medium-reply first audio and native streaming semantics, despite weak full-render time and prior clone-quality concerns.
- `F5` remains the safest incumbent for long-form first audio and chunked behavior.
- `Chatterbox Turbo` should not be promoted without a quality fix. The long-form samples were reported as pure gibberish.
- `TADA 1B` should stay WSL-only for now. Windows failed during CUDA warmup/generation, while WSL produced measurable samples.
- `Qwen3 0.6B-Base` remains an experiment/play path only. It is far too slow in this matrix.

## Known Blockers

- Numeric latency does not capture intelligibility, speaker similarity, accent, or prosody.
- The harness must implement token-aware long-text splitting for XTTS streaming. Long text must be segmented before `inference_stream` so no segment reaches the 400-token cap, while preserving sentence boundaries where possible and measuring first-segment TTFA plus total stitched playback time.
- The harness must implement a shared best-in-class chunking algorithm for all engines. It should prefer sentence boundaries, enforce model-specific token/character caps, avoid tiny unnatural fragments, support lookahead where useful, measure first-chunk TTFA, total stitched time, inter-chunk gaps, and produce the stitched WAV for listening.
- Chatterbox Turbo long samples failed manual listening and should be treated as rejected until reproduced or fixed.
- TADA 1B native Windows remains unstable in this harness due a CUDA failure during warmup/generation.
- The current harness uses three fixed text scenarios, not a live LLM output corpus.
- The current harness emits WAVs but does not yet collect structured human ratings automatically.

## What to Run Next

First run a manual listening pass, because the next decision is quality-gated:

```bash
explorer.exe "$(wslpath -w .planning/phases/00-measurement-gate/results/tts_scenario_audio)"
```

Record the pass in:

```text
.planning/spikes/003-tts-engine-extension-luxtts-chatterbox-tada/MANUAL-QUALITY.csv
```

Use this priority order:

1. Listen to all `luxtts__optimized__*.wav` samples from Windows and WSL.
2. Listen to `xtts__optimized__medium_reply.wav` and `f5__optimized__long_reply.wav` as current baselines.
3. Re-check all `chatterbox_turbo__optimized__long_reply.wav` samples and mark them rejected unless a rerun produces intelligible audio.
4. Listen to WSL-only `tada_1b__optimized__*.wav`; ignore Windows TADA until the CUDA failure is debugged.
5. Treat `qwen3` as optional listening only, because the latency result is already noncompetitive.

Then run the next engineering pass:

```bash
python3 .planning/phases/00-measurement-gate/probes/tts_runtime_matrix_v2.py --output .planning/phases/00-measurement-gate/results/tts_runtime_matrix_v2.json
```

Before rerunning for final long-form comparison, update `tts_scenario_matrix.py` with a shared chunk planner. XTTS must use it to stay under the 400-token streaming cap, and non-streaming engines must use it to measure their best practical chunked playback path rather than only whole-generation latency. Then rerun the full Windows plus WSL matrix and refresh the JSON plus WAV outputs.

After manual scoring, the likely next code task is to teach the TTS decision logic to read the quality sidecar so quality failures can override raw latency wins.
