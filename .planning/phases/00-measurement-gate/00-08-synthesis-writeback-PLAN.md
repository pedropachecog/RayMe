---
phase: 00-measurement-gate
plan: 08
type: execute
wave: 4
depends_on: [02, 03, 04, 05, 07, "07.1", "07.2"]
files_modified:
  - .planning/phases/00-measurement-gate/KEY_DECISIONS.md
  - .planning/phases/00-measurement-gate/results/phase0_summary.json
  - .planning/PROJECT.md
  - .planning/STATE.md
autonomous: false
requirements: []
user_setup: []

must_haves:
  truths:
    - "KEY_DECISIONS.md is a human-readable summary of every results/*.json file from plans 02-07"
    - "phase0_summary.json is a machine-readable consolidation with pointers to each source JSON and the final decisions"
    - "PROJECT.md has a new 'Phase 0 Key Decisions' section committing: chosen Whisper rung, chosen v1 TTS engine, Qwen3-TTS v1 disposition, FA2 verdict, and HTTPS strategy"
    - "STATE.md reflects Phase 0 complete with a Key Decisions summary and next-phase pointer"
    - "Any cascade triggers (Resolved Tension #2 or #3) are explicitly flagged with their downstream Phase 2 implications"
    - "Any TTS runtime or acceleration claim cites `results/tts_runtime_matrix.json` when that artifact exists; backend labels alone are not treated as proof of cross-runtime parity"
  artifacts:
    - path: ".planning/phases/00-measurement-gate/KEY_DECISIONS.md"
      provides: "Builder-facing summary: every decision from Phase 0 with the quantitative reason"
      contains: "# Phase 0 Key Decisions"
    - path: ".planning/phases/00-measurement-gate/results/phase0_summary.json"
      provides: "Machine-readable roll-up of all per-plan results JSONs + final decisions"
      contains: "decisions"
    - path: ".planning/PROJECT.md"
      provides: "Updated Key Decisions section reflecting the empirical Phase 0 outputs"
      contains: "Phase 0 Key Decisions"
    - path: ".planning/STATE.md"
      provides: "Updated project state: Phase 0 complete, pointers to next phase"
      contains: "Phase 0 complete"
  key_links:
    - from: ".planning/phases/00-measurement-gate/KEY_DECISIONS.md"
      to: "results/{whisper,tts_ttfa,tts_runtime_matrix,vram_soak_*,fa2_install,https_android}.json"
      via: "human-readable rendering of each JSON payload"
      pattern: "whisper\\.json|tts_ttfa\\.json|tts_runtime_matrix\\.json|fa2_install\\.json|https_android\\.json|vram_soak"
    - from: ".planning/PROJECT.md"
      to: ".planning/phases/00-measurement-gate/KEY_DECISIONS.md"
      via: "reference link from the updated Key Decisions section"
      pattern: "KEY_DECISIONS.md|phases/00"
---

<objective>
Consolidate every Phase 0 measurement into a single Key Decisions document, write the empirical outcomes back to PROJECT.md and STATE.md so Phase 1+ freezes the stack on data, and render a machine-readable summary JSON for tooling.

Purpose: Phase 0's deliverables are Key Decisions, not shipped features (per roadmap). Every downstream phase needs a single authoritative answer for: "what Whisper rung?", "what TTS engine?", "is Qwen3-TTS shipping in v1?", "what HTTPS strategy?", "is FA2 installed?". Without this writeback, the measurements exist in isolated JSON files and Phase 2 must re-discover them.

Output: `KEY_DECISIONS.md` (human-readable), `results/phase0_summary.json` (machine-readable roll-up), updated `PROJECT.md` + `STATE.md`.
</objective>

<execution_context>
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/workflows/execute-plan.md
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/00-measurement-gate/results/https_android.json
@.planning/phases/00-measurement-gate/results/whisper.json
@.planning/phases/00-measurement-gate/results/tts_ttfa.json
@.planning/phases/00-measurement-gate/results/vram_soak_f5.json
@.planning/phases/00-measurement-gate/results/vram_soak_xtts.json
@.planning/phases/00-measurement-gate/results/vram_soak_qwen3.json
@.planning/phases/00-measurement-gate/results/fa2_install.json
@.planning/phases/00-measurement-gate/results/tts_attention_matrix.json
@.planning/phases/00-measurement-gate/results/tts_runtime_matrix.json
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md

<interfaces>
The synthesis must resolve every quantitative cascade trigger from the roadmap:

**Resolved Tension #2 (Whisper default):**
- Whisper default rung = `results/whisper.json["default_rung"]`
- If `default_rung == "large-v3"` (FP16) AND its `peak_vram_mb > 8000`: the Resolved Tension #2 cascade fires -> in Phase 2, XTTS must replace F5 as v1 default (VRAM math).

**Resolved Tension #3 (TTS default):**
- v1 TTS default = `results/tts_ttfa.json["v1_default"]`
- If `v1_default == "f5"`: F5 kept as incumbent, plan for both XTTS and Qwen3 as secondary engines per their acceptance gates.
- If `v1_default == "xtts"`: F5 demoted to per-voice opt-in.
- If `v1_default == "qwen3"`: F5 AND XTTS both demoted; Qwen3 becomes primary. (Unlikely but possible.)

**Qwen3-TTS v1 disposition (QWEN3-TTS.md §7):**
- Accepted if: `tts_ttfa.json["qwen_gate"]["accepted"] == true` AND `vram_soak_qwen3.json["fits_3060_budget"] == true` AND (optionally) `fa2_install.json["installed"] == true` if 1.7B is desired.
- Rejected otherwise. When rejected: REQ-22 falls back to two engines, Voice Lab hides the Qwen option.

**TTS optimization backend labeling:**
- `tts_attention_matrix.json` is the source of truth for which backend was actually measured per engine (`eager`, `sdpa`, `flash_attention_2`, `not_supported`, `not_applicable`).
- The writeback must not present Qwen3 eager-baseline numbers as if they were FlashAttention-optimized results.

**TTS runtime / acceleration matrix:**
- `tts_runtime_matrix.json` is the source of truth for cross-runtime claims such as native Windows vs WSL Python vs WSL Triton for F5, XTTS baseline vs DeepSpeed-enabled paths, and Qwen eager vs FlashAttention 2 runs.
- If `tts_runtime_matrix.json` is missing, the writeback must explicitly say that the phase did not complete the requested runtime-matrix comparison and must avoid implying those permutations were measured.

**FA2 / Qwen3-TTS 1.7B:**
- 1.7B eligible iff `fa2_install.json["qwen17b_recommended"] == true`.
- Even if FA2 installed: only plan 1.7B if Qwen3-TTS passed its v1 acceptance gate in the first place.

**HTTPS strategy:**
- From `https_android.json["strategy"]` — expected to be `mkcert`. Pin in PROJECT.md.

**Hardware discrepancy note (per 00-RESEARCH.md Open Q #1):**
- All measurements were made on RTX 4090 (sm_89, 24 GB).
- Roadmap and REQ-02 reference RTX 3060 (sm_86, 12 GB).
- The `fits_3060_budget` flag in each soak JSON answers the 3060 question directly (peak_vram_mb < 11000).
- KEY_DECISIONS.md must include a "Hardware note" section noting the discrepancy + per-engine 3060 fit verdict.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Build phase0_summary.json + KEY_DECISIONS.md from all per-plan results</name>
  <files>
    .planning/phases/00-measurement-gate/results/phase0_summary.json
    .planning/phases/00-measurement-gate/KEY_DECISIONS.md
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/results/https_android.json
    .planning/phases/00-measurement-gate/results/whisper.json
    .planning/phases/00-measurement-gate/results/tts_ttfa.json
    .planning/phases/00-measurement-gate/results/vram_soak_f5.json
    .planning/phases/00-measurement-gate/results/vram_soak_xtts.json
    .planning/phases/00-measurement-gate/results/vram_soak_qwen3.json
    .planning/phases/00-measurement-gate/results/fa2_install.json
    .planning/research/QWEN3-TTS.md (§7 acceptance gate for cross-referencing)
    .planning/ROADMAP.md (Phase 0 success criteria)
  </read_first>
  <action>
    1. Read each of the 8 results JSONs above. If any is missing, record that fact in a "Missing Inputs" section of KEY_DECISIONS.md (do not fail — the synthesis proceeds with available data and flags gaps).

    2. Build `results/phase0_summary.json` — a consolidation:

       ```json
       {
         "meta": { "timestamp": "<ISO8601>", "phase": "00-measurement-gate" },
         "inputs": {
           "https_android":   "results/https_android.json",
           "whisper":         "results/whisper.json",
           "tts_ttfa":        "results/tts_ttfa.json",
           "tts_runtime_matrix": "results/tts_runtime_matrix.json",
           "vram_soak_f5":    "results/vram_soak_f5.json",
           "vram_soak_xtts":  "results/vram_soak_xtts.json",
           "vram_soak_qwen3": "results/vram_soak_qwen3.json",
           "fa2_install":     "results/fa2_install.json"
         },
         "measured_on": {
           "gpu": "<from any results meta.gpu.name>",
           "vram_total_mb": <integer>,
           "compute_capability": "<>",
           "python": "3.11.x",
           "torch": "2.5.1+cu121"
         },
         "decisions": {
           "https_strategy":       "mkcert" | null,
           "whisper_default_rung": "distil-large-v3" | "large-v3-turbo" | "large-v3",
           "whisper_default_compute_type": "int8_float16" | "float16",
           "tts_v1_default":       "f5" | "xtts" | "qwen3" | null,
           "qwen3_v1_accepted":    true | false,
           "qwen3_v1_variant":     "0.6B-Base" | "1.7B-Base" | null,
           "fa2_installed":        true | false
         },
         "cascades_triggered": {
           "resolved_tension_2_whisper_fp16_forces_xtts":  true | false,
           "resolved_tension_3_f5_demoted":                 true | false,
           "qwen3_gate_rejected":                            true | false,
           "fa2_install_failed":                             true | false
         },
         "vram_budget_3060": {
           "f5_fits":    true | false,
           "xtts_fits":  true | false,
           "qwen3_0_6b_fits": true | false,
           "notes": "Measured on RTX 4090 (24 GB); fits_3060 computed from peak_vram_mb < 11000."
         }
       }
       ```

       Use Python (invoked via the Phase 0 venv, since it needs to parse JSON and compute the decisions):

       ```python
       # Run inline or as a throwaway helper. This is NOT a committed probe.
       import json
       from datetime import datetime, timezone
       from pathlib import Path

       ROOT = Path(".planning/phases/00-measurement-gate")
       RESULTS = ROOT / "results"

       def _load(p):
           path = RESULTS / p
           if not path.exists():
               return None
           return json.loads(path.read_text())

       https = _load("https_android.json") or {}
       whisp = _load("whisper.json") or {}
       tts   = _load("tts_ttfa.json") or {}
       tts_runtime = _load("tts_runtime_matrix.json") or {}
       soak_f5   = _load("vram_soak_f5.json")   or {}
       soak_xtts = _load("vram_soak_xtts.json") or {}
       soak_qwen = _load("vram_soak_qwen3.json") or {}
       fa2    = _load("fa2_install.json") or {}

       # Derive decisions
       default_rung = whisp.get("default_rung")
       rungs_by_name = {r["model"]: r for r in whisp.get("rungs", [])}
       default_rung_obj = rungs_by_name.get(default_rung, {})
       whisper_compute_type = default_rung_obj.get("compute_type")

       tts_default = tts.get("v1_default")
       qwen_gate = tts.get("qwen_gate", {})
       qwen_accepted = bool(qwen_gate.get("accepted"))
       fa2_installed = bool(fa2.get("installed"))

       # Qwen3 variant: 1.7B only if FA2 installed AND Qwen accepted
       qwen_variant = None
       if qwen_accepted:
           qwen_variant = "1.7B-Base" if fa2_installed else "0.6B-Base"

       # Cascade: Resolved Tension #2
       rt2_triggered = (default_rung == "large-v3" and
                        default_rung_obj.get("peak_vram_mb", 0) > 8000)
       # Cascade: Resolved Tension #3 (F5 demoted)
       rt3_triggered = (tts_default in ("xtts", "qwen3"))

       # 3060 fit per engine
       def fits(d): return bool(d.get("fits_3060_budget"))

       payload = {
           "meta": {
               "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "phase": "00-measurement-gate",
           },
           "inputs": {
               "https_android":   "results/https_android.json",
               "whisper":         "results/whisper.json",
               "tts_ttfa":        "results/tts_ttfa.json",
               "tts_runtime_matrix": "results/tts_runtime_matrix.json",
               "vram_soak_f5":    "results/vram_soak_f5.json",
               "vram_soak_xtts":  "results/vram_soak_xtts.json",
               "vram_soak_qwen3": "results/vram_soak_qwen3.json",
               "fa2_install":     "results/fa2_install.json",
           },
           "measured_on": (whisp.get("meta", {}).get("gpu")
                           or tts.get("meta", {}).get("gpu")
                           or {}),
           "decisions": {
               "https_strategy":       https.get("strategy"),
               "whisper_default_rung": default_rung,
               "whisper_default_compute_type": whisper_compute_type,
               "tts_v1_default":       tts_default,
               "qwen3_v1_accepted":    qwen_accepted,
               "qwen3_v1_variant":     qwen_variant,
               "fa2_installed":        fa2_installed,
           },
           "cascades_triggered": {
               "resolved_tension_2_whisper_fp16_forces_xtts": rt2_triggered,
               "resolved_tension_3_f5_demoted":                rt3_triggered,
               "qwen3_gate_rejected":                          (not qwen_accepted),
               "fa2_install_failed":                           (not fa2_installed),
           },
           "vram_budget_3060": {
               "f5_fits":         fits(soak_f5),
               "xtts_fits":       fits(soak_xtts),
               "qwen3_0_6b_fits": fits(soak_qwen),
               "notes": "Measured on RTX 4090; fits_3060 computed from peak_vram_mb < 11000.",
           },
       }
       (RESULTS / "phase0_summary.json").write_text(json.dumps(payload, indent=2))
       ```

    3. Build `.planning/phases/00-measurement-gate/KEY_DECISIONS.md`:

       Template structure (fill from phase0_summary.json + each results JSON):

       ```markdown
       # Phase 0 Key Decisions

       **Phase:** 00-measurement-gate
       **Completed:** <ISO date>
       **Hardware:** RTX 4090 (sm_89, 24 GB). *Roadmap references RTX 3060 (12 GB) — see Hardware Note below.*
       **Runtime:** Python 3.11.5 + torch 2.5.1+cu121

       ## Summary Table

       | Decision | Value | Source |
       |---|---|---|
       | HTTPS strategy | `{mkcert}` | results/https_android.json |
       | Whisper default rung | `{distil-large-v3|large-v3-turbo|large-v3}` @ `{compute_type}` | results/whisper.json |
       | v1 TTS default engine | `{f5|xtts|qwen3}` | results/tts_ttfa.json |
       | Qwen3-TTS v1 disposition | `{accepted|rejected}` | results/tts_ttfa.json + vram_soak_qwen3.json |
       | Qwen3-TTS variant (if accepted) | `{0.6B-Base|1.7B-Base}` | derived from fa2_install.json |
       | FlashAttention 2 installed | `{yes|no}` (build: `{duration}`s) | results/fa2_install.json |

       ## 1. HTTPS on Android

       *(Summarize https_android.json — exact URL that worked, Android browser, and any notes.)*

       ## 2. Whisper WER

       *(Table of the 3 rungs with WER / p50 / peak VRAM; explain why the default rung was chosen; note Resolved Tension #2 cascade if triggered.)*

       ## 3. TTS TTFA

       *(Table of the 3 engines with TTFA / RTF / peak VRAM; explain why the v1 default was chosen; flag Qwen3 gate decision + reasons; note Resolved Tension #3 cascade if triggered.)*

       ## 4. VRAM Soak (30-min cycling)

       *(Table of the 3 engines with peak_vram_mb / growth_detected / fits_3060_budget; flag any engine that exceeded 11 GB on the 3060-constrained basis.)*

       ## 5. FlashAttention 2

       *(Install outcome, build duration, version if installed, failure_reason if not; recommendation on Qwen3-TTS 1.7B eligibility.)*

       ## Cascades triggered

       *(For each cascade flag in phase0_summary.json that is true, write one paragraph explaining the downstream Phase 2+ implication.)*

       ## Hardware Note

       All measurements were performed on an RTX 4090 (24 GB, sm_89), not the RTX 3060 (12 GB, sm_86) referenced in REQ-02 and STACK.md. Every soak JSON has a `fits_3060_budget` flag computed from `peak_vram_mb < 11000` to answer the 3060 VRAM question directly. TTFA and RTF numbers were NOT extrapolated to 3060 — they are 4090 measurements. Phase 2 should either (a) re-measure on the 3060 if the builder has one, or (b) accept the open question that 3060 TTFA may be ~2.5x higher and bias toward the lower-RTF engine per the extrapolation math in QWEN3-TTS.md §3.3.

       ## Phase 1+ implications

       - STT default: `{rung}` (@ `{compute_type}`)
       - TTS v1 default: `{engine}`
       - Engines shipping in v1 Voice Lab: `{two-engine-list|three-engine-list}`
       - HTTPS: `{strategy}` documented in `HTTPS-SETUP.md`
       - PROJECT.md Key Decisions section updated (see that file).

       ## Source JSONs

       - [HTTPS Android](results/https_android.json)
       - [Whisper WER](results/whisper.json)
       - [TTS TTFA](results/tts_ttfa.json)
       - [VRAM soak F5](results/vram_soak_f5.json)
       - [VRAM soak XTTS](results/vram_soak_xtts.json)
       - [VRAM soak Qwen3](results/vram_soak_qwen3.json)
       - [FA2 install](results/fa2_install.json)
       ```

       Render the actual values from phase0_summary.json. Use the Phase 0 venv's Python for the render — a simple templating pass is fine; do not add new dependencies.
  </action>
  <verify>
    <automated>test -f .planning/phases/00-measurement-gate/results/phase0_summary.json &amp;&amp; test -f .planning/phases/00-measurement-gate/KEY_DECISIONS.md &amp;&amp; .planning/phases/00-measurement-gate/.venv-phase0/Scripts/python.exe -c "import json; d = json.load(open('.planning/phases/00-measurement-gate/results/phase0_summary.json')); assert 'decisions' in d and 'cascades_triggered' in d and 'vram_budget_3060' in d; assert set(d['decisions'].keys()) &gt;= {'https_strategy','whisper_default_rung','tts_v1_default','qwen3_v1_accepted','fa2_installed'}; print('OK')" &amp;&amp; grep -q "# Phase 0 Key Decisions" .planning/phases/00-measurement-gate/KEY_DECISIONS.md &amp;&amp; grep -q "Hardware Note" .planning/phases/00-measurement-gate/KEY_DECISIONS.md</automated>
  </verify>
  <acceptance_criteria>
    - File `results/phase0_summary.json` exists with valid JSON.
    - JSON has top-level keys `meta`, `inputs`, `measured_on`, `decisions`, `cascades_triggered`, `vram_budget_3060`.
    - `decisions` has all expected keys from the current interfaces.
    - File `KEY_DECISIONS.md` exists with a level-1 heading `# Phase 0 Key Decisions`.
    - KEY_DECISIONS.md references every source JSON (grep: `whisper.json`, `tts_ttfa.json`, `vram_soak_f5.json`, `vram_soak_xtts.json`, `vram_soak_qwen3.json`, `fa2_install.json`, `https_android.json`).
    - KEY_DECISIONS.md has a "Hardware Note" section calling out the 4090 vs 3060 discrepancy.
    - KEY_DECISIONS.md has a "Cascades triggered" section (even if no cascades fired, the section exists with "none triggered" text).
  </acceptance_criteria>
  <done>Human-readable summary + machine-readable roll-up produced.</done>
</task>

<task type="checkpoint:decision" gate="blocking">
  <name>Task 2: Builder reviews KEY_DECISIONS.md and approves writeback to PROJECT.md + STATE.md</name>
  <files>
    .planning/PROJECT.md
    .planning/STATE.md
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/KEY_DECISIONS.md  (the proposed decisions the builder is approving)
    .planning/phases/00-measurement-gate/results/phase0_summary.json
    .planning/PROJECT.md  (current state — so the writeback only adds/updates relevant sections)
    .planning/STATE.md  (current state)
  </read_first>
  <decision>
    The builder reviews `KEY_DECISIONS.md` and approves (or rejects) the propagation of its decisions into `PROJECT.md` and `STATE.md`. Rejection paths exist because a measurement may have produced a clear result that the builder is willing to override (e.g., "Whisper picked distil but I want to pay the 2pp WER for better accent handling").
  </decision>
  <context>
    KEY_DECISIONS.md proposes 5 decisions to pin in PROJECT.md's Key Decisions section:
    - HTTPS strategy
    - Whisper default rung
    - v1 TTS default engine
    - Qwen3-TTS v1 disposition (accepted/rejected) + variant
    - FA2 status + Qwen3-TTS 1.7B eligibility

    Each decision has a quantitative backing. Rejection should come with a reason (recorded in STATE.md blockers or RETROSPECTIVE.md).
  </context>
  <options>
    <option id="approve-all">
      <name>Approve all decisions as proposed</name>
      <pros>
        - Phase 1 can start immediately with pinned defaults
        - Every decision has quantitative backing
        - No re-measurement cost
      </pros>
      <cons>
        - None if measurements are sound
      </cons>
    </option>
    <option id="approve-with-override">
      <name>Approve with specific overrides</name>
      <pros>
        - Builder retains editorial judgment (e.g., prefers large-v3 despite distil being within 2pp)
      </pros>
      <cons>
        - Overrides MUST be recorded with the reason so future-you does not lose context
      </cons>
    </option>
    <option id="reject-request-remeasure">
      <name>Reject — request re-measurement of a specific probe</name>
      <pros>
        - Fixes a known measurement bug (e.g., noisy WAV recording, wrong Whisper compute_type)
      </pros>
      <cons>
        - Blocks Phase 1 start until the specific probe is re-run
        - The orchestrator routes to a gap-closure plan for the re-measurement
      </cons>
    </option>
  </options>
  <action>
    When the builder approves (any option above), apply the following writebacks. Record overrides explicitly in the PROJECT.md section.

    **1. Update PROJECT.md — append or replace a "## Phase 0 Key Decisions" section:**

    ```markdown
    ## Phase 0 Key Decisions

    *Frozen <ISO date> from `.planning/phases/00-measurement-gate/KEY_DECISIONS.md`
    (machine-readable: `.planning/phases/00-measurement-gate/results/phase0_summary.json`).*

    - **HTTPS strategy (REQ-A1):** `mkcert` on LAN. Setup: see `.planning/phases/00-measurement-gate/HTTPS-SETUP.md`.
    - **STT default (REQ-A3):** faster-whisper `{model}` (`{compute_type}`). WER on builder's Spanish-accented English = `{wer}`. Peak VRAM = `{mb}` MB.
    - **TTS v1 default (Resolved Tension #3):** `{engine}`. TTFA = `{ms}` ms, RTF = `{rtf}`.
    - **TTS v1 engine roster (REQ-22):** {F5-TTS, XTTS v2} or {F5-TTS, XTTS v2, Qwen3-TTS 0.6B-Base} — depending on Qwen gate outcome.
    - **FA2 (Qwen3-TTS 1.7B eligibility):** {installed v{x.y.z} | not installed; reason: {...}}. Qwen3-TTS 1.7B is { eligible | ineligible } for v1.
    - **Hardware discrepancy note:** measured on RTX 4090; REQ-02 assumes RTX 3060. Per-engine 3060-fit: F5={yes|no}, XTTS={yes|no}, Qwen3-0.6B={yes|no}.
    - **Overrides (if any):** {list of decisions the builder manually overrode and why, else "none"}.
    ```

    Preserve all other content in PROJECT.md. If a "Phase 0 Key Decisions" section already exists, replace it in place.

    **2. Update STATE.md:**

    - Mark Phase 0 as complete (append or update a "Phases Completed" section).
    - Add a "Current Decisions" block mirroring the PROJECT.md bullets (so `/gsd-status` and future planners see them at a glance).
    - Point to Phase 1 as the next phase.

    If STATE.md does not exist yet, create it with a minimal template.

    **3. Commit both files** with message:
    ```
    docs(00): Phase 0 decisions frozen - Whisper/TTS/LLM/HTTPS pinned
    ```
  </action>
  <acceptance_criteria>
    - `.planning/PROJECT.md` contains a section heading `## Phase 0 Key Decisions`.
    - That section contains all five decision bullets (HTTPS, STT, TTS default, TTS roster, FA2).
    - `.planning/STATE.md` references "Phase 0 complete" or equivalent status marker.
    - `.planning/STATE.md` has a Current Decisions block that matches the PROJECT.md section's values.
    - Git commit contains both files.
  </acceptance_criteria>
  <resume-signal>
    Reply with one of:
    - `approve` — apply all decisions as proposed
    - `approve with overrides: <list>` — apply with specific overrides and reasons
    - `reject: remeasure <probe-name> because <reason>` — skip writeback, trigger a gap-closure plan
  </resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| None (internal) | Pure doc writeback; no code, no endpoints, no secrets. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-08-01 | Tampering | PROJECT.md / STATE.md | accept | Changes are versioned in git; any tampering is visible in the diff. |
| T-00-08-02 | Info Disclosure | KEY_DECISIONS.md contains summarized measurements | accept | All summarized data is already in the individual results JSONs (already committed where appropriate). No new sensitive data surfaced. |

No high-severity threats. This plan is doc-only.
</threat_model>

<verification>
```bash
# Structural checks
test -f .planning/phases/00-measurement-gate/KEY_DECISIONS.md
test -f .planning/phases/00-measurement-gate/results/phase0_summary.json
grep -q "## Phase 0 Key Decisions" .planning/PROJECT.md
grep -qE "Phase 0 (complete|Complete|COMPLETE)" .planning/STATE.md

# Decision consistency: every decision in PROJECT.md must match phase0_summary.json
.venv-phase0/Scripts/python.exe -c "
import json
s = json.load(open('.planning/phases/00-measurement-gate/results/phase0_summary.json'))
p = open('.planning/PROJECT.md', encoding='utf-8').read()
d = s['decisions']
assert d['whisper_default_rung'] in p, f'missing whisper rung {d[\"whisper_default_rung\"]}'
assert d['tts_v1_default'] in p, f'missing tts default {d[\"tts_v1_default\"]}'
print('OK: decisions consistent between summary JSON and PROJECT.md')
"
```
</verification>

<success_criteria>
- [ ] KEY_DECISIONS.md renders every Phase 0 measurement with a quantitative reason
- [ ] phase0_summary.json rolls up all per-plan JSONs + the 6 cascade flags
- [ ] PROJECT.md has an approved "Phase 0 Key Decisions" section
- [ ] STATE.md reflects Phase 0 complete + current decisions
- [ ] Any builder overrides are explicitly listed with reasons
- [ ] Cascades (Resolved Tension #2/#3, Qwen gate, FA2) are flagged for Phase 2+
</success_criteria>

<output>
After completion, create `.planning/phases/00-measurement-gate/00-08-SUMMARY.md` summarizing:
- Six Phase 0 decisions committed to PROJECT.md
- Any builder overrides + reasons
- Cascade triggers fired + downstream implications
- Readiness for `/gsd-plan-phase 1`
</output>
