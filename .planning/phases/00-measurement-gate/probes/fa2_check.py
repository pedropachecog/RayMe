"""FlashAttention 2 install + verify for Phase 0 success criterion #6."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from bench_utils import write_results

BUILD_TIMEOUT_S = 30 * 60


def attempt_install(python_exe: str) -> dict[str, Any]:
    """Run the flash-attn install attempt with a hard timeout."""
    env = os.environ.copy()
    env["FLASH_ATTENTION_SKIP_CUDA_BUILD"] = "FALSE"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

    cmd = [python_exe, "-m", "pip", "install", "flash-attn", "--no-build-isolation"]
    print(f"[fa2] Running: {' '.join(cmd)}", flush=True)
    print(f"[fa2] Timeout: {BUILD_TIMEOUT_S}s ({BUILD_TIMEOUT_S // 60} min)", flush=True)

    started = time.perf_counter()
    stdout = ""
    stderr = ""
    exit_code = -1
    timed_out = False

    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=BUILD_TIMEOUT_S,
        )
        exit_code = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""

    duration_s = round(time.perf_counter() - started, 1)
    return {
        "exit_code": exit_code,
        "duration_s": duration_s,
        "timed_out": timed_out,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
    }


def verify_import(python_exe: str) -> dict[str, Any]:
    """Import flash_attn and expose the installed version when available."""
    cmd = [
        python_exe,
        "-c",
        (
            "import flash_attn; "
            "from flash_attn import flash_attn_func; "
            "print(flash_attn.__version__)"
        ),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
        )
    except Exception as exc:  # pragma: no cover - exercised on backend only
        return {"imports_ok": False, "version": None, "error": repr(exc)}

    if proc.returncode == 0:
        return {"imports_ok": True, "version": proc.stdout.strip(), "error": None}
    return {"imports_ok": False, "version": None, "error": proc.stderr[-2000:]}


def classify_failure(install: dict[str, Any]) -> str | None:
    """Map the install transcript into a stable result label."""
    if install["exit_code"] == 0:
        return None
    if install["timed_out"]:
        return "build_timeout_30min"

    combined = (install.get("stderr_tail", "") + install.get("stdout_tail", "")).lower()
    if (
        "error c" in combined
        or "failed with exit code 2" in combined
        or "failed building wheel for flash-attn" in combined
    ):
        return "windows_build_compile_error"
    if (
        "cl.exe" in combined and ("not found" in combined or "no such file" in combined)
    ) or ("microsoft visual" in combined and "required" in combined):
        return "msvc_toolchain_missing"
    if "cuda" in combined and ("not found" in combined or "missing" in combined):
        return "cuda_toolkit_mismatch"
    if "no matching distribution" in combined:
        return "no_prebuilt_wheel_and_source_build_failed"
    if "memoryerror" in combined or "out of memory" in combined:
        return "build_oom"
    return "unknown_build_error"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--python-exe",
        default=str(Path(".venv-phase0/Scripts/python.exe")),
        help="Path to the venv python that should receive FlashAttention 2",
    )
    args = parser.parse_args()

    preflight = verify_import(args.python_exe)
    if preflight["imports_ok"]:
        payload = {
            "probe": "fa2_install",
            "installed": True,
            "version": preflight["version"],
            "build_duration_s": 0,
            "failure_reason": None,
            "qwen17b_recommended": True,
            "notes": "FA2 was already installed before the probe started.",
        }
        write_results(args.output, payload)
        print(f"[fa2] FA2 already installed: {preflight['version']}", flush=True)
        return 0

    install = attempt_install(args.python_exe)
    verify = (
        verify_import(args.python_exe)
        if install["exit_code"] == 0
        else {"imports_ok": False, "version": None, "error": "install failed; import skipped"}
    )
    failure_reason = None if verify["imports_ok"] else classify_failure(install)

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
        print(
            f"[fa2] INSTALLED: flash_attn {payload['version']} "
            f"(build took {payload['build_duration_s']:.0f}s)",
            flush=True,
        )
    else:
        print(f"[fa2] FAILED: {payload['failure_reason']}", flush=True)
        print(f"[fa2] stderr tail:\n{install['stderr_tail'][-1000:]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
