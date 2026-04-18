---
phase: 00-measurement-gate
plan: 06
type: execute
wave: 2
depends_on: [01]
files_modified:
  - .planning/phases/00-measurement-gate/probes/llm_cancel.py
  - .planning/phases/00-measurement-gate/probes/test_llm_cancel.py
  - .planning/phases/00-measurement-gate/results/llm_cancel.json
autonomous: false
requirements: []
user_setup:
  - service: ollama-model
    why: "The cancel probe needs a local LLM to stream against. Ollama is installed but has no model loaded at research time."
    env_vars: []
    dashboard_config:
      - task: "Start ollama and pull a small model: `ollama serve` (if not running) + `ollama pull llama3.2:3b`. Confirm `ollama list` shows the model."
        location: "Any terminal"

must_haves:
  truths:
    - "At least 5 cancel trials have been run against a local OpenAI-compatible LLM server (ollama or llama-server)"
    - "Each trial records: stream_close_ms_after_start, gpu_idle_ms_after_close (via nvidia-smi polling), tokens_received_before_cancel"
    - "p50 cancel_to_idle_ms is recorded in results/llm_cancel.json"
    - "Phase 4 barge-in budget target: cancel_to_idle_ms < 200 ms (Resolved Risk #3 trigger)"
    - "The chosen LLM server (ollama vs llama-server) is recorded so Phase 2 can freeze the v1 LLM contract"
  artifacts:
    - path: ".planning/phases/00-measurement-gate/probes/llm_cancel.py"
      provides: "Streaming cancel probe with nvidia-smi GPU-idle polling"
      contains: "AbortController"
    - path: ".planning/phases/00-measurement-gate/probes/test_llm_cancel.py"
      provides: "Unit tests for the nvidia-smi output parser + cancel-to-idle calculator"
      contains: "def test_parse_nvidia_smi"
    - path: ".planning/phases/00-measurement-gate/results/llm_cancel.json"
      provides: "Phase 0 criterion #5 deliverable — per-trial cancel metrics + p50 + server choice"
      contains: "cancel_to_idle_ms"
  key_links:
    - from: "probes/llm_cancel.py"
      to: "httpx.AsyncClient stream()"
      via: "async context manager + explicit abort via response.aclose()"
      pattern: "async with.*stream|aclose"
    - from: "probes/llm_cancel.py"
      to: "nvidia-smi subprocess"
      via: "subprocess.Popen polling GPU utilization at 100ms interval for 2s post-cancel"
      pattern: "nvidia-smi.*utilization"
---

<objective>
Empirically verify that closing a streaming OpenAI-compatible Chat Completions request to the local LLM server actually aborts generation on the GPU, and measure the latency from stream-close to GPU-idle.

Purpose: Phase 0 success criterion #5 and Phase 4's barge-in acceptance criterion. Research (PITFALLS.md #8) flags that some OpenAI-compatible servers (llama-server, LM Studio, early vLLM) only notice disconnection at the next token-write or sampling boundary — cancellations that take 1-2 seconds to reach the GPU defeat barge-in UX. This probe confirms cancel semantics on the builder's specific server choice so Phase 2 can freeze the v1 LLM contract.

Output: `probes/llm_cancel.py` + `results/llm_cancel.json` with per-trial metrics and p50 cancel-to-idle latency.
</objective>

<execution_context>
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/workflows/execute-plan.md
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/00-measurement-gate/00-RESEARCH.md
@.planning/phases/00-measurement-gate/00-VALIDATION.md
@.planning/research/PITFALLS.md

<interfaces>
From 00-RESEARCH.md §Standard Stack: both `llama-server` (llama.cpp) and `ollama 0.17.0` are installed. Planning guidance says **default to ollama** for simpler API and pull-model UX; support llama-server as alternative.

Ollama OpenAI-compatible endpoint:
- Base URL: `http://localhost:11434/v1`
- Path: `/chat/completions`
- Streaming: `{"stream": true}`
- Works with httpx, openai-python, etc.
- To start: `ollama serve` (daemon)
- To pull a model: `ollama pull llama3.2:3b` (~2 GB, small, fast, streams rapidly)

Cancel pattern (00-RESEARCH.md §Architecture Patterns Pattern 3):
```python
import asyncio, time
import httpx

async def probe_llm_cancel(base_url: str, model: str):
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        async with client.stream("POST", "/v1/chat/completions", json={
            "model": model,
            "messages": [{"role": "user", "content": "Write a 500-word essay on gardens."}],
            "stream": True, "max_tokens": 500,
        }) as response:
            t_start = time.perf_counter()
            tokens_seen = 0
            async for chunk in response.aiter_lines():
                tokens_seen += 1
                if time.perf_counter() - t_start > 0.5:  # cancel after ~500 ms
                    break  # aexit closes the stream
    t_close = time.perf_counter()
    # Poll nvidia-smi for GPU utilization dropping to 0 or near-0
    return t_start, t_close, tokens_seen
```

nvidia-smi polling (100 ms interval):
```bash
nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -l 0.1
# Output: integer percent per line, one per sample. Parser strips trailing units if present.
# Python equivalent: subprocess with --query-gpu=utilization.gpu --format=csv,noheader,nounits -lms 100
```

Python nvidia-smi poller (replaces `-lms` which is not on all versions):
```python
import subprocess, time
def poll_gpu_util(duration_s: float, interval_s: float = 0.1):
    samples = []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < duration_s:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu",
             "--format=csv,noheader,nounits"], text=True, timeout=2,
        ).strip()
        samples.append({"t": time.perf_counter() - t0, "util": int(out.splitlines()[0])})
        time.sleep(interval_s)
    return samples

def first_idle_ms(samples, threshold_pct=5):
    for s in samples:
        if s["util"] <= threshold_pct:
            return s["t"] * 1000
    return None
```

Phase 4 acceptance: `cancel_to_idle_ms < 200` across p50 of >=5 trials.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Build llm_cancel.py + unit tests for the nvidia-smi parser + idle detector</name>
  <files>
    .planning/phases/00-measurement-gate/probes/llm_cancel.py
    .planning/phases/00-measurement-gate/probes/test_llm_cancel.py
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/00-RESEARCH.md (§Architecture Patterns Pattern 3 — LLM cancel probe; §Standard Stack — LLM servers)
    .planning/research/PITFALLS.md (Pitfall #8 — LLM cancel semantics)
  </read_first>
  <behavior>
    - Test 1 (parse nvidia-smi single-gpu output): `parse_nvidia_smi_gpu_util("45\n")` returns `45`.
    - Test 2 (parse with whitespace): `parse_nvidia_smi_gpu_util("  12  \n")` returns `12`.
    - Test 3 (parse with units suffix): `parse_nvidia_smi_gpu_util("23 %\n")` returns `23` (strip ' %' defensively).
    - Test 4 (first_idle_ms detects idle): samples `[{t:0,util:95},{t:0.1,util:80},{t:0.2,util:10},{t:0.3,util:2}]` -> returns 200 (t in ms when util <= 5).
    - Test 5 (first_idle_ms returns None if never idle): samples `[{t:0,util:95},{t:0.1,util:80}]` -> returns `None`.
    - Test 6 (compute_p50_cancel_ms): `[{"cancel_to_idle_ms": 120}, {"cancel_to_idle_ms": 150}, {"cancel_to_idle_ms": 180}, {"cancel_to_idle_ms": 200}, {"cancel_to_idle_ms": 250}]` -> returns 180.
    - Test 7 (compute_p50 handles None): `[{"cancel_to_idle_ms": 120}, {"cancel_to_idle_ms": None}]` -> returns 120 (ignores Nones) OR returns None if all are None.
  </behavior>
  <action>
    1. Create `.planning/phases/00-measurement-gate/probes/llm_cancel.py`:

       ```python
       """LLM mid-stream cancel probe for Phase 0 success criterion #5.

       Opens a streaming Chat Completions request, waits ~500 ms into the
       stream, closes the connection, then polls nvidia-smi for GPU
       utilization dropping to idle (<= 5%). Records cancel_to_idle_ms per trial.

       Usage:
         # First: ensure the server is running and a model is loaded.
         #   ollama serve               # in another terminal
         #   ollama pull llama3.2:3b     # once

         .venv-phase0/Scripts/python.exe probes/llm_cancel.py \
           --base-url http://localhost:11434/v1 \
           --model llama3.2:3b \
           --trials 5 \
           --output results/llm_cancel.json

       Fallback to llama-server: change --base-url to the llama-server port.
       """
       from __future__ import annotations
       import argparse
       import asyncio
       import json
       import statistics
       import subprocess
       import sys
       import time
       from pathlib import Path
       from typing import Any

       from bench_utils import write_results

       CANCEL_AFTER_S = 0.5
       POLL_WINDOW_S = 2.0
       POLL_INTERVAL_S = 0.1
       IDLE_THRESHOLD_PCT = 5


       def parse_nvidia_smi_gpu_util(raw: str) -> int:
           """Parses one line of `nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits`.
           Defensive against trailing ' %' if nounits is ignored for some reason.
           """
           line = raw.strip().splitlines()[0].strip()
           # Strip trailing '%' and whitespace
           line = line.rstrip("%").rstrip()
           return int(line)


       def first_idle_ms(samples: list[dict[str, Any]],
                         threshold_pct: int = IDLE_THRESHOLD_PCT) -> float | None:
           """Returns the time in ms (relative to samples[0]) of the first
           sample whose GPU utilization is <= threshold. Returns None if
           no sample reached idle."""
           for s in samples:
               if s["util"] <= threshold_pct:
                   return round(s["t"] * 1000, 1)
           return None


       def compute_p50_cancel_ms(trials: list[dict[str, Any]]) -> float | None:
           vals = [t["cancel_to_idle_ms"] for t in trials
                   if t.get("cancel_to_idle_ms") is not None]
           if not vals:
               return None
           return round(statistics.median(vals), 1)


       def poll_gpu_util(duration_s: float, interval_s: float = POLL_INTERVAL_S) -> list[dict]:
           """Polls nvidia-smi utilization.gpu at the given interval for the
           given duration. Returns list of {t, util} samples.
           """
           samples: list[dict[str, Any]] = []
           t0 = time.perf_counter()
           while time.perf_counter() - t0 < duration_s:
               t_sample = time.perf_counter() - t0
               try:
                   out = subprocess.check_output(
                       ["nvidia-smi", "--query-gpu=utilization.gpu",
                        "--format=csv,noheader,nounits"],
                       text=True, timeout=2,
                   )
                   util = parse_nvidia_smi_gpu_util(out)
               except Exception as e:
                   util = -1  # mark parse failure
               samples.append({"t": round(t_sample, 3), "util": util})
               time.sleep(interval_s)
           return samples


       async def one_trial(base_url: str, model: str, prompt: str) -> dict[str, Any]:
           import httpx
           tokens_seen = 0
           t_start = time.perf_counter()
           t_first_token: float | None = None

           async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
               async with client.stream("POST", "/chat/completions", json={
                   "model": model,
                   "messages": [{"role": "user", "content": prompt}],
                   "stream": True,
                   "max_tokens": 500,
               }) as response:
                   if response.status_code != 200:
                       body = await response.aread()
                       raise RuntimeError(
                           f"server returned {response.status_code}: {body[:200]!r}"
                       )
                   async for line in response.aiter_lines():
                       if not line.strip():
                           continue
                       if t_first_token is None:
                           t_first_token = time.perf_counter()
                       tokens_seen += 1
                       if time.perf_counter() - t_start > CANCEL_AFTER_S:
                           break  # triggers aexit -> connection close
           t_close = time.perf_counter()

           # Poll nvidia-smi starting right after close
           samples = poll_gpu_util(POLL_WINDOW_S)
           idle_ms = first_idle_ms(samples)

           return {
               "tokens_seen": tokens_seen,
               "time_to_first_token_ms": round(((t_first_token or t_start) - t_start) * 1000, 1),
               "stream_close_ms_after_start": round((t_close - t_start) * 1000, 1),
               "cancel_to_idle_ms": idle_ms,
               "poll_samples": samples,
           }


       async def run_trials(base_url: str, model: str, trials: int) -> dict[str, Any]:
           prompt = "Write a 500-word essay about the history of gardens."
           trial_records: list[dict[str, Any]] = []
           for i in range(trials):
               print(f"[cancel] Trial {i+1}/{trials}...", flush=True)
               try:
                   r = await one_trial(base_url, model, prompt)
                   r["trial"] = i + 1
                   trial_records.append(r)
                   print(f"[cancel]   tokens={r['tokens_seen']} "
                         f"ttft={r['time_to_first_token_ms']}ms "
                         f"cancel_to_idle={r['cancel_to_idle_ms']}ms", flush=True)
               except Exception as e:
                   print(f"[cancel]   FAILED: {e!r}", file=sys.stderr)
                   trial_records.append({"trial": i + 1, "error": repr(e),
                                         "cancel_to_idle_ms": None})
               # Cool off between trials
               await asyncio.sleep(1.0)

           p50 = compute_p50_cancel_ms(trial_records)
           return {
               "probe": "llm_cancel",
               "base_url": base_url,
               "model": model,
               "trials": trial_records,
               "p50_cancel_to_idle_ms": p50,
               "meets_phase4_budget_200ms": (p50 is not None and p50 < 200),
           }


       def main() -> int:
           ap = argparse.ArgumentParser()
           ap.add_argument("--base-url", default="http://localhost:11434/v1",
                           help="OpenAI-compatible base URL (ollama: 11434/v1, "
                                "llama-server typically 8080/v1)")
           ap.add_argument("--model", default="llama3.2:3b",
                           help="Model name the server exposes")
           ap.add_argument("--trials", type=int, default=5)
           ap.add_argument("--output", required=True)
           args = ap.parse_args()

           try:
               payload = asyncio.run(run_trials(args.base_url, args.model, args.trials))
           except Exception as e:
               print(f"[cancel] ERROR: {e!r}", file=sys.stderr)
               return 2

           write_results(args.output, payload)
           print(f"\n[cancel] p50 cancel_to_idle = {payload['p50_cancel_to_idle_ms']} ms "
                 f"(budget 200 ms, meets={payload['meets_phase4_budget_200ms']})",
                 flush=True)
           return 0


       if __name__ == "__main__":
           sys.exit(main())
       ```

    2. Create `.planning/phases/00-measurement-gate/probes/test_llm_cancel.py`:

       ```python
       """Unit tests for llm_cancel.py — parser + idle detector + p50."""
       from llm_cancel import (
           parse_nvidia_smi_gpu_util,
           first_idle_ms,
           compute_p50_cancel_ms,
       )


       def test_parse_nvidia_smi_simple():
           assert parse_nvidia_smi_gpu_util("45\n") == 45


       def test_parse_nvidia_smi_whitespace():
           assert parse_nvidia_smi_gpu_util("  12  \n") == 12


       def test_parse_nvidia_smi_with_percent_suffix():
           assert parse_nvidia_smi_gpu_util("23 %\n") == 23


       def test_first_idle_ms_detects_idle():
           samples = [
               {"t": 0.0, "util": 95},
               {"t": 0.1, "util": 80},
               {"t": 0.2, "util": 10},
               {"t": 0.3, "util": 2},
           ]
           assert first_idle_ms(samples) == 200.0


       def test_first_idle_ms_returns_none_if_never_idle():
           samples = [{"t": 0.0, "util": 95}, {"t": 0.1, "util": 80}]
           assert first_idle_ms(samples) is None


       def test_compute_p50_median():
           trials = [
               {"cancel_to_idle_ms": 120},
               {"cancel_to_idle_ms": 150},
               {"cancel_to_idle_ms": 180},
               {"cancel_to_idle_ms": 200},
               {"cancel_to_idle_ms": 250},
           ]
           assert compute_p50_cancel_ms(trials) == 180.0


       def test_compute_p50_skips_none():
           trials = [{"cancel_to_idle_ms": 120}, {"cancel_to_idle_ms": None}]
           assert compute_p50_cancel_ms(trials) == 120.0


       def test_compute_p50_all_none():
           trials = [{"cancel_to_idle_ms": None}, {"cancel_to_idle_ms": None}]
           assert compute_p50_cancel_ms(trials) is None
       ```

    3. Run tests:
       ```bash
       cd .planning/phases/00-measurement-gate/probes
       ../.venv-phase0/Scripts/python.exe -m pytest test_llm_cancel.py -v
       ```
       Must pass 8/8 (7 listed above + test_compute_p50_all_none).
  </action>
  <verify>
    <automated>cd .planning/phases/00-measurement-gate/probes &amp;&amp; ../.venv-phase0/Scripts/python.exe -m pytest test_llm_cancel.py -v 2&gt;&amp;1 | tee /tmp/cancel_tests.out &amp;&amp; grep -q "8 passed" /tmp/cancel_tests.out &amp;&amp; grep -q "def parse_nvidia_smi_gpu_util" llm_cancel.py &amp;&amp; grep -q "response.aiter_lines" llm_cancel.py</automated>
  </verify>
  <acceptance_criteria>
    - File `probes/llm_cancel.py` exists with functions `parse_nvidia_smi_gpu_util`, `first_idle_ms`, `compute_p50_cancel_ms`, `one_trial`, `run_trials`, `main`, `poll_gpu_util`.
    - Uses `httpx.AsyncClient` with `stream()` context manager.
    - File `probes/test_llm_cancel.py` has 8 `def test_*` functions.
    - Pytest exits 0 with `8 passed`.
  </acceptance_criteria>
  <done>Cancel probe + unit-tested parser ready; waiting for ollama model to be pulled.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: Pull LLM model, run 5 cancel trials, verify p50 result</name>
  <files>
    .planning/phases/00-measurement-gate/results/llm_cancel.json
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/probes/llm_cancel.py (invocation reference)
    .planning/phases/00-measurement-gate/00-RESEARCH.md (§Open Questions #5 — LLM model availability)
  </read_first>
  <action>Human-verification checkpoint. Claude has already completed the automated work described under &lt;what-built&gt; above. The builder performs the steps in &lt;how-to-verify&gt; below and records the outcome as described; acceptance is gated on &lt;acceptance_criteria&gt;. When `workflow.auto_advance=true`, auto-mode auto-approves this checkpoint.</action>
  <what-built>
    Task 1 produced a probe that opens a streaming Chat Completions request, reads ~500 ms of tokens, closes the stream, then polls nvidia-smi for GPU-idle. Parser and reducer are unit-tested. What cannot be automated is pulling the LLM model weights (one-time, ~2 GB).
  </what-built>
  <how-to-verify>
    **Builder one-time setup:**

    1. Start ollama if not already running:
       ```bash
       # Windows: ollama service may already be installed; confirm with:
       curl http://localhost:11434/api/tags
       # If empty response or connection refused, start it:
       ollama serve  # leave running in another terminal
       ```

    2. Pull a small fast model (~2 GB download):
       ```bash
       ollama pull llama3.2:3b
       ollama list  # confirm the model is present
       ```

    3. Smoke test the endpoint:
       ```bash
       curl http://localhost:11434/v1/chat/completions \
         -H "Content-Type: application/json" \
         -d '{"model":"llama3.2:3b","messages":[{"role":"user","content":"Hi"}],"stream":false}'
       ```
       Expect a JSON response with a completion. If 404: endpoint path may differ for your ollama version — try `/api/chat` or upgrade.

    **Claude runs the probe:**

    ```bash
    cd .planning/phases/00-measurement-gate
    .venv-phase0/Scripts/python.exe probes/llm_cancel.py \
      --base-url http://localhost:11434/v1 \
      --model llama3.2:3b \
      --trials 5 \
      --output results/llm_cancel.json
    ```

    Expected runtime: ~20 seconds (5 trials × ~3s each).

    **Fallback to llama-server IF ollama fails:**
    ```bash
    # Separate terminal: start llama-server with a GGUF model
    llama-server -m <path/to/model.gguf> --port 8080

    # Re-run probe:
    .venv-phase0/Scripts/python.exe probes/llm_cancel.py \
      --base-url http://localhost:8080/v1 \
      --model <exposed-model-name> \
      --trials 5 \
      --output results/llm_cancel.json
    ```

    **Acceptance check (automated):**
    ```bash
    .venv-phase0/Scripts/python.exe -c "
    import json
    d = json.load(open('results/llm_cancel.json'))
    assert len(d['trials']) == 5, f'expected 5 trials, got {len(d[\"trials\"])}'
    assert d['p50_cancel_to_idle_ms'] is not None, 'p50 is None - probably all trials failed'
    assert d['base_url'].startswith(('http://localhost:11434','http://localhost:8080'))
    print(f'p50 cancel_to_idle = {d[\"p50_cancel_to_idle_ms\"]} ms')
    print(f'meets_phase4_budget_200ms = {d[\"meets_phase4_budget_200ms\"]}')
    for t in d['trials']:
        if 'error' in t:
            print(f'  trial {t[\"trial\"]}: ERROR {t[\"error\"]}')
        else:
            print(f'  trial {t[\"trial\"]}: tokens={t[\"tokens_seen\"]} cancel_to_idle={t[\"cancel_to_idle_ms\"]}ms')
    "
    ```
  </how-to-verify>
  <acceptance_criteria>
    - File `.planning/phases/00-measurement-gate/results/llm_cancel.json` exists with valid JSON.
    - JSON has keys `trials` (length 5), `p50_cancel_to_idle_ms` (non-null), `meets_phase4_budget_200ms` (bool), `base_url`, `model`.
    - Each trial has either an `error` key or all of: `tokens_seen`, `stream_close_ms_after_start`, `cancel_to_idle_ms`, `poll_samples`.
    - At least 3 of 5 trials succeeded (non-error). If fewer, the probe failed the run and the orchestrator should investigate.
  </acceptance_criteria>
  <resume-signal>
    Reply "approved" with the p50 value if the probe completed. If the p50 is >= 200 ms, Phase 4's barge-in design needs reinforcement (falls back to pinning a specific LLM server in Key Decisions — Phase 8 handles the writeback).
  </resume-signal>
  <verify><automated>echo "checkpoint: acceptance delegated to &lt;acceptance_criteria&gt; above; pass when resume-signal received"</automated></verify>
  <done>Acceptance criteria above are satisfied and the builder returned the expected resume-signal.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Probe -> localhost LLM server | Local loopback only. No credentials; ollama has no auth. Not reachable from LAN per default ollama bind. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-06-01 | Info Disclosure | Prompt content sent to local LLM | accept | Prompt is hardcoded benign text ("Write a 500-word essay about gardens"). No user PII or credentials. |
| T-00-06-02 | DoS | Ollama OOM on too-large model | accept | `llama3.2:3b` (~2 GB) is small; fits comfortably on the 4090 alongside this probe's zero GPU load. |
| T-00-06-03 | Spoofing | Probe connects to localhost endpoint | accept | Loopback only; no network exposure. |

No high-severity threats. Probe is a short-lived local HTTP client.
</threat_model>

<verification>
```bash
.venv-phase0/Scripts/python.exe -c "
import json
d = json.load(open('results/llm_cancel.json'))
print(f'p50 = {d[\"p50_cancel_to_idle_ms\"]} ms (budget 200, pass={d[\"meets_phase4_budget_200ms\"]})')
print(f'server = {d[\"base_url\"]} ({d[\"model\"]})')
"
```
</verification>

<success_criteria>
- [ ] 5 cancel trials executed against the configured LLM server
- [ ] p50 cancel_to_idle_ms recorded
- [ ] Pass/fail for <200 ms Phase 4 budget recorded
- [ ] Server choice (ollama or llama-server) recorded for Phase 2 freeze
- [ ] Unit tests 8/8 passing
</success_criteria>

<output>
After completion, create `.planning/phases/00-measurement-gate/00-06-SUMMARY.md` summarizing:
- Chosen LLM server + model
- p50 cancel-to-idle latency
- Pass/fail against the 200 ms Phase 4 barge-in budget
- If fail: recommendation for Phase 2 LLM server pin (e.g., "use ollama with model X" or "pin OpenAI API as v1 LLM contract")
</output>
