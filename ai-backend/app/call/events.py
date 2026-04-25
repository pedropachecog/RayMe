from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

from typing_extensions import NotRequired

USER_FINAL_EVENT = "user_final"
AI_AUDIO_STARTED_EVENT = "ai_audio_started"
AI_DONE_EVENT = "ai_done"
MUTED_EVENT = "muted"
INTERRUPTED_EVENT = "interrupted"
ENDED_EVENT = "ended"
FAILED_EVENT = "failed"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class BaseCallEvent(TypedDict):
    type: str
    session_id: str


class TurnCallEvent(BaseCallEvent, total=False):
    turn_id: str


class UserFinalEvent(TurnCallEvent):
    type: Literal["user_final"]
    turn_id: str
    text: str
    started_at: NotRequired[str]
    ended_at: NotRequired[str]


class FailedEvent(TurnCallEvent, total=False):
    type: Literal["failed"]
    code: str
    message: str
    retry_allowed: bool


def user_final_event(
    *,
    session_id: str,
    turn_id: str,
    text: str,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> UserFinalEvent:
    event: UserFinalEvent = {
        "type": USER_FINAL_EVENT,
        "session_id": session_id,
        "turn_id": turn_id,
        "text": text,
    }
    if started_at is not None:
        event["started_at"] = started_at
    if ended_at is not None:
        event["ended_at"] = ended_at
    return event


def simple_event(
    event_type: Literal[
        "ai_audio_started",
        "ai_done",
        "muted",
        "interrupted",
        "ended",
    ],
    *,
    session_id: str,
    turn_id: str | None = None,
    **fields: Any,
) -> TurnCallEvent:
    event: TurnCallEvent = {"type": event_type, "session_id": session_id}
    if turn_id is not None:
        event["turn_id"] = turn_id
    event.update(fields)
    return event


def failed_event(
    *,
    session_id: str,
    code: str,
    message: str,
    retry_allowed: bool = True,
    turn_id: str | None = None,
) -> FailedEvent:
    event: FailedEvent = {
        "type": FAILED_EVENT,
        "session_id": session_id,
        "code": code,
        "message": message,
        "retry_allowed": retry_allowed,
    }
    if turn_id is not None:
        event["turn_id"] = turn_id
    return event
