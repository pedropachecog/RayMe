---
phase: 00-measurement-gate
plan: 03
type: execute
wave: 2
depends_on: [01]
files_modified:
  - .planning/phases/00-measurement-gate/probes/whisper_bench.py
  - .planning/phases/00-measurement-gate/probes/fixtures/reference_transcript.txt
  - .planning/phases/00-measurement-gate/probes/test_whisper_bench.py
  - .planning/phases/00-measurement-gate/results/whisper.json
autonomous: false
requirements: []
user_setup:
  - service: voice-sample-capture
    why: "Phase 0 criterion #2 requires a 10-minute read-aloud in the builder's Spanish-accented English to measure WER against three Whisper model rungs. Only the builder can produce this recording."
    env_vars: []
    dashboard_config:
      - task: "Record a ~10-minute read-aloud of the reference transcript in a quiet room, mono, 16 kHz or higher, save as probes/fixtures/reference_audio.wav"
        location: "Any audio recorder (macOS Voice Memos + export as WAV, Windows Sound Recorder, Audacity). The file is gitignored as *.wav per plan 01."

must_haves:
  truths:
    - "Three Whisper rungs (distil-large-v3 INT8, large-v3-turbo INT8, large-v3 FP16) have been benchmarked against the builder's Spanish-accented English voice"
    - "Per-rung metrics exist: WER (via jiwer), p50 latency, p95 latency, peak VRAM during transcription"
    - "Exactly ONE rung is marked default:true in results/whisper.json, and the choice is justified against the roadmap Resolved Tension #2 rule"
    - "The hypothesis transcript for each rung is persisted so the WER can be re-computed if the normalization rule changes"
    - "Voice sample audio is NOT committed to git (*.wav excluded)"
  artifacts:
    - path: ".planning/phases/00-measurement-gate/probes/whisper_bench.py"
      provides: "WER + latency + VRAM measurement rig for three Whisper model rungs"
      contains: "faster_whisper"
    - path: ".planning/phases/00-measurement-gate/probes/fixtures/reference_transcript.txt"
      provides: "~1500-word English reference transcript for the builder to read aloud"
      contains: "The quick brown fox"
    - path: ".planning/phases/00-measurement-gate/probes/test_whisper_bench.py"
      provides: "Unit tests for the WER computation + results schema — NOT the 30-min bench itself"
      contains: "def test_wer_perfect_match"
    - path: ".planning/phases/00-measurement-gate/results/whisper.json"
      provides: "Phase 0 criterion #2 deliverable: machine-readable per-rung metrics + chosen default"
      contains: "\"default\": true"
  key_links:
    - from: ".planning/phases/00-measurement-gate/probes/whisper_bench.py"
      to: ".planning/phases/00-measurement-gate/probes/bench_utils.py"
      via: "direct import"
      pattern: "from bench_utils import"
    - from: ".planning/phases/00-measurement-gate/probes/whisper_bench.py"
      to: "faster_whisper.WhisperModel"
      via: "transcribe(audio_path, beam_size=5, condition_on_previous_text=False)"
      pattern: "WhisperModel.*transcribe"
---

<objective>
Empirically measure Word Error Rate, latency, and peak VRAM for three Whisper model rungs on the builder's Spanish-accented English voice, so Phase 2 can freeze the v1 STT default with data rather than intuition.

Purpose: Phase 0 success criterion #2 and the trigger for Resolved Tension #2 in the roadmap. REQ-A3 locks STT quality to Spanish-accented English on the builder's voice; the three rungs have different WER/latency/VRAM tradeoffs and no published benchmark exists for this exact voice. If distil-large-v3 INT8 is within 2 pp WER of the heavier rungs, it wins on VRAM and latency. If it is worse by >2 pp, we promote turbo or FP16 — and in the FP16 case, per the roadmap, XTTS must replace F5 as the v1 default (VRAM math).

Output: `probes/whisper_bench.py` (reusable measurement rig), a reference transcript for the builder to read, unit tests for the measurement logic, and `results/whisper.json` containing per-rung WER + latency + VRAM + the chosen default rung.
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
Public contract the plan depends on:

From `probes/bench_utils.py` (created in plan 01):
- `gpu_info()` -> dict with gpu metadata
- `sample_vram_mb()` -> dict with allocated/reserved/peak/used_mb_nvml
- `Timer` context manager -> `.elapsed_ms` property
- `warmup_cuda()` -> no-arg warmup before timing
- `write_results(path, payload)` -> pretty JSON writer

faster-whisper API (from 00-RESEARCH.md §Code Examples Pattern 1 — already verified):
```python
from faster_whisper import WhisperModel

model = WhisperModel(model_size, device="cuda", compute_type=quantization)
# compute_type options: "int8_float16" (quantized), "float16" (FP16), "int8" (pure int8 CPU)
segments, info = model.transcribe(
    audio_path,
    beam_size=5,
    condition_on_previous_text=False,  # CRITICAL per PITFALLS.md #6 (hallucinations)
    vad_filter=False,                  # we are measuring raw model; VAD filter is Phase 2's concern
    language="en",                     # REQ-A3: English-only
)
hypothesis = " ".join(s.text for s in segments)
```

Rung list (from roadmap §Phase 0 success criterion #2 + 00-RESEARCH.md §Standard Stack):
1. `distil-large-v3` + `int8_float16` (smallest, ~1.5 GB VRAM)
2. `large-v3-turbo` + `int8_float16` (~0.75 GB on disk, ~1.5 GB loaded)
3. `large-v3` + `float16` (~3 GB)

jiwer WER API (standard library):
```python
import jiwer
wer = jiwer.wer(reference, hypothesis)  # returns float 0.0-1.0+
```

Per the QWEN3-TTS.md Open Question #6 and general ASR evaluation practice, WER must be computed on NORMALIZED text (lowercase, punctuation stripped, whitespace collapsed). Use jiwer's built-in transform chain:

```python
from jiwer import Compose, ToLowerCase, RemovePunctuation, RemoveMultipleSpaces, Strip
transform = Compose([ToLowerCase(), RemovePunctuation(), RemoveMultipleSpaces(), Strip()])
wer = jiwer.wer(reference, hypothesis,
                reference_transform=transform, hypothesis_transform=transform)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Build whisper_bench.py + reference transcript + unit tests (TDD on the WER + schema logic)</name>
  <files>
    .planning/phases/00-measurement-gate/probes/whisper_bench.py
    .planning/phases/00-measurement-gate/probes/fixtures/reference_transcript.txt
    .planning/phases/00-measurement-gate/probes/test_whisper_bench.py
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/probes/bench_utils.py (API already defined by plan 01)
    .planning/phases/00-measurement-gate/00-RESEARCH.md (§Architecture Patterns Pattern 1 — WER script template; §Common Pitfalls #4 — pre-downloaded weights)
    .planning/research/PITFALLS.md (Pitfall #6 — Whisper hallucinations; Pitfall #7 — VRAM budget rule)
  </read_first>
  <behavior>
    - Test 1 (perfect match): `compute_wer("hello world", "hello world")` returns 0.0
    - Test 2 (one substitution): `compute_wer("hello world", "hello mars")` returns 0.5 (1 sub / 2 words)
    - Test 3 (punctuation normalization): `compute_wer("Hello, world!", "hello world")` returns 0.0 after normalization
    - Test 4 (case normalization): `compute_wer("Hello World", "hello world")` returns 0.0 after normalization
    - Test 5 (results schema): `build_result(rung_metrics, default_rung="distil-large-v3")` produces a dict with keys `rungs` (list of 3), `default_rung` (str), and each rung has keys `model`, `compute_type`, `wer`, `p50_latency_ms`, `p95_latency_ms`, `peak_vram_mb`, `hypothesis`, `default` (bool). Exactly one rung has `default: true`.
    - Test 6 (default picker): `pick_default(rungs)` applies Resolved Tension #2 logic:
      - Sort rungs ascending by WER.
      - If the lightest rung (distil-large-v3) is within 2 pp of the best WER, pick distil-large-v3.
      - Else if large-v3-turbo is within 2 pp of FP16 best, pick large-v3-turbo.
      - Else pick the best WER rung (likely large-v3 FP16).
  </behavior>
  <action>
    1. Create `.planning/phases/00-measurement-gate/probes/fixtures/reference_transcript.txt` — a ~1500-word English passage that includes:
       - Common conversational English (natural speech rhythm)
       - A few deliberately tricky tokens: proper nouns, numbers, homophones (their/there/they're), acronyms
       - No code blocks, no foreign-language phrases
       - Target length: ~10 min of read-aloud at ~150 WPM

       Use a mix of three public-domain sources to reach ~1500 words without rights issues:
       - An excerpt from a classic speech (e.g., a paragraph from Lincoln's Gettysburg Address)
       - A technology-neutral Wikipedia-style encyclopedic paragraph (write original)
       - A conversational paragraph about daily routines (write original)

       Start the file with a header comment:
       ```
       # RayMe Phase 0 - Whisper WER reference transcript
       #
       # Read this aloud in a quiet room at normal conversational pace.
       # Expected duration: ~10 minutes.
       # Save the recording as probes/fixtures/reference_audio.wav (mono, 16 kHz+).
       # The audio file is gitignored per plan 01; only this transcript is committed.
       ```

       Body: the actual ~1500-word transcript as plain text, punctuation included.

    2. Create `.planning/phases/00-measurement-gate/probes/test_whisper_bench.py` — the 6 test cases described in `<behavior>`. Import `compute_wer`, `build_result`, `pick_default` from `whisper_bench`. These tests run fast (no model load, no audio) and should gate the implementation.

       ```python
       """Unit tests for whisper_bench.py — verifies the WER normalization,
       the results-JSON schema builder, and the default-rung picker logic.

       These tests do NOT run the actual Whisper models; they validate the
       pure-Python logic around it.
       """
       import pytest
       from whisper_bench import compute_wer, build_result, pick_default


       def test_wer_perfect_match():
           assert compute_wer("hello world", "hello world") == pytest.approx(0.0)


       def test_wer_one_substitution():
           assert compute_wer("hello world", "hello mars") == pytest.approx(0.5)


       def test_wer_ignores_punctuation():
           assert compute_wer("Hello, world!", "hello world") == pytest.approx(0.0)


       def test_wer_ignores_case():
           assert compute_wer("Hello World", "hello world") == pytest.approx(0.0)


       def test_build_result_schema():
           rungs = [
               {"model": "distil-large-v3", "compute_type": "int8_float16",
                "wer": 0.11, "p50_latency_ms": 2500, "p95_latency_ms": 3100,
                "peak_vram_mb": 1500, "hypothesis": "..."},
               {"model": "large-v3-turbo", "compute_type": "int8_float16",
                "wer": 0.10, "p50_latency_ms": 2800, "p95_latency_ms": 3400,
                "peak_vram_mb": 1800, "hypothesis": "..."},
               {"model": "large-v3", "compute_type": "float16",
                "wer": 0.09, "p50_latency_ms": 5200, "p95_latency_ms": 6000,
                "peak_vram_mb": 3200, "hypothesis": "..."},
           ]
           result = build_result(rungs)
           assert "rungs" in result and len(result["rungs"]) == 3
           assert sum(1 for r in result["rungs"] if r.get("default")) == 1
           assert "default_rung" in result
           # All required keys present
           for r in result["rungs"]:
               for k in ("model", "compute_type", "wer", "p50_latency_ms",
                         "p95_latency_ms", "peak_vram_mb", "hypothesis", "default"):
                   assert k in r, f"missing key {k} in {r}"


       def test_pick_default_distil_wins_when_within_2pp():
           rungs = [
               {"model": "distil-large-v3", "wer": 0.11},
               {"model": "large-v3-turbo", "wer": 0.10},
               {"model": "large-v3", "wer": 0.095},
           ]
           # best is large-v3 at 0.095; distil at 0.11 is 1.5pp off -> distil wins
           assert pick_default(rungs) == "distil-large-v3"


       def test_pick_default_promotes_when_distil_falls_behind():
           rungs = [
               {"model": "distil-large-v3", "wer": 0.15},
               {"model": "large-v3-turbo", "wer": 0.095},
               {"model": "large-v3", "wer": 0.090},
           ]
           # distil is 6pp worse than best; turbo is within 0.5pp of best -> turbo wins
           assert pick_default(rungs) == "large-v3-turbo"


       def test_pick_default_falls_through_to_fp16_when_all_quantized_bad():
           rungs = [
               {"model": "distil-large-v3", "wer": 0.17},
               {"model": "large-v3-turbo", "wer": 0.15},
               {"model": "large-v3", "wer": 0.08},
           ]
           assert pick_default(rungs) == "large-v3"
       ```

    3. Create `.planning/phases/00-measurement-gate/probes/whisper_bench.py`:

       ```python
       """Whisper WER + latency + VRAM benchmark for Phase 0 success criterion #2.

       Usage:
         .venv-phase0/Scripts/python.exe probes/whisper_bench.py \
           --audio probes/fixtures/reference_audio.wav \
           --reference probes/fixtures/reference_transcript.txt \
           --output results/whisper.json

       Runs all three Whisper rungs sequentially:
         - distil-large-v3 + int8_float16
         - large-v3-turbo  + int8_float16
         - large-v3        + float16

       Emits per-rung WER (normalized), p50/p95 latency over 3 runs, peak VRAM.
       Picks a default rung per Resolved Tension #2 rule.
       """
       from __future__ import annotations
       import argparse
       import json
       import statistics
       import sys
       from pathlib import Path
       from typing import Any

       from bench_utils import Timer, sample_vram_mb, warmup_cuda, write_results

       RUNGS: list[tuple[str, str]] = [
           ("distil-large-v3", "int8_float16"),
           ("large-v3-turbo",  "int8_float16"),
           ("large-v3",        "float16"),
       ]

       # Default-picker thresholds (roadmap Resolved Tension #2)
       DISTIL_WITHIN_PP = 0.02   # 2 percentage points
       TURBO_WITHIN_PP  = 0.02


       def _normalize_transform():
           """Builds the jiwer transform chain for WER normalization.
           Kept as a factory so the transform is fresh per call (jiwer requires this)."""
           from jiwer import Compose, ToLowerCase, RemovePunctuation, RemoveMultipleSpaces, Strip
           return Compose([ToLowerCase(), RemovePunctuation(), RemoveMultipleSpaces(), Strip()])


       def compute_wer(reference: str, hypothesis: str) -> float:
           """WER on normalized text. Returns 0.0 on perfect match after normalization."""
           import jiwer
           t = _normalize_transform()
           return float(jiwer.wer(reference, hypothesis,
                                  reference_transform=t, hypothesis_transform=t))


       def pick_default(rungs: list[dict[str, Any]]) -> str:
           """Returns the chosen default model name per Resolved Tension #2:
           prefer lighter rungs when their WER is within 2pp of the best."""
           best_wer = min(r["wer"] for r in rungs)
           by_name = {r["model"]: r for r in rungs}
           distil = by_name.get("distil-large-v3")
           turbo  = by_name.get("large-v3-turbo")
           fp16   = by_name.get("large-v3")
           if distil and distil["wer"] - best_wer <= DISTIL_WITHIN_PP:
               return "distil-large-v3"
           if turbo and turbo["wer"] - best_wer <= TURBO_WITHIN_PP:
               return "large-v3-turbo"
           # fallback: the best WER rung
           return min(rungs, key=lambda r: r["wer"])["model"]


       def build_result(rungs: list[dict[str, Any]]) -> dict[str, Any]:
           """Marks the chosen default rung and returns the payload for results JSON."""
           default_name = pick_default(rungs)
           out = []
           for r in rungs:
               r = dict(r)
               r.setdefault("default", False)
               if r["model"] == default_name:
                   r["default"] = True
               else:
                   r["default"] = False
               out.append(r)
           return {
               "probe": "whisper_bench",
               "rungs": out,
               "default_rung": default_name,
           }


       def measure_rung(model_name: str, compute_type: str, audio_path: str,
                        reference: str, trials: int = 3) -> dict[str, Any]:
           """Loads the model, runs N transcriptions, returns metrics."""
           import torch
           from faster_whisper import WhisperModel

           print(f"[bench] Loading {model_name} ({compute_type})...", flush=True)
           torch.cuda.empty_cache()
           torch.cuda.reset_peak_memory_stats()

           model = WhisperModel(model_name, device="cuda", compute_type=compute_type)
           warmup_cuda()

           latencies: list[float] = []
           hypothesis = ""
           vram_peaks: list[float] = []

           for i in range(trials):
               torch.cuda.reset_peak_memory_stats()
               with Timer() as t:
                   segments, info = model.transcribe(
                       audio_path,
                       beam_size=5,
                       condition_on_previous_text=False,   # PITFALLS.md #6
                       vad_filter=False,
                       language="en",
                   )
                   # Consume the generator (transcribe is lazy)
                   parts = [s.text for s in segments]
               latencies.append(t.elapsed_ms)
               vram_peaks.append(sample_vram_mb()["peak_allocated_mb"])
               if i == 0:
                   hypothesis = " ".join(parts)
               print(f"[bench]   trial {i+1}/{trials}: {t.elapsed_ms:.0f} ms", flush=True)

           # Release VRAM before next rung
           del model
           torch.cuda.empty_cache()

           wer = compute_wer(reference, hypothesis)
           return {
               "model": model_name,
               "compute_type": compute_type,
               "wer": round(wer, 4),
               "p50_latency_ms": round(statistics.median(latencies), 1),
               "p95_latency_ms": round(sorted(latencies)[-1], 1) if trials < 20
                                 else round(statistics.quantiles(latencies, n=20)[-1], 1),
               "peak_vram_mb": round(max(vram_peaks), 1),
               "hypothesis": hypothesis[:4000],  # truncate to keep JSON readable
               "trials": trials,
           }


       def main() -> int:
           ap = argparse.ArgumentParser()
           ap.add_argument("--audio", required=True,
                           help="Path to the builder's read-aloud WAV")
           ap.add_argument("--reference", required=True,
                           help="Path to the reference transcript .txt")
           ap.add_argument("--output", required=True,
                           help="Path to write results JSON")
           ap.add_argument("--trials", type=int, default=3)
           args = ap.parse_args()

           audio = Path(args.audio)
           if not audio.exists():
               print(f"ERROR: audio file not found: {audio}", file=sys.stderr)
               print("Builder must record probes/fixtures/reference_audio.wav first.", file=sys.stderr)
               return 2

           reference = Path(args.reference).read_text(encoding="utf-8")
           # Strip comment lines (lines starting with '#') from the transcript
           reference = "\n".join(
               line for line in reference.splitlines()
               if not line.strip().startswith("#")
           )

           rung_metrics: list[dict[str, Any]] = []
           for model_name, compute_type in RUNGS:
               try:
                   metrics = measure_rung(model_name, compute_type, str(audio), reference, args.trials)
               except Exception as e:
                   print(f"[bench] FAILED {model_name} ({compute_type}): {e!r}", file=sys.stderr)
                   metrics = {
                       "model": model_name, "compute_type": compute_type,
                       "wer": None, "p50_latency_ms": None, "p95_latency_ms": None,
                       "peak_vram_mb": None, "hypothesis": "",
                       "trials": 0, "error": repr(e),
                   }
               rung_metrics.append(metrics)

           payload = build_result(rung_metrics)
           write_results(args.output, payload)
           print(f"\n[bench] Default rung: {payload['default_rung']}", flush=True)
           print(f"[bench] Wrote {args.output}", flush=True)
           return 0


       if __name__ == "__main__":
           sys.exit(main())
       ```

    4. Run unit tests from the venv:
       ```bash
       cd .planning/phases/00-measurement-gate/probes
       ../.venv-phase0/Scripts/python.exe -m pytest test_whisper_bench.py -v
       ```
       Must exit 0 with 8 passing tests (1 schema + 4 WER + 3 pick_default = 8 total). Fix any failures before proceeding to the measurement task.

    5. Commit all three files.
  </action>
  <verify>
    <automated>cd .planning/phases/00-measurement-gate/probes &amp;&amp; ../.venv-phase0/Scripts/python.exe -m pytest test_whisper_bench.py -v 2&gt;&amp;1 | tee /tmp/wer_tests.out &amp;&amp; grep -q "8 passed" /tmp/wer_tests.out &amp;&amp; test -f fixtures/reference_transcript.txt &amp;&amp; wc -w &lt; fixtures/reference_transcript.txt | awk '{exit !($1 &gt;= 1000)}'</automated>
  </verify>
  <acceptance_criteria>
    - File `.planning/phases/00-measurement-gate/probes/whisper_bench.py` exists with functions `compute_wer`, `pick_default`, `build_result`, `measure_rung`, `main` (grep each).
    - File `.planning/phases/00-measurement-gate/probes/test_whisper_bench.py` has 8 `def test_*` functions.
    - Running pytest on the test file under the Phase 0 venv exits 0 with `8 passed`.
    - File `.planning/phases/00-measurement-gate/probes/fixtures/reference_transcript.txt` exists and contains at least 1000 words (target ~1500) after stripping comment lines.
    - `whisper_bench.py` uses `condition_on_previous_text=False` and `language="en"` in the transcribe call (grep both).
  </acceptance_criteria>
  <done>Bench rig + unit tests are green; ready for the builder to record the audio and run the measurement.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: Builder records reference audio, run bench, verify results/whisper.json</name>
  <files>
    .planning/phases/00-measurement-gate/probes/fixtures/reference_audio.wav  (gitignored, local only)
    .planning/phases/00-measurement-gate/results/whisper.json
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/probes/fixtures/reference_transcript.txt  (the exact text to read aloud)
    .planning/phases/00-measurement-gate/probes/whisper_bench.py  (for invocation reference)
  </read_first>
  <action>Human-verification checkpoint. Claude has already completed the automated work described under &lt;what-built&gt; above. The builder performs the steps in &lt;how-to-verify&gt; below and records the outcome as described; acceptance is gated on &lt;acceptance_criteria&gt;. When `workflow.auto_advance=true`, auto-mode auto-approves this checkpoint.</action>
  <what-built>
    Task 1 delivered a measurement rig (`whisper_bench.py`) with unit-tested WER + default-picker logic. The rig loads each Whisper rung, runs 3 transcription trials, and writes a structured results JSON. Only the audio input is missing — recording the builder's voice is the one step Claude cannot automate.
  </what-built>
  <how-to-verify>
    **Builder action (one time):**

    1. Open `probes/fixtures/reference_transcript.txt` in any editor. Read it silently once to be familiar.
    2. Record yourself reading the transcript aloud at normal conversational pace in a quiet room.
       - Target duration: ~10 minutes (the transcript is sized for this).
       - Mono, 16 kHz or higher sample rate.
       - WAV format (not MP3 — faster-whisper handles MP3/FLAC/WAV but WAV avoids decoder variation).
       - Save to `.planning/phases/00-measurement-gate/probes/fixtures/reference_audio.wav`.
    3. Privacy note: this file is a voice sample + therefore PII. It is excluded from git by the plan 01 `.gitignore` (`*.wav` pattern). After Phase 0 concludes, delete the file if retention is not desired.

    **Claude runs after the file exists:**

    ```bash
    cd .planning/phases/00-measurement-gate
    .venv-phase0/Scripts/python.exe probes/whisper_bench.py \
      --audio probes/fixtures/reference_audio.wav \
      --reference probes/fixtures/reference_transcript.txt \
      --output results/whisper.json \
      --trials 3
    ```
    Expect runtime ~8-15 min total (three models × three trials on a 10-min audio, distil fastest, large-v3 slowest).

    **Acceptance check (automated):**
    ```bash
    .venv-phase0/Scripts/python.exe -c "
    import json, sys
    d = json.load(open('results/whisper.json'))
    assert 'rungs' in d and len(d['rungs']) == 3, 'expected 3 rungs'
    for r in d['rungs']:
        for k in ('model','compute_type','wer','p50_latency_ms','p95_latency_ms','peak_vram_mb','hypothesis','default'):
            assert k in r, f'missing {k} in {r[\"model\"]}'
    assert sum(1 for r in d['rungs'] if r['default']) == 1, 'exactly one rung must be default'
    assert d['default_rung'] in ('distil-large-v3','large-v3-turbo','large-v3')
    print('OK: WER per rung =', {r['model']: r['wer'] for r in d['rungs']})
    print('OK: default =', d['default_rung'])
    "
    ```

    **Builder sanity check:**
    - Open `results/whisper.json` and scan the `hypothesis` field for each rung. Does the text look like a transcription of what you actually read? If a rung has obviously wrong output (e.g., Chinese characters, "Thank you for watching" hallucinations, or totally different words) flag it and note in the summary.
    - If `peak_vram_mb` for `large-v3` FP16 exceeds 11 GB, the Resolved Tension #2 cascade fires: note this in the summary because it forces XTTS-over-F5 in Phase 2.

    **Resume signal:** Reply with "approved" if the acceptance check script prints both `OK:` lines. If any rung errored out, the results JSON will include an `"error"` key for that rung — report the error text and the orchestrator can decide whether to retry or fall back.
  </how-to-verify>
  <acceptance_criteria>
    - File `.planning/phases/00-measurement-gate/results/whisper.json` exists with valid JSON.
    - JSON has `rungs` list of length 3 with models `distil-large-v3`, `large-v3-turbo`, `large-v3`.
    - Each rung has non-null values for `wer`, `p50_latency_ms`, `p95_latency_ms`, `peak_vram_mb`, `hypothesis` (unless the rung errored — then an `error` key is present and the summary notes it).
    - Exactly one rung has `default: true`.
    - Top-level `default_rung` matches the marked rung.
    - File `probes/fixtures/reference_audio.wav` is NOT staged for git (confirm: `git status --porcelain | grep reference_audio.wav` returns empty).
  </acceptance_criteria>
  <resume-signal>
    Reply "approved" once the acceptance criteria pass. If any rung failed with an error (OOM, weights missing, decoder error), describe the error and the orchestrator will route to a repair.
  </resume-signal>
  <verify><automated>echo "checkpoint: acceptance delegated to &lt;acceptance_criteria&gt; above; pass when resume-signal received"</automated></verify>
  <done>Acceptance criteria above are satisfied and the builder returned the expected resume-signal.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Builder's voice -> probe fixture | Audio recording contains PII (builder's voice). Never committed; gitignored. |
| HF hub -> local model cache | Whisper weights are downloaded from HF. Integrity: HF's own hash manifests. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-03-01 | Info Disclosure | `reference_audio.wav` (voice PII) | mitigate | `.gitignore` excludes `*.wav`; acceptance criteria verify file is not staged; HTTPS-SETUP-style deletion guidance in the builder instructions ("delete after Phase 0 concludes if retention is not desired"). |
| T-00-03-02 | Info Disclosure | `hypothesis` text in results/whisper.json | accept | Hypothesis is derived from the reference transcript which IS committed (public-domain content). Any text in hypothesis is either a correct transcription (matches public transcript) or a Whisper hallucination (benign). |
| T-00-03-03 | Tampering | Whisper weights from HF | accept | Official SYSTRAN-hosted CTranslate2 weights; HF provides integrity checks. No hash pinning at this spike stage. |
| T-00-03-04 | DoS | Long-running benchmark exhausts VRAM | mitigate | `torch.cuda.empty_cache()` between rungs; each rung's peak is recorded; if FP16 exceeds 11 GB the cascade trigger fires downstream. |

No high-severity threats. Voice PII is the only sensitive artifact and is .gitignored.
</threat_model>

<verification>
Final acceptance:

```bash
# Schema + default rung check
.venv-phase0/Scripts/python.exe -c "
import json
d = json.load(open('results/whisper.json'))
assert len(d['rungs']) == 3
assert sum(1 for r in d['rungs'] if r['default']) == 1
print('Rungs:')
for r in d['rungs']:
    flag = '*' if r['default'] else ' '
    print(f'  {flag} {r[\"model\"]:18s} wer={r[\"wer\"]}  p50={r[\"p50_latency_ms\"]}ms  vram={r[\"peak_vram_mb\"]}MB')
print(f'Default: {d[\"default_rung\"]}')
"

# No voice PII staged
git status --porcelain | grep -E 'reference_audio\.(wav|mp3|flac)' && echo "FAIL: voice PII staged" || echo "OK"
```
</verification>

<success_criteria>
- [ ] Three Whisper rungs benchmarked on the builder's voice
- [ ] Each rung has WER (normalized), p50/p95 latency, peak VRAM in results/whisper.json
- [ ] Exactly one rung marked `default: true` per Resolved Tension #2 logic
- [ ] Reference transcript is committed (public-domain composition); audio is NOT
- [ ] Unit tests for WER + default-picker pass 8/8
</success_criteria>

<output>
After completion, create `.planning/phases/00-measurement-gate/00-03-SUMMARY.md` summarizing:
- Per-rung WER + latency + VRAM (one-line table)
- Chosen default rung and the quantitative reason
- Whether Resolved Tension #2 cascade triggered (large-v3 FP16 forced as default → XTTS-over-F5 in Phase 2)
- Any hallucinations observed (PITFALLS.md #6 smoke test)
- Qualitative note from the builder: does the hypothesis read like what you said?
</output>
