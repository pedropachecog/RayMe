"""Bounded process-local metadata for recent refusal recovery activity."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from typing import Literal

RefusalAction = Literal[
    "send",
    "regenerate",
    "swipe",
    "continue",
    "call_offer",
    "call_turn",
    "preview",
]
RefusalReasonCode = Literal[
    "generic_identity",
    "policy_or_safety",
    "apology",
    "redirect",
    "warning",
    "safe_prefix",
    "upstream_complete",
]
RefusalTerminalOutcome = Literal[
    "retry",
    "accepted",
    "exhausted",
    "empty",
    "failed",
    "cancelled",
]

_ACTIONS = {
    "send",
    "regenerate",
    "swipe",
    "continue",
    "call_offer",
    "call_turn",
    "preview",
}
_REASON_CODES = {
    "generic_identity",
    "policy_or_safety",
    "apology",
    "redirect",
    "warning",
    "safe_prefix",
    "upstream_complete",
}
_OUTCOMES = {"retry", "accepted", "exhausted", "empty", "failed", "cancelled"}


@dataclass(frozen=True, slots=True)
class RefusalActivityRecord:
    """Positive-allowlist activity row containing no generated content."""

    action: RefusalAction
    attempt: int
    reason_code: RefusalReasonCode
    prefix_characters: int
    prefix_estimated_tokens: int
    retry_count: int
    release_ms: float | None
    decision_ms: float | None
    terminal_outcome: RefusalTerminalOutcome
    timestamp: str

    def __post_init__(self) -> None:
        if self.action not in _ACTIONS:
            raise ValueError("unsupported refusal activity action")
        if self.reason_code not in _REASON_CODES:
            raise ValueError("unsupported refusal reason code")
        if self.terminal_outcome not in _OUTCOMES:
            raise ValueError("unsupported refusal terminal outcome")
        if isinstance(self.attempt, bool) or not 1 <= self.attempt <= 3:
            raise ValueError("attempt must be between one and three")
        if isinstance(self.retry_count, bool) or not 0 <= self.retry_count <= 2:
            raise ValueError("retry_count must be between zero and two")
        if (
            isinstance(self.prefix_characters, bool)
            or self.prefix_characters < 0
            or isinstance(self.prefix_estimated_tokens, bool)
            or self.prefix_estimated_tokens < 0
        ):
            raise ValueError("prefix counts must be non-negative")
        for field_name, value in (
            ("release_ms", self.release_ms),
            ("decision_ms", self.decision_ms),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative number or null")
        if not isinstance(self.timestamp, str) or not self.timestamp.endswith("Z"):
            raise ValueError("timestamp must be a UTC ISO-8601 string")

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "attempt": self.attempt,
            "reason_code": self.reason_code,
            "prefix_characters": self.prefix_characters,
            "prefix_estimated_tokens": self.prefix_estimated_tokens,
            "retry_count": self.retry_count,
            "release_ms": self.release_ms,
            "decision_ms": self.decision_ms,
            "terminal_outcome": self.terminal_outcome,
            "timestamp": self.timestamp,
        }


class RefusalActivityStore:
    """Thread-keyed ring deliberately lost when the Web process restarts."""

    def __init__(self, *, max_records_per_thread: int = 20) -> None:
        if isinstance(max_records_per_thread, bool) or max_records_per_thread < 1:
            raise ValueError("max_records_per_thread must be positive")
        self._max_records_per_thread = max_records_per_thread
        self._records: defaultdict[str, deque[RefusalActivityRecord]] = defaultdict(
            lambda: deque(maxlen=self._max_records_per_thread)
        )
        self._lock = Lock()

    def append(self, thread_id: str, record: RefusalActivityRecord) -> None:
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("thread_id is required")
        if not isinstance(record, RefusalActivityRecord):
            raise TypeError("record must be RefusalActivityRecord")
        with self._lock:
            self._records[thread_id].append(record)

    def list_recent(self, thread_id: str) -> tuple[RefusalActivityRecord, ...]:
        with self._lock:
            records = self._records.get(thread_id)
            return tuple(records) if records is not None else ()

    def serialize_recent(self, thread_id: str) -> list[dict[str, object]]:
        return [record.to_dict() for record in self.list_recent(thread_id)]


_PROCESS_LOCAL_REFUSAL_ACTIVITY = RefusalActivityStore()


def get_process_local_refusal_activity_store() -> RefusalActivityStore:
    """Return the bounded activity ring shared by Web routes in this process."""

    return _PROCESS_LOCAL_REFUSAL_ACTIVITY


__all__ = [
    "RefusalAction",
    "RefusalActivityRecord",
    "RefusalActivityStore",
    "RefusalReasonCode",
    "RefusalTerminalOutcome",
    "get_process_local_refusal_activity_store",
]
