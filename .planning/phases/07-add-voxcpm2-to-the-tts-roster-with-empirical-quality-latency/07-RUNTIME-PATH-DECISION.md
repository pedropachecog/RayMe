# Phase 07 VoxCPM2 Runtime Path Decision

Date: 2026-05-11

## Constraint Summary

RayMe keeps one public AI backend API for Web UI and browser callers. VoxCPM2 runtime details must remain behind the existing AI backend model manager, engine registry, and `/tts/synthesize` route. CPU fallback is not acceptable for production TTS runtime; the chosen path must force CUDA and preserve one-hot TTS residency on the RTX 3060 target.

## Runtime Path Evaluation

| Candidate | Evidence source | RTX 3060 / Windows feasibility | Call TTFA implications | Operational cost | One-public-API preservation | Disposition | Evidence gate required to revisit |
|---|---|---|---|---|---|---|---|
| `standard_python_generate` | Phase 07 research, VoxCPM API docs, existing import-gated F5 adapter pattern | Feasible first path: official `voxcpm==2.0.2` Python API can run in the AI backend process with `VoxCPM.from_pretrained("openbmb/VoxCPM2", device="cuda")`; OMEN evidence still required before promotion | Whole-result synthesis may not improve first audio by itself, but it fits the current transient synthesis and call enqueue contract without changing browser behavior | Low: one optional dependency, one adapter, existing temp-file and `soundfile` patterns | Preserves one public AI backend API through the current registry and synthesis routes | selected | Revisit only if OMEN install/load, 48 kHz synthesis, VRAM, or call-flow smoke fails in the standard runtime |
| `standard_python_generate_streaming` | Phase 07 research and VoxCPM `generate_streaming` API docs | Plausible on the same package/runtime, but RayMe needs a chunk-consumption path that can enqueue partial audio without breaking existing call/session contracts | Could improve first generated chunk latency, but RayMe currently returns complete WAV bytes from generic adapters, so TTFA gain must be measured in a call-path implementation | Medium: requires streaming adapter contract changes and call playback evidence | Can preserve one public API if streaming stays internal to the AI backend | benchmark_only | Revisit after baseline standard runtime works and a call-path benchmark proves lower warm TTFA without interrupt regressions |
| `nanovllm_voxcpm` | Phase 07 research and NanoVLLM-VoxCPM deployment docs | CUDA-centric serving path; likely better aligned with Linux/GPU serving than current OMEN Windows in-process runtime | May improve scheduling and streaming latency, but evidence is not RayMe call-path evidence yet | High: extra serving stack, local checkpoint layout, Triton/FlashAttention-style dependencies, more deployment surface | Can preserve one public API only if wrapped behind the AI backend as an internal service | ruled_out_for_initial_path | Revisit only after standard runtime evidence shows a concrete latency or feasibility blocker that NanoVLLM is expected to solve |
| `vllm_omni_serving` | Phase 07 research and vLLM-Omni-style serving docs | Server-backed path adds another rapidly moving GPU serving layer and is not the simplest fit for the OMEN Windows target | Could help concurrent serving, but RayMe is single-user and needs measured call-feel wins before extra infrastructure | High: separate service lifecycle, dependency churn, OpenAI-style speech API mapping, more ops evidence | Can preserve one public API only through an AI backend proxy layer | ruled_out_for_initial_path | Revisit only if RayMe later needs batching/concurrency or the in-process runtime cannot meet RTX 3060 call-flow goals |

## Chosen Initial Path

Use the standard Python `generate` path through an import-gated `VoxCpm2TtsAdapter`. This keeps the runtime inside the existing AI backend boundary, pins the optional package, forces `device="cuda"`, and gives Phase 07 a baseline for install, sample-rate, latency, VRAM, quality, and call-flow evidence before considering a streaming or serving variant.

## Implementation Notes

- Package: `voxcpm==2.0.2`, under the AI backend optional `tts` extra only.
- Model id: `openbmb/VoxCPM2`.
- Output sample rate: use the runtime-reported value, expected to include 48 kHz.
- Public API: keep `/tts/synthesize` and later call routes as RayMe-owned surfaces; do not expose NanoVLLM, vLLM-Omni, cache paths, or model internals to browser callers.
- Revisit gate: Phase 07 OMEN and scenario evidence must record package version, model id, CUDA runtime, sample rate, VRAM, TTFA/RTF, generated samples, and sanitized failures.
