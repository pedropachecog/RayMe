---
spike: 003
name: tts-engine-extension-luxtts-chatterbox-tada
type: standard
validates: "Given the Phase 0 TTS probe host on OMEN-PC, when LuxTTS, Chatterbox Turbo, and TADA 1B are integrated using Voicebox-compatible installs, then their warm-model latency, VRAM fit, quality risks, and acceleration levers are known."
verdict: PASS_WITH_CAVEATS
related: [002]
tags: [tts, luxtts, chatterbox, tada, benchmark, quality]
---

# Spike 003: TTS Engine Extension - LuxTTS, Chatterbox Turbo, TADA 1B

## Current Verdict

Current verdict: `PASS_WITH_CAVEATS`

The shared chunk planner has now been implemented in `.planning/phases/00-measurement-gate/probes/tts_scenario_matrix.py` and the full Windows plus WSL matrix has been rerun on OMEN-PC. XTTS optimized long-form now uses `shared_chunked_streaming` with three safe chunks and no `inference_stream` 400-token fallback. Non-streaming engines now have optimized chunked-playback rows with first-chunk TTFA, stitched playback time, inter-chunk gaps, and stitched WAVs.

The spike is closed as `PASS_WITH_CAVEATS`: the latency, fit, quality risks, and next implementation caveats are known well enough to move on. Manual listening is not exhaustive, but it is enough to avoid promoting a misleading raw latency winner as a default.

Manual listening on 2026-04-23 found quality failures in all six listened `luxtts` optimized samples from Windows and WSL: reference/sample tail repetition, metallic noise, over-fast delivery, sample phrase leakage, poor speaker match, and accent loss. These are sample-level evaluation findings for the current user voice sample, not a decision to remove LuxTTS from future implementation. LuxTTS currently wins several latency rows and should stay available for retesting with better-padded reference audio and other speakers/accents.

Manual listening on 2026-04-23 also clarified Chatterbox Turbo: baseline long-form samples are gibberish on both runtimes, while normal optimized long-form and `optimized_seed_1337` long-form samples are fine on both runtimes. That points away from seed sensitivity as the primary issue; the raw/baseline long-form path is bad, while the optimized chunked path fixes long-form intelligibility for these samples.

Do not promote any new engine solely on latency. Keep all engine paths available in future implementation, and use `MANUAL-QUALITY.csv` to decide defaults, labels, warnings, and retest priorities.

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

The sidecar currently contains 66 measured non-Qwen rows. Sixteen rows are scored from user listening so far: five accepts, eight rejects, and three caution rows.

Full measured matrix:

- `.planning/spikes/003-tts-engine-extension-luxtts-chatterbox-tada/RESULT-MATRIX.csv`

## What Changed

- Added experimental engine support for `luxtts`, `chatterbox_turbo`, and `tada_1b`.
- Added `requirements-tts-experimental.txt` for Voicebox-compatible dependency setup.
- Added warm-model scenario harness and Windows plus WSL matrix driver.
- Implemented a shared sentence-aware chunk planner for all engines.
- Reran the full Windows plus WSL matrix after chunking.
- Added Chatterbox Turbo `optimized_seed_1337` rows and WAVs for seed-sensitivity listening.

## Warm-Model Results

These metrics exclude model load and warmup. They measure request-time behavior after the model is already resident. The winner tables below are latency-only; LuxTTS is the latency winner but has current-sample quality failures that must be remembered when choosing defaults.

Streaming and chunking caveat:

- Baseline rows remain raw whole-request or native-stream measurements for comparison.
- Optimized rows now use `shared_chunked_playback` or `shared_chunked_streaming` where applicable.
- XTTS optimized long-form is now measured as true native streaming over three planner chunks, not fallback full-render timing.
- Non-streaming engines still are not true incremental decoders, but their optimized rows now measure the RayMe-shaped chunked playback path rather than only whole-generation latency.
- `stitched_playback_ms` is the better long-form playback comparison for chunked rows because it models chunk readiness plus audio duration and gaps; `request_total_ms` remains raw generation wall time.

Best optimized winners:

| Scenario | Metric | Winner | Runtime | Value | Sample |
|---|---|---|---|---:|---|
| `short_reply` | request TTFA | `luxtts` | WSL | 300.5 ms | `wsl_python/luxtts__optimized__short_reply.wav` |
| `short_reply` | request total | `luxtts` | WSL | 635.8 ms | `wsl_python/luxtts__optimized__short_reply.wav` |
| `short_reply` | stitched playback | `luxtts` | WSL | 4535.1 ms | `wsl_python/luxtts__optimized__short_reply.wav` |
| `medium_reply` | request TTFA | `luxtts` | Windows | 320.4 ms | `windows_native/luxtts__optimized__medium_reply.wav` |
| `medium_reply` | request total | `luxtts` | WSL | 738.9 ms | `wsl_python/luxtts__optimized__medium_reply.wav` |
| `medium_reply` | stitched playback | `luxtts` | Windows | 12075.0 ms | `windows_native/luxtts__optimized__medium_reply.wav` |
| `long_reply` | request TTFA | `luxtts` | Windows | 352.9 ms | `windows_native/luxtts__optimized__long_reply.wav` |
| `long_reply` | request total | `luxtts` | Windows | 1869.6 ms | `windows_native/luxtts__optimized__long_reply.wav` |
| `long_reply` | stitched playback | `xtts` | WSL | 43606.1 ms | `wsl_python/xtts__optimized__long_reply.wav` |

Optimized long reply, sorted by request TTFA:

| Runtime | Engine | Profile | Mode | TTFA ms | Total ms | Stitched ms | Chunks | Notes |
|---|---|---|---|---:|---:|---:|---:|---|
| Windows | `luxtts` | optimized | shared chunked playback | 352.9 | 1869.6 | 43638.2 | 3 | fastest long TTFA |
| WSL | `luxtts` | optimized | shared chunked playback | 380.3 | 1930.8 | 43665.6 | 3 | near Windows parity |
| WSL | `xtts` | optimized | shared chunked streaming | 427.4 | 23525.3 | 43606.1 | 3 | best long stitched playback |
| Windows | `xtts` | optimized | shared chunked streaming | 482.3 | 36433.6 | 57591.6 | 3 | no streaming fallback |
| Windows | `f5` | optimized | shared chunked playback | 981.2 | 8119.7 | 103583.8 | 3 | incumbent fallback |
| WSL | `f5` | optimized | shared chunked playback | 994.8 | 7667.1 | 103597.5 | 3 | incumbent fallback |
| WSL | `tada_1b` | optimized | shared chunked playback | 1714.1 | 11840.1 | 58293.4 | 3 | caution: voice morphing/hiccups |
| WSL | `chatterbox_turbo` | optimized | shared chunked playback | 2994.2 | 24157.6 | 61543.8 | 3 | accepted long-form |
| WSL | `chatterbox_turbo` | optimized_seed_1337 | shared chunked playback | 3167.1 | 24607.7 | 64433.8 | 3 | seed-sensitivity sample |
| Windows | `chatterbox_turbo` | optimized_seed_1337 | shared chunked playback | 3227.2 | 27960.5 | 66185.2 | 3 | seed-sensitivity sample |
| Windows | `chatterbox_turbo` | optimized | shared chunked playback | 3312.2 | 27302.0 | 63947.3 | 3 | accepted long-form |
| Windows | `qwen3` | optimized | shared chunked playback | 19150.3 | 156058.6 | 173658.0 | 4 | too slow |
| WSL | `qwen3` | optimized | shared chunked playback | 19907.3 | 166020.4 | 184378.3 | 4 | too slow |

## Engine Notes

- `LuxTTS` remains in scope for future implementation, but the current user-sample evaluation is poor despite winning optimized TTFA rows. The listened optimized samples repeat reference/sample audio, sound metallic, run too fast, leak sample words or phrases, and fail speaker/accent match. Retest with better-padded reference audio and other speakers/accents before using it as a default.
- `XTTS` remains valuable for native streaming semantics. After chunking, WSL XTTS has the best optimized long-form stitched playback, but the listened WSL optimized long sample is metallic, hiccupy, and not a complete voice match. User prior testing says XTTS is strongly sample-sensitive.
- `F5` remains the safest incumbent already accepted by Phase 0, but the listened Windows optimized long sample is stretched/slow in parts, hiccupy, and degrades into mumbling/silence before recovering. The `1.5` duration/stretch setting is likely too aggressive; keep F5 but tune sample/transcription and speed/duration handling.
- `Chatterbox Turbo` baseline long-form is rejected as gibberish on both runtimes. Normal optimized long-form and seed-1337 optimized long-form are accepted on both runtimes, so the failure appears tied to the raw/baseline long-form path rather than the seed.
- `TADA 1B` is viable enough to keep: Windows optimized long sounded acceptable with some hiccups. WSL optimized long was worse, less steady, and morphed toward another voice, so WSL TADA needs a caution label and retest.
- `Qwen3 0.6B-Base` remains an experiment/play path only. It is far too slow in this matrix.
- TADA was not run with an explicit fixed seed in this harness. Only Chatterbox has a dedicated alternate-seed path. The Windows/WSL TADA difference can come from stochastic generation state, runtime differences, and WSL `model.compile`.

## Known Blockers

- Manual quality is partially scored, but enough to close the spike and move on.
- Numeric latency does not capture intelligibility, speaker similarity, accent, or prosody.
- LuxTTS should stay implemented but must carry the current user-sample caveat until better reference-audio handling or speaker/accent conditions change the quality result.
- Chatterbox Turbo baseline long-form is rejected; optimized long-form is accepted for the listened long samples, but short and medium quality are still unscored.
- The harness uses three fixed text scenarios, not a corpus of real RayMe LLM answers.
- The harness emits WAVs but does not yet collect structured human ratings automatically.
- No engine should be removed from future implementation because of this spike. The evaluations drive defaults, tuning, and caveats.

## Closure

This spike can close. Future implementation should keep every measured engine path available:

- `F5`: keep as incumbent/default candidate, but reduce or remove the long-form stretch/duration multiplier and require good sample/transcription handling.
- `XTTS`: keep as native-streaming fallback; retest with better references because it is sample-sensitive.
- `LuxTTS`: keep as fastest experimental candidate; retest with better-padded references and different speakers/accents before default use.
- `Chatterbox Turbo`: keep optimized chunked path; do not use baseline/raw long-form.
- `TADA 1B`: keep as experimental; Windows long sample passed, WSL long sample needs caution/retest.
- `Qwen3`: keep opt-in/play-only unless latency changes substantially.

Next product work should move on from the spike. The likely follow-up implementation task is to make TTS selection read `MANUAL-QUALITY.csv` or an equivalent quality policy so defaults can be metric-aware without dropping engine support.
