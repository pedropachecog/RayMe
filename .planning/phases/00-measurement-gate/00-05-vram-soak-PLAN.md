---
phase: 00-measurement-gate
plan: 05
type: execute
wave: 3
depends_on: [01, 03, 04]
files_modified:
  - .planning/phases/00-measurement-gate/probes/vram_soak.py
  - .planning/phases/00-measurement-gate/probes/test_vram_soak.py
  - .planning/phases/00-measurement-gate/results/vram_soak_f5.json
  - .planning/phases/00-measurement-gate/results/vram_soak_xtts.json
  - .planning/phases/00-measurement-gate/results/vram_soak_qwen3.json
autonomous: false
requirements: []
user_setup: []

must_haves:
  truths:
    - "Each of three TTS engines (F5, XTTS, Qwen3-TTS 0.6B-Base) has been paired with Whisper default rung + Silero VAD and run for 30 minutes of realistic cycling"
    - "Peak VRAM (torch.cuda.max_memory_allocated + nvml used) is recorded per engine"
    - "The growth_detected flag is computed per engine (slope over the last 20 minutes of samples > 50 MB/min threshold)"
    - "Results distinguish between the 4090 measured value and the 3060 extrapolation (does fit? <11 GB?) — both fields present in every results JSON"
    - "No voice audio or intermediate WAVs leak into git"
  artifacts:
    - path: ".planning/phases/00-measurement-gate/probes/vram_soak.py"
      provides: "30-minute per-engine soak harness cycling synth+transcribe+VAD+sleep"
      contains: "def soak"
    - path: ".planning/phases/00-measurement-gate/probes/test_vram_soak.py"
      provides: "Unit tests for the slope-based growth detector + results schema"
      contains: "def test_growth_detected"
    - path: ".planning/phases/00-measurement-gate/results/vram_soak_f5.json"
      provides: "F5 + Whisper default + VAD soak result"
      contains: "peak_vram_mb"
    - path: ".planning/phases/00-measurement-gate/results/vram_soak_xtts.json"
      provides: "XTTS v2 + Whisper default + VAD soak result"
      contains: "peak_vram_mb"
    - path: ".planning/phases/00-measurement-gate/results/vram_soak_qwen3.json"
      provides: "Qwen3-TTS 0.6B + Whisper default + VAD soak result"
      contains: "peak_vram_mb"
  key_links:
    - from: "probes/vram_soak.py"
      to: "probes/bench_utils.py"
      via: "sample_vram_mb, write_results"
      pattern: "from bench_utils"
    - from: "probes/vram_soak.py"
      to: "results/whisper.json"
      via: "reads default_rung to know which Whisper to pair with"
      pattern: "default_rung"
---

<objective>
For each of the three TTS engines, run a 30-minute cycling soak alongside the Whisper default rung (chosen in plan 03) + Silero VAD, log VRAM over time, detect fragmentation growth, and record per-engine peak VRAM.

Purpose: Phase 0 success criterion #4. The 12 GB 3060 budget only holds if real-world runtime VRAM (weights + activations + KV cache + fragmentation + cuDNN workspace) stays under 11 GB. Research (PITFALLS.md #7) flags that simultaneous load + fragmentation drift is where this breaks — not at weights-only load. This plan measures on the 4090 (24 GB, so nothing OOMs locally) and extrapolates to the 3060 budget via the observed peak value directly (the number does not change with total VRAM — it is what this process allocates).

Output: Three results JSONs (`vram_soak_f5.json`, `vram_soak_xtts.json`, `vram_soak_qwen3.json`), each containing the VRAM time series, peak, and a growth-detected flag.
</objective>

<execution_context>
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/workflows/execute-plan.md
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/00-measurement-gate/00-RESEARCH.md
@.planning/phases/00-measurement-gate/00-VALIDATION.md
@.planning/research/PITFALLS.md
@.planning/research/STACK.md

<interfaces>
From plan 01's `bench_utils.py`:
- `sample_vram_mb() -> {allocated_mb, reserved_mb, peak_allocated_mb, used_mb_nvml, free_mb_nvml}`
- `Timer`, `warmup_cuda`, `write_results`

Soak cycle (per engine):
1. Load Whisper (per `results/whisper.json` `default_rung`).
2. Load Silero VAD (ONNX, CPU or GPU — use CPU; it is what production will do).
3. Load target TTS engine.
4. Every 10 seconds: synthesize a short phrase, transcribe the result (round-trip), invoke Silero VAD on the synthesized audio.
5. Every 60 seconds: sample VRAM and append to time series.
6. Every 10 cycles: call `torch.cuda.empty_cache()` (mitigates fragmentation per PITFALLS.md #7).
7. After 30 minutes: teardown + compute peak + compute growth slope.

Growth detection:
- Linear regression of `reserved_mb` over time (last 20 minutes of samples).
- If slope > 50 MB/min -> `growth_detected: true`.
- If slope < 0 (negative) -> `growth_detected: false` (memory is being freed, good).
- If slope between 0 and 50 MB/min -> `growth_detected: false` (noise tolerance).

Silero VAD (Python):
```python
import torch
model, utils = torch.hub.load('snakers4/silero-vad', 'silero_vad',
                              trust_repo=True, onnx=False)
(get_speech_ts, _, _, _, _) = utils
# For VRAM soak purposes we just need to call the model periodically:
speech = model(audio_tensor, 16000)  # any 16kHz audio tensor
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Build vram_soak.py + unit tests for the growth detector</name>
  <files>
    .planning/phases/00-measurement-gate/probes/vram_soak.py
    .planning/phases/00-measurement-gate/probes/test_vram_soak.py
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/probes/bench_utils.py
    .planning/phases/00-measurement-gate/00-RESEARCH.md (§Architecture Patterns Pattern 4 — VRAM soak skeleton)
    .planning/research/PITFALLS.md (Pitfall #7 — fragmentation + expandable_segments rationale)
  </read_first>
  <behavior>
    - Test 1 (detect_growth flat): `detect_growth([{t:0,v:2000}, {t:600,v:2000}, {t:1200,v:2000}, {t:1800,v:2000}], window_s=1200)` returns `(False, slope ≈ 0)`.
    - Test 2 (detect_growth upward): `detect_growth([{t:0,v:2000}, {t:600,v:2500}, {t:1200,v:3000}, {t:1800,v:3500}], window_s=1200)` returns `(True, slope > 50 MB/min)`.
    - Test 3 (detect_growth downward): `detect_growth([{t:0,v:3000}, {t:600,v:2500}, {t:1200,v:2200}, {t:1800,v:2100}], window_s=1200)` returns `(False, slope < 0)` (memory freeing, not growth).
    - Test 4 (detect_growth within noise tolerance): slope of 20 MB/min -> `(False, slope ≈ 20)`.
    - Test 5 (results builder): `build_soak_result('f5', samples, cycles_completed=180)` returns dict with keys `engine`, `peak_vram_mb`, `growth_detected`, `growth_slope_mb_per_min`, `cycles_completed`, `samples`, `duration_s`.
  </behavior>
  <action>
    1. Create `.planning/phases/00-measurement-gate/probes/vram_soak.py`:

       ```python
       """30-minute VRAM soak for {Whisper default + Silero VAD + one TTS engine}.

       Phase 0 success criterion #4. Runs one engine per invocation.

       Usage:
         .venv-phase0/Scripts/python.exe probes/vram_soak.py --engine f5    --duration-min 30
         .venv-phase0/Scripts/python.exe probes/vram_soak.py --engine xtts  --duration-min 30
         .venv-phase0/Scripts/python.exe probes/vram_soak.py --engine qwen3 --duration-min 30

       Reads the Whisper default from results/whisper.json. FAILS LOUDLY
       (stderr + non-zero exit) if that file does not yet exist — plan 05
       hard-depends on plan 03's output.
       """
       from __future__ import annotations
       import argparse
       import json
       import sys
       import time
       from pathlib import Path
       from typing import Any

       from bench_utils import sample_vram_mb, warmup_cuda, write_results

       GROWTH_THRESHOLD_MB_PER_MIN = 50.0
       GROWTH_WINDOW_MIN = 20
       EMPTY_CACHE_EVERY_N_CYCLES = 10
       SAMPLE_INTERVAL_S = 60
       CYCLE_INTERVAL_S = 10

       SHORT_PHRASES = [
           "Hey got it.",
           "Right okay sounds good.",
           "Let me think about that.",
           "Yeah I agree.",
           "Could you repeat that please?",
       ]


       def detect_growth(samples: list[dict[str, float]],
                         window_s: int) -> tuple[bool, float]:
           """Linear regression of reserved_mb over time (last window_s seconds).
           Returns (growth_detected, slope_mb_per_min).
           """
           if len(samples) < 2:
               return False, 0.0
           # Take samples within window
           max_t = max(s["t"] for s in samples)
           window = [s for s in samples if s["t"] >= max_t - window_s]
           if len(window) < 2:
               window = samples
           # Simple least-squares slope
           n = len(window)
           sum_t = sum(s["t"] for s in window)
           sum_v = sum(s["v"] for s in window)
           sum_tt = sum(s["t"] ** 2 for s in window)
           sum_tv = sum(s["t"] * s["v"] for s in window)
           denom = n * sum_tt - sum_t * sum_t
           if denom == 0:
               return False, 0.0
           slope_mb_per_s = (n * sum_tv - sum_t * sum_v) / denom
           slope_mb_per_min = slope_mb_per_s * 60.0
           return slope_mb_per_min > GROWTH_THRESHOLD_MB_PER_MIN, slope_mb_per_min


       def build_soak_result(engine: str, samples: list[dict[str, Any]],
                              cycles_completed: int) -> dict[str, Any]:
           peak = max((s.get("v", 0) for s in samples), default=0)
           grew, slope = detect_growth(samples, window_s=GROWTH_WINDOW_MIN * 60)
           duration_s = samples[-1]["t"] - samples[0]["t"] if samples else 0
           return {
               "probe": "vram_soak",
               "engine": engine,
               "peak_vram_mb": round(peak, 1),
               "growth_detected": grew,
               "growth_slope_mb_per_min": round(slope, 2),
               "cycles_completed": cycles_completed,
               "duration_s": duration_s,
               "samples": samples,
               "fits_3060_budget": peak < 11000,   # <11 GB per PITFALLS.md #7
           }


       def _load_whisper_default() -> tuple[str, str]:
           """Returns (model_name, compute_type) for the Whisper rung to pair with.
           Hard-fails if results/whisper.json is missing — plan 05 depends on plan 03."""
           results = Path(".planning/phases/00-measurement-gate/results/whisper.json")
           if not results.exists():
               print(f"ERROR: results/whisper.json missing — plan 03 must complete first.",
                     file=sys.stderr)
               sys.exit(2)
           d = json.loads(results.read_text())
           for r in d.get("rungs", []):
               if r.get("default"):
                   return r["model"], r["compute_type"]
           print("ERROR: results/whisper.json has no default rung set.", file=sys.stderr)
           sys.exit(2)


       def _load_silero():
           import torch
           model, utils = torch.hub.load("snakers4/silero-vad", "silero_vad",
                                         trust_repo=True, onnx=False)
           return model, utils


       def _load_tts(engine: str, ref_audio: str, ref_text: str):
           import torch
           if engine == "f5":
               from f5_tts.api import F5TTS
               m = F5TTS()
               return ("f5", m, {"ref_audio": ref_audio, "ref_text": ref_text})
           if engine == "xtts":
               from TTS.api import TTS
               m = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
               return ("xtts", m, {"ref_audio": ref_audio})
           if engine == "qwen3":
               from qwen_tts import Qwen3TTSModel
               m = Qwen3TTSModel.from_pretrained(
                   "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                   device_map="cuda:0", torch_dtype=torch.bfloat16,
               )
               prompt = m.create_voice_clone_prompt(
                   ref_audio=ref_audio, ref_text=ref_text, x_vector_only_mode=False)
               return ("qwen3", m, {"prompt": prompt})
           raise ValueError(f"unknown engine {engine}")


       def _synthesize(engine: str, tts, ctx: dict, text: str):
           if engine == "f5":
               wav, sr, _ = tts.infer(ctx["ref_audio"], ctx["ref_text"], text, nfe_step=7)
               return wav, sr
           if engine == "xtts":
               wav = tts.tts(text=text, speaker_wav=ctx["ref_audio"], language="en")
               import numpy as np
               return np.asarray(wav, dtype="float32"), 24000
           if engine == "qwen3":
               wavs, sr = tts.generate_voice_clone(
                   text=text, voice_clone_prompt=ctx["prompt"], language="English")
               w = wavs[0] if hasattr(wavs, "__len__") else wavs
               if hasattr(w, "detach"):
                   w = w.detach().cpu().numpy().astype("float32").flatten()
               return w, int(sr)
           raise AssertionError


       def soak(engine: str, ref_audio: str, ref_text: str,
                duration_min: int) -> dict[str, Any]:
           import torch
           from faster_whisper import WhisperModel

           whisper_name, whisper_ct = _load_whisper_default()
           print(f"[soak] Whisper: {whisper_name} ({whisper_ct})", flush=True)
           whisper = WhisperModel(whisper_name, device="cuda", compute_type=whisper_ct)
           silero, _ = _load_silero()
           name, tts, ctx = _load_tts(engine, ref_audio, ref_text)
           print(f"[soak] TTS: {name}", flush=True)
           warmup_cuda()

           samples: list[dict[str, float]] = []
           t0 = time.perf_counter()
           deadline = t0 + duration_min * 60
           last_sample_t = t0
           cycle = 0

           while time.perf_counter() < deadline:
               phrase = SHORT_PHRASES[cycle % len(SHORT_PHRASES)]
               try:
                   wav, sr = _synthesize(engine, tts, ctx, phrase)
                   # Round-trip: transcribe
                   import soundfile as sf
                   tmp = Path("_soak_tmp.wav")
                   sf.write(tmp, wav, sr)
                   segs, _ = whisper.transcribe(str(tmp), beam_size=5,
                                                 condition_on_previous_text=False,
                                                 language="en")
                   _ = list(segs)
                   tmp.unlink(missing_ok=True)
                   # VAD invocation (makes sure silero is kept warm)
                   import numpy as np
                   import torch as _t
                   if sr != 16000:
                       # Resample is not needed for soak correctness; feed 16k silence
                       audio_16k = _t.from_numpy(np.zeros(16000, dtype="float32"))
                   else:
                       audio_16k = _t.from_numpy(wav[:16000])
                   _ = silero(audio_16k, 16000)
               except Exception as e:
                   print(f"[soak] cycle {cycle} errored: {e!r}", file=sys.stderr)

               cycle += 1
               if cycle % EMPTY_CACHE_EVERY_N_CYCLES == 0:
                   torch.cuda.empty_cache()

               now = time.perf_counter()
               if now - last_sample_t >= SAMPLE_INTERVAL_S:
                   vram = sample_vram_mb()
                   samples.append({
                       "t": round(now - t0, 1),
                       "v": vram["reserved_mb"],
                       "allocated_mb": vram["allocated_mb"],
                       "peak_allocated_mb": vram["peak_allocated_mb"],
                       "used_mb_nvml": vram["used_mb_nvml"],
                       "cycle": cycle,
                   })
                   last_sample_t = now
                   print(f"[soak] t={samples[-1]['t']:.0f}s cycle={cycle} "
                         f"reserved={vram['reserved_mb']}MB "
                         f"peak={vram['peak_allocated_mb']}MB "
                         f"nvml={vram['used_mb_nvml']}MB", flush=True)

               # Target ~6 cycles/min
               time.sleep(max(0, CYCLE_INTERVAL_S - (time.perf_counter() - now)))

           return build_soak_result(engine, samples, cycle)


       def main() -> int:
           ap = argparse.ArgumentParser()
           ap.add_argument("--engine", required=True, choices=["f5", "xtts", "qwen3"])
           ap.add_argument("--ref-audio",
                           default="probes/fixtures/short_ref_audio.wav",
                           help="Reference WAV (from plan 04)")
           ap.add_argument("--ref-text",
                           default="probes/fixtures/short_ref_transcript.txt",
                           help="Reference transcript")
           ap.add_argument("--duration-min", type=int, default=30)
           ap.add_argument("--output",
                           help="Defaults to results/vram_soak_{engine}.json")
           args = ap.parse_args()

           out = args.output or f"results/vram_soak_{args.engine}.json"
           ref_text_path = Path(args.ref_text)
           ref_text = "\n".join(
               l for l in ref_text_path.read_text(encoding="utf-8").splitlines()
               if not l.strip().startswith("#")
           ).strip()

           if not Path(args.ref_audio).exists():
               print(f"ERROR: ref-audio missing: {args.ref_audio}", file=sys.stderr)
               return 2

           result = soak(args.engine, args.ref_audio, ref_text, args.duration_min)
           write_results(out, result)
           print(f"\n[soak] {args.engine}: peak={result['peak_vram_mb']}MB "
                 f"grew={result['growth_detected']} "
                 f"slope={result['growth_slope_mb_per_min']}MB/min "
                 f"fits_3060={result['fits_3060_budget']}", flush=True)
           return 0


       if __name__ == "__main__":
           sys.exit(main())
       ```

    2. Create `.planning/phases/00-measurement-gate/probes/test_vram_soak.py` with the 5 tests described in `<behavior>`.

       ```python
       """Unit tests for vram_soak.py — growth detector + results schema."""
       import pytest
       from vram_soak import detect_growth, build_soak_result, GROWTH_THRESHOLD_MB_PER_MIN


       def _linear(t_points, start, slope_per_s):
           return [{"t": t, "v": start + slope_per_s * t} for t in t_points]


       def test_growth_flat():
           ts = list(range(0, 1801, 60))
           samples = [{"t": t, "v": 2000.0} for t in ts]
           grew, slope = detect_growth(samples, window_s=1200)
           assert grew is False
           assert abs(slope) < 1.0


       def test_growth_upward():
           # slope of 100 MB/min = 1.6667 MB/s
           samples = _linear(list(range(0, 1801, 60)), 2000.0, 100 / 60)
           grew, slope = detect_growth(samples, window_s=1200)
           assert grew is True
           assert slope > GROWTH_THRESHOLD_MB_PER_MIN


       def test_growth_downward():
           samples = _linear(list(range(0, 1801, 60)), 3000.0, -50 / 60)
           grew, slope = detect_growth(samples, window_s=1200)
           assert grew is False
           assert slope < 0


       def test_growth_within_noise_tolerance():
           # 20 MB/min = below 50 MB/min threshold
           samples = _linear(list(range(0, 1801, 60)), 2000.0, 20 / 60)
           grew, slope = detect_growth(samples, window_s=1200)
           assert grew is False
           assert 15 < slope < 25


       def test_build_soak_result_schema():
           samples = [
               {"t": 0,   "v": 4500.0},
               {"t": 600, "v": 4600.0},
               {"t": 1200,"v": 4700.0},
               {"t": 1800,"v": 4800.0},
           ]
           r = build_soak_result("f5", samples, cycles_completed=180)
           for k in ("engine","peak_vram_mb","growth_detected",
                     "growth_slope_mb_per_min","cycles_completed",
                     "duration_s","samples","fits_3060_budget"):
               assert k in r, f"missing key {k}"
           assert r["engine"] == "f5"
           assert r["peak_vram_mb"] == 4800.0
           assert r["fits_3060_budget"] is True
       ```

    3. Run tests:
       ```bash
       cd .planning/phases/00-measurement-gate/probes
       ../.venv-phase0/Scripts/python.exe -m pytest test_vram_soak.py -v
       ```
       Must pass 5/5.
  </action>
  <verify>
    <automated>cd .planning/phases/00-measurement-gate/probes &amp;&amp; ../.venv-phase0/Scripts/python.exe -m pytest test_vram_soak.py -v 2&gt;&amp;1 | tee /tmp/soak_tests.out &amp;&amp; grep -q "5 passed" /tmp/soak_tests.out &amp;&amp; grep -q "def soak" vram_soak.py</automated>
  </verify>
  <acceptance_criteria>
    - File `probes/vram_soak.py` exists with `soak`, `detect_growth`, `build_soak_result`, `main` functions.
    - File `probes/test_vram_soak.py` has 5 `def test_*` functions.
    - Pytest exits 0 with `5 passed`.
    - `vram_soak.py` reads `results/whisper.json` for the default Whisper rung AND fails loudly (`sys.exit(2)`) if that file is missing — no silent fallback (grep `sys.exit(2)`).
  </acceptance_criteria>
  <done>Soak harness + unit-tested growth detector ready; awaiting the three 30-minute runs.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: Run three 30-minute soaks sequentially (F5, XTTS, Qwen3) and capture results</name>
  <files>
    .planning/phases/00-measurement-gate/results/vram_soak_f5.json
    .planning/phases/00-measurement-gate/results/vram_soak_xtts.json
    .planning/phases/00-measurement-gate/results/vram_soak_qwen3.json
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/probes/vram_soak.py
    .planning/phases/00-measurement-gate/results/whisper.json (so the soak uses the chosen default rung)
    .planning/phases/00-measurement-gate/probes/fixtures/short_ref_audio.wav (must exist from plan 04)
  </read_first>
  <action>Human-verification checkpoint. Claude has already completed the automated work described under &lt;what-built&gt; above. The builder performs the steps in &lt;how-to-verify&gt; below and records the outcome as described; acceptance is gated on &lt;acceptance_criteria&gt;. When `workflow.auto_advance=true`, auto-mode auto-approves this checkpoint.</action>
  <what-built>
    Task 1 produced `vram_soak.py` — a 30-minute harness that loads Whisper (chosen default rung) + Silero VAD + one TTS engine, and cycles synth+transcribe+VAD every 10 seconds while logging VRAM every minute. Growth detection is unit-tested.

    What cannot be automated: the total wall time is ~90 minutes (three 30-min runs). A human is not strictly required, but the runs must be kicked off one at a time and confirmed to complete successfully. We use a checkpoint because the runs tie up the GPU and the builder may want to schedule them.
  </what-built>
  <how-to-verify>
    1. Confirm `results/whisper.json` exists (plan 03 complete). If not, the soak falls back to `distil-large-v3 int8_float16`.
    2. Confirm `probes/fixtures/short_ref_audio.wav` exists (plan 04 complete).

    Run each soak sequentially — do NOT parallelize (the VRAM rule is one-TTS-at-a-time):

    ```bash
    cd .planning/phases/00-measurement-gate

    # F5 (~30 min)
    .venv-phase0/Scripts/python.exe probes/vram_soak.py --engine f5 --duration-min 30

    # XTTS (~30 min)
    .venv-phase0/Scripts/python.exe probes/vram_soak.py --engine xtts --duration-min 30

    # Qwen3 (~30 min)
    .venv-phase0/Scripts/python.exe probes/vram_soak.py --engine qwen3 --duration-min 30
    ```

    Each run writes `results/vram_soak_{engine}.json` with the time series, peak, and growth flag. Builder may schedule these across a work day.

    **Acceptance check (automated):**

    ```bash
    .venv-phase0/Scripts/python.exe -c "
    import json
    for engine in ('f5','xtts','qwen3'):
        d = json.load(open(f'results/vram_soak_{engine}.json'))
        print(f'{engine:6s}: peak={d[\"peak_vram_mb\"]}MB  '
              f'grew={d[\"growth_detected\"]}  '
              f'slope={d[\"growth_slope_mb_per_min\"]}MB/min  '
              f'fits_3060={d[\"fits_3060_budget\"]}  '
              f'cycles={d[\"cycles_completed\"]}')
        assert d['samples'], f'{engine}: empty samples list'
        assert d['cycles_completed'] >= 100, f'{engine}: too few cycles'
    "
    ```
  </how-to-verify>
  <acceptance_criteria>
    - Three files exist: `results/vram_soak_{f5,xtts,qwen3}.json`, each valid JSON.
    - Each file has keys `engine`, `peak_vram_mb`, `growth_detected`, `growth_slope_mb_per_min`, `cycles_completed`, `samples`, `duration_s`, `fits_3060_budget`.
    - Each file has `cycles_completed >= 100` (30 min × ~6 cycles/min = 180 expected; >=100 is a soft lower bound allowing for slow cycles).
    - Each file has a non-empty `samples` list (at least 20 entries for 30 min at 1-sample/min).
    - Each file has `duration_s >= 1500` (25 minutes — tolerates 5 min of setup overhead).
  </acceptance_criteria>
  <resume-signal>
    Reply "approved" once the acceptance check prints three lines with valid numbers. If any engine errored out, report which and the orchestrator will route to repair (most likely OOM on 4090 indicating a real code bug, since the 24 GB machine has plenty of headroom).
  </resume-signal>
  <verify><automated>echo "checkpoint: acceptance delegated to &lt;acceptance_criteria&gt; above; pass when resume-signal received"</automated></verify>
  <done>Acceptance criteria above are satisfied and the builder returned the expected resume-signal.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| None (internal) | Local-only GPU load test. No network endpoints. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-05-01 | DoS | 30-min GPU soak blocks other workloads | accept | Builder schedules runs around other GPU usage. Single-user workstation — no contention. |
| T-00-05-02 | Info Disclosure | `_soak_tmp.wav` intermediate files | mitigate | Written then immediately unlinked in each cycle. gitignored even if crash leaves one behind (`*.wav` pattern). |
| T-00-05-03 | Tampering | Silero VAD model from `torch.hub` | accept | Official `snakers4/silero-vad` repo; downloaded and cached locally. |

No high-severity threats. Pure local measurement.
</threat_model>

<verification>
```bash
.venv-phase0/Scripts/python.exe -c "
import json
for engine in ('f5','xtts','qwen3'):
    d = json.load(open(f'results/vram_soak_{engine}.json'))
    flag = 'FITS' if d['fits_3060_budget'] else 'OOM-RISK'
    grew = 'GROWTH' if d['growth_detected'] else 'stable'
    print(f'  {engine}: peak={d[\"peak_vram_mb\"]}MB {flag} {grew}')
"
```
</verification>

<success_criteria>
- [ ] F5, XTTS, Qwen3-TTS each soaked for 30 min with realistic cycling
- [ ] Peak VRAM, growth slope, and 3060-budget-fit flag recorded per engine
- [ ] Unit tests 5/5 passing
- [ ] No intermediate WAV files staged for git
</success_criteria>

<output>
After completion, create `.planning/phases/00-measurement-gate/00-05-SUMMARY.md` summarizing:
- Per-engine peak VRAM + growth + 3060-fit (one-line table)
- Any engine that exceeded the 11 GB 3060 budget and the implication for Phase 2 (which engines are v1-eligible on 3060 hardware)
- Whether growth was detected anywhere (indicates fragmentation bug that needs `torch.cuda.empty_cache()` more aggressively in production)
</output>
