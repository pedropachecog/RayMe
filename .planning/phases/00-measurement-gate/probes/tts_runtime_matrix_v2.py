"""Cross-runtime warm-model TTS scenario matrix for RayMe."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PHASE_DIR = Path(".planning/phases/00-measurement-gate")
PROBE_DIR = PHASE_DIR / "probes"
RESULT_DIR = PHASE_DIR / "results"
COMBINED_OUTPUT = RESULT_DIR / "tts_runtime_matrix_v2.json"
SSH_BOOTSTRAP = Path("scripts/bootstrap-rayme-ssh.sh")
WINDOWS_STAGE_ROOT = "C:\\Users\\rayme-ssh.OMEN-PC\\phase0-probes"
WINDOWS_STAGE_ROOT_SCP = "/C:/Users/rayme-ssh.OMEN-PC/phase0-probes"
WINDOWS_VENV_PYTHON = "C:\\Users\\rayme-ssh.OMEN-PC\\.venv-phase0\\Scripts\\python.exe"
WSL_VENV = "/home/pmpg/rayme/.venv-cu121"
WSL_PYTHON = f"{WSL_VENV}/bin/python"
WIN_PROBE_ROOT_WSL = "/mnt/c/Users/rayme-ssh.OMEN-PC/phase0-probes"
WINDOWS_RAW_OUTPUT = f"{WINDOWS_STAGE_ROOT}\\results\\tts_scenario_matrix_windows_native.json"
WSL_RAW_OUTPUT = f"{WIN_PROBE_ROOT_WSL}/results/tts_scenario_matrix_wsl_python.json"

STAGE_FILES = [
    (PROBE_DIR / "bench_utils.py", f"{WINDOWS_STAGE_ROOT_SCP}/bench_utils.py"),
    (PROBE_DIR / "tts_ttfa.py", f"{WINDOWS_STAGE_ROOT_SCP}/tts_ttfa.py"),
    (PROBE_DIR / "f5_production_chunking.py", f"{WINDOWS_STAGE_ROOT_SCP}/f5_production_chunking.py"),
    (PROBE_DIR / "tts_scenario_matrix.py", f"{WINDOWS_STAGE_ROOT_SCP}/tts_scenario_matrix.py"),
    (PROBE_DIR / "test_tts_scenario_matrix.py", f"{WINDOWS_STAGE_ROOT_SCP}/test_tts_scenario_matrix.py"),
    (PHASE_DIR / "requirements-tts-experimental.txt", f"{WINDOWS_STAGE_ROOT_SCP}/requirements-tts-experimental.txt"),
    (PROBE_DIR / "fixtures" / "short_ref_audio.wav", f"{WINDOWS_STAGE_ROOT_SCP}/fixtures/short_ref_audio.wav"),
    (PROBE_DIR / "fixtures" / "short_ref_transcript.txt", f"{WINDOWS_STAGE_ROOT_SCP}/fixtures/short_ref_transcript.txt"),
    (PROBE_DIR / "fixtures" / "target_text_1min.txt", f"{WINDOWS_STAGE_ROOT_SCP}/fixtures/target_text_1min.txt"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_local(
    command: list[str] | str,
    *,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        input=input_text,
        capture_output=True,
        check=check,
    )


def ssh_windows(command: str) -> str:
    return run_local(["ssh", "rayme-ssh", command]).stdout


def ssh_wsl(script: str) -> str:
    return run_local(
        ["ssh", "rayme-pmpg", "wsl", "-d", "Ubuntu", "--cd", "/home/pmpg", "-e", "bash", "-s"],
        input_text=script,
    ).stdout


def bootstrap_ssh(alias: str, user: str) -> None:
    env = os.environ.copy()
    env["RAYME_SSH_ALIAS"] = alias
    env["RAYME_SSH_USER"] = user
    subprocess.run(
        [str(SSH_BOOTSTRAP), "restore"],
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def ensure_windows_stage_dirs() -> None:
    directories = [
        WINDOWS_STAGE_ROOT,
        f"{WINDOWS_STAGE_ROOT}\\fixtures",
        f"{WINDOWS_STAGE_ROOT}\\results",
        f"{WINDOWS_STAGE_ROOT}\\results\\tts_scenario_audio",
        f"{WINDOWS_STAGE_ROOT}\\results\\tts_scenario_audio\\windows_native",
        f"{WINDOWS_STAGE_ROOT}\\results\\tts_scenario_audio\\wsl_python",
    ]
    for directory in directories:
        ssh_windows(f'cmd /c "if not exist {directory} mkdir {directory}"')


def stage_files() -> None:
    ensure_windows_stage_dirs()
    for local_path, remote_path in STAGE_FILES:
        run_local(["scp", str(local_path), f"rayme-ssh:{remote_path}"])


def install_windows_experimental_deps() -> None:
    ssh_windows(
        f'{WINDOWS_VENV_PYTHON} -m pip install -r "{WINDOWS_STAGE_ROOT}\\requirements-tts-experimental.txt"'
    )
    ssh_windows(
        f'{WINDOWS_VENV_PYTHON} -m pip install --no-deps chatterbox-tts hume-tada'
    )


def install_wsl_experimental_deps() -> None:
    script = f"""
set -euo pipefail
source {shlex.quote(WSL_VENV)}/bin/activate
python -m pip install -r {shlex.quote(WIN_PROBE_ROOT_WSL)}/requirements-tts-experimental.txt
python -m pip install --no-deps chatterbox-tts hume-tada
"""
    ssh_wsl(script)


def run_windows_matrix() -> None:
    command = (
        "cmd /c "
        f'"cd /d {WINDOWS_STAGE_ROOT} && '
        f'{WINDOWS_VENV_PYTHON} tts_scenario_matrix.py '
        '--runtime-label windows_native '
        '--host-account rayme-ssh '
        '--ref-audio fixtures\\short_ref_audio.wav '
        '--ref-text fixtures\\short_ref_transcript.txt '
        '--sample-root results\\tts_scenario_audio\\windows_native '
        '--output results\\tts_scenario_matrix_windows_native.json"'
    )
    ssh_windows(command)


def run_wsl_matrix() -> None:
    script = f"""
set -euo pipefail
source {shlex.quote(WSL_VENV)}/bin/activate
python {shlex.quote(WIN_PROBE_ROOT_WSL)}/tts_scenario_matrix.py \
  --runtime-label wsl_python \
  --host-account rayme-pmpg \
  --ref-audio {shlex.quote(WIN_PROBE_ROOT_WSL)}/fixtures/short_ref_audio.wav \
  --ref-text {shlex.quote(WIN_PROBE_ROOT_WSL)}/fixtures/short_ref_transcript.txt \
  --sample-root {shlex.quote(WIN_PROBE_ROOT_WSL)}/results/tts_scenario_audio/wsl_python \
  --output {shlex.quote(WSL_RAW_OUTPUT)}
"""
    ssh_wsl(script)


def fetch_remote_artifacts() -> tuple[dict[str, Any], dict[str, Any]]:
    local_audio_root = RESULT_DIR / "tts_scenario_audio"
    local_audio_root.mkdir(parents=True, exist_ok=True)

    windows_json_local = RESULT_DIR / "tts_scenario_matrix_windows_native.json"
    wsl_json_local = RESULT_DIR / "tts_scenario_matrix_wsl_python.json"

    run_local(
        [
            "scp",
            f"rayme-ssh:{WINDOWS_STAGE_ROOT_SCP}/results/tts_scenario_matrix_windows_native.json",
            str(windows_json_local),
        ]
    )
    run_local(
        [
            "scp",
            f"rayme-ssh:{WINDOWS_STAGE_ROOT_SCP}/results/tts_scenario_matrix_wsl_python.json",
            str(wsl_json_local),
        ]
    )
    run_local(
        [
            "scp",
            "-r",
            f"rayme-ssh:{WINDOWS_STAGE_ROOT_SCP}/results/tts_scenario_audio/windows_native",
            str(local_audio_root),
        ]
    )
    run_local(
        [
            "scp",
            "-r",
            f"rayme-ssh:{WINDOWS_STAGE_ROOT_SCP}/results/tts_scenario_audio/wsl_python",
            str(local_audio_root),
        ]
    )

    windows_payload = json.loads(windows_json_local.read_text(encoding="utf-8"))
    wsl_payload = json.loads(wsl_json_local.read_text(encoding="utf-8"))
    return windows_payload, wsl_payload


def build_combined_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scenarios = []
    for row in rows:
        scenario = row.get("scenario")
        if scenario and scenario not in scenarios:
            scenarios.append(scenario)

    summary: dict[str, Any] = {"best_request_ttfa": {}, "best_request_total": {}}
    for scenario in scenarios:
        measured = [
            row
            for row in rows
            if row.get("scenario") == scenario and row.get("status") == "measured"
        ]
        if not measured:
            continue
        best_ttfa = min(
            [row for row in measured if row.get("request_ttfa_ms") is not None],
            key=lambda row: (
                float(row["request_ttfa_ms"]),
                float(row.get("request_rtf") or float("inf")),
            ),
        )
        best_total = min(
            [row for row in measured if row.get("request_total_ms") is not None],
            key=lambda row: (
                float(row["request_total_ms"]),
                float(row.get("request_rtf") or float("inf")),
            ),
        )
        summary["best_request_ttfa"][scenario] = {
            "engine": best_ttfa["engine"],
            "runtime": best_ttfa["runtime"],
            "profile": best_ttfa["profile"],
            "request_ttfa_ms": best_ttfa["request_ttfa_ms"],
            "output_wav": best_ttfa["output_wav"],
        }
        summary["best_request_total"][scenario] = {
            "engine": best_total["engine"],
            "runtime": best_total["runtime"],
            "profile": best_total["profile"],
            "request_total_ms": best_total["request_total_ms"],
            "output_wav": best_total["output_wav"],
        }
    return summary


def run_combined(output: Path) -> dict[str, Any]:
    bootstrap_ssh("rayme-ssh", "rayme-ssh")
    bootstrap_ssh("rayme-pmpg", "pmpg")
    stage_files()
    install_windows_experimental_deps()
    install_wsl_experimental_deps()
    run_windows_matrix()
    run_wsl_matrix()
    windows_payload, wsl_payload = fetch_remote_artifacts()

    rows = list(windows_payload.get("rows", [])) + list(wsl_payload.get("rows", []))
    payload = {
        "probe": "tts_runtime_matrix_v2",
        "generated_at": utc_now(),
        "runs": {
            "windows_native": str(RESULT_DIR / "tts_scenario_matrix_windows_native.json"),
            "wsl_python": str(RESULT_DIR / "tts_scenario_matrix_wsl_python.json"),
        },
        "audio_root": str(RESULT_DIR / "tts_scenario_audio"),
        "rows": rows,
        "summary": build_combined_summary(rows),
    }
    write_json(output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(COMBINED_OUTPUT))
    args = parser.parse_args()
    payload = run_combined(Path(args.output))
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
