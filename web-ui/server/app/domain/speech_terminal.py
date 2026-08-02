"""Dependency-free validation for AI-backend speech terminal responses."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class SpeechTurnTerminal:
    """One sanitized terminal result for a multi-segment speech turn."""

    status: Literal["normal", "cancelled", "error"]
    playout_completed: bool
    response: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None


def _speech_terminal_from_response(
    response: Mapping[str, Any] | None,
    *,
    require_final: bool,
) -> SpeechTurnTerminal:
    if response is None:
        return _speech_error_terminal("call_tts_failed")
    raw_event = response.get("event")
    if not isinstance(raw_event, Mapping):
        return _speech_error_terminal("call_tts_failed", response=response)
    event = raw_event
    event_type = event.get("type")
    event_status = event.get("status")
    if event_status == "cancelled" or event_type == "cancelled":
        return SpeechTurnTerminal(
            status="cancelled",
            playout_completed=False,
            response=dict(response),
        )
    if event_type in {"failed", "error"} or event_status == "error":
        return _speech_error_terminal("call_tts_failed", response=response)

    if (
        not require_final
        and event_type is None
        and event_status in {"queued", "normal"}
    ):
        # A Qwen segment is deliberately admitted before its playout drains so
        # the next natural segment can start generating. Only the explicit
        # final marker proves end-of-turn playout; treating this queued result
        # as a terminal failure prevents that marker from ever being sent.
        return SpeechTurnTerminal(
            status="normal",
            playout_completed=False,
            response=dict(response),
        )

    if event_type != "ai_done":
        return _speech_error_terminal("call_tts_failed", response=response)

    raw_playout = event.get("tts_playback_final")
    if not isinstance(raw_playout, Mapping):
        return _speech_error_terminal("call_tts_failed", response=response)
    if raw_playout.get("playout_wait_completed") is not True:
        return _speech_error_terminal("call_tts_failed", response=response)
    return SpeechTurnTerminal(
        status="normal",
        playout_completed=True,
        response=dict(response),
    )


def _speech_error_terminal(
    code: str,
    *,
    response: Mapping[str, Any] | None = None,
) -> SpeechTurnTerminal:
    return SpeechTurnTerminal(
        status="error",
        playout_completed=False,
        response=dict(response) if response is not None else None,
        error_code=code,
        error_message="Speech playback failed",
    )
