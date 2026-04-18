---
phase: 00-measurement-gate
plan: 04
type: execute
wave: 2
depends_on: [01]
files_modified:
  - .planning/phases/00-measurement-gate/probes/tts_ttfa.py
  - .planning/phases/00-measurement-gate/probes/fixtures/short_ref_transcript.txt
  - .planning/phases/00-measurement-gate/probes/test_tts_ttfa.py
  - .planning/phases/00-measurement-gate/results/tts_ttfa.json
autonomous: false
requirements: []
user_setup:
  - service: short-reference-audio
    why: "TTS voice cloning requires a short reference audio (6-15s) of the builder's voice. Only the builder can produce this."
    env_vars: []
    dashboard_config:
      - task: "Record a 6-12 second clean voice sample reading probes/fixtures/short_ref_transcript.txt. Save as probes/fixtures/short_ref_audio.wav (mono, ≥24 kHz)."
        location: "Any audio recorder. File is gitignored per plan 01."

must_haves:
  truths:
    - "Three TTS engines (F5-TTS 7-step Sway, XTTS v2 first-chunk streaming, Qwen3-TTS 0.6B-Base) have been benchmarked for TTFA"
    - "TTFA is measured as: wall time from synthesis call entry -> first audio sample available in the output stream"
    - "RTF (real-time factor) is measured alongside TTFA for each engine"
    - "Exactly ONE engine is marked v1_default:true in results/tts_ttfa.json, chosen per Resolved Tension #3 rule"
    - "Qwen3-TTS acceptance gate disposition (accept/reject for v1) is explicitly set in the JSON with a reason field"
    - "Voice reference audio is NOT committed to git"
  artifacts:
    - path: ".planning/phases/00-measurement-gate/probes/tts_ttfa.py"
      provides: "TTFA + RTF measurement rig for F5-TTS, XTTS v2, Qwen3-TTS 0.6B-Base"
      contains: "measure_f5"
    - path: ".planning/phases/00-measurement-gate/probes/fixtures/short_ref_transcript.txt"
      provides: "~15-word reference transcript for the short voice sample"
      contains: "resent you"
    - path: ".planning/phases/00-measurement-gate/probes/test_tts_ttfa.py"
      provides: "Unit tests for TTFA/RTF computation + default-picker + Qwen gate logic"
      contains: "def test_pick_v1_default_f5_wins_when_under_400ms"
    - path: ".planning/phases/00-measurement-gate/results/tts_ttfa.json"
      provides: "Phase 0 criterion #3 deliverable — per-engine TTFA, RTF, v1 default, Qwen3-TTS acceptance verdict"
      contains: "v1_default"
  key_links:
    - from: ".planning/phases/00-measurement-gate/probes/tts_ttfa.py"
      to: ".planning/phases/00-measurement-gate/probes/bench_utils.py"
      via: "Timer, warmup_cuda, write_results, sample_vram_mb"
      pattern: "from bench_utils import"
    - from: ".planning/phases/00-measurement-gate/probes/tts_ttfa.py"
      to: "f5_tts, TTS (coqui), qwen_tts"
      via: "direct imports guarded by try/except so one missing engine does not abort the other two"
      pattern: "import f5_tts|from TTS|from qwen_tts"
---

<objective>
Empirically measure Time-To-First-Audio and Real-Time Factor for the three candidate TTS engines on the builder's voice, and apply Resolved Tension #3 logic to pick the v1 default engine.

Purpose: Phase 0 success criterion #3. Research could not find a 3060 TTFA number for any of these engines on this voice, so Phase 2 cannot freeze a TTS default without data. The decision logic is:
1. If F5-TTS TTFA ≤400 ms AND RTF <1 AND clone quality is acceptable -> F5 is v1 default.
2. Else if XTTS v2 first-chunk TTFA ≤400 ms -> XTTS is v1 default.
3. Else if Qwen3-TTS 0.6B-Base TTFA ≤400 ms AND RTF <1 AND subjective accent preservation is acceptable -> Qwen3-TTS becomes v1 default AND the Qwen3-TTS acceptance gate (QWEN3-TTS.md §7) flips to ACCEPT.
4. Else Qwen3-TTS is feature-flagged off for v1 (gate REJECT); F5 or XTTS wins based on measured TTFA.

Output: `probes/tts_ttfa.py` (rig), `results/tts_ttfa.json` (measurements + v1_default + qwen_gate disposition), and WAV output samples the builder can listen to (in `probes/fixtures/tts_samples/`, gitignored).
</objective>

<execution_context>
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/workflows/execute-plan.md
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/00-measurement-gate/00-RESEARCH.md
@.planning/phases/00-measurement-gate/00-VALIDATION.md
@.planning/research/STACK.md
@.planning/research/PITFALLS.md
@.planning/research/QWEN3-TTS.md

<interfaces>
API contracts the plan uses (from 00-RESEARCH.md §Code Examples Pattern 2 — already verified against upstream docs):

**F5-TTS 1.1.17:**
```python
from f5_tts.api import F5TTS
model = F5TTS()  # loads the base v1 model to CUDA by default
wav, sr, _ = model.infer(ref_audio_path, ref_text, target_text, nfe_step=7)
# wav is numpy float32; sr typically 24000
```
Note: F5 generates the whole utterance (no native streaming). TTFA == full synthesis time for the target sentence. Research §Common Pitfall §anti-patterns: "Always set nfe_step=7" for the fast Sway path.

**XTTS v2 via coqui-tts 0.27.5:**
```python
from TTS.api import TTS
model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
# Streaming inference (first-chunk = TTFA):
stream = model.tts_stream(
    text=target_text,
    speaker_wav=ref_audio_path,
    language="en",
)
# stream is an iterator yielding PCM chunks; first yield is the TTFA event
```
The 00-RESEARCH.md §Architecture Patterns Pattern 2 references `tts_with_vc_to_file_streaming` but that was an approximation. The actual coqui-tts 0.27.5 API for XTTS streaming is `TTS.tts_stream` (or the lower-level model's `inference_stream` for finer control). If `tts_stream` is absent on 0.27.5, fall through to `model.tts(...)` (non-streaming) and measure full utterance time — flag this in the results JSON as `fallback_to_non_streaming: true` so downstream analysis notes XTTS lost its streaming advantage.

**Qwen3-TTS 0.1.1:**
```python
import torch
from qwen_tts import Qwen3TTSModel
model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    device_map="cuda:0",
    dtype=torch.bfloat16,
    # attn_implementation="flash_attention_2",  # SKIP — FA2 is plan 07's concern.
    # If FA2 is not installed, eager attention is used automatically.
)
prompt = model.create_voice_clone_prompt(ref_audio=ref_audio_path, ref_text=ref_text)
# Non-streaming (simpler, measures RTF cleanly):
wavs, sr = model.generate_voice_clone(text=target_text, voice_clone_prompt=prompt)
# Streaming (if available):
# for chunk in model.stream_generate_voice_clone(text=target_text, voice_clone_prompt=prompt):
#     yield chunk  # PCM
```
QWEN3-TTS.md §4.1 confirms `stream_generate_voice_clone` exists. Use the non-streaming path for this plan and measure full synthesis time; if the non-streaming time already misses 400 ms, streaming would only help marginally. If non-streaming clears 400 ms, still use it for RTF (RTF is meaningful only over the full utterance).

**Acceptance rule for v1 default (Resolved Tension #3 + QWEN3-TTS.md §7):**
```
TTFA_TARGET_MS = 400
RTF_TARGET = 1.0

def pick_v1_default(engines: dict[str, dict]) -> str:
    # engines = {'f5': {...}, 'xtts': {...}, 'qwen3': {...}}
    f5 = engines.get('f5')
    xtts = engines.get('xtts')
    qwen = engines.get('qwen3')
    # Priority 1: F5 if it hits the target (keeps incumbent plan)
    if f5 and f5.get('ttfa_ms') is not None \
       and f5['ttfa_ms'] <= TTFA_TARGET_MS \
       and f5['rtf'] < RTF_TARGET:
        return 'f5'
    # Priority 2: XTTS (proven streaming on consumer GPUs)
    if xtts and xtts.get('ttfa_ms') is not None \
       and xtts['ttfa_ms'] <= TTFA_TARGET_MS \
       and xtts['rtf'] < RTF_TARGET:
        return 'xtts'
    # Priority 3: Qwen3-TTS (Apache-2.0 advantage, only wins when F5/XTTS missed)
    if qwen and qwen.get('ttfa_ms') is not None \
       and qwen['ttfa_ms'] <= TTFA_TARGET_MS \
       and qwen['rtf'] < RTF_TARGET:
        return 'qwen3'
    # No engine clears the budget: pick the best TTFA anyway and flag
    measured = {k: v for k, v in engines.items() if v.get('ttfa_ms') is not None}
    if not measured:
        return None
    return min(measured, key=lambda k: measured[k]['ttfa_ms'])
```

**Qwen3-TTS acceptance gate** (QWEN3-TTS.md §7) — set as a SEPARATE field in the JSON regardless of v1_default:
- `qwen_gate.accepted = true` iff TTFA <400 ms AND RTF <1 AND subjective accent test passes
- The subjective accent test is a human checkpoint below; the automated run records only the objective metrics, then the builder confirms.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Build tts_ttfa.py + short reference transcript + unit tests</name>
  <files>
    .planning/phases/00-measurement-gate/probes/tts_ttfa.py
    .planning/phases/00-measurement-gate/probes/fixtures/short_ref_transcript.txt
    .planning/phases/00-measurement-gate/probes/test_tts_ttfa.py
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/probes/bench_utils.py
    .planning/phases/00-measurement-gate/00-RESEARCH.md (§Architecture Patterns Pattern 2 — TTFA measurement for F5/XTTS/Qwen3; §Common Pitfalls §Anti-Patterns — warm model before timing, always nfe_step=7 for F5)
    .planning/research/QWEN3-TTS.md (§2.5 for Qwen voice-clone API; §7 for acceptance gate triggers)
    .planning/research/STACK.md (§VRAM Budget — confirms one TTS at a time)
    .planning/research/PITFALLS.md (Pitfall #4 — F5 latency; Pitfall #9 — ref transcript accuracy)
  </read_first>
  <behavior>
    - Test 1 (default picker, F5 wins): `pick_v1_default({'f5': {'ttfa_ms': 320, 'rtf': 0.08}, 'xtts': {'ttfa_ms': 180, 'rtf': 0.3}, 'qwen3': {'ttfa_ms': 600, 'rtf': 1.1}})` returns `'f5'` (first priority when it clears budget).
    - Test 2 (default picker, F5 fails -> XTTS wins): `pick_v1_default({'f5': {'ttfa_ms': 550, 'rtf': 0.15}, 'xtts': {'ttfa_ms': 180, 'rtf': 0.3}, 'qwen3': {'ttfa_ms': 600, 'rtf': 1.1}})` returns `'xtts'`.
    - Test 3 (default picker, F5+XTTS fail -> Qwen wins if within budget): `pick_v1_default({'f5': {'ttfa_ms': 550, 'rtf': 0.15}, 'xtts': {'ttfa_ms': 450, 'rtf': 0.4}, 'qwen3': {'ttfa_ms': 380, 'rtf': 0.9}})` returns `'qwen3'`.
    - Test 4 (default picker, all miss -> returns best TTFA): `pick_v1_default({'f5': {'ttfa_ms': 600}, 'xtts': {'ttfa_ms': 500}, 'qwen3': {'ttfa_ms': 700}})` returns `'xtts'`.
    - Test 5 (default picker, all engines errored): `pick_v1_default({'f5': {'ttfa_ms': None}, 'xtts': {'ttfa_ms': None}, 'qwen3': {'ttfa_ms': None}})` returns `None`.
    - Test 6 (qwen gate accepts on all conditions): `qwen_gate_disposition({'ttfa_ms': 380, 'rtf': 0.9}, accent_ok=True)` returns `{'accepted': True, 'reasons': ['ttfa_ok','rtf_ok','accent_ok']}`.
    - Test 7 (qwen gate rejects on TTFA): `qwen_gate_disposition({'ttfa_ms': 500, 'rtf': 0.9}, accent_ok=True)` returns `{'accepted': False, 'reasons': ['ttfa_too_high']}`.
    - Test 8 (qwen gate rejects when accent_ok=False): `qwen_gate_disposition({'ttfa_ms': 380, 'rtf': 0.9}, accent_ok=False)` returns `{'accepted': False, 'reasons': ['accent_drift_or_untested']}`.
    - Test 9 (rtf computation): `compute_rtf(audio_duration_s=5.0, synthesis_time_s=1.0)` returns 0.2.
  </behavior>
  <action>
    1. Create `.planning/phases/00-measurement-gate/probes/fixtures/short_ref_transcript.txt`:
       ```
       # RayMe Phase 0 - Short TTS reference transcript
       #
       # Read aloud cleanly in a quiet room. Aim for 6-12 seconds total.
       # Save recording as probes/fixtures/short_ref_audio.wav (mono, ≥24 kHz).
       # This is the reference clip all three TTS engines clone from.

       Okay. Yeah. I resent you. I love you. I respect you. But you know what? You blew it!
       ```
       (~15 words, lifted from the Qwen3-TTS README sample to keep the engine happy — it's the same text shape the upstream examples assume. Cadence is natural conversational English.)

    2. Create `.planning/phases/00-measurement-gate/probes/test_tts_ttfa.py` — the 9 unit tests described above. Import `pick_v1_default`, `qwen_gate_disposition`, `compute_rtf` from `tts_ttfa`.

    3. Create `.planning/phases/00-measurement-gate/probes/tts_ttfa.py`:

       ```python
       """TTS TTFA + RTF benchmark for Phase 0 success criterion #3.

       Measures three engines sequentially (one-TTS-at-a-time, VRAM rule):
         - F5-TTS with nfe_step=7 (Sway sampling)
         - XTTS v2 via coqui-tts (streaming; first-chunk = TTFA)
         - Qwen3-TTS 0.6B-Base (non-streaming; full-utterance time)

       Emits per-engine TTFA (ms), RTF, peak VRAM, plus chosen v1 default
       and Qwen3-TTS acceptance gate disposition.

       Each engine writes its synthesized WAV to fixtures/tts_samples/ so the
       builder can listen (especially for the Qwen accent test).

       Usage:
         .venv-phase0/Scripts/python.exe probes/tts_ttfa.py \
           --ref-audio probes/fixtures/short_ref_audio.wav \
           --ref-text  probes/fixtures/short_ref_transcript.txt \
           --target-text "Hey, got it." \
           --output results/tts_ttfa.json
       """
       from __future__ import annotations
       import argparse
       import json
       import sys
       import traceback
       from pathlib import Path
       from typing import Any

       from bench_utils import Timer, sample_vram_mb, warmup_cuda, write_results

       TTFA_TARGET_MS = 400
       RTF_TARGET = 1.0
       OUTPUT_SAMPLE_DIR = Path(".planning/phases/00-measurement-gate/probes/fixtures/tts_samples")


       def compute_rtf(audio_duration_s: float, synthesis_time_s: float) -> float:
           """RTF = synthesis_time / audio_duration. <1 means faster than real-time."""
           if audio_duration_s <= 0:
               return float("inf")
           return synthesis_time_s / audio_duration_s


       def pick_v1_default(engines: dict[str, dict[str, Any]]) -> str | None:
           """Resolved Tension #3 priority:
             1. F5 if ttfa <=400ms AND rtf <1
             2. XTTS if same
             3. Qwen3 if same
             4. Else best ttfa
             5. If all ttfa are None -> None
           """
           def ok(e):
               t = e.get("ttfa_ms")
               r = e.get("rtf")
               return t is not None and r is not None and t <= TTFA_TARGET_MS and r < RTF_TARGET

           for name in ("f5", "xtts", "qwen3"):
               e = engines.get(name)
               if e and ok(e):
                   return name
           measured = {k: v for k, v in engines.items() if v.get("ttfa_ms") is not None}
           if not measured:
               return None
           return min(measured, key=lambda k: measured[k]["ttfa_ms"])


       def qwen_gate_disposition(qwen_metrics: dict[str, Any], accent_ok: bool) -> dict[str, Any]:
           """QWEN3-TTS.md §7 acceptance gate."""
           reasons: list[str] = []
           ttfa = qwen_metrics.get("ttfa_ms")
           rtf = qwen_metrics.get("rtf")
           if ttfa is None or ttfa > TTFA_TARGET_MS:
               reasons.append("ttfa_too_high")
           else:
               reasons.append("ttfa_ok")
           if rtf is None or rtf >= RTF_TARGET:
               reasons.append("rtf_too_high")
           else:
               reasons.append("rtf_ok")
           if accent_ok:
               reasons.append("accent_ok")
           else:
               reasons.append("accent_drift_or_untested")
           accepted = ("ttfa_ok" in reasons and "rtf_ok" in reasons and "accent_ok" in reasons)
           return {"accepted": accepted, "reasons": reasons}


       # -------------------- Per-engine measurement --------------------

       def measure_f5(ref_audio: str, ref_text: str, target_text: str,
                      sample_out: Path) -> dict[str, Any]:
           import torch
           torch.cuda.empty_cache()
           torch.cuda.reset_peak_memory_stats()
           import soundfile as sf
           from f5_tts.api import F5TTS

           print("[tts] Loading F5-TTS...", flush=True)
           model = F5TTS()  # default v1 base model on CUDA
           warmup_cuda()
           # One dummy inference to JIT-compile CUDA kernels (avoid cold-load inflation)
           _ = model.infer(ref_audio, ref_text, "Warm.", nfe_step=7)
           torch.cuda.synchronize()

           with Timer() as t:
               wav, sr, _ = model.infer(ref_audio, ref_text, target_text, nfe_step=7)
               torch.cuda.synchronize()
           synth_s = t.elapsed_s
           # F5 returns the whole utterance; TTFA == full synth time.
           audio_dur = len(wav) / float(sr)
           sf.write(sample_out, wav, sr)
           peak_vram = sample_vram_mb()["peak_allocated_mb"]

           del model
           torch.cuda.empty_cache()

           return {
               "engine": "f5",
               "mode": "non_streaming",
               "ttfa_ms": round(synth_s * 1000, 1),
               "rtf": round(compute_rtf(audio_dur, synth_s), 3),
               "audio_duration_s": round(audio_dur, 3),
               "synthesis_time_s": round(synth_s, 3),
               "peak_vram_mb": round(peak_vram, 1),
               "sample_rate": int(sr),
               "output_wav": str(sample_out),
           }


       def measure_xtts(ref_audio: str, target_text: str,
                        sample_out: Path) -> dict[str, Any]:
           import torch
           torch.cuda.empty_cache()
           torch.cuda.reset_peak_memory_stats()
           import numpy as np
           import soundfile as sf
           from TTS.api import TTS

           print("[tts] Loading XTTS v2...", flush=True)
           model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
           warmup_cuda()

           # Try streaming API first. coqui-tts 0.27.5 may expose tts_stream
           # or require drilling into the underlying model. Handle both paths.
           streaming_ok = False
           chunks: list[np.ndarray] = []
           sr_out = 24000
           ttfa_ms: float
           synth_s: float

           try:
               # Warm with a dummy utterance (non-streaming) to JIT kernels
               _ = model.tts(text="Warm.", speaker_wav=ref_audio, language="en")
               torch.cuda.synchronize()

               if hasattr(model, "tts_stream"):
                   with Timer() as t_total:
                       first_chunk_t: float | None = None
                       start = None
                       import time as _time
                       start = _time.perf_counter()
                       for chunk in model.tts_stream(
                           text=target_text, speaker_wav=ref_audio, language="en"
                       ):
                           if first_chunk_t is None:
                               first_chunk_t = _time.perf_counter() - start
                           if isinstance(chunk, torch.Tensor):
                               chunk = chunk.detach().cpu().numpy()
                           chunks.append(np.asarray(chunk, dtype=np.float32).flatten())
                   ttfa_ms = round((first_chunk_t or 0.0) * 1000, 1)
                   synth_s = t_total.elapsed_s
                   streaming_ok = True
               else:
                   # Fallback: non-streaming tts() call; TTFA = full synthesis time
                   with Timer() as t_total:
                       wav = model.tts(text=target_text, speaker_wav=ref_audio, language="en")
                       torch.cuda.synchronize()
                   synth_s = t_total.elapsed_s
                   ttfa_ms = round(synth_s * 1000, 1)
                   chunks = [np.asarray(wav, dtype=np.float32).flatten()]
           except Exception:
               # Any streaming failure -> final fallback: plain tts()
               traceback.print_exc()
               with Timer() as t_total:
                   wav = model.tts(text=target_text, speaker_wav=ref_audio, language="en")
                   torch.cuda.synchronize()
               synth_s = t_total.elapsed_s
               ttfa_ms = round(synth_s * 1000, 1)
               chunks = [np.asarray(wav, dtype=np.float32).flatten()]

           full_wav = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
           audio_dur = len(full_wav) / float(sr_out)
           sf.write(sample_out, full_wav, sr_out)
           peak_vram = sample_vram_mb()["peak_allocated_mb"]

           del model
           torch.cuda.empty_cache()

           return {
               "engine": "xtts",
               "mode": "streaming" if streaming_ok else "non_streaming_fallback",
               "fallback_to_non_streaming": not streaming_ok,
               "ttfa_ms": ttfa_ms,
               "rtf": round(compute_rtf(audio_dur, synth_s), 3),
               "audio_duration_s": round(audio_dur, 3),
               "synthesis_time_s": round(synth_s, 3),
               "peak_vram_mb": round(peak_vram, 1),
               "sample_rate": sr_out,
               "output_wav": str(sample_out),
           }


       def measure_qwen3(ref_audio: str, ref_text: str, target_text: str,
                         sample_out: Path) -> dict[str, Any]:
           import torch
           torch.cuda.empty_cache()
           torch.cuda.reset_peak_memory_stats()
           import soundfile as sf
           from qwen_tts import Qwen3TTSModel

           print("[tts] Loading Qwen3-TTS 0.6B-Base...", flush=True)
           # Do NOT request FA2 here; plan 07 owns FA2 install. Use default attn.
           model = Qwen3TTSModel.from_pretrained(
               "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
               device_map="cuda:0",
               torch_dtype=torch.bfloat16,
           )
           warmup_cuda()

           prompt = model.create_voice_clone_prompt(
               ref_audio=ref_audio, ref_text=ref_text, x_vector_only_mode=False
           )
           # Warmup with a dummy call to compile kernels
           _ = model.generate_voice_clone(
               text="Warm.", voice_clone_prompt=prompt, language="English",
           )
           torch.cuda.synchronize()

           with Timer() as t:
               wavs, sr = model.generate_voice_clone(
                   text=target_text, voice_clone_prompt=prompt, language="English",
               )
               torch.cuda.synchronize()
           synth_s = t.elapsed_s
           wav = wavs[0] if hasattr(wavs, "__len__") and len(wavs) > 0 else wavs
           if hasattr(wav, "detach"):
               wav = wav.detach().cpu().numpy().astype("float32").flatten()
           audio_dur = len(wav) / float(sr)
           sf.write(sample_out, wav, int(sr))
           peak_vram = sample_vram_mb()["peak_allocated_mb"]

           del model
           torch.cuda.empty_cache()

           return {
               "engine": "qwen3",
               "mode": "non_streaming",
               "variant": "0.6B-Base",
               "flash_attention": "eager",  # plan 07 upgrades this
               "ttfa_ms": round(synth_s * 1000, 1),
               "rtf": round(compute_rtf(audio_dur, synth_s), 3),
               "audio_duration_s": round(audio_dur, 3),
               "synthesis_time_s": round(synth_s, 3),
               "peak_vram_mb": round(peak_vram, 1),
               "sample_rate": int(sr),
               "output_wav": str(sample_out),
           }


       # -------------------- Driver --------------------

       def main() -> int:
           ap = argparse.ArgumentParser()
           ap.add_argument("--ref-audio", required=True,
                           help="Short reference audio (6-12s) of the builder's voice")
           ap.add_argument("--ref-text", required=True,
                           help="Reference transcript text file (matches ref-audio content)")
           ap.add_argument("--target-text", default="Hey, got it.",
                           help="Short target utterance to synthesize (3-5 words ideal)")
           ap.add_argument("--output", required=True, help="Results JSON path")
           ap.add_argument("--accent-ok", action="store_true",
                           help="Set to true ONLY after builder confirms Qwen3-TTS "
                                "accent-preservation listening test passes (defaults false)")
           args = ap.parse_args()

           ref_audio = args.ref_audio
           ref_text_path = Path(args.ref_text)
           ref_text_raw = ref_text_path.read_text(encoding="utf-8")
           # Strip comment lines
           ref_text = "\n".join(l for l in ref_text_raw.splitlines()
                                if not l.strip().startswith("#")).strip()

           if not Path(ref_audio).exists():
               print(f"ERROR: ref-audio missing: {ref_audio}", file=sys.stderr)
               print("Builder must record probes/fixtures/short_ref_audio.wav first.", file=sys.stderr)
               return 2

           OUTPUT_SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

           engines: dict[str, dict[str, Any]] = {}

           for name, fn, sample_name in [
               ("f5",    lambda: measure_f5(ref_audio, ref_text, args.target_text,
                                            OUTPUT_SAMPLE_DIR / "f5.wav"),
                         "f5.wav"),
               ("xtts",  lambda: measure_xtts(ref_audio, args.target_text,
                                               OUTPUT_SAMPLE_DIR / "xtts.wav"),
                         "xtts.wav"),
               ("qwen3", lambda: measure_qwen3(ref_audio, ref_text, args.target_text,
                                                OUTPUT_SAMPLE_DIR / "qwen3.wav"),
                         "qwen3.wav"),
           ]:
               try:
                   engines[name] = fn()
                   print(f"[tts] {name}: TTFA={engines[name]['ttfa_ms']} ms, "
                         f"RTF={engines[name]['rtf']}, VRAM={engines[name]['peak_vram_mb']} MB",
                         flush=True)
               except Exception as e:
                   print(f"[tts] {name}: FAILED {e!r}", file=sys.stderr)
                   traceback.print_exc()
                   engines[name] = {
                       "engine": name, "ttfa_ms": None, "rtf": None,
                       "error": repr(e),
                   }

           default = pick_v1_default(engines)
           qwen_gate = qwen_gate_disposition(engines.get("qwen3", {}), args.accent_ok)

           payload = {
               "probe": "tts_ttfa",
               "target_text": args.target_text,
               "ref_audio": ref_audio,
               "engines": engines,
               "v1_default": default,
               "v1_default_reason": (
                   f"{default} cleared TTFA<={TTFA_TARGET_MS}ms and RTF<{RTF_TARGET}"
                   if default and engines.get(default, {}).get("ttfa_ms", 99999) <= TTFA_TARGET_MS
                   else f"No engine hit the budget; {default} has best TTFA"
                   if default else "All engines failed"
               ),
               "qwen_gate": qwen_gate,
               "accent_ok_passed_to_probe": args.accent_ok,
           }
           write_results(args.output, payload)
           print(f"\n[tts] v1_default = {default}", flush=True)
           print(f"[tts] qwen_gate  = {qwen_gate}", flush=True)
           return 0


       if __name__ == "__main__":
           sys.exit(main())
       ```

    4. Run unit tests:
       ```bash
       cd .planning/phases/00-measurement-gate/probes
       ../.venv-phase0/Scripts/python.exe -m pytest test_tts_ttfa.py -v
       ```
       Must pass 9/9.

    5. Commit all three files.
  </action>
  <verify>
    <automated>cd .planning/phases/00-measurement-gate/probes &amp;&amp; ../.venv-phase0/Scripts/python.exe -m pytest test_tts_ttfa.py -v 2&gt;&amp;1 | tee /tmp/tts_tests.out &amp;&amp; grep -q "9 passed" /tmp/tts_tests.out &amp;&amp; grep -q "def measure_f5" tts_ttfa.py &amp;&amp; grep -q "def measure_xtts" tts_ttfa.py &amp;&amp; grep -q "def measure_qwen3" tts_ttfa.py &amp;&amp; grep -q "nfe_step=7" tts_ttfa.py &amp;&amp; test -f fixtures/short_ref_transcript.txt
</automated>
  </verify>
  <acceptance_criteria>
    - File `.planning/phases/00-measurement-gate/probes/tts_ttfa.py` exists with functions `measure_f5`, `measure_xtts`, `measure_qwen3`, `pick_v1_default`, `qwen_gate_disposition`, `compute_rtf`, `main`.
    - File references `nfe_step=7` for F5 (per PITFALLS.md #4 / STACK.md Sway sampling rule).
    - File `.planning/phases/00-measurement-gate/probes/test_tts_ttfa.py` has 9 `def test_*` functions.
    - Running pytest exits 0 with `9 passed`.
    - File `.planning/phases/00-measurement-gate/probes/fixtures/short_ref_transcript.txt` exists with at least 10 words (post-comment-strip).
  </acceptance_criteria>
  <done>TTFA bench rig with unit-tested logic is ready; awaiting the builder's short voice reference.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: Builder records short_ref_audio.wav, runs bench, does subjective accent test, writes results</name>
  <files>
    .planning/phases/00-measurement-gate/probes/fixtures/short_ref_audio.wav  (gitignored)
    .planning/phases/00-measurement-gate/probes/fixtures/tts_samples/f5.wav  (gitignored)
    .planning/phases/00-measurement-gate/probes/fixtures/tts_samples/xtts.wav  (gitignored)
    .planning/phases/00-measurement-gate/probes/fixtures/tts_samples/qwen3.wav  (gitignored)
    .planning/phases/00-measurement-gate/results/tts_ttfa.json
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/probes/fixtures/short_ref_transcript.txt  (the exact lines to read aloud)
    .planning/phases/00-measurement-gate/probes/tts_ttfa.py  (for invocation reference)
    .planning/research/QWEN3-TTS.md (§2.6 accent handling, §9.2 known bugs — accent drift is the big risk)
  </read_first>
  <action>Human-verification checkpoint. Claude has already completed the automated work described under &lt;what-built&gt; above. The builder performs the steps in &lt;how-to-verify&gt; below and records the outcome as described; acceptance is gated on &lt;acceptance_criteria&gt;. When `workflow.auto_advance=true`, auto-mode auto-approves this checkpoint.</action>
  <what-built>
    Task 1 produced a measurement rig that loads each of the three TTS engines sequentially, clones from a reference WAV, synthesizes a short target phrase, and records TTFA + RTF + peak VRAM. Each engine's output WAV is saved under `probes/fixtures/tts_samples/` so the builder can listen. Claude cannot fabricate the reference voice or judge accent preservation — that is the builder's job.
  </what-built>
  <how-to-verify>
    **Builder records the reference (once):**

    1. Open `probes/fixtures/short_ref_transcript.txt`. Read the body aloud in a quiet room at natural pace.
    2. Target 6–12 seconds of clean audio, mono, 24 kHz or higher, saved as `probes/fixtures/short_ref_audio.wav`.
    3. Privacy: `.gitignore` from plan 01 excludes `*.wav`. Delete the file after Phase 0 concludes if retention is not desired.

    **Claude runs the bench (round 1, `--accent-ok` NOT passed):**

    ```bash
    cd .planning/phases/00-measurement-gate
    .venv-phase0/Scripts/python.exe probes/tts_ttfa.py \
      --ref-audio probes/fixtures/short_ref_audio.wav \
      --ref-text  probes/fixtures/short_ref_transcript.txt \
      --target-text "Hey, got it." \
      --output results/tts_ttfa.json
    ```

    Expected runtime: ~5–10 min (three models × load + warm + one timed run).

    **Builder does the subjective accent listening test:**

    1. Open `probes/fixtures/tts_samples/qwen3.wav` in any player (VLC, Windows Media Player).
    2. Listen. Does the synthesized voice preserve your Spanish-accented English, or does it drift toward American English or Chinese-accented English?
    3. Also listen to `f5.wav` and `xtts.wav` for comparison (both are known to preserve accent from reference).
    4. Decide: does Qwen3 sound like you, or does it sound like a different person?

    **Claude re-runs with `--accent-ok` IF builder approves Qwen3:**

    ```bash
    .venv-phase0/Scripts/python.exe probes/tts_ttfa.py \
      --ref-audio probes/fixtures/short_ref_audio.wav \
      --ref-text  probes/fixtures/short_ref_transcript.txt \
      --target-text "Hey, got it." \
      --output results/tts_ttfa.json \
      --accent-ok
    ```

    If builder says the accent drifts, leave `--accent-ok` OFF — the `qwen_gate.accepted` field stays false.

    **Acceptance check (automated):**

    ```bash
    .venv-phase0/Scripts/python.exe -c "
    import json
    d = json.load(open('results/tts_ttfa.json'))
    assert 'engines' in d and set(d['engines'].keys()) == {'f5','xtts','qwen3'}
    for name, e in d['engines'].items():
        if 'error' not in e:
            assert e['ttfa_ms'] is not None, f'{name} missing ttfa_ms'
            assert e['rtf'] is not None, f'{name} missing rtf'
            assert e['peak_vram_mb'] is not None, f'{name} missing peak_vram_mb'
    assert d['v1_default'] in ('f5','xtts','qwen3', None)
    assert 'qwen_gate' in d and 'accepted' in d['qwen_gate']
    print('v1_default =', d['v1_default'])
    print('qwen_gate  =', d['qwen_gate'])
    "
    ```
  </how-to-verify>
  <acceptance_criteria>
    - File `.planning/phases/00-measurement-gate/results/tts_ttfa.json` exists with valid JSON.
    - JSON has `engines` keyed by `f5`, `xtts`, `qwen3`.
    - Each engine (unless it errored) has non-null `ttfa_ms`, `rtf`, `peak_vram_mb`.
    - `v1_default` is one of `f5`, `xtts`, `qwen3`, or `null` (all failed).
    - `qwen_gate.accepted` is a boolean; `qwen_gate.reasons` is a non-empty list.
    - Three output WAVs exist at `probes/fixtures/tts_samples/{f5,xtts,qwen3}.wav` (unless the engine errored).
    - No `*.wav` file is staged for git (`git status --porcelain | grep '\.wav$'` returns empty).
  </acceptance_criteria>
  <resume-signal>
    Reply "approved" once the acceptance check prints all three engines' metrics and the JSON satisfies the criteria. If any engine failed to load (OOM, import error, missing weights), quote the error text and the orchestrator can route to a repair plan. If you reject Qwen3 on accent, say so — the JSON will correctly record `qwen_gate.accepted=false`.
  </resume-signal>
  <verify><automated>echo "checkpoint: acceptance delegated to &lt;acceptance_criteria&gt; above; pass when resume-signal received"</automated></verify>
  <done>Acceptance criteria above are satisfied and the builder returned the expected resume-signal.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Builder's voice -> `short_ref_audio.wav` | PII; gitignored. |
| TTS engines -> HF model weights | Downloaded from HuggingFace at first use; integrity via HF manifests. |
| Synthesized samples -> `tts_samples/*.wav` | Contain synthesized clones of the builder's voice. Same sensitivity as the reference. gitignored. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-04-01 | Info Disclosure | `short_ref_audio.wav` + `tts_samples/*.wav` (voice clones) | mitigate | `.gitignore` pattern `*.wav` from plan 01 catches these; acceptance check verifies no WAV is staged. Builder instructed to delete after Phase 0. |
| T-00-04-02 | Tampering | Model weights (F5, XTTS, Qwen3) from HF | accept | Official upstream weights from maintainer-owned HF repos. No pinned hashes at spike stage. |
| T-00-04-03 | DoS | OOM on Qwen3-TTS load | mitigate | Plan 04 tests only 0.6B-Base (QWEN3-TTS.md §3.2 confirms fits in ~3 GB bf16). `torch.cuda.empty_cache()` between engines prevents accumulation. |
| T-00-04-04 | Info Disclosure | Non-commercial license (F5 CC-BY-NC / XTTS CPML) on synthesized samples | accept | F5 and XTTS synthesized samples are measurement outputs, not distributed. Test samples stay local; not shared. Qwen3-TTS is Apache-2.0, no constraint. |

No high-severity threats. Voice PII is the only sensitive artifact class; fully gitignored.
</threat_model>

<verification>
```bash
.venv-phase0/Scripts/python.exe -c "
import json
d = json.load(open('results/tts_ttfa.json'))
print(f'v1_default: {d[\"v1_default\"]}')
print(f'qwen_gate:  {d[\"qwen_gate\"]}')
for n, e in d['engines'].items():
    status = 'ERR' if 'error' in e else 'OK'
    print(f'  [{status}] {n}: ttfa={e.get(\"ttfa_ms\")}ms rtf={e.get(\"rtf\")} vram={e.get(\"peak_vram_mb\")}MB')
"
git status --porcelain | grep -E '\.wav$' && echo "FAIL: wav staged" || echo "OK: no wav staged"
```
</verification>

<success_criteria>
- [ ] Three TTS engines measured; TTFA + RTF + peak VRAM recorded for each (or error captured)
- [ ] `v1_default` chosen per Resolved Tension #3 rule
- [ ] Qwen3-TTS acceptance gate disposition recorded (accept/reject + reasons)
- [ ] Output WAVs exist under `probes/fixtures/tts_samples/` for builder listening
- [ ] Unit tests 9/9 passing
- [ ] No voice audio or synthesized sample staged for git
</success_criteria>

<output>
After completion, create `.planning/phases/00-measurement-gate/00-04-SUMMARY.md` summarizing:
- Per-engine TTFA / RTF / VRAM (one-line table)
- Chosen `v1_default` engine and the quantitative reason
- Qwen3-TTS acceptance gate verdict (accepted/rejected) with all reasons
- Builder's subjective note on Qwen3-TTS accent preservation
- Whether the Resolved Tension #3 cascade fired (F5 demoted -> XTTS/Qwen3 promoted)
- Guidance for Phase 2 Voice Lab: which engines ship in v1 (two if Qwen rejected, three if accepted)
</output>
