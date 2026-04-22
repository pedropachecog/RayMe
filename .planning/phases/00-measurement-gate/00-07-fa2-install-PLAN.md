---
phase: 00-measurement-gate
plan: 07
type: execute
wave: 2
depends_on: [01]
files_modified:
  - .planning/phases/00-measurement-gate/probes/fa2_check.py
  - .planning/phases/00-measurement-gate/results/fa2_install.json
autonomous: true
requirements: []
user_setup: []

must_haves:
  truths:
    - "FlashAttention 2 install has been attempted under the Phase 0 venv on the backend's RTX 3060 (sm_86, 12 GB) after plan 01 provisions Python 3.11 + torch"
    - "Outcome (success / fail / timeout) is recorded with the build duration"
    - "If install succeeded: `from flash_attn import flash_attn_func` is verified to import"
    - "If install failed: the stderr tail is captured in the results JSON, and the Qwen3-TTS 1.7B feature flag is set to OFF in the recommendation field"
  artifacts:
    - path: ".planning/phases/00-measurement-gate/probes/fa2_check.py"
      provides: "FA2 install attempter + verifier + timeout wrapper"
      contains: "flash_attn_func"
    - path: ".planning/phases/00-measurement-gate/results/fa2_install.json"
      provides: "Phase 0 criterion #6 deliverable — installed (bool), version, build_duration_s, failure_reason, qwen17b_recommended"
      contains: "installed"
  key_links:
    - from: "probes/fa2_check.py"
      to: "pip install flash-attn via subprocess"
      via: "subprocess.run with 30-min timeout"
      pattern: "flash-attn"
    - from: "probes/fa2_check.py"
      to: "from flash_attn import flash_attn_func"
      via: "import probe after install attempt"
      pattern: "flash_attn_func"
---

<objective>
Attempt to install FlashAttention 2 under the Phase 0 venv and record whether the install (and subsequent import) succeeded, along with build duration. This is Phase 0 success criterion #6.

Purpose: Research (00-RESEARCH.md Pitfall #4 + STACK.md §Qwen3-TTS install friction + QWEN3-TTS.md §9.2) shows that FA2 will likely require a source build on this backend. The real host state is: Python 3.11 is not preinstalled yet, `nvcc` 11.7 is on PATH, and `cl.exe` is not on PATH. That makes this a realistic Windows tooling gate, not the previously assumed “already-provisioned 4090 workstation” case. **This plan's outcome directly gates Qwen3-TTS 1.7B adoption:** on 12 GB 3060, 1.7B without FA2 crosses the VRAM budget (QWEN3-TTS.md §3.2).

Output: `results/fa2_install.json` with installed flag, version, build_duration_s, failure_reason, and the qwen17b_recommended recommendation.
</objective>

<execution_context>
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/workflows/execute-plan.md
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/00-measurement-gate/00-RESEARCH.md
@.planning/research/STACK.md
@.planning/research/QWEN3-TTS.md

<interfaces>
From 00-RESEARCH.md §Code Examples → FlashAttention 2 Install and Verify:

```bash
# On the Phase 0 venv after plan 01 installs Python 3.11 + torch
# Re-research note: the host currently exposes nvcc 11.7 and no cl.exe on PATH
# First: try to find prebuilt wheel
.venv-phase0/Scripts/python.exe -m pip install flash-attn==2.8.3 --dry-run 2>&1 | head -20

# If source build needed:
set FLASH_ATTENTION_SKIP_CUDA_BUILD=FALSE
.venv-phase0/Scripts/python.exe -m pip install flash-attn --no-build-isolation

# Verify:
.venv-phase0/Scripts/python.exe -c "from flash_attn import flash_attn_func; print('FA2 installed')"
```

Timeout: 30 minutes (00-RESEARCH.md §Common Pitfalls #2). If the build has not completed by then, kill the subprocess and record `failure_reason: "build_timeout_30min"`.

Windows MSVC requirement: If the build chain is not present (no `cl.exe` in PATH, no MSVC Build Tools installed), the build will fail with a clear error from setuptools. Re-research found `cl.exe` absent on this host today. Capture the last ~50 lines of stderr for diagnosis.

Recommendation rule (QWEN3-TTS.md §3.2 + STACK.md VRAM Budget):
```python
def qwen17b_recommended(installed: bool) -> bool:
    # 1.7B without FA2 = ~8 GB on Windows => Whisper + VAD + 1.7B + slack > 11 GB => reject
    # 1.7B with FA2    = ~5-6 GB => fits with Whisper + slack => accept
    # 0.6B is always eligible regardless of FA2
    return installed
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write fa2_check.py (install + verify + timeout + result writer)</name>
  <files>
    .planning/phases/00-measurement-gate/probes/fa2_check.py
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/probes/bench_utils.py
    .planning/phases/00-measurement-gate/00-RESEARCH.md (§Code Examples → FA2 install; §Common Pitfalls #2 — build timeout + Windows MSVC)
    .planning/research/QWEN3-TTS.md (§3.2 VRAM math for 1.7B with/without FA2; §9.2 known bugs)
  </read_first>
  <action>
    Create `.planning/phases/00-measurement-gate/probes/fa2_check.py`:

    ```python
    """FlashAttention 2 install + verify for Phase 0 success criterion #6.

    Runs:
      1. `pip install flash-attn --no-build-isolation` with 30-min timeout
      2. On success: verify `from flash_attn import flash_attn_func`
      3. Emit results/fa2_install.json with installed/version/build_duration/
         failure_reason/qwen17b_recommended.

    Usage:
      .venv-phase0/Scripts/python.exe probes/fa2_check.py \
        --output results/fa2_install.json
    """
    from __future__ import annotations
    import argparse
    import os
    import subprocess
    import sys
    import time
    from pathlib import Path
    from typing import Any

    from bench_utils import write_results

    BUILD_TIMEOUT_S = 30 * 60  # 30 minutes per 00-RESEARCH.md Pitfall #2


    def attempt_install(python_exe: str) -> dict[str, Any]:
        """Runs `pip install flash-attn --no-build-isolation` with timeout.
        Returns dict with keys: exit_code, duration_s, timed_out, stdout_tail, stderr_tail.
        """
        env = os.environ.copy()
        env["FLASH_ATTENTION_SKIP_CUDA_BUILD"] = "FALSE"

        cmd = [python_exe, "-m", "pip", "install", "flash-attn", "--no-build-isolation"]
        print(f"[fa2] Running: {' '.join(cmd)}", flush=True)
        print(f"[fa2] Timeout: {BUILD_TIMEOUT_S}s ({BUILD_TIMEOUT_S//60} min)", flush=True)

        t0 = time.perf_counter()
        timed_out = False
        stdout = stderr = ""
        exit_code = -1

        try:
            proc = subprocess.run(
                cmd, env=env, capture_output=True, text=True,
                timeout=BUILD_TIMEOUT_S,
            )
            exit_code = proc.returncode
            stdout, stderr = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            timed_out = True
            stdout = e.stdout or ""
            stderr = e.stderr or ""
            exit_code = -1
        duration_s = time.perf_counter() - t0

        # Tail 4 KB of each stream (avoid bloating results JSON)
        return {
            "exit_code": exit_code,
            "duration_s": round(duration_s, 1),
            "timed_out": timed_out,
            "stdout_tail": stdout[-4000:],
            "stderr_tail": stderr[-4000:],
        }


    def verify_import(python_exe: str) -> dict[str, Any]:
        """Runs `python -c "from flash_attn import flash_attn_func; print(flash_attn.__version__)"`.
        Returns dict: imports_ok (bool), version (str|None), error (str|None).
        """
        cmd = [python_exe, "-c",
               "import flash_attn; from flash_attn import flash_attn_func; "
               "print(flash_attn.__version__)"]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if out.returncode == 0:
                return {"imports_ok": True, "version": out.stdout.strip(), "error": None}
            return {"imports_ok": False, "version": None, "error": out.stderr[-2000:]}
        except Exception as e:
            return {"imports_ok": False, "version": None, "error": repr(e)}


    def classify_failure(install: dict[str, Any]) -> str | None:
        if install["exit_code"] == 0:
            return None
        if install["timed_out"]:
            return "build_timeout_30min"
        stderr = install.get("stderr_tail", "")
        stdout = install.get("stdout_tail", "")
        combined = (stderr + stdout).lower()
        if "microsoft visual" in combined or "cl.exe" in combined or "msvc" in combined:
            return "msvc_toolchain_missing"
        if "cuda" in combined and ("not found" in combined or "missing" in combined):
            return "cuda_toolkit_mismatch"
        if "no matching distribution" in combined:
            return "no_prebuilt_wheel_and_source_build_failed"
        if "memoryerror" in combined or "out of memory" in combined:
            return "build_oom"
        return "unknown_build_error"


    def main() -> int:
        ap = argparse.ArgumentParser()
        ap.add_argument("--output", required=True)
        ap.add_argument("--python-exe",
                        default=str(Path(".venv-phase0/Scripts/python.exe")),
                        help="Path to the venv python that should receive FA2")
        args = ap.parse_args()

        # Short-circuit if already installed
        pre = verify_import(args.python_exe)
        if pre["imports_ok"]:
            print(f"[fa2] FA2 already installed: {pre['version']}", flush=True)
            payload = {
                "probe": "fa2_install",
                "installed": True,
                "version": pre["version"],
                "build_duration_s": 0,
                "failure_reason": None,
                "qwen17b_recommended": True,
                "notes": "FA2 was already present at probe start; no build performed.",
            }
            write_results(args.output, payload)
            return 0

        install = attempt_install(args.python_exe)
        verify = verify_import(args.python_exe) if install["exit_code"] == 0 else {
            "imports_ok": False, "version": None, "error": "install failed; skipping import check"
        }
        failure_reason = classify_failure(install) if not verify["imports_ok"] else None

        payload = {
            "probe": "fa2_install",
            "installed": verify["imports_ok"],
            "version": verify["version"],
            "build_duration_s": install["duration_s"],
            "failure_reason": failure_reason,
            "qwen17b_recommended": verify["imports_ok"],
            "install_exit_code": install["exit_code"],
            "install_timed_out": install["timed_out"],
            "install_stdout_tail": install["stdout_tail"],
            "install_stderr_tail": install["stderr_tail"],
            "import_error": verify["error"],
        }
        write_results(args.output, payload)

        if payload["installed"]:
            print(f"[fa2] INSTALLED: flash_attn {payload['version']} "
                  f"(build took {payload['build_duration_s']:.0f}s)", flush=True)
        else:
            print(f"[fa2] FAILED: {payload['failure_reason']}", flush=True)
            print(f"[fa2] stderr tail:\n{install['stderr_tail'][-1000:]}", flush=True)
        return 0


    if __name__ == "__main__":
        sys.exit(main())
    ```

    Then run the probe (it installs into the venv and writes the results JSON):
    ```bash
    cd .planning/phases/00-measurement-gate
    .venv-phase0/Scripts/python.exe probes/fa2_check.py --output results/fa2_install.json
    ```

    Expected wall time: 10–30 min on first run (source build). Re-runs: <5 s (already installed -> short-circuit).

    Note: the probe is autonomous because it simply writes outcome to JSON. Even on failure it exits 0 (the failure is represented in the JSON, not the exit code — Phase 8 consumes the JSON to make decisions).
  </action>
  <verify>
    <automated>test -f .planning/phases/00-measurement-gate/probes/fa2_check.py &amp;&amp; .planning/phases/00-measurement-gate/.venv-phase0/Scripts/python.exe -c "import ast; ast.parse(open('.planning/phases/00-measurement-gate/probes/fa2_check.py').read())" &amp;&amp; grep -q "flash_attn_func" .planning/phases/00-measurement-gate/probes/fa2_check.py &amp;&amp; grep -q "BUILD_TIMEOUT_S = 30 \* 60" .planning/phases/00-measurement-gate/probes/fa2_check.py</automated>
  </verify>
  <acceptance_criteria>
    - File `.planning/phases/00-measurement-gate/probes/fa2_check.py` exists and parses as valid Python.
    - File contains `flash_attn_func` (import probe), `BUILD_TIMEOUT_S = 30 * 60` (30-min cap), `classify_failure` function.
    - File uses `subprocess.run(..., timeout=...)` for the pip install.
  </acceptance_criteria>
  <done>FA2 probe script committed.</done>
</task>

<task type="auto">
  <name>Task 2: Run fa2_check.py and produce results/fa2_install.json</name>
  <files>
    .planning/phases/00-measurement-gate/results/fa2_install.json
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/probes/fa2_check.py
    .planning/phases/00-measurement-gate/00-RESEARCH.md (§Open Questions #4 — whether FA2 builds on this machine)
  </read_first>
  <action>
    Run the probe:
    ```bash
    cd .planning/phases/00-measurement-gate
    .venv-phase0/Scripts/python.exe probes/fa2_check.py --output results/fa2_install.json
    ```

    Wait for completion. Expected runtimes:
    - If prebuilt wheel matches: <60s
    - If source build succeeds: 10–30 min (normal on this machine per research)
    - If build fails: exits within a few minutes after compilation errors
    - If timeout: exactly 30 min

    The probe always writes the results JSON and exits 0. Do NOT retry if it "fails" — the failure outcome IS the measurement.

    **Important:** DO NOT halt the execute-phase on a non-zero exit code here. The probe's contract is: always produce `results/fa2_install.json`; downstream plans (especially 08) read that JSON and decide disposition.

    After the probe completes, read the JSON to confirm outcome:
    ```bash
    .venv-phase0/Scripts/python.exe -c "
    import json
    d = json.load(open('results/fa2_install.json'))
    print(f'installed: {d[\"installed\"]}')
    print(f'version: {d[\"version\"]}')
    print(f'build_duration_s: {d[\"build_duration_s\"]}')
    print(f'failure_reason: {d[\"failure_reason\"]}')
    print(f'qwen17b_recommended: {d[\"qwen17b_recommended\"]}')
    "
    ```

    If `installed: false`, the JSON also contains `install_stderr_tail` with the last 4KB of the build log — the Phase 8 synthesis plan summarizes this. Do not paste the tail into chat unless the user asks.
  </action>
  <verify>
    <automated>test -f .planning/phases/00-measurement-gate/results/fa2_install.json &amp;&amp; .planning/phases/00-measurement-gate/.venv-phase0/Scripts/python.exe -c "import json; d = json.load(open('.planning/phases/00-measurement-gate/results/fa2_install.json')); assert 'installed' in d and isinstance(d['installed'], bool); assert 'build_duration_s' in d; assert 'qwen17b_recommended' in d; assert 'failure_reason' in d; print('OK installed=' + str(d['installed']))"</automated>
  </verify>
  <acceptance_criteria>
    - File `.planning/phases/00-measurement-gate/results/fa2_install.json` exists with valid JSON.
    - JSON has keys `installed` (bool), `version` (str or null), `build_duration_s` (number), `failure_reason` (str or null), `qwen17b_recommended` (bool).
    - If `installed: true`, `version` is a non-null semver string like `"2.8.3"`.
    - If `installed: false`, `failure_reason` is one of `build_timeout_30min`, `msvc_toolchain_missing`, `cuda_toolkit_mismatch`, `no_prebuilt_wheel_and_source_build_failed`, `build_oom`, `unknown_build_error`.
    - `qwen17b_recommended == installed` (rule from QWEN3-TTS.md §3.2).
  </acceptance_criteria>
  <done>FA2 install outcome is recorded; Phase 8 can consume it.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Probe -> PyPI | Pulls `flash-attn` source tarball; integrity via PyPI hashes. |
| Probe -> pip subprocess | Runs pip inside the existing venv; inherits venv isolation. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-07-01 | Tampering | `flash-attn` source from PyPI | accept | Official Dao-AILab-published package. No hash pinning at spike stage; upstream is actively maintained. |
| T-00-07-02 | DoS | 30-min build ties up CPU + disk | accept | Bounded by `BUILD_TIMEOUT_S = 30 * 60`; subprocess is killed on expiry. Single-user workstation; builder accepts the wait. |
| T-00-07-03 | Info Disclosure | `stderr_tail` field captures build logs | accept | Logs contain compilation output + file paths (e.g., `C:\Users\pmpg\...`); this is local-only metadata. JSON is reviewed before committing. |

No high-severity threats. Pure local install probe.
</threat_model>

<verification>
```bash
.venv-phase0/Scripts/python.exe -c "
import json
d = json.load(open('results/fa2_install.json'))
print(f'installed: {d[\"installed\"]} version: {d[\"version\"]}')
print(f'build_duration_s: {d[\"build_duration_s\"]}')
print(f'failure_reason: {d[\"failure_reason\"]}')
print(f'qwen17b_recommended (1.7B eligible): {d[\"qwen17b_recommended\"]}')
"
```
</verification>

<success_criteria>
- [ ] FA2 install attempted under the Phase 0 venv
- [ ] Outcome (success/fail/timeout) captured in results/fa2_install.json
- [ ] If success: `from flash_attn import flash_attn_func` verified to import
- [ ] If fail: failure_reason classified + stderr tail preserved
- [ ] qwen17b_recommended flag set per FA2 outcome
</success_criteria>

<output>
After completion, create `.planning/phases/00-measurement-gate/00-07-SUMMARY.md` summarizing:
- Install outcome + version or failure_reason
- Build duration
- Recommendation: is Qwen3-TTS 1.7B eligible for v1 (subject to plan 04 accent test)?
- If failed: guidance for the builder on what to fix (install MSVC Build Tools, upgrade CUDA toolkit, etc.)
</output>
