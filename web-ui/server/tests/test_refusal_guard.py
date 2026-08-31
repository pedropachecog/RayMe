"""Frozen precision, lifecycle, and metadata contracts for refusal recovery."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any

import pytest

from app.domain.llm_stream import ChatCompletionSettings, collect_chat_completion
from app.domain.refusal_guard import LLMEmptyOutput, PrefixRefusalGuard

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "phase091_refusal_corpus.json"
CORPUS = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _case_ids(group: str) -> list[str]:
    return [str(case["id"]) for case in CORPUS[group]]


@pytest.mark.parametrize("case", CORPUS["refusals"], ids=_case_ids("refusals"))
@pytest.mark.parametrize("schedule", CORPUS["fragmentation_schedules"])
def test_explicit_refusals_are_suppressed_under_every_fragmentation(
    case: dict[str, str],
    schedule: str,
) -> None:
    guard = PrefixRefusalGuard()
    emitted: list[str] = []
    refusal = None

    for chunk in _fragments(case["text"], schedule):
        decision = guard.feed(chunk)
        emitted.extend(decision.released_text)
        if decision.refused:
            refusal = decision
            break

    if refusal is None:
        refusal = guard.finish()

    assert refusal.refused is True
    assert refusal.reason_code in {
        "generic_identity",
        "policy_or_safety",
        "apology",
        "redirect",
        "warning",
    }
    assert emitted == []


@pytest.mark.parametrize("case", CORPUS["benign"], ids=_case_ids("benign"))
@pytest.mark.parametrize("schedule", CORPUS["fragmentation_schedules"])
def test_benign_roleplay_round_trips_unchanged_under_every_fragmentation(
    case: dict[str, str],
    schedule: str,
) -> None:
    guard = PrefixRefusalGuard()
    emitted: list[str] = []

    for chunk in _fragments(case["text"], schedule):
        decision = guard.feed(chunk)
        assert decision.refused is False
        emitted.extend(decision.released_text)
    final = guard.finish()
    assert final.refused is False
    emitted.extend(final.released_text)

    original = case["text"]
    released = "".join(emitted)
    assert released == original
    assert released.encode("utf-8") == original.encode("utf-8")


def test_safe_held_open_stream_releases_from_feed_before_finish() -> None:
    guard = PrefixRefusalGuard()

    decision = guard.feed("This ordinary in-world sentence releases immediately.")

    assert decision.state == "passthrough"
    assert decision.released_text == (
        "This ordinary in-world sentence releases immediately.",
    )
    assert decision.decision_ms is not None


def test_guard_cpu_p95_stays_below_five_milliseconds() -> None:
    samples_ms: list[float] = []
    cases = [*CORPUS["refusals"], *CORPUS["benign"]]
    for index in range(220):
        case = cases[index % len(cases)]
        guard = PrefixRefusalGuard()
        started = time.perf_counter_ns()
        for chunk in _fragments(case["text"], "one_codepoint"):
            decision = guard.feed(chunk)
            if decision.refused:
                break
        else:
            guard.finish()
        samples_ms.append((time.perf_counter_ns() - started) / 1_000_000)

    p95 = statistics.quantiles(samples_ms, n=20)[18]
    assert p95 < 5.0


def test_activity_ring_is_content_free_bounded_and_process_local() -> None:
    from app.domain.refusal_activity import (
        RefusalActivityRecord,
        RefusalActivityStore,
    )

    store = RefusalActivityStore(max_records_per_thread=20)
    forbidden_canaries = {
        "prompt": "private prompt",
        "history": "private history",
        "prose": "rejected prose",
        "api_key": "secret-key",
        "url_credential": "user:pass@host",
        "seed": 12345,
        "exception": "traceback detail",
        "audio": "base64-audio",
    }

    for index in range(25):
        store.append(
            "thread-a",
            RefusalActivityRecord(
                action="call_turn",
                attempt=(index % 3) + 1,
                reason_code="policy_or_safety",
                prefix_characters=60 + index,
                prefix_estimated_tokens=15 + index,
                retry_count=min(index, 2),
                release_ms=None,
                decision_ms=0.5,
                terminal_outcome="retry" if index < 24 else "accepted",
                timestamp=f"2026-08-31T00:00:{index:02d}Z",
            ),
        )

    serialized = store.serialize_recent("thread-a")
    assert len(serialized) == 20
    assert serialized[0]["prefix_characters"] == 65
    assert serialized[-1]["prefix_characters"] == 84
    assert set(serialized[-1]) == {
        "action",
        "attempt",
        "reason_code",
        "prefix_characters",
        "prefix_estimated_tokens",
        "retry_count",
        "release_ms",
        "decision_ms",
        "terminal_outcome",
        "timestamp",
    }
    recursive = json.dumps(serialized, sort_keys=True)
    for field_name, canary in forbidden_canaries.items():
        assert field_name not in serialized[-1]
        assert str(canary) not in recursive

    restarted_store = RefusalActivityStore(max_records_per_thread=20)
    assert restarted_store.serialize_recent("thread-a") == []


async def test_empty_upstream_completion_is_typed_unusable_output() -> None:
    class EmptyCompletion:
        async def stream_chat_completion_tokens(self, settings: Any, messages: Any):
            del settings, messages
            if False:
                yield "unreachable"

    with pytest.raises(LLMEmptyOutput) as exc_info:
        await collect_chat_completion(
            ChatCompletionSettings(base_url="https://llm.invalid/v1", model="qwen-test"),
            [{"role": "user", "content": "Say something."}],
            client=EmptyCompletion(),
        )

    assert exc_info.value.code == "llm_empty_output"


def _fragments(text: str, schedule: str) -> list[str]:
    if schedule == "one_chunk":
        return [text]
    if schedule == "one_codepoint":
        return list(text)
    if schedule == "word_boundaries":
        return _split_after(text, lambda character: character.isspace())
    if schedule == "punctuation_boundaries":
        return _split_after(text, lambda character: character in ".,;:!?—–\"'")
    irregular_sizes = {
        "irregular_1": (1, 4, 2, 7, 3),
        "irregular_2": (8, 1, 1, 5, 2, 9),
        "irregular_3": (3, 6, 1, 10, 2, 4),
        "irregular_4": (11, 2, 5, 1, 7, 3),
    }
    sizes = irregular_sizes[schedule]
    chunks: list[str] = []
    offset = 0
    index = 0
    while offset < len(text):
        size = sizes[index % len(sizes)]
        chunks.append(text[offset : offset + size])
        offset += size
        index += 1
    return chunks


def _split_after(text: str, predicate: Any) -> list[str]:
    chunks: list[str] = []
    start = 0
    for index, character in enumerate(text, start=1):
        if predicate(character):
            chunks.append(text[start:index])
            start = index
    if start < len(text):
        chunks.append(text[start:])
    return [chunk for chunk in chunks if chunk]
