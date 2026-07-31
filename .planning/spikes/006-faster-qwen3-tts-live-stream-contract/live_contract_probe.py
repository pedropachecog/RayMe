#!/usr/bin/env python3
"""Exercise Faster Qwen3-TTS through a bounded live-call stream bridge."""

from __future__ import annotations

import argparse
import json
import queue
import random
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import torch

from faster_qwen3_tts import FasterQwen3TTS


QUEUE_CAPACITY = 2
CHUNK_SIZE = 4
LONG_TEXT = (
    "A live voice should begin speaking while the rest of this answer is still being generated. "
    "The producer and consumer must overlap without collecting the whole waveform first. "
    "Even when playback is deliberately slower than synthesis, the queue must stay bounded, "
    "and an interruption must stop new audio before a completed-turn signal can escape."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3-TTS-12Hz-1.7B-Base")
    parser.add_argument("--reference-audio", required=True)
    parser.add_argument("--reference-text-file", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def fake_stream() -> Iterable[tuple[np.ndarray, int, dict[str, Any]]]:
    for index in range(10):
        time.sleep(0.01)
        yield np.full(7680, index / 100.0, dtype=np.float32), 24000, {"chunk_index": index}


def run_bridge(
    stream_factory: Callable[[], Iterable[Any]],
    *,
    label: str,
    consumer_delay_seconds: float,
    cancel_after_chunks: int | None = None,
) -> dict[str, Any]:
    bridge: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=QUEUE_CAPACITY)
    stop_event = threading.Event()
    producer_started = threading.Event()
    producer_done = threading.Event()
    producer_error: list[str] = []
    produced = 0
    consumed = 0
    post_cancel_produced = 0
    max_queue_depth = 0
    producer_done_at: float | None = None
    cancel_at: float | None = None
    first_consume_at: float | None = None
    started_at = time.perf_counter()

    def put_bounded(item: tuple[str, Any]) -> bool:
        nonlocal max_queue_depth
        while not stop_event.is_set():
            try:
                bridge.put(item, timeout=0.05)
                max_queue_depth = max(max_queue_depth, bridge.qsize())
                return True
            except queue.Full:
                continue
        return False

    def produce() -> None:
        nonlocal produced, post_cancel_produced, producer_done_at
        stream = stream_factory()
        producer_started.set()
        try:
            for item in stream:
                if stop_event.is_set():
                    post_cancel_produced += 1
                    break
                if not put_bounded(("chunk", item)):
                    break
                produced += 1
        except Exception as exc:  # pragma: no cover - runtime evidence path
            producer_error.append(f"{type(exc).__name__}: {exc}")
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
            producer_done_at = time.perf_counter()
            producer_done.set()
            if not stop_event.is_set():
                put_bounded(("done", None))

    producer = threading.Thread(target=produce, name=f"{label}-producer", daemon=True)
    producer.start()
    producer_started.wait(timeout=2.0)

    timed_out = False
    while True:
        try:
            kind, _item = bridge.get(timeout=5.0)
        except queue.Empty:
            timed_out = True
            stop_event.set()
            break
        if kind == "done":
            break
        consumed += 1
        if first_consume_at is None:
            first_consume_at = time.perf_counter()
        if cancel_after_chunks is not None and consumed >= cancel_after_chunks:
            cancel_at = time.perf_counter()
            stop_event.set()
            break
        time.sleep(consumer_delay_seconds)

    producer.join(timeout=3.0)
    stopped_at = time.perf_counter()
    return {
        "label": label,
        "queue_capacity": QUEUE_CAPACITY,
        "max_queue_depth": max_queue_depth,
        "produced_chunks": produced,
        "consumed_chunks": consumed,
        "post_cancel_produced_chunks": post_cancel_produced,
        "producer_error": producer_error,
        "timed_out": timed_out,
        "producer_stopped": not producer.is_alive(),
        "producer_completed_normally": producer_done.is_set() and cancel_at is None,
        "first_consume_ms": round((first_consume_at - started_at) * 1000.0, 3)
        if first_consume_at is not None
        else None,
        "producer_complete_ms": round((producer_done_at - started_at) * 1000.0, 3)
        if producer_done_at is not None
        else None,
        "first_consume_before_completion": bool(
            first_consume_at is not None
            and (producer_done_at is None or first_consume_at < producer_done_at)
        ),
        "interrupt_to_stop_ms": round((stopped_at - cancel_at) * 1000.0, 3)
        if cancel_at is not None
        else None,
        "whole_stream_collected_before_consume": False,
    }


def main() -> int:
    args = parse_args()
    reference_text = Path(args.reference_text_file).read_text(encoding="utf-8").strip()
    seed_all(20260731)

    fake_complete = run_bridge(
        fake_stream,
        label="fake-complete",
        consumer_delay_seconds=0.03,
    )
    fake_interrupt = run_bridge(
        fake_stream,
        label="fake-interrupt",
        consumer_delay_seconds=0.0,
        cancel_after_chunks=2,
    )

    model = FasterQwen3TTS.from_pretrained(
        args.model,
        device="cuda",
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        max_seq_len=2048,
    )
    model.warmup(prefill_len=100)
    for _ in model.generate_voice_clone_streaming(
        text="The stream is ready.",
        language="English",
        ref_audio=args.reference_audio,
        ref_text=reference_text,
        chunk_size=CHUNK_SIZE,
        max_new_tokens=128,
        xvec_only=False,
        non_streaming_mode=True,
        append_silence=True,
    ):
        pass

    def real_stream(seed: int) -> Iterable[Any]:
        seed_all(seed)
        return model.generate_voice_clone_streaming(
            text=LONG_TEXT,
            language="English",
            ref_audio=args.reference_audio,
            ref_text=reference_text,
            chunk_size=CHUNK_SIZE,
            max_new_tokens=512,
            xvec_only=False,
            non_streaming_mode=True,
            append_silence=True,
        )

    real_complete = run_bridge(
        lambda: real_stream(7001),
        label="real-complete",
        consumer_delay_seconds=0.4,
    )
    real_interrupt = run_bridge(
        lambda: real_stream(7002),
        label="real-interrupt",
        consumer_delay_seconds=0.0,
        cancel_after_chunks=3,
    )

    cases = [fake_complete, fake_interrupt, real_complete, real_interrupt]
    gates = {
        "all_producers_stopped": all(case["producer_stopped"] for case in cases),
        "no_producer_errors": all(not case["producer_error"] for case in cases),
        "no_timeouts": all(not case["timed_out"] for case in cases),
        "bounded_queue": all(case["max_queue_depth"] <= QUEUE_CAPACITY for case in cases),
        "first_consume_before_completion": all(
            case["first_consume_before_completion"] for case in cases
        ),
        "normal_streams_completed": all(
            case["producer_completed_normally"] for case in (fake_complete, real_complete)
        ),
        "interrupts_stop_below_2s": all(
            case["interrupt_to_stop_ms"] is not None
            and case["interrupt_to_stop_ms"] < 2000.0
            for case in (fake_interrupt, real_interrupt)
        ),
        "at_most_one_post_cancel_chunk": all(
            case["post_cancel_produced_chunks"] <= 1
            for case in (fake_interrupt, real_interrupt)
        ),
        "never_collects_whole_stream": all(
            not case["whole_stream_collected_before_consume"] for case in cases
        ),
    }
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model": args.model,
        "package": "faster-qwen3-tts==0.3.2",
        "settings": {"queue_capacity": QUEUE_CAPACITY, "chunk_size": CHUNK_SIZE},
        "cases": cases,
        "gates": gates,
        "overall_status": "passed" if all(gates.values()) else "failed",
    }
    Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload), flush=True)
    return 0 if payload["overall_status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
