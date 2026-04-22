"""LLM mid-stream cancel probe for Phase 0 success criterion #5."""

from __future__ import annotations

import argparse
import asyncio
import statistics
import subprocess
import sys
import time
from typing import Any

from bench_utils import write_results

CANCEL_AFTER_S = 0.5
POLL_WINDOW_S = 2.0
POLL_INTERVAL_S = 0.1
IDLE_THRESHOLD_PCT = 5


def parse_nvidia_smi_gpu_util(raw: str) -> int:
    """Parse one utilization.gpu sample from nvidia-smi."""
    line = raw.strip().splitlines()[0].strip()
    line = line.rstrip("%").rstrip()
    return int(line)


def first_idle_ms(
    samples: list[dict[str, Any]], threshold_pct: int = IDLE_THRESHOLD_PCT
) -> float | None:
    """Return the first timestamp whose utilization is at or below threshold."""
    for sample in samples:
        util = sample.get("util")
        if util is not None and util <= threshold_pct:
            return round(sample["t"] * 1000, 1)
    return None


def compute_p50_cancel_ms(trials: list[dict[str, Any]]) -> float | None:
    values = [
        trial["cancel_to_idle_ms"]
        for trial in trials
        if trial.get("cancel_to_idle_ms") is not None
    ]
    if not values:
        return None
    return round(statistics.median(values), 1)


def poll_gpu_util(
    duration_s: float, interval_s: float = POLL_INTERVAL_S
) -> list[dict[str, Any]]:
    """Poll nvidia-smi utilization.gpu for a fixed window."""
    samples: list[dict[str, Any]] = []
    started = time.perf_counter()
    while time.perf_counter() - started < duration_s:
        t_sample = time.perf_counter() - started
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                text=True,
                timeout=2,
            )
            util: int | None = parse_nvidia_smi_gpu_util(output)
        except Exception:
            util = None
        samples.append({"t": round(t_sample, 3), "util": util})
        time.sleep(interval_s)
    return samples


async def one_trial(base_url: str, model: str, prompt: str) -> dict[str, Any]:
    import httpx

    tokens_seen = 0
    started = time.perf_counter()
    first_token: float | None = None

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        async with client.stream(
            "POST",
            "/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
                "max_tokens": 500,
            },
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise RuntimeError(f"server returned {response.status_code}: {body[:200]!r}")

            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                if first_token is None:
                    first_token = time.perf_counter()
                tokens_seen += 1
                if time.perf_counter() - started > CANCEL_AFTER_S:
                    break

    closed = time.perf_counter()
    samples = poll_gpu_util(POLL_WINDOW_S)
    idle_ms = first_idle_ms(samples)

    return {
        "tokens_seen": tokens_seen,
        "time_to_first_token_ms": round(((first_token or started) - started) * 1000, 1),
        "stream_close_ms_after_start": round((closed - started) * 1000, 1),
        "cancel_to_idle_ms": idle_ms,
        "poll_samples": samples,
    }


async def run_trials(base_url: str, model: str, trials: int) -> dict[str, Any]:
    prompt = "Write a 500-word essay about the history of gardens."
    records: list[dict[str, Any]] = []

    for index in range(trials):
        print(f"[cancel] Trial {index + 1}/{trials}...", flush=True)
        try:
            record = await one_trial(base_url, model, prompt)
            record["trial"] = index + 1
            records.append(record)
            print(
                f"[cancel]   tokens={record['tokens_seen']} "
                f"ttft={record['time_to_first_token_ms']}ms "
                f"cancel_to_idle={record['cancel_to_idle_ms']}ms",
                flush=True,
            )
        except Exception as exc:
            print(f"[cancel]   FAILED: {exc!r}", file=sys.stderr)
            records.append(
                {"trial": index + 1, "error": repr(exc), "cancel_to_idle_ms": None}
            )
        await asyncio.sleep(1.0)

    p50 = compute_p50_cancel_ms(records)
    return {
        "probe": "llm_cancel",
        "base_url": base_url,
        "model": model,
        "trials": records,
        "p50_cancel_to_idle_ms": p50,
        "meets_phase4_budget_200ms": (p50 is not None and p50 < 200),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="http://localhost:11434/v1",
        help="OpenAI-compatible base URL (Ollama: 11434/v1, llama-server often 8080/v1)",
    )
    parser.add_argument("--model", default="llama3.2:3b", help="Model name the server exposes")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        payload = asyncio.run(run_trials(args.base_url, args.model, args.trials))
    except Exception as exc:
        print(f"[cancel] ERROR: {exc!r}", file=sys.stderr)
        return 2

    write_results(args.output, payload)
    print(
        f"\n[cancel] p50 cancel_to_idle = {payload['p50_cancel_to_idle_ms']} ms "
        f"(budget 200 ms, meets={payload['meets_phase4_budget_200ms']})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
