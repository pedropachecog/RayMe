from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import hashlib
import inspect
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

from app.call.events import (
    AI_AUDIO_STARTED_EVENT,
    AI_DONE_EVENT,
    ENDED_EVENT,
    FAILED_EVENT,
    INTERRUPTED_EVENT,
    MUTED_EVENT,
    failed_event,
    simple_event,
    user_final_event,
    utc_timestamp,
)
from app.call.tracks import (
    InboundAudioFrameNormalizer,
    OutboundAudioBuffer,
    PcmAudioFrame,
    audio_stats_for_wav_bytes,
    normalize_inbound_audio_frame,
    write_pcm_frames_to_temp_wav,
)
from app.config import AiBackendSettings
from app.models.tts_registry import (
    MAX_REFERENCE_AUDIO_BYTES,
    TtsAudioChunk,
    TtsStreamingAdapter,
    TtsSynthesisInput,
)

EventSink = Callable[[dict[str, Any]], Awaitable[None] | None]
PromptLeaseReleaser = Callable[[str], Awaitable[bool] | bool]

CALL_TTS_AUDIO_PREROLL_SECONDS = 0.25
CALL_TTS_REMOTE_PLAYOUT_HOLD_SECONDS = 0.75
CALL_TTS_STREAM_START_MIN_CHUNKS = 2
CALL_TTS_STREAM_START_MIN_AUDIO_SECONDS = 0.75
CALL_TTS_STREAM_MAX_STARTUP_BUFFER_SECONDS = 1.25
CALL_QWEN3_TTS_AUDIO_PREROLL_SECONDS = 0.0
CALL_QWEN3_STREAM_START_MIN_AUDIO_SECONDS = 0.60
CALL_TTS_STREAM_BRIDGE_CAPACITY = 2
CALL_TTS_CANCEL_DRAIN_TIMEOUT_SECONDS = 2.0
CALL_INTERRUPT_RECEIVER_DRAIN_MS = 250
LIVE_STREAMING_TTS_ENGINES = frozenset({"voxcpm2", "qwen3_1_7b"})
VOXCPM2_LIVE_MAX_INFERENCE_TIMESTEPS = 4
VOXCPM2_LIVE_NORMALIZE = False
VOXCPM2_LIVE_DENOISE = False
CALL_RECONNECT_BACKFILL_HOLD_SECONDS = 12.0
CALL_RECONNECT_BACKFILL_MAX_OVERLAP_SECONDS = 30.0
CALL_RECONNECT_BACKFILL_MIN_OVERLAP_FRAMES = 25
CALL_RECONNECT_BACKFILL_OVERLAP_CORRELATION = 0.92
CALL_RECONNECT_BACKFILL_OVERLAP_MEAN_RATIO = 0.60
CALL_STT_TRAILING_SILENCE_KEEP_MS = 400
CALL_BARGE_IN_MIN_SPEECH_MS = 120
CALL_BARGE_IN_MAX_ONSET_BUFFER_MS = 1000
CALL_BARGE_IN_MIN_RMS = 200.0
CALL_RECOVERABLE_EVENT_TYPES = {"user_final", "failed"}
CALL_ENDED_EVENT_RECOVERY_GRACE_SECONDS = 60.0
CALL_PEER_RECONNECT_GRACE_SECONDS = 8.0
CALL_PEER_REPLACEMENT_TIMEOUT_SECONDS = 8.0
CALL_SWITCH_CLEANUP_STEP_TIMEOUT_SECONDS = 2.0
CALL_TERMINAL_CLEANUP_STEP_TIMEOUT_SECONDS = 2.0
CALL_TERMINAL_CLEANUP_RETRY_LIMIT = 32
CALL_TERMINAL_CLEANUP_RETRY_BASE_SECONDS = 0.05
CALL_TERMINAL_CLEANUP_RETRY_MAX_SECONDS = 1.0
CALL_PROMPT_LEASE_CLEANUP_RETRY_LIMIT = 3


def _voxcpm2_options_for_engine(engine_id: str, options: dict[str, Any]) -> dict[str, Any]:
    if engine_id != "voxcpm2":
        return {}
    return dict(options)


def _voxcpm2_live_stream_options(engine_id: str, options: dict[str, Any]) -> dict[str, Any]:
    voxcpm2_options = _voxcpm2_options_for_engine(engine_id, options)
    if not voxcpm2_options:
        return {}
    live_options = dict(voxcpm2_options)
    requested_timesteps = int(live_options.get("voxcpm2_inference_timesteps") or 10)
    live_options["voxcpm2_inference_timesteps"] = min(
        requested_timesteps,
        VOXCPM2_LIVE_MAX_INFERENCE_TIMESTEPS,
    )
    live_options["voxcpm2_normalize"] = VOXCPM2_LIVE_NORMALIZE
    live_options["voxcpm2_denoise"] = VOXCPM2_LIVE_DENOISE
    return live_options


def _voxcpm2_call_text_options(adapter: Any, engine_id: str, options: dict[str, Any]) -> dict[str, Any]:
    voxcpm2_options = _voxcpm2_options_for_engine(engine_id, options)
    if not voxcpm2_options:
        return {}
    try:
        signature = inspect.signature(adapter.synthesize_call_text)
    except (TypeError, ValueError):
        return {}
    parameters = signature.parameters.values()
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return voxcpm2_options
    accepted = set(signature.parameters)
    return {
        key: value
        for key, value in voxcpm2_options.items()
        if key in accepted
    }


def _decode_reference_audio_b64(reference_audio_b64: str) -> bytes:
    decoded = base64.b64decode(reference_audio_b64, validate=True)
    if len(decoded) > MAX_REFERENCE_AUDIO_BYTES:
        raise ValueError("call TTS reference audio is too large")
    return decoded


def _adapter_supports_streaming(adapter: Any, engine_id: str) -> bool:
    return (
        engine_id in LIVE_STREAMING_TTS_ENGINES
        and adapter is not None
        and callable(getattr(adapter, "stream", None))
    )


class NullPeerConnection:
    connectionState = "new"

    async def close(self) -> None:
        return None


class TerminalCallSessionError(RuntimeError):
    """Raised when a peer candidate cannot be registered on a terminal call."""


class PeerSwitchInProgressError(RuntimeError):
    """Raised when a second candidate races an owned engine switch."""


class SpeechSessionSelectionError(RuntimeError):
    """Raised when speech does not match the accepted call configuration."""


class SpeechSegmentConflictError(RuntimeError):
    """Raised when a segment identity is reused inconsistently."""


class SpeechTurnTerminalError(RuntimeError):
    """Raised when speech is submitted after a turn terminalized."""


@dataclass(frozen=True)
class AcceptedSpeechConfiguration:
    epoch: int
    voice_id: str
    engine_id: str


@dataclass(frozen=True)
class PeerOfferConfiguration:
    thread_id: str
    voice_id: str
    engine_id: str
    prompt_messages: tuple[dict[str, Any], ...]
    vad_adapter: Any | None
    stt_adapter: Any | None


@dataclass
class _PendingPeerCandidate:
    peer_connection: Any
    generation: int
    epoch: int
    outbound_audio_track: Any | None = None
    data_channel: Any | None = None
    timeout_task: asyncio.Task[None] | None = None
    configuration: PeerOfferConfiguration | None = None


@dataclass
class _PeerLifecycle:
    """All peer replacement and reconnect ownership guarded by one lock."""

    epoch: int = 0
    phase: str = "stable"
    candidate_generation: int = 0
    candidate: _PendingPeerCandidate | None = None
    active_generation: int = 0
    switch_generation: int = 0
    switch_owner: Any | None = None
    switch_task: asyncio.Task[tuple[bool, Any | None]] | None = None
    switch_transaction: _PeerSwitchTransaction | None = None
    retiring_peer: Any | None = None
    retiring_generation: int | None = None
    terminal_state: str | None = None
    state_before_reconnect: str | None = None
    grace_peer: Any | None = None
    grace_task: asyncio.Task[None] | None = None


@dataclass
class _TerminalCleanup:
    target_state: str
    reason: str
    cancel_cause: str
    active_peer: Any
    candidate_peer: Any | None
    prompt_lease_releaser: PromptLeaseReleaser | None
    cancel_pending: bool
    owned_peer_ids: set[int] = field(default_factory=set)
    owned_track_ids: set[int] = field(default_factory=set)
    owned_prompt_cleanups_pending: list[_OwnedPromptLeaseCleanup] = field(
        default_factory=list
    )
    owned_prompt_handoffs_pending: list[_OwnedPromptLeaseHandoff] = field(
        default_factory=list
    )
    extra_peers_pending: list[Any] = field(default_factory=list)
    extra_tracks_pending: list[Any] = field(default_factory=list)
    active_peer_pending: bool = True
    candidate_peer_pending: bool = True
    prompt_lease_pending: bool = True
    cancel_context: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    last_attempt_timed_out: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class _TerminalOutcome:
    target_state: str
    reason: str
    event: dict[str, Any] | None = None
    error: BaseException | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    emission_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    transaction_task: asyncio.Task[dict[str, Any]] | None = None
    event_commit: _EventOutboxEntry | None = None


@dataclass
class _OwnedPromptLeaseCleanup:
    releaser: PromptLeaseReleaser
    reason: str
    attempts: int = 0
    released: bool = False
    failure_state: dict[str, Any] | None = None
    task: asyncio.Task[None] | None = None


@dataclass
class _OwnedPromptLeaseHandoff:
    releaser: PromptLeaseReleaser
    accepted_configuration: AcceptedSpeechConfiguration | None
    task: asyncio.Task[bool] | None = None
    installed: bool = False
    release_cleanup: _OwnedPromptLeaseCleanup | None = None


@dataclass
class _EventOutboxEntry:
    sequence: int
    event: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: BaseException | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    done: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass(frozen=True)
class _CapturedTurnCancellation:
    active_task: Any | None
    turn_id: str | None
    request_id: str | None
    adapter: Any | None
    metrics_snapshot: Callable[[], dict[str, Any]] | None
    pending_terminal_turn_id: str | None
    pending_playback_final: dict[str, Any] | None


@dataclass
class _SpeechAdmission:
    """One speech owner installed atomically with its segment claim."""

    token: int
    lifecycle_epoch: int
    turn_id: str
    request_id: str
    adapter: Any
    active_task: asyncio.Task[Any] | None
    done: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass(frozen=True)
class _PeerSwitchTransaction:
    generation: int
    candidate_generation: int
    peer_connection: Any
    previous_peer_connection: Any | None
    previous_outbound_audio_track: Any | None
    accepted_outbound_audio_track: Any | None
    accepted_data_channel: Any | None
    configuration: PeerOfferConfiguration | None
    cancellation: _CapturedTurnCancellation | None
    prompt_lease_releaser: PromptLeaseReleaser | None
    state_before_switch: str
    stt_admission_tokens: tuple[int, ...]


@dataclass
class _PeerSwitchCleanupResult:
    errors: list[tuple[str, Exception]] = field(default_factory=list)
    unresolved_peers: list[Any] = field(default_factory=list)
    unresolved_tracks: list[Any] = field(default_factory=list)


@dataclass
class _ReconnectBackfillAdmission:
    token: int
    lifecycle_epoch: int


@dataclass
class _SttTurnAdmission:
    token: int
    lifecycle_epoch: int
    allow_transport_reconnect: bool
    task: asyncio.Task[Any] | None


@dataclass
class _TtsSegmentLedgerEntry:
    segment_id: str
    ordinal: int
    content_digest: str
    final_chunk: bool
    worker_request_id: str
    attempt_generation: int = 1
    state: str = "reserved"
    response: dict[str, Any] | None = None
    attempt_done: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class _TtsTurnLedger:
    state: str = "active"
    next_ordinal: int = 0
    segments: dict[str, _TtsSegmentLedgerEntry] = field(default_factory=dict)
    ordinal_owners: dict[int, str] = field(default_factory=dict)


class CallSession:
    def __init__(
        self,
        *,
        session_id: str,
        thread_id: str | None = None,
        voice_id: str | None = None,
        engine_id: str | None = None,
        prompt_messages: list[dict[str, Any]] | None = None,
        peer_connection: Any | None = None,
        data_channel: Any | None = None,
        vad_adapter: Any | None = None,
        stt_adapter: Any | None = None,
        settings: AiBackendSettings | None = None,
        event_sink: EventSink | None = None,
        tts_adapter: Any | None = None,
        outbound_audio_track: Any | None = None,
    ) -> None:
        self.session_id = session_id
        self.thread_id = thread_id
        self.voice_id = voice_id
        self.engine_id = engine_id
        self.prompt_messages = list(prompt_messages or [])
        self.peer_connection = peer_connection or NullPeerConnection()
        self.data_channel = data_channel
        self.vad_adapter = vad_adapter
        self.stt_adapter = stt_adapter
        self.settings = settings or AiBackendSettings()
        self.event_sink = event_sink
        self.tts_adapter = tts_adapter
        self.outbound_audio_track = outbound_audio_track
        self.outbound_audio_buffer = OutboundAudioBuffer()
        self.state = "listening"
        self.muted = False
        self.incoming_audio_frames = 0
        self.dropped_audio_frames = 0
        self.active_turn_task: Any | None = None
        self.started_at = datetime.now(timezone.utc)
        self.ended_at: datetime | None = None
        self.end_reason: str | None = None
        self.interrupted = False
        self._normalizer = InboundAudioFrameNormalizer()
        self._turn_frames: list[PcmAudioFrame] = []
        self._turn_started_at: str | None = None
        self._turn_index = 0
        self._tts_turn_ledgers: dict[str, _TtsTurnLedger] = {}
        self._tts_turn_playback_seconds: dict[str, float] = {}
        self._speech_turn_cancel_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
        self._speech_seen = False
        self._silence_ms = 0
        self._speech_start_frame: int | None = None
        self._barge_in_frames: list[PcmAudioFrame] = []
        self._barge_in_buffered_ms = 0
        self._barge_in_speech_ms = 0
        self._barge_in_speech_start_index: int | None = None
        self._barge_in_speech_started_at: str | None = None
        self._barge_in_energy_start_index: int | None = None
        self._barge_in_energy_started_at: str | None = None
        self._barge_in_interrupting = False
        self._cancelled_ai_turns: set[str] = set()
        self._cancelling_ai_turns: set[str] = set()
        self._active_tts_adapter: Any | None = None
        self._active_tts_request_id: str | None = None
        self._active_tts_turn_id: str | None = None
        self._active_tts_cancel_requested = False
        self._active_tts_metrics_snapshot: Callable[[], dict[str, Any]] | None = None
        self._speech_admission_generation = 0
        self._speech_admission: _SpeechAdmission | None = None
        self._last_tts_cancel_context: dict[str, Any] | None = None
        self._pending_speech_terminal_turn_id: str | None = None
        self._pending_speech_terminal_voice_id: str | None = None
        self._pending_speech_terminal_engine_id: str | None = None
        self._pending_speech_playback_final: dict[str, Any] | None = None
        self._late_tts_event_discard_count = 0
        self._undelivered_events: list[dict[str, Any]] = []
        self._event_commit_sequence = 0
        self._event_outbox: list[_EventOutboxEntry] = []
        self._event_delivery_task: asyncio.Task[None] | None = None
        self._media_reconnect_grace_pending = False
        self._media_reconnect_grace_until = 0.0
        self._media_reconnect_grace_logged = False
        self._media_reconnect_grace_audio_diag_count = 0
        self._reconnect_audio_backfill_ids: set[str] = set()
        self._active_reconnect_backfills = 0
        self._reconnect_backfill_admission_generation = 0
        self._reconnect_backfill_admissions: dict[
            int,
            _ReconnectBackfillAdmission,
        ] = {}
        self._stt_admission_generation = 0
        self._stt_admissions: dict[int, _SttTurnAdmission] = {}
        self._reconnect_live_frame_hold_until = 0.0
        self._reconnect_live_frame_hold_logged = False
        self._reconnect_live_frame_hold_frames: list[PcmAudioFrame] = []
        self._lifecycle_lock = asyncio.Lock()
        self._peer_lifecycle = _PeerLifecycle()
        self._tts_prompt_lease_releaser: PromptLeaseReleaser | None = None
        self._terminal_cleanup: _TerminalCleanup | None = None
        self._terminal_outcome: _TerminalOutcome | None = None
        self._terminal_cleanup_task: asyncio.Task[None] | None = None
        self._terminal_cleanup_failure_state: dict[str, Any] | None = None
        self._owned_peer_cleanup_tasks: set[asyncio.Task[None]] = set()
        self._owned_peer_cleanup_failures: list[dict[str, Any]] = []
        self._owned_track_cleanup_tasks: set[asyncio.Task[None]] = set()
        self._owned_track_cleanup_failures: list[dict[str, Any]] = []
        self._owned_prompt_lease_cleanups: list[_OwnedPromptLeaseCleanup] = []
        self._owned_prompt_lease_cleanup_tasks: set[asyncio.Task[None]] = set()
        self._owned_prompt_lease_cleanup_failures: list[dict[str, Any]] = []
        self._owned_prompt_lease_handoffs: list[_OwnedPromptLeaseHandoff] = []
        self._owned_prompt_lease_handoff_tasks: set[asyncio.Task[bool]] = set()

    @property
    def _pending_peer_connections(self) -> list[Any]:
        candidate = self._peer_lifecycle.candidate
        return [candidate.peer_connection] if candidate is not None else []

    @property
    def active_ai_turn(self) -> Any | None:
        return self.active_turn_task

    @active_ai_turn.setter
    def active_ai_turn(self, value: Any | None) -> None:
        self.active_turn_task = value

    async def can_prepare_tts_prompt(self) -> bool:
        async with self._lifecycle_lock:
            return self.ended_at is None and self.state not in {"ended", "failed"}

    async def install_or_release_tts_prompt_lease(
        self,
        releaser: PromptLeaseReleaser,
        *,
        accepted_configuration: AcceptedSpeechConfiguration | None = None,
    ) -> bool:
        handoff = self.start_prompt_lease_handoff(
            releaser,
            accepted_configuration=accepted_configuration,
        )
        return await self.wait_prompt_lease_handoff(handoff)

    def start_prompt_lease_handoff(
        self,
        releaser: PromptLeaseReleaser,
        *,
        accepted_configuration: AcceptedSpeechConfiguration | None = None,
    ) -> _OwnedPromptLeaseHandoff:
        """Synchronously own a model-granted lease before any caller await."""

        handoff = _OwnedPromptLeaseHandoff(
            releaser=releaser,
            accepted_configuration=accepted_configuration,
        )
        task = asyncio.create_task(self._run_prompt_lease_handoff(handoff))
        handoff.task = task
        self._owned_prompt_lease_handoffs.append(handoff)
        self._owned_prompt_lease_handoff_tasks.add(task)
        task.add_done_callback(self._owned_prompt_lease_handoff_tasks.discard)
        return handoff

    async def wait_prompt_lease_handoff(
        self,
        handoff: _OwnedPromptLeaseHandoff,
    ) -> bool:
        if handoff.task is None:
            raise RuntimeError("owned prompt lease handoff has no task")
        return await asyncio.shield(handoff.task)

    async def _run_prompt_lease_handoff(
        self,
        handoff: _OwnedPromptLeaseHandoff,
    ) -> bool:
        selection_error: SpeechSessionSelectionError | None = None
        owned_cleanup: _OwnedPromptLeaseCleanup | None = None
        async with self._lifecycle_lock:
            if handoff.accepted_configuration is not None:
                try:
                    self._validate_accepted_speech_configuration_locked(
                        handoff.accepted_configuration
                    )
                except SpeechSessionSelectionError as exc:
                    selection_error = exc
            if (
                selection_error is None
                and self.ended_at is None
                and self.state not in {"ended", "failed"}
            ):
                self._tts_prompt_lease_releaser = handoff.releaser
                handoff.installed = True
                return True
            owned_cleanup = self._start_owned_prompt_lease_cleanup_locked(
                handoff.releaser,
                reason=(
                    "stale_prepare_selection"
                    if selection_error is not None
                    else "terminal_prepare_result"
                ),
            )
            handoff.release_cleanup = owned_cleanup
        if owned_cleanup.task is None:
            raise RuntimeError("owned prompt lease cleanup has no task")
        await asyncio.shield(owned_cleanup.task)
        if selection_error is not None:
            raise selection_error
        return False

    def _start_owned_prompt_lease_cleanup_locked(
        self,
        releaser: PromptLeaseReleaser,
        *,
        reason: str,
    ) -> _OwnedPromptLeaseCleanup:
        cleanup = _OwnedPromptLeaseCleanup(releaser=releaser, reason=reason)
        task = asyncio.create_task(self._run_owned_prompt_lease_cleanup(cleanup))
        cleanup.task = task
        self._owned_prompt_lease_cleanups.append(cleanup)
        self._owned_prompt_lease_cleanup_tasks.add(task)
        task.add_done_callback(self._owned_prompt_lease_cleanup_tasks.discard)
        return cleanup

    async def _run_owned_prompt_lease_cleanup(
        self,
        cleanup: _OwnedPromptLeaseCleanup,
    ) -> None:
        for attempt in range(1, CALL_PROMPT_LEASE_CLEANUP_RETRY_LIMIT + 1):
            cleanup.attempts = attempt
            try:
                await asyncio.wait_for(
                    self._invoke_tts_prompt_lease_releaser(cleanup.releaser),
                    timeout=CALL_SWITCH_CLEANUP_STEP_TIMEOUT_SECONDS,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "[rayme-call] prompt_lease.owned_cleanup_failed session=%s "
                    "reason=%s attempt=%d exc=%s",
                    self.session_id,
                    cleanup.reason,
                    attempt,
                    exc.__class__.__name__,
                )
                if attempt < CALL_PROMPT_LEASE_CLEANUP_RETRY_LIMIT:
                    delay = min(
                        CALL_TERMINAL_CLEANUP_RETRY_BASE_SECONDS
                        * (2 ** max(attempt - 1, 0)),
                        CALL_TERMINAL_CLEANUP_RETRY_MAX_SECONDS,
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue
                cleanup.failure_state = {
                    "status": "retry_exhausted",
                    "reason": cleanup.reason,
                    "attempts": attempt,
                    "error": exc.__class__.__name__,
                }
                self._owned_prompt_lease_cleanup_failures.append(
                    dict(cleanup.failure_state)
                )
                return
            else:
                cleanup.released = True
                cleanup.failure_state = None
                return

    async def reserve_accepted_speech_configuration(
        self,
        *,
        voice_id: str,
        engine_id: str,
    ) -> AcceptedSpeechConfiguration:
        async with self._lifecycle_lock:
            lifecycle = self._peer_lifecycle
            if (
                self.ended_at is not None
                or lifecycle.phase == "terminal"
                or lifecycle.phase == "switching"
                or self.state in {"ended", "failed"}
            ):
                raise SpeechSessionSelectionError("call session is terminal")
            if voice_id != self.voice_id or engine_id != self.engine_id:
                raise SpeechSessionSelectionError(
                    "speech selection does not match the accepted call"
                )
            return AcceptedSpeechConfiguration(
                epoch=lifecycle.epoch,
                voice_id=voice_id,
                engine_id=engine_id,
            )

    async def _validate_accepted_speech_configuration(
        self,
        reservation: AcceptedSpeechConfiguration,
    ) -> None:
        async with self._lifecycle_lock:
            self._validate_accepted_speech_configuration_locked(reservation)

    def _validate_accepted_speech_configuration_locked(
        self,
        reservation: AcceptedSpeechConfiguration,
    ) -> None:
        lifecycle = self._peer_lifecycle
        if (
            self.ended_at is not None
            or lifecycle.phase != "stable"
            or reservation.epoch != lifecycle.epoch
            or reservation.voice_id != self.voice_id
            or reservation.engine_id != self.engine_id
        ):
            raise SpeechSessionSelectionError(
                "accepted call configuration changed before speech"
            )

    async def handle_inbound_audio_frame(self, frame: Any) -> dict[str, Any] | bool | None:
        self.incoming_audio_frames += 1
        was_raw_bytes = isinstance(frame, bytes)
        if (
            self.ended_at is not None
            or self._peer_lifecycle.phase == "terminal"
            or self.muted
            or self.state in {"ended", "failed", "rehearsing"}
        ):
            self.dropped_audio_frames += 1
            if self.incoming_audio_frames % 100 == 0:
                logger.info(
                    "[rayme-call] inbound.dropped session=%s total=%d dropped=%d "
                    "muted=%s state=%s",
                    self.session_id,
                    self.incoming_audio_frames,
                    self.dropped_audio_frames,
                    self.muted,
                    self.state,
                )
            return False if was_raw_bytes else None

        if self.state == "speaking":
            normalized = normalize_inbound_audio_frame(frame)
            return await self._handle_speaking_audio_frame(normalized)

        # During understanding/thinking/rehearsing states the AI is transcribing,
        # generating text, or preparing voice. Accepting inbound audio during this window causes ambient
        # noise to accumulate in the turn buffer, which Whisper then
        # hallucinates (e.g. "thank you" from room-tone silence). Drop frames
        # so the next turn starts clean.
        if self.state in {"understanding", "thinking", "rehearsing"}:
            self.dropped_audio_frames += 1
            return False if was_raw_bytes else None

        self._release_reconnect_live_frames_if_expired()

        normalized = normalize_inbound_audio_frame(frame)
        if self._hold_reconnect_live_frame_if_needed(normalized):
            return None

        speech_seen_before = self._speech_seen
        silence_before = self._silence_ms
        vad_result = self._append_turn_frame(normalized)
        end_of_turn = vad_result.get("end_of_turn", False)

        if not speech_seen_before and self._speech_seen:
            logger.info(
                "[rayme-call] vad.speech_start session=%s turn_frames=%d",
                self.session_id,
                len(self._turn_frames),
            )
        if not end_of_turn:
            if self._speech_seen and self._silence_ms != silence_before \
               and self._silence_ms > 0 and self._silence_ms % 200 < 40:
                logger.info(
                    "[rayme-call] vad.silence session=%s silence_ms=%d "
                    "threshold_ms=%d",
                    self.session_id,
                    self._silence_ms,
                    self._call_end_silence_ms(),
                )
            return None

        logger.info(
            "[rayme-call] vad.end_of_turn session=%s turn_frames=%d "
            "silence_ms=%d",
            self.session_id,
            len(self._turn_frames),
            self._silence_ms,
        )
        return await self.finalize_user_turn()

    def mark_media_reconnect_pending(self) -> None:
        if self.state == "listening" and self._speech_seen and self._turn_frames:
            self._media_reconnect_grace_pending = True
            logger.info(
                "[rayme-call] vad.reconnect_grace.pending session=%s "
                "turn_frames=%d silence_ms=%d",
                self.session_id,
                len(self._turn_frames),
                self._silence_ms,
            )

    def start_media_reconnect_grace_if_pending(self) -> None:
        if not self._media_reconnect_grace_pending:
            return
        self._media_reconnect_grace_pending = False
        grace_ms = self._call_media_reconnect_grace_ms()
        if grace_ms <= 0:
            return
        self._media_reconnect_grace_until = max(
            self._media_reconnect_grace_until,
            time.monotonic() + (grace_ms / 1000.0),
        )
        self._media_reconnect_grace_logged = False
        self._media_reconnect_grace_audio_diag_count = 0
        self._reconnect_live_frame_hold_until = max(
            self._reconnect_live_frame_hold_until,
            time.monotonic() + CALL_RECONNECT_BACKFILL_HOLD_SECONDS,
        )
        self._reconnect_live_frame_hold_logged = False
        logger.info(
            "[rayme-call] vad.reconnect_grace.start session=%s grace_ms=%d "
            "backfill_hold_ms=%d",
            self.session_id,
            grace_ms,
            int(CALL_RECONNECT_BACKFILL_HOLD_SECONDS * 1000),
        )

    async def mark_peer_connection_pending(
        self,
        peer_connection: Any,
        *,
        outbound_audio_track: Any | None = None,
        configuration: PeerOfferConfiguration | None = None,
        timeout_seconds: float = CALL_PEER_REPLACEMENT_TIMEOUT_SECONDS,
    ) -> int:
        reject_switching = False
        async with self._lifecycle_lock:
            lifecycle = self._peer_lifecycle
            if (
                self.ended_at is not None
                or self.state in {"ended", "failed"}
                or lifecycle.phase == "terminal"
            ):
                raise TerminalCallSessionError(
                    "cannot register a peer candidate on a terminal call"
                )
            if lifecycle.phase == "switching":
                reject_switching = True
                superseded_peers: list[Any] = []
                generation = lifecycle.candidate_generation
            else:
                superseded_candidate = lifecycle.candidate
                superseded_peers = (
                    [superseded_candidate.peer_connection]
                    if superseded_candidate is not None
                    and superseded_candidate.peer_connection is not peer_connection
                    else []
                )
                self._cancel_pending_peer_timeout_locked()
                lifecycle.candidate_generation += 1
                generation = lifecycle.candidate_generation
                candidate = _PendingPeerCandidate(
                    peer_connection=peer_connection,
                    generation=generation,
                    epoch=lifecycle.epoch,
                    outbound_audio_track=outbound_audio_track,
                    configuration=configuration,
                )
                lifecycle.candidate = candidate
                candidate.timeout_task = asyncio.create_task(
                    self._expire_pending_peer_connection(
                        peer_connection,
                        generation,
                        timeout_seconds,
                    )
                )
        if reject_switching:
            self._start_owned_peer_cleanup(
                peer_connection,
                reason="overlapping_switch_rejected",
            )
            await asyncio.sleep(0)
            raise PeerSwitchInProgressError(
                "cannot register a peer candidate during an engine switch"
            )
        for superseded_peer in superseded_peers:
            self._start_owned_peer_cleanup(
                superseded_peer,
                reason="candidate_superseded",
            )
        if superseded_peers:
            await asyncio.sleep(0)
        return generation

    def _start_owned_peer_cleanup(
        self,
        peer_connection: Any,
        *,
        reason: str,
    ) -> asyncio.Task[None]:
        task = asyncio.create_task(
            self._close_peer_until_resolved(
                peer_connection,
                reason=reason,
            )
        )
        self._owned_peer_cleanup_tasks.add(task)
        task.add_done_callback(self._owned_peer_cleanup_tasks.discard)
        return task

    async def _close_peer_until_resolved(
        self,
        peer_connection: Any,
        *,
        reason: str,
    ) -> None:
        for attempt in range(1, CALL_TERMINAL_CLEANUP_RETRY_LIMIT + 1):
            try:
                await asyncio.wait_for(
                    self._close_peer(peer_connection),
                    timeout=CALL_SWITCH_CLEANUP_STEP_TIMEOUT_SECONDS,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "[rayme-call] peer.owned_cleanup_failed session=%s "
                    "reason=%s attempt=%d exc=%s",
                    self.session_id,
                    reason,
                    attempt,
                    exc.__class__.__name__,
                )
                if attempt < CALL_TERMINAL_CLEANUP_RETRY_LIMIT:
                    delay = min(
                        CALL_TERMINAL_CLEANUP_RETRY_BASE_SECONDS
                        * (2 ** max(attempt - 1, 0)),
                        CALL_TERMINAL_CLEANUP_RETRY_MAX_SECONDS,
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue
                failure = {
                    "status": "retry_exhausted",
                    "reason": reason,
                    "attempts": attempt,
                    "peer_id": id(peer_connection),
                }
                self._owned_peer_cleanup_failures.append(failure)
                logger.error(
                    "[rayme-call] peer.owned_cleanup_exhausted session=%s "
                    "reason=%s attempts=%d peer_id=%d",
                    self.session_id,
                    reason,
                    attempt,
                    id(peer_connection),
                )
                return
            else:
                return

    def _start_owned_track_cleanup(
        self,
        track: Any,
        *,
        reason: str,
    ) -> asyncio.Task[None]:
        task = asyncio.create_task(
            self._stop_track_until_resolved(track, reason=reason)
        )
        self._owned_track_cleanup_tasks.add(task)
        task.add_done_callback(self._owned_track_cleanup_tasks.discard)
        return task

    async def _stop_track_until_resolved(
        self,
        track: Any,
        *,
        reason: str,
    ) -> None:
        stop = getattr(track, "stop_current", None)
        if not callable(stop):
            return
        for attempt in range(1, CALL_TERMINAL_CLEANUP_RETRY_LIMIT + 1):
            try:
                result = stop()
                if inspect.isawaitable(result):
                    await asyncio.wait_for(
                        result,
                        timeout=CALL_SWITCH_CLEANUP_STEP_TIMEOUT_SECONDS,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "[rayme-call] track.owned_cleanup_failed session=%s "
                    "reason=%s attempt=%d exc=%s",
                    self.session_id,
                    reason,
                    attempt,
                    exc.__class__.__name__,
                )
                if attempt < CALL_TERMINAL_CLEANUP_RETRY_LIMIT:
                    delay = min(
                        CALL_TERMINAL_CLEANUP_RETRY_BASE_SECONDS
                        * (2 ** max(attempt - 1, 0)),
                        CALL_TERMINAL_CLEANUP_RETRY_MAX_SECONDS,
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue
                self._owned_track_cleanup_failures.append(
                    {
                        "status": "retry_exhausted",
                        "reason": reason,
                        "attempts": attempt,
                        "track_id": id(track),
                    }
                )
                return
            else:
                return

    def is_peer_connection_pending(
        self,
        peer_connection: Any,
        generation: int | None = None,
    ) -> bool:
        candidate = self._peer_lifecycle.candidate
        return (
            candidate is not None
            and candidate.peer_connection is peer_connection
            and (
                generation is None
                or generation == candidate.generation
            )
        )

    def is_peer_connection_active_or_pending(self, peer_connection: Any) -> bool:
        return (
            peer_connection is self.peer_connection
            or peer_connection in self._pending_peer_connections
            or (
                self._peer_lifecycle.phase == "switching"
                and self._peer_lifecycle.switch_owner is peer_connection
            )
        )

    async def wait_for_peer_media_admission(
        self,
        peer_connection: Any,
        *,
        generation: int | None = None,
    ) -> bool:
        """Hold at most the receiver's current frame until its switch commits."""

        while True:
            async with self._lifecycle_lock:
                lifecycle = self._peer_lifecycle
                if self.ended_at is not None or lifecycle.phase == "terminal":
                    return False
                if (
                    peer_connection is self.peer_connection
                    and lifecycle.phase != "switching"
                ):
                    return True
                if (
                    lifecycle.phase == "switching"
                    and lifecycle.switch_owner is peer_connection
                    and lifecycle.switch_task is not None
                ):
                    switch_task = lifecycle.switch_task
                else:
                    return False
            try:
                await asyncio.shield(switch_task)
            except asyncio.CancelledError:
                raise
            except Exception:
                return False

    def set_data_channel_for_peer(
        self,
        peer_connection: Any,
        data_channel: Any,
        *,
        generation: int | None = None,
    ) -> None:
        if peer_connection is self.peer_connection:
            self.data_channel = data_channel
            return
        if not self.is_peer_connection_pending(peer_connection, generation):
            return
        candidate = self._peer_lifecycle.candidate
        if candidate is not None:
            candidate.data_channel = data_channel

    async def accept_pending_peer_connection(
        self,
        peer_connection: Any,
        *,
        generation: int | None = None,
        outbound_audio_track: Any | None = None,
    ) -> tuple[bool, Any | None]:
        # This snapshot has no await points, so another coroutine cannot alter
        # the lifecycle between the ownership checks. Avoiding a preliminary
        # lock acquisition also preserves FIFO ordering between candidate
        # acceptance and a reconnect-grace terminal decision.
        lifecycle = self._peer_lifecycle
        existing_switch_task = (
            lifecycle.switch_task
            if lifecycle.phase == "switching"
            and lifecycle.switch_owner is peer_connection
            else None
        )
        if existing_switch_task is not None:
            return await asyncio.shield(existing_switch_task)

        selection_changed = False
        cancel_selection = False
        captured_cancellation: _CapturedTurnCancellation | None = None
        accepted_configuration: PeerOfferConfiguration | None = None
        switch_generation: int | None = None
        released_prompt_lease: PromptLeaseReleaser | None = None
        previous_outbound_audio_track: Any | None = None
        accepted_outbound_audio_track: Any | None = None
        accepted_data_channel: Any | None = None
        switch_task: asyncio.Task[tuple[bool, Any | None]] | None = None
        async with self._lifecycle_lock:
            lifecycle = self._peer_lifecycle
            candidate = lifecycle.candidate
            if (
                candidate is None
                or candidate.peer_connection is not peer_connection
                or (generation is not None and generation != candidate.generation)
                or candidate.epoch != lifecycle.epoch
                or lifecycle.phase == "terminal"
                or self.ended_at is not None
            ):
                return False, None
            previous_peer_connection = (
                self.peer_connection
                if self.peer_connection is not peer_connection
                else None
            )
            previous_outbound_audio_track = self.outbound_audio_track
            if outbound_audio_track is None:
                outbound_audio_track = candidate.outbound_audio_track
            accepted_outbound_audio_track = (
                outbound_audio_track
                if outbound_audio_track is not None
                else self.outbound_audio_track
            )
            accepted_data_channel = (
                candidate.data_channel
                if candidate.data_channel is not None
                else self.data_channel
            )
            accepted_configuration = candidate.configuration
            if accepted_configuration is not None:
                selection_changed = (
                    accepted_configuration.voice_id != self.voice_id
                    or accepted_configuration.engine_id != self.engine_id
                )
            cancel_selection = selection_changed and (
                self._speech_admission is not None
                or self.active_turn_task is not None
                or self._active_tts_turn_id is not None
                or self._pending_speech_terminal_turn_id is not None
            )
            if cancel_selection:
                captured_cancellation = self._capture_turn_cancellation_locked()
                cancelling_turn_id = captured_cancellation.turn_id
                if cancelling_turn_id is not None:
                    self._cancelling_ai_turns.add(cancelling_turn_id)
            if (
                selection_changed
                and self.engine_id == "qwen3_1_7b"
                and accepted_configuration is not None
                and accepted_configuration.engine_id != "qwen3_1_7b"
            ):
                released_prompt_lease = self._tts_prompt_lease_releaser
            self._clear_pending_peer_locked(peer_connection)
            if selection_changed:
                # Do not publish the candidate selection while old generation
                # ownership is unresolved. Speech reservations are rejected in
                # this phase, so no new turn can be mistaken for the old one.
                lifecycle.phase = "switching"
                lifecycle.switch_generation += 1
                switch_generation = lifecycle.switch_generation
                lifecycle.switch_owner = peer_connection
                lifecycle.retiring_peer = previous_peer_connection
                lifecycle.retiring_generation = lifecycle.active_generation
                switch = _PeerSwitchTransaction(
                    generation=switch_generation,
                    candidate_generation=candidate.generation,
                    peer_connection=peer_connection,
                    previous_peer_connection=previous_peer_connection,
                    previous_outbound_audio_track=previous_outbound_audio_track,
                    accepted_outbound_audio_track=accepted_outbound_audio_track,
                    accepted_data_channel=accepted_data_channel,
                    configuration=accepted_configuration,
                    cancellation=captured_cancellation,
                    prompt_lease_releaser=released_prompt_lease,
                    state_before_switch=self.state,
                    stt_admission_tokens=tuple(self._stt_admissions),
                )
                switch_task = asyncio.create_task(
                    self._finish_peer_switch(switch)
                )
                lifecycle.switch_task = switch_task
                lifecycle.switch_transaction = switch
            else:
                self.peer_connection = peer_connection
                lifecycle.active_generation = candidate.generation
                self.outbound_audio_track = accepted_outbound_audio_track
                self.data_channel = accepted_data_channel
                if accepted_configuration is not None:
                    self._apply_peer_configuration_locked(accepted_configuration)
                self._complete_transport_reconnect_locked()
        if selection_changed:
            if switch_task is None:
                raise RuntimeError("engine switch has no owned completion task")
            return await asyncio.shield(switch_task)
        elif previous_peer_connection is not None:
            await self._close_peer(previous_peer_connection)
        return True, previous_peer_connection

    async def _finish_peer_switch(
        self,
        switch: _PeerSwitchTransaction,
    ) -> tuple[bool, Any | None]:
        """Finish one switch independently of its initiating callback."""

        cleanup = await self._run_peer_switch_cleanup(switch)
        terminal_outcome: _TerminalOutcome | None = None
        abandoned_peer: Any | None = None
        abandoned_track: Any | None = None
        async with self._lifecycle_lock:
            lifecycle = self._peer_lifecycle
            if lifecycle.phase == "terminal" or self.ended_at is not None:
                abandoned_peer = switch.peer_connection
                if (
                    switch.accepted_outbound_audio_track
                    in cleanup.unresolved_tracks
                    and switch.accepted_outbound_audio_track
                    is not switch.previous_outbound_audio_track
                ):
                    abandoned_track = switch.accepted_outbound_audio_track
                terminal_outcome = self._terminal_outcome
                owns_switch = False
            else:
                owns_switch = (
                    lifecycle.phase == "switching"
                    and lifecycle.switch_generation == switch.generation
                    and lifecycle.switch_owner is switch.peer_connection
                    and lifecycle.switch_task is asyncio.current_task()
                    and lifecycle.switch_transaction is switch
                )
            if not owns_switch:
                if lifecycle.switch_task is asyncio.current_task():
                    lifecycle.switch_task = None
                if lifecycle.switch_owner is switch.peer_connection:
                    lifecycle.switch_owner = None
                if lifecycle.switch_transaction is switch:
                    lifecycle.switch_transaction = None
                if lifecycle.retiring_peer is switch.previous_peer_connection:
                    lifecycle.retiring_peer = None
                    lifecycle.retiring_generation = None
                abandoned_peer = switch.peer_connection
                if (
                    switch.accepted_outbound_audio_track
                    in cleanup.unresolved_tracks
                    and switch.accepted_outbound_audio_track
                    is not switch.previous_outbound_audio_track
                ):
                    abandoned_track = switch.accepted_outbound_audio_track
            elif not cleanup.errors and switch.prompt_lease_releaser is not None:
                try:
                    await asyncio.wait_for(
                        self._invoke_tts_prompt_lease_releaser(
                            switch.prompt_lease_releaser
                        ),
                        timeout=CALL_SWITCH_CLEANUP_STEP_TIMEOUT_SECONDS,
                    )
                except Exception as exc:
                    cleanup.errors.append(("prompt_lease", exc))
                else:
                    if (
                        self._tts_prompt_lease_releaser
                        is switch.prompt_lease_releaser
                    ):
                        self._tts_prompt_lease_releaser = None
            if owns_switch and cleanup.errors:
                # The candidate becomes the terminal active transport only
                # after the stable switch has been abandoned. Every unresolved
                # old resource is transferred explicitly into terminal retry.
                self.peer_connection = switch.peer_connection
                self.outbound_audio_track = switch.accepted_outbound_audio_track
                self.data_channel = switch.accepted_data_channel
                lifecycle.switch_owner = None
                lifecycle.switch_task = None
                lifecycle.retiring_peer = None
                lifecycle.retiring_generation = None
                self._transition_terminal_locked(
                    target_state="failed",
                    reason="engine_switch_failed",
                    extra_peers=cleanup.unresolved_peers,
                    extra_tracks=cleanup.unresolved_tracks,
                )
                terminal_outcome = self._terminal_outcome
            elif owns_switch:
                self.peer_connection = switch.peer_connection
                lifecycle.active_generation = switch.candidate_generation
                self.outbound_audio_track = switch.accepted_outbound_audio_track
                self.data_channel = switch.accepted_data_channel
                if switch.configuration is not None:
                    self._apply_peer_configuration_locked(switch.configuration)
                preserved_conversational_state = (
                    self.state
                    if switch.state_before_switch in {"understanding", "thinking"}
                    and self.state in {"understanding", "thinking"}
                    else None
                )
                self._complete_transport_reconnect_locked()
                lifecycle.switch_owner = None
                lifecycle.switch_task = None
                lifecycle.switch_transaction = None
                lifecycle.retiring_peer = None
                lifecycle.retiring_generation = None
                if (
                    switch.cancellation is not None
                    and self.state not in {"ended", "failed"}
                ):
                    self.state = "listening"
                elif preserved_conversational_state is not None:
                    self.state = preserved_conversational_state
        if not owns_switch:
            terminal_cleanup = self._terminal_cleanup
            terminal_owns_abandoned_peer = (
                terminal_cleanup is not None
                and abandoned_peer is not None
                and id(abandoned_peer) in terminal_cleanup.owned_peer_ids
            )
            terminal_owns_abandoned_track = (
                terminal_cleanup is not None
                and abandoned_track is not None
                and id(abandoned_track) in terminal_cleanup.owned_track_ids
            )
            if (
                abandoned_peer is not None
                and abandoned_peer is not self.peer_connection
                and not terminal_owns_abandoned_peer
            ):
                self._start_owned_peer_cleanup(
                    abandoned_peer,
                    reason="switch_ownership_lost",
                )
            if abandoned_track is not None and not terminal_owns_abandoned_track:
                self._start_owned_track_cleanup(
                    abandoned_track,
                    reason="switch_ownership_lost",
                )
            await asyncio.sleep(0)
            if (
                terminal_outcome is not None
                and terminal_outcome.transaction_task is not None
            ):
                await asyncio.shield(terminal_outcome.transaction_task)
            return False, switch.previous_peer_connection
        if cleanup.errors:
            for step, exc in cleanup.errors:
                logger.error(
                    "[rayme-call] peer.switch_cleanup_failed session=%s "
                    "generation=%d step=%s exc=%s",
                    self.session_id,
                    switch.generation,
                    step,
                    exc.__class__.__name__,
                )
            if (
                terminal_outcome is not None
                and terminal_outcome.transaction_task is not None
            ):
                await asyncio.shield(terminal_outcome.transaction_task)
            return False, switch.previous_peer_connection
        return True, switch.previous_peer_connection

    async def _run_peer_switch_cleanup(
        self,
        switch: _PeerSwitchTransaction,
    ) -> _PeerSwitchCleanupResult:
        """Run every fallible switch cleanup step without stranding ownership."""

        cleanup = _PeerSwitchCleanupResult()
        stopped_track_ids: set[int] = set()
        for label, track in (
            ("old_playout", switch.previous_outbound_audio_track),
            ("new_playout", switch.accepted_outbound_audio_track),
        ):
            if track is None or id(track) in stopped_track_ids:
                continue
            stopped_track_ids.add(id(track))
            stop = getattr(track, "stop_current", None)
            if not callable(stop):
                continue
            try:
                result = stop()
                if inspect.isawaitable(result):
                    await asyncio.wait_for(
                        result,
                        timeout=CALL_SWITCH_CLEANUP_STEP_TIMEOUT_SECONDS,
                    )
            except Exception as exc:
                cleanup.errors.append((label, exc))
                cleanup.unresolved_tracks.append(track)
        self.outbound_audio_buffer.drain()

        if switch.previous_peer_connection is not None:
            try:
                await asyncio.wait_for(
                    self._close_peer(switch.previous_peer_connection),
                    timeout=CALL_SWITCH_CLEANUP_STEP_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                cleanup.errors.append(("old_peer", exc))
                cleanup.unresolved_peers.append(
                    switch.previous_peer_connection
                )

        if switch.cancellation is not None:
            try:
                await asyncio.wait_for(
                    self.cancel_ai_turn(
                        cause="engine_switch",
                        playout_tracks=(
                            switch.previous_outbound_audio_track,
                            switch.accepted_outbound_audio_track,
                        ),
                        playout_already_stopped=True,
                        captured=switch.cancellation,
                    ),
                    timeout=CALL_SWITCH_CLEANUP_STEP_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                cleanup.errors.append(("cancel", exc))
        return cleanup

    def _apply_peer_configuration_locked(
        self,
        configuration: PeerOfferConfiguration,
    ) -> None:
        self.thread_id = configuration.thread_id
        self.voice_id = configuration.voice_id
        self.engine_id = configuration.engine_id
        self.prompt_messages = [
            dict(message) for message in configuration.prompt_messages
        ]
        self.vad_adapter = configuration.vad_adapter
        self.stt_adapter = configuration.stt_adapter

    def _capture_turn_cancellation_locked(self) -> _CapturedTurnCancellation:
        admission = self._speech_admission
        resolved_turn_id = (
            self._active_tts_turn_id
            or self._pending_speech_terminal_turn_id
            or (admission.turn_id if admission is not None else None)
        )
        return _CapturedTurnCancellation(
            active_task=(
                self.active_turn_task
                or (admission.active_task if admission is not None else None)
            ),
            turn_id=resolved_turn_id,
            request_id=(
                self._active_tts_request_id
                or (admission.request_id if admission is not None else None)
            ),
            adapter=(
                self._active_tts_adapter
                or (admission.adapter if admission is not None else None)
            ),
            metrics_snapshot=(
                self._active_tts_metrics_snapshot
                if self._active_tts_request_id is not None
                and resolved_turn_id == self._active_tts_turn_id
                else None
            ),
            pending_terminal_turn_id=self._pending_speech_terminal_turn_id,
            pending_playback_final=(
                dict(self._pending_speech_playback_final)
                if self._pending_speech_playback_final is not None
                else None
            ),
        )

    async def reject_pending_peer_connection(
        self,
        peer_connection: Any,
        *,
        generation: int | None = None,
    ) -> bool:
        async with self._lifecycle_lock:
            if not self.is_peer_connection_pending(peer_connection, generation):
                return False
            self._clear_pending_peer_locked(peer_connection)
        self._start_owned_peer_cleanup(
            peer_connection,
            reason="candidate_rejected",
        )
        await asyncio.sleep(0)
        return True

    def _clear_pending_peer_locked(self, peer_connection: Any) -> None:
        candidate = self._peer_lifecycle.candidate
        if candidate is None or candidate.peer_connection is not peer_connection:
            return
        self._cancel_pending_peer_timeout_locked()
        self._peer_lifecycle.candidate = None

    def _cancel_pending_peer_timeout_locked(self) -> None:
        candidate = self._peer_lifecycle.candidate
        task = candidate.timeout_task if candidate is not None else None
        if candidate is not None:
            candidate.timeout_task = None
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()

    async def _expire_pending_peer_connection(
        self,
        peer_connection: Any,
        generation: int,
        timeout_seconds: float,
    ) -> None:
        try:
            await asyncio.sleep(max(timeout_seconds, 0.0))
            expired = await self.reject_pending_peer_connection(
                peer_connection,
                generation=generation,
            )
            if expired:
                logger.info(
                    "[rayme-call] peer.pending.timeout session=%s generation=%d "
                    "timeout_seconds=%.1f",
                    self.session_id,
                    generation,
                    timeout_seconds,
                )
        except asyncio.CancelledError:
            return

    @staticmethod
    async def _close_peer(peer_connection: Any) -> None:
        close = getattr(peer_connection, "close", None)
        if not callable(close):
            return
        result = close()
        if inspect.isawaitable(result):
            await result

    async def backfill_reconnect_audio(
        self,
        *,
        pcm: bytes,
        sample_rate: int = 16000,
        channels: int = 1,
        backfill_id: str | None = None,
        reason: str | None = None,
        attempt: int | None = None,
        batch_index: int | None = None,
        final: bool = True,
    ) -> dict[str, Any]:
        async with self._lifecycle_lock:
            if (
                self.ended_at is not None
                or self._peer_lifecycle.phase == "terminal"
                or self.state in {"ended", "failed"}
            ):
                return {
                    "status": "terminal",
                    "frames": 0,
                    "duration_ms": 0,
                    "state": self.state,
                    "reason": self.end_reason,
                }
            self._active_reconnect_backfills += 1
            self._reconnect_backfill_admission_generation += 1
            admission = _ReconnectBackfillAdmission(
                token=self._reconnect_backfill_admission_generation,
                lifecycle_epoch=self._peer_lifecycle.epoch,
            )
            self._reconnect_backfill_admissions[admission.token] = admission
        try:
            return await self._backfill_reconnect_audio_admitted(
                pcm=pcm,
                sample_rate=sample_rate,
                channels=channels,
                backfill_id=backfill_id,
                reason=reason,
                attempt=attempt,
                batch_index=batch_index,
                final=final,
                admission=admission,
            )
        finally:
            async with self._lifecycle_lock:
                self._reconnect_backfill_admissions.pop(admission.token, None)
                self._active_reconnect_backfills = max(
                    self._active_reconnect_backfills - 1,
                    0,
                )
                lifecycle = self._peer_lifecycle
                if (
                    self._active_reconnect_backfills == 0
                    and lifecycle.phase == "reconnecting"
                    and lifecycle.grace_peer is not None
                    and (
                        lifecycle.grace_task is None
                        or lifecycle.grace_task.done()
                    )
                ):
                    lifecycle.grace_task = asyncio.create_task(
                        self._expire_peer_reconnect_grace(
                            lifecycle.epoch,
                            lifecycle.grace_peer,
                        )
                    )

    async def _backfill_reconnect_audio_admitted(
        self,
        *,
        pcm: bytes,
        sample_rate: int,
        channels: int,
        backfill_id: str | None,
        reason: str | None,
        attempt: int | None,
        batch_index: int | None,
        final: bool,
        admission: _ReconnectBackfillAdmission,
    ) -> dict[str, Any]:
        if backfill_id and backfill_id in self._reconnect_audio_backfill_ids:
            logger.info(
                "[rayme-call] reconnect_audio.backfill.duplicate session=%s "
                "backfill_id=%s",
                self.session_id,
                backfill_id,
            )
            return {
                "status": "duplicate",
                "frames": 0,
                "duration_ms": 0,
                "state": self.state,
            }
        if self.muted or self.state in {"ended", "speaking", "understanding", "thinking", "rehearsing"}:
            logger.info(
                "[rayme-call] reconnect_audio.backfill.skip session=%s "
                "state=%s muted=%s bytes=%d reason=%s attempt=%s "
                "batch=%s final=%s",
                self.session_id,
                self.state,
                self.muted,
                len(pcm),
                reason or "",
                attempt if attempt is not None else "",
                batch_index if batch_index is not None else "",
                final,
            )
            return {
                "status": "skipped",
                "frames": 0,
                "duration_ms": 0,
                "state": self.state,
            }
        frames = self._pcm_backfill_frames(
            pcm,
            sample_rate=sample_rate,
            channels=channels,
        )
        if not frames:
            event = None
            if final:
                released_end = self._release_reconnect_live_frames(reason="final_empty_backfill")
                if self._should_finalize_after_reconnect_backfill(released_end, final=final):
                    event = await self.finalize_user_turn(
                        backfill_admission=admission
                    )
            if event is not None and event.get("status") in {"terminal", "superseded"}:
                return event
            response = {
                "status": "empty",
                "frames": 0,
                "duration_ms": 0,
                "state": self.state,
            }
            if event is not None:
                response["event"] = event
            return response
        if self.state != "listening":
            logger.info(
                "[rayme-call] reconnect_audio.backfill.skip session=%s "
                "state=%s frames=%d reason=%s attempt=%s batch=%s final=%s",
                self.session_id,
                self.state,
                len(frames),
                reason or "",
                attempt if attempt is not None else "",
                batch_index if batch_index is not None else "",
                final,
            )
            return {
                "status": "skipped",
                "frames": 0,
                "duration_ms": 0,
                "state": self.state,
            }

        overlap_trimmed_frames = 0
        frames, overlap_trimmed_frames = self._trim_reconnect_backfill_overlap(frames)
        if not frames:
            if backfill_id:
                self._reconnect_audio_backfill_ids.add(backfill_id)
            event = None
            if final:
                released_end = self._release_reconnect_live_frames(reason="final_overlap_backfill")
                if self._should_finalize_after_reconnect_backfill(released_end, final=final):
                    event = await self.finalize_user_turn(
                        backfill_admission=admission
                    )
            if event is not None and event.get("status") in {"terminal", "superseded"}:
                return event
            logger.info(
                "[rayme-call] reconnect_audio.backfill.overlap_only session=%s "
                "backfill_id=%s overlap_trimmed_frames=%d reason=%s attempt=%s "
                "batch=%s final=%s",
                self.session_id,
                backfill_id or "",
                overlap_trimmed_frames,
                reason or "",
                attempt if attempt is not None else "",
                batch_index if batch_index is not None else "",
                final,
            )
            response = {
                "status": "accepted",
                "frames": 0,
                "duration_ms": 0,
                "state": self.state,
            }
            if event is not None:
                response["event"] = event
            return response

        if backfill_id:
            self._reconnect_audio_backfill_ids.add(backfill_id)
        was_pending = self._media_reconnect_grace_pending
        started_turn = self._turn_started_at is None
        end_of_turn = False
        for frame in frames:
            vad_result = self._append_turn_frame(frame, source="reconnect_backfill")
            end_of_turn = end_of_turn or bool(vad_result.get("end_of_turn"))
        # Keep the grace armed for the first replacement-track frame. The
        # backfill inserts missing audio but does not prove the new transport is
        # stable yet, and a short post-reconnect silence should not finalize
        # before the browser's replacement track has a chance to resume.
        self._media_reconnect_grace_pending = was_pending or self._media_reconnect_grace_pending
        if final:
            released_end = self._release_reconnect_live_frames(reason="final_backfill")
            end_of_turn = end_of_turn or released_end

        duration_ms = sum(
            int((len(frame.pcm) // 2) * 1000 / max(frame.sample_rate, 1))
            for frame in frames
        )
        audio_stats = self._turn_audio_stats(frames)
        logger.info(
            "[rayme-call] reconnect_audio.backfill.applied session=%s "
            "backfill_id=%s frames=%d duration_ms=%d bytes=%d rms=%s peak=%s "
            "turn_frames=%d speech_seen=%s silence_ms=%d reason=%s attempt=%s "
            "batch=%s final=%s held_frames=%d started_turn=%s "
            "overlap_trimmed_frames=%d",
            self.session_id,
            backfill_id or "",
            len(frames),
            duration_ms,
            len(pcm),
            f"{audio_stats['rms']:.1f}" if audio_stats is not None else "unknown",
            f"{audio_stats['peak']:.1f}" if audio_stats is not None else "unknown",
            len(self._turn_frames),
            self._speech_seen,
            self._silence_ms,
            reason or "",
            attempt if attempt is not None else "",
            batch_index if batch_index is not None else "",
            final,
            len(self._reconnect_live_frame_hold_frames),
            started_turn,
            overlap_trimmed_frames,
        )
        event = None
        if self._should_finalize_after_reconnect_backfill(end_of_turn, final=final):
            logger.info(
                "[rayme-call] reconnect_audio.backfill.finalize session=%s "
                "turn_frames=%d silence_ms=%d reason=%s attempt=%s "
                "batch=%s",
                self.session_id,
                len(self._turn_frames),
                self._silence_ms,
                reason or "",
                attempt if attempt is not None else "",
                batch_index if batch_index is not None else "",
            )
            event = await self.finalize_user_turn(
                backfill_admission=admission
            )

        if event is not None and event.get("status") in {"terminal", "superseded"}:
            return event

        response = {
            "status": "accepted",
            "frames": len(frames),
            "duration_ms": duration_ms,
            "state": self.state,
        }
        if event is not None:
            response["event"] = event
        return response

    def _append_turn_frame(
        self,
        frame: PcmAudioFrame,
        *,
        source: str = "live",
    ) -> dict[str, bool]:
        self._turn_frames.append(frame)
        if self._turn_started_at is None:
            self._turn_started_at = utc_timestamp()
            logger.info(
                "[rayme-call] turn.started session=%s frame_count=%d "
                "sample_rate=%d pcm_bytes=%d source=%s",
                self.session_id,
                self.incoming_audio_frames,
                frame.sample_rate,
                len(frame.pcm),
                source,
            )
        vad_result = self._accept_vad_frame(frame)
        if vad_result.get("speech_detected", True):
            self._speech_seen = True
        return vad_result

    async def _handle_speaking_audio_frame(
        self,
        frame: PcmAudioFrame,
    ) -> dict[str, Any] | None:
        if self._barge_in_interrupting:
            self._preserve_barge_in_turn_frame(frame)
            return None

        # Browser capture keeps WebRTC echo cancellation/noise suppression on;
        # this server-side gate additionally requires sustained VAD-positive,
        # sufficiently energetic PCM before it can interrupt assistant playout.
        self._append_barge_in_onset_frame(frame)
        rms, _ = self._pcm_frame_rms_peak(frame)
        energetic = rms >= max(
            CALL_BARGE_IN_MIN_RMS,
            float(self.settings.call_min_turn_rms),
        )
        if energetic:
            if self._barge_in_energy_start_index is None:
                self._barge_in_energy_start_index = len(self._barge_in_frames) - 1
                self._barge_in_energy_started_at = utc_timestamp()
        else:
            self._barge_in_energy_start_index = None
            self._barge_in_energy_started_at = None
        speech_now, detected_start_index = self._detect_barge_in_speech(frame)
        frame_ms = self._pcm_frame_duration_ms(frame)
        if speech_now:
            if self._barge_in_energy_start_index is not None:
                detected_start_index = max(
                    detected_start_index or 0,
                    self._barge_in_energy_start_index,
                )
            if self._barge_in_speech_ms <= 0:
                self._barge_in_speech_start_index = (
                    detected_start_index
                    if detected_start_index is not None
                    else len(self._barge_in_frames) - 1
                )
                self._barge_in_speech_started_at = (
                    self._barge_in_energy_started_at or utc_timestamp()
                )
            elif detected_start_index is not None:
                current_start = self._barge_in_speech_start_index
                self._barge_in_speech_start_index = (
                    detected_start_index
                    if current_start is None
                    else min(current_start, detected_start_index)
                )
            self._barge_in_speech_ms += frame_ms
        else:
            self._barge_in_speech_ms = 0
            self._barge_in_speech_start_index = None
            self._barge_in_speech_started_at = None
            return None

        if self._barge_in_speech_ms < CALL_BARGE_IN_MIN_SPEECH_MS:
            return None

        onset_index = self._barge_in_speech_start_index
        if onset_index is None:
            onset_index = max(len(self._barge_in_frames) - 1, 0)
        # Keep one frame of preroll, but exclude older playback echo/noise from
        # the next STT turn. The candidate buffer itself is explicitly bounded.
        onset_index = max(onset_index - 1, 0)
        onset_frames = list(self._barge_in_frames[onset_index:])
        onset_started_at = self._barge_in_speech_started_at
        self._reset_barge_in_onset()
        self._begin_barge_in_turn(onset_frames, started_at=onset_started_at)

        logger.info(
            "[rayme-call] vad.barge_in session=%s onset_frames=%d onset_ms=%d",
            self.session_id,
            len(onset_frames),
            sum(self._pcm_frame_duration_ms(item) for item in onset_frames),
        )
        self._barge_in_interrupting = True
        try:
            return await self.interrupt(cause="vad_barge_in")
        finally:
            self._barge_in_interrupting = False

    def _append_barge_in_onset_frame(self, frame: PcmAudioFrame) -> None:
        self._barge_in_frames.append(frame)
        self._barge_in_buffered_ms += self._pcm_frame_duration_ms(frame)
        while (
            self._barge_in_buffered_ms > CALL_BARGE_IN_MAX_ONSET_BUFFER_MS
            and len(self._barge_in_frames) > 1
        ):
            removed = self._barge_in_frames.pop(0)
            self._barge_in_buffered_ms -= self._pcm_frame_duration_ms(removed)
            if self._barge_in_speech_start_index is not None:
                self._barge_in_speech_start_index = max(
                    self._barge_in_speech_start_index - 1,
                    0,
                )
            if self._barge_in_energy_start_index is not None:
                self._barge_in_energy_start_index = max(
                    self._barge_in_energy_start_index - 1,
                    0,
                )

    def _detect_barge_in_speech(
        self,
        frame: PcmAudioFrame,
    ) -> tuple[bool, int | None]:
        rms, _ = self._pcm_frame_rms_peak(frame)
        if rms < max(CALL_BARGE_IN_MIN_RMS, float(self.settings.call_min_turn_rms)):
            return False, None

        adapter = self.vad_adapter
        if adapter is not None and hasattr(adapter, "accept_audio_frame"):
            result = dict(adapter.accept_audio_frame(frame.pcm))
            return bool(result.get("speech_detected", False)), None

        if adapter is not None and hasattr(adapter, "speech_timestamps"):
            samples = self._pcm_frames_as_float32(self._barge_in_frames)
            timestamps = list(adapter.speech_timestamps(samples))
            if not timestamps:
                return False, None
            latest = timestamps[-1]
            frame_samples = max(len(frame.pcm) // 2, 1)
            latest_end = int(latest.get("end", 0))
            speech_reaches_current_frame = latest_end >= max(
                len(samples) - frame_samples,
                0,
            )
            if not speech_reaches_current_frame:
                return False, None
            speech_start_sample = max(int(latest.get("start", 0)), 0)
            return True, self._frame_index_for_sample_offset(
                self._barge_in_frames,
                speech_start_sample,
            )

        energy_threshold = max(
            CALL_BARGE_IN_MIN_RMS,
            float(self.settings.vad_threshold) * 1000.0,
        )
        return rms >= energy_threshold, None

    def _begin_barge_in_turn(
        self,
        frames: list[PcmAudioFrame],
        *,
        started_at: str | None,
    ) -> None:
        if not frames:
            return
        self._turn_frames.extend(frames)
        if self._turn_started_at is None:
            self._turn_started_at = started_at or utc_timestamp()
        self._speech_seen = True
        self._silence_ms = 0
        if self._speech_start_frame is None:
            self._speech_start_frame = max(len(self._turn_frames) - len(frames) + 1, 1)

    def _preserve_barge_in_turn_frame(self, frame: PcmAudioFrame) -> None:
        self._turn_frames.append(frame)
        if self._turn_started_at is None:
            self._turn_started_at = utc_timestamp()
        rms, _ = self._pcm_frame_rms_peak(frame)
        if rms >= max(CALL_BARGE_IN_MIN_RMS, float(self.settings.call_min_turn_rms)):
            self._speech_seen = True
            self._silence_ms = 0

    def _reset_barge_in_onset(self) -> None:
        self._barge_in_frames.clear()
        self._barge_in_buffered_ms = 0
        self._barge_in_speech_ms = 0
        self._barge_in_speech_start_index = None
        self._barge_in_speech_started_at = None
        self._barge_in_energy_start_index = None
        self._barge_in_energy_started_at = None

    @staticmethod
    def _pcm_frame_duration_ms(frame: PcmAudioFrame) -> int:
        sample_count = len(frame.pcm) // 2
        return max(int(sample_count * 1000 / max(frame.sample_rate, 1)), 1)

    @staticmethod
    def _pcm_frames_as_float32(frames: list[PcmAudioFrame]) -> np.ndarray:
        chunks = [
            np.frombuffer(frame.pcm, dtype=np.int16).astype(np.float32)
            / float(np.iinfo(np.int16).max)
            for frame in frames
            if len(frame.pcm) >= 2 and len(frame.pcm) % 2 == 0
        ]
        if not chunks:
            return np.asarray([], dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32, copy=False)

    @staticmethod
    def _frame_index_for_sample_offset(
        frames: list[PcmAudioFrame],
        sample_offset: int,
    ) -> int:
        consumed = 0
        for index, frame in enumerate(frames):
            consumed += len(frame.pcm) // 2
            if sample_offset < consumed:
                return index
        return max(len(frames) - 1, 0)

    def _release_reconnect_live_frames_if_expired(self) -> None:
        until = self._reconnect_live_frame_hold_until
        if until <= 0:
            return
        if time.monotonic() >= until:
            self._release_reconnect_live_frames(reason="timeout")

    def _hold_reconnect_live_frame_if_needed(self, frame: PcmAudioFrame) -> bool:
        until = self._reconnect_live_frame_hold_until
        if until <= 0:
            return False
        now = time.monotonic()
        if now >= until:
            self._release_reconnect_live_frames(reason="timeout")
            return False

        self._reconnect_live_frame_hold_frames.append(frame)
        held = len(self._reconnect_live_frame_hold_frames)
        if not self._reconnect_live_frame_hold_logged or held <= 3 or held % 25 == 0:
            self._reconnect_live_frame_hold_logged = True
            logger.info(
                "[rayme-call] reconnect_audio.live_hold session=%s "
                "held_frames=%d remaining_ms=%d rms=%.1f peak=%.1f",
                self.session_id,
                held,
                int((until - now) * 1000),
                *self._pcm_frame_rms_peak(frame),
            )
        return True

    def _release_reconnect_live_frames(self, *, reason: str) -> bool:
        frames = list(self._reconnect_live_frame_hold_frames)
        self._reconnect_live_frame_hold_frames.clear()
        self._reconnect_live_frame_hold_until = 0.0
        self._reconnect_live_frame_hold_logged = False
        if not frames:
            logger.info(
                "[rayme-call] reconnect_audio.live_hold.release session=%s "
                "reason=%s held_frames=0",
                self.session_id,
                reason,
            )
            return False

        logger.info(
            "[rayme-call] reconnect_audio.live_hold.release session=%s "
            "reason=%s held_frames=%d",
            self.session_id,
            reason,
            len(frames),
        )
        end_of_turn = False
        for frame in frames:
            vad_result = self._append_turn_frame(frame, source="reconnect_live_hold")
            end_of_turn = end_of_turn or bool(vad_result.get("end_of_turn"))
        return end_of_turn

    def _should_finalize_after_reconnect_backfill(
        self,
        end_of_turn: bool,
        *,
        final: bool,
    ) -> bool:
        if not self._turn_frames:
            return False
        if final:
            if end_of_turn:
                return True
            return self._speech_seen and self._silence_ms >= self._call_end_silence_ms()
        return (
            self._speech_seen
            and self._silence_ms >= self._nonfinal_reconnect_backfill_silence_ms()
        )

    def _nonfinal_reconnect_backfill_silence_ms(self) -> int:
        return max(
            self._call_end_silence_ms(),
            self._call_media_reconnect_grace_ms(),
            3000,
        )

    async def finalize_user_turn(
        self,
        *,
        backfill_admission: _ReconnectBackfillAdmission | None = None,
    ) -> dict[str, Any] | None:
        if not self._turn_frames:
            return None

        admission, stale_response = await self._admit_stt_turn(
            allow_transport_reconnect=backfill_admission is not None
        )
        if stale_response is not None:
            return stale_response
        if admission is None:
            raise RuntimeError("STT turn was admitted without lifecycle ownership")
        try:
            return await self._finalize_user_turn_admitted(admission)
        finally:
            async with self._lifecycle_lock:
                self._release_stt_admission_locked(admission)

    async def _finalize_user_turn_admitted(
        self,
        admission: _SttTurnAdmission,
    ) -> dict[str, Any] | None:
        if not self._turn_frames:
            return None

        turn_id = f"user-turn-{self._turn_index + 1}"
        frames = self._trim_trailing_silence_for_stt(list(self._turn_frames))
        started_at = self._turn_started_at or utc_timestamp()
        ended_at = utc_timestamp()
        total_pcm_bytes = sum(len(f.pcm) for f in frames)
        audio_stats = self._turn_audio_stats(frames)
        if (
            audio_stats is not None
            and audio_stats["rms"] < float(self.settings.call_min_turn_rms)
        ):
            logger.info(
                "[rayme-call] stt.skip_near_silence session=%s turn=%s "
                "frames=%d rms=%.1f peak=%.1f threshold=%.1f",
                self.session_id,
                turn_id,
                len(frames),
                audio_stats["rms"],
                audio_stats["peak"],
                float(self.settings.call_min_turn_rms),
            )
            self._turn_frames.clear()
            self._turn_started_at = None
            self._speech_seen = False
            self._silence_ms = 0
            self._speech_start_frame = None
            self._media_reconnect_grace_audio_diag_count = 0
            if self.ended_at is None:
                self.state = "listening"
            return None
        self._turn_index += 1
        turn_id = f"user-turn-{self._turn_index}"
        if self.ended_at is None:
            self.state = "understanding"
            await self.emit_event(
                simple_event("state", session_id=self.session_id, turn_id=turn_id, state="understanding")
            )
        logger.info(
            "[rayme-call] stt.begin session=%s turn=%s frames=%d pcm_bytes=%d "
            "rms=%s peak=%s",
            self.session_id,
            turn_id,
            len(frames),
            total_pcm_bytes,
            f"{audio_stats['rms']:.1f}" if audio_stats is not None else "unknown",
            f"{audio_stats['peak']:.1f}" if audio_stats is not None else "unknown",
        )
        stt_started = time.perf_counter()
        self._turn_frames.clear()
        self._turn_started_at = None
        self._speech_seen = False
        self._silence_ms = 0
        self._speech_start_frame = None
        self._media_reconnect_grace_audio_diag_count = 0

        transcription: dict[str, Any] | None = None
        transcription_error: Exception | None = None
        try:
            transcription = await asyncio.to_thread(self._transcribe_turn, frames)
        except Exception as exc:
            transcription_error = exc

        stale_response = await self._stale_stt_turn_response(admission)
        if stale_response is not None:
            return stale_response

        if transcription_error is not None:
            logger.error(
                "[rayme-call] stt.failed session=%s turn=%s elapsed_ms=%d exc=%s",
                self.session_id,
                turn_id,
                int((time.perf_counter() - stt_started) * 1000),
                transcription_error.__class__.__name__,
            )
            event = failed_event(
                session_id=self.session_id,
                turn_id=turn_id,
                code="call_stt_failed",
                message="Speech transcription failed. Please try speaking again.",
                retry_allowed=True,
            )
            stale_response = await self._stale_stt_turn_response(admission)
            if stale_response is not None:
                return stale_response
            _, stale_response = await self._commit_stt_event(
                admission,
                event,
                next_state="listening",
            )
            if stale_response is not None:
                return stale_response
            return event

        if transcription is None:
            raise RuntimeError("speech transcription returned no result")

        text = str(transcription.get("transcript") or "").strip()
        status = str(transcription.get("status") or "")
        logger.info(
            "[rayme-call] stt.result session=%s turn=%s transcript_len=%d "
            "language=%s elapsed_ms=%d",
            self.session_id,
            turn_id,
            len(text),
            transcription.get("language"),
            int((time.perf_counter() - stt_started) * 1000),
        )
        if status != "accepted" or not text:
            event = failed_event(
                session_id=self.session_id,
                turn_id=turn_id,
                code="call_stt_failed",
                message="Speech transcription failed. Please try speaking again.",
                retry_allowed=True,
            )
            stale_response = await self._stale_stt_turn_response(admission)
            if stale_response is not None:
                return stale_response
            _, stale_response = await self._commit_stt_event(
                admission,
                event,
                next_state="listening",
            )
            if stale_response is not None:
                return stale_response
            return event
        event = user_final_event(
            session_id=self.session_id,
            turn_id=turn_id,
            text=text,
            started_at=started_at,
            ended_at=ended_at,
        )
        stale_response = await self._stale_stt_turn_response(admission)
        if stale_response is not None:
            return stale_response
        _, stale_response = await self._commit_stt_event(
            admission,
            event,
            next_state="thinking",
        )
        if stale_response is not None:
            return stale_response
        return {
            "type": event["type"],
            "session_id": event["session_id"],
            "turn_id": event["turn_id"],
            "text": event["text"],
        }

    async def _admit_stt_turn(
        self,
        *,
        allow_transport_reconnect: bool,
    ) -> tuple[_SttTurnAdmission | None, dict[str, Any] | None]:
        async with self._lifecycle_lock:
            lifecycle = self._peer_lifecycle
            if (
                self.ended_at is not None
                or lifecycle.phase == "terminal"
                or self.state in {"ended", "failed"}
            ):
                return None, self._terminal_stt_response_locked()
            self._stt_admission_generation += 1
            admission = _SttTurnAdmission(
                token=self._stt_admission_generation,
                lifecycle_epoch=lifecycle.epoch,
                allow_transport_reconnect=allow_transport_reconnect,
                task=asyncio.current_task(),
            )
            self._stt_admissions[admission.token] = admission
            return admission, None

    async def _stale_stt_turn_response(
        self,
        admission: _SttTurnAdmission,
    ) -> dict[str, Any] | None:
        async with self._lifecycle_lock:
            return self._stale_stt_turn_response_locked(admission)

    def _stale_stt_turn_response_locked(
        self,
        admission: _SttTurnAdmission,
    ) -> dict[str, Any] | None:
        current = self._stt_admissions.get(admission.token)
        lifecycle = self._peer_lifecycle
        if current is not admission:
            return {
                "status": "superseded",
                "state": self.state,
            }
        if (
            self.ended_at is not None
            or lifecycle.phase == "terminal"
            or self.state in {"ended", "failed"}
        ):
            return self._terminal_stt_response_locked()
        if (
            admission.lifecycle_epoch != lifecycle.epoch
            or (
                lifecycle.phase not in {"stable", "reconnecting"}
                and not (
                    lifecycle.phase == "switching"
                    and lifecycle.switch_transaction is not None
                    and admission.token
                    in lifecycle.switch_transaction.stt_admission_tokens
                    and admission.task is not None
                    and not admission.task.done()
                )
            )
        ):
            return {
                "status": "superseded",
                "state": self.state,
            }
        return None

    def _release_stt_admission_locked(
        self,
        admission: _SttTurnAdmission,
    ) -> None:
        current = self._stt_admissions.get(admission.token)
        if current is not admission:
            return
        self._stt_admissions.pop(admission.token, None)
        lifecycle = self._peer_lifecycle
        if (
            self.state == "understanding"
            and self.ended_at is None
            and lifecycle.phase != "terminal"
            and not self._stt_admissions
        ):
            self.state = (
                "reconnecting"
                if lifecycle.phase == "reconnecting"
                else "listening"
            )

    async def _commit_stt_event(
        self,
        admission: _SttTurnAdmission,
        event: dict[str, Any],
        *,
        next_state: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Atomically order an STT event against terminal lifecycle commit."""

        async with self._lifecycle_lock:
            stale_response = self._stale_stt_turn_response_locked(admission)
            if stale_response is not None:
                return None, stale_response
            entry = self._commit_event(event)
            self.state = next_state
        return await self._await_event_commit(entry), None

    def _terminal_stt_response_locked(self) -> dict[str, Any]:
        return {
            "status": "terminal",
            "frames": 0,
            "duration_ms": 0,
            "state": self.state,
            "reason": self.end_reason,
        }

    def _commit_event(
        self,
        event: dict[str, Any] | None = None,
    ) -> _EventOutboxEntry:
        """Append one event to the session order without awaiting its sink."""

        self._event_commit_sequence += 1
        entry = _EventOutboxEntry(sequence=self._event_commit_sequence)
        if event is not None:
            entry.event = dict(event)
            entry.ready.set()
        self._event_outbox.append(entry)
        if self._event_delivery_task is None or self._event_delivery_task.done():
            self._event_delivery_task = asyncio.create_task(
                self._deliver_event_outbox()
            )
        return entry

    def _resolve_event_commit(
        self,
        entry: _EventOutboxEntry,
        event: dict[str, Any],
    ) -> None:
        if entry.ready.is_set():
            return
        entry.event = dict(event)
        entry.ready.set()

    async def _deliver_event_outbox(self) -> None:
        try:
            while self._event_outbox:
                entry = self._event_outbox[0]
                await entry.ready.wait()
                try:
                    if entry.event is None:
                        raise RuntimeError("committed event has no payload")
                    entry.result = await self._deliver_event(entry.event)
                except BaseException as exc:
                    entry.error = exc
                finally:
                    if self._event_outbox and self._event_outbox[0] is entry:
                        self._event_outbox.pop(0)
                    entry.done.set()
        finally:
            self._event_delivery_task = None
            if self._event_outbox:
                self._event_delivery_task = asyncio.create_task(
                    self._deliver_event_outbox()
                )

    async def _await_event_commit(
        self,
        entry: _EventOutboxEntry,
    ) -> dict[str, Any]:
        await asyncio.shield(entry.done.wait())
        if entry.error is not None:
            raise entry.error
        if entry.result is None:
            raise RuntimeError("committed event completed without a result")
        return dict(entry.result)

    async def emit_event(self, event: dict[str, Any]) -> dict[str, Any]:
        entry = self._commit_event(event)
        if asyncio.current_task() is self._event_delivery_task:
            # The only delivery worker cannot await an entry queued behind the
            # event whose sink it is currently invoking. Ownership is already
            # committed; delivery resumes in order after the sink returns.
            return dict(event)
        return await self._await_event_commit(entry)

    async def _deliver_event(self, event: dict[str, Any]) -> dict[str, Any]:
        event_type = event.get("type")
        event_turn_id = event.get("turn_id")
        if (
            event_type in {AI_AUDIO_STARTED_EVENT, AI_DONE_EVENT}
            and isinstance(event_turn_id, str)
            and (
                event_turn_id in self._cancelled_ai_turns
                or event_turn_id in self._cancelling_ai_turns
                or self.state in {"ended", "failed"}
            )
        ):
            self._late_tts_event_discard_count += 1
            logger.info(
                "[rayme-call] tts.event.discarded session=%s turn=%s type=%s",
                self.session_id,
                event_turn_id,
                event_type,
            )
            return {"status": "discarded", "turn_id": event_turn_id}

        if self.event_sink is not None:
            result = self.event_sink(event)
            if inspect.isawaitable(result):
                await result

        channel = self.data_channel
        ready_state = getattr(channel, "readyState", None) if channel is not None else None
        delivered = False
        if channel is None:
            logger.info(
                "[rayme-call] event.skip_no_channel session=%s type=%s",
                self.session_id,
                event_type,
            )
        elif ready_state is not None and ready_state != "open":
            logger.info(
                "[rayme-call] event.skip_channel_not_open session=%s type=%s "
                "readyState=%s",
                self.session_id,
                event_type,
                ready_state,
            )
        if channel is not None and getattr(channel, "readyState", "open") == "open":
            send = getattr(channel, "send", None)
            if callable(send):
                try:
                    send(json.dumps(event, separators=(",", ":")))
                    delivered = True
                    logger.info(
                        "[rayme-call] event.sent session=%s type=%s readyState=%s",
                        self.session_id,
                        event_type,
                        ready_state or "open",
                    )
                except Exception as exc:
                    logger.exception(
                        "[rayme-call] event.send_failed session=%s type=%s exc=%s",
                        self.session_id,
                        event_type,
                        exc.__class__.__name__,
                    )
        if not delivered and event_type in CALL_RECOVERABLE_EVENT_TYPES:
            self._undelivered_events.append(dict(event))
            logger.info(
                "[rayme-call] event.queued_undelivered session=%s type=%s pending=%d",
                self.session_id,
                event_type,
                len(self._undelivered_events),
            )
        return event

    def drain_undelivered_events(self) -> list[dict[str, Any]]:
        events = list(self._undelivered_events)
        self._undelivered_events.clear()
        if events:
            logger.info(
                "[rayme-call] event.drain_undelivered session=%s count=%d",
                self.session_id,
                len(events),
            )
        return events

    async def set_muted(self, muted: bool) -> dict[str, Any]:
        async with self._lifecycle_lock:
            self._ensure_control_mutable_locked()
            self.muted = muted
            self.state = "muted" if muted else "listening"
            event = simple_event(
                MUTED_EVENT,
                session_id=self.session_id,
                muted=muted,
            )
            entry = self._commit_event(event)
        if asyncio.current_task() is self._event_delivery_task:
            return event
        return await self._await_event_commit(entry)

    async def interrupt(self, *, cause: str = "button_interrupt") -> dict[str, Any]:
        async with self._lifecycle_lock:
            self._ensure_control_mutable_locked()
            self.interrupted = True
            captured = self._capture_turn_cancellation_locked()
        cancel_context = await self.cancel_ai_turn(
            cause=cause,
            captured=captured,
        )
        async with self._lifecycle_lock:
            self._ensure_control_mutable_locked()
            self.state = "interrupted"
            event_payload = simple_event(
                INTERRUPTED_EVENT,
                session_id=self.session_id,
                receiver_drain_ms=CALL_INTERRUPT_RECEIVER_DRAIN_MS,
                **cancel_context,
            )
            entry = self._commit_event(event_payload)
        if asyncio.current_task() is self._event_delivery_task:
            event = event_payload
        else:
            event = await self._await_event_commit(entry)
        async with self._lifecycle_lock:
            if (
                self.ended_at is None
                and self._peer_lifecycle.phase != "terminal"
                and self.state == "interrupted"
            ):
                self.state = "listening"
        return event

    async def cancel_speech_turn(self, turn_id: str) -> dict[str, Any]:
        """Cancel one web-owned speech turn exactly once, even across retries."""
        async with self._lifecycle_lock:
            self._ensure_control_mutable_locked()
            cancel_task = self._speech_turn_cancel_tasks.get(turn_id)
            if cancel_task is None:
                cancel_task = asyncio.create_task(
                    self._cancel_speech_turn_once(turn_id)
                )
                self._speech_turn_cancel_tasks[turn_id] = cancel_task
        return await asyncio.shield(cancel_task)

    async def _cancel_speech_turn_once(self, turn_id: str) -> dict[str, Any]:
        async with self._lifecycle_lock:
            self._ensure_control_mutable_locked()
            owns_active_speech = (
                self._active_tts_turn_id == turn_id
                or self._pending_speech_terminal_turn_id == turn_id
            )
            if not owns_active_speech:
                self._cancel_tts_turn_locked(turn_id)

        if owns_active_speech:
            cancel_context = await self.cancel_ai_turn(
                turn_id,
                cause="web_turn_cancel",
            )
        else:
            cancel_context = {
                "control_cause": "web_turn_cancel",
                "cancelled_turn_id": turn_id,
            }
        async with self._lifecycle_lock:
            self._ensure_control_mutable_locked()
            self.state = "listening"
        return cancel_context

    async def update_call_selection(
        self,
        *,
        voice_id: str | None,
        engine_id: str | None,
    ) -> None:
        async with self._lifecycle_lock:
            self._ensure_control_mutable_locked()
            changed = voice_id != self.voice_id or engine_id != self.engine_id
            cancel_selection = changed and (
                self._speech_admission is not None
                or self.active_turn_task is not None
                or self._active_tts_turn_id is not None
                or self._pending_speech_terminal_turn_id is not None
            )
            captured = (
                self._capture_turn_cancellation_locked()
                if cancel_selection
                else None
            )
        if captured is not None:
            await self.cancel_ai_turn(
                cause="engine_switch",
                captured=captured,
            )
        async with self._lifecycle_lock:
            self._ensure_control_mutable_locked()
            if captured is not None:
                self.state = "listening"
            self.voice_id = voice_id
            self.engine_id = engine_id

    def _ensure_control_mutable_locked(self) -> None:
        if (
            self.ended_at is not None
            or self._peer_lifecycle.phase == "terminal"
            or self.state in {"ended", "failed"}
        ):
            raise TerminalCallSessionError(
                "cannot mutate controls on a terminal call"
            )

    async def complete_speech_turn(
        self,
        *,
        turn_id: str,
        voice_id: str,
        engine_id: str,
        segment_id: str | None = None,
        segment_ordinal: int | None = None,
        accepted_configuration: AcceptedSpeechConfiguration | None = None,
    ) -> dict[str, Any]:
        """Terminalize a fully played incremental turn without synthesizing again."""
        if accepted_configuration is not None:
            await self._validate_accepted_speech_configuration(
                accepted_configuration
            )
        segment, cached_response = await self._claim_tts_segment(
            turn_id=turn_id,
            text="",
            final_chunk=True,
            segment_id=segment_id,
            requested_ordinal=segment_ordinal,
        )
        if cached_response is not None:
            return cached_response

        matches_pending = (
            turn_id == self._pending_speech_terminal_turn_id
            and voice_id == self._pending_speech_terminal_voice_id
            and engine_id == self._pending_speech_terminal_engine_id
            and self._pending_speech_playback_final is not None
        )
        if not matches_pending:
            event = failed_event(
                session_id=self.session_id,
                turn_id=turn_id,
                code="call_tts_failed",
                message="Speech playback failed. Please try again.",
                retry_allowed=True,
            )
            event["engine_id"] = engine_id
            await self.emit_event(event)
            await self._release_tts_segment_attempt(turn_id, segment)
            return event

        playback_final = dict(self._pending_speech_playback_final or {})
        mark_track_input_complete = getattr(
            self.outbound_audio_track,
            "mark_playout_input_complete",
            None,
        )
        if callable(mark_track_input_complete):
            mark_track_input_complete()
        turn_playback_seconds = self._tts_turn_playback_seconds.get(turn_id, 0.0)
        playout_wait_completed = await self._wait_for_outbound_audio_playback(
            turn_playback_seconds
        )
        playback_final["playout_wait_completed"] = playout_wait_completed
        playback_final["turn_total_playback_ms"] = round(
            turn_playback_seconds * 1000,
            1,
        )
        self._clear_pending_speech_terminal()
        self.state = "listening"
        result = await self.emit_event(
            simple_event(
                AI_DONE_EVENT,
                session_id=self.session_id,
                turn_id=turn_id,
                voice_id=voice_id,
                engine_id=engine_id,
                tts_playback_final=playback_final,
            )
        )
        await self._commit_tts_segment(turn_id, segment, result)
        return result

    async def speak_text(
        self,
        turn_id: str,
        text: str,
        voice_id: str,
        engine_id: str,
        final_chunk: bool = False,
        *,
        segment_id: str | None = None,
        segment_ordinal: int | None = None,
        accepted_configuration: AcceptedSpeechConfiguration | None = None,
        tts_adapter: Any | None = None,
        reference_audio_b64: str | None = None,
        reference_transcript: str | None = None,
        reference_audio_content_type: str | None = None,
        voxcpm2_cloning_mode: str = "auto",
        voxcpm2_style_prompt: str | None = None,
        voxcpm2_cfg_value: float = 2.0,
        voxcpm2_inference_timesteps: int = 10,
        voxcpm2_normalize: bool = True,
        voxcpm2_denoise: bool = True,
        qwen3_release_evidence_mode: str | None = None,
        qwen3_release_evidence_seed: int | None = None,
    ) -> dict[str, Any]:
        adapter = tts_adapter or self.tts_adapter
        current_task = asyncio.current_task()
        segment, cached_response, admission = await self._admit_tts_segment(
            turn_id=turn_id,
            text=text,
            final_chunk=final_chunk,
            segment_id=segment_id,
            requested_ordinal=segment_ordinal,
            accepted_configuration=accepted_configuration,
            adapter=adapter,
            active_task=current_task,
        )
        if cached_response is not None:
            return cached_response
        if admission is None:
            raise RuntimeError("speech segment was admitted without an owner")
        try:
            await self._promote_speech_admission(
                admission,
                accepted_configuration=accepted_configuration,
            )
        except BaseException:
            await self._release_tts_segment_attempt(turn_id, segment)
            await self._release_speech_admission(admission)
            raise
        reserved_segment_ordinal = segment.ordinal

        audio_started_event: dict[str, Any] | None = None
        final_playback: dict[str, Any] | None = None
        generation_started = time.perf_counter()
        voxcpm2_options = {
            "voxcpm2_cloning_mode": voxcpm2_cloning_mode,
            "voxcpm2_style_prompt": voxcpm2_style_prompt,
            "voxcpm2_cfg_value": voxcpm2_cfg_value,
            "voxcpm2_inference_timesteps": voxcpm2_inference_timesteps,
            "voxcpm2_normalize": voxcpm2_normalize,
            "voxcpm2_denoise": voxcpm2_denoise,
        }
        try:
            if _adapter_supports_streaming(adapter, engine_id):
                result = await self._speak_streaming_speech(
                    turn_id=turn_id,
                    text=text,
                    voice_id=voice_id,
                    engine_id=engine_id,
                    final_chunk=final_chunk,
                    adapter=adapter,
                    reference_audio_b64=reference_audio_b64,
                    reference_transcript=reference_transcript,
                    reference_audio_content_type=reference_audio_content_type,
                    voxcpm2_options=voxcpm2_options,
                    qwen3_release_evidence_mode=qwen3_release_evidence_mode,
                    qwen3_release_evidence_seed=qwen3_release_evidence_seed,
                    segment_ordinal=reserved_segment_ordinal,
                    worker_request_id=segment.worker_request_id,
                )
                if self._tts_segment_result_succeeded(result):
                    await self._commit_tts_segment(turn_id, segment, result)
                elif result.get("status") == "cancelled":
                    await self._cancel_tts_turn(turn_id)
                else:
                    await self._release_tts_segment_attempt(turn_id, segment)
                return result

            result = await self._synthesize_speech(
                turn_id=turn_id,
                text=text,
                voice_id=voice_id,
                engine_id=engine_id,
                tts_adapter=adapter,
                reference_audio_b64=reference_audio_b64,
                reference_transcript=reference_transcript,
                reference_audio_content_type=reference_audio_content_type,
                voxcpm2_options=voxcpm2_options,
            )
            total_generation_ms = round((time.perf_counter() - generation_started) * 1000, 1)
            if turn_id in self._cancelled_ai_turns:
                await self._cancel_tts_turn(turn_id)
                return {"status": "cancelled", "turn_id": turn_id}
            wav_bytes = bytes(result.get("wav_bytes") or b"")
            playback_seconds = 0.0
            if wav_bytes:
                audio_stats = audio_stats_for_wav_bytes(
                    wav_bytes,
                    target_sample_rate=int(getattr(self.outbound_audio_track, "sample_rate", 48000)),
                )
                playback_seconds = await self._queue_outbound_audio(
                    wav_bytes,
                    preroll_seconds=CALL_TTS_AUDIO_PREROLL_SECONDS,
                )
                first_chunk_enqueued_ms = round((time.perf_counter() - generation_started) * 1000, 1)
                self._reset_barge_in_onset()
                self.state = "speaking"
                ai_audio_started_ms = round((time.perf_counter() - generation_started) * 1000, 1)
                audio_started_event = simple_event(
                    AI_AUDIO_STARTED_EVENT,
                    session_id=self.session_id,
                    turn_id=turn_id,
                    voice_id=voice_id,
                    engine_id=engine_id,
                    audio=audio_stats,
                    tts_playback={
                        "streaming_used": False,
                        "fallback_used": False,
                        "whole_wav_fallback_used": False,
                        "first_chunk_generated_ms": None,
                        "first_chunk_enqueued_ms": first_chunk_enqueued_ms,
                        "ai_audio_started_ms": ai_audio_started_ms,
                        "chunk_count_at_start": 1,
                        "inter_chunk_gaps_ms": [],
                    },
                )
                await self.emit_event(audio_started_event)
                turn_playback_seconds = self._record_tts_turn_playback(
                    turn_id,
                    playback_seconds,
                )
                playout_wait_completed: bool | None = None
                if final_chunk:
                    playout_wait_completed = await self._wait_for_outbound_audio_playback(
                        turn_playback_seconds
                    )
                final_playback = {
                    "streaming_used": False,
                    "fallback_used": False,
                    "whole_wav_fallback_used": False,
                    "chunk_count": 1,
                    "total_generation_ms": total_generation_ms,
                    "total_playback_ms": round(playback_seconds * 1000, 1),
                    "inter_chunk_gaps_ms": [],
                    "playout_wait_completed": playout_wait_completed,
                    "turn_total_playback_ms": round(
                        turn_playback_seconds * 1000,
                        1,
                    ),
                }
            else:
                await self._queue_outbound_audio(wav_bytes)
                final_playback = {
                    "streaming_used": False,
                    "fallback_used": False,
                    "whole_wav_fallback_used": False,
                    "chunk_count": 0,
                    "total_generation_ms": total_generation_ms,
                    "total_playback_ms": 0.0,
                    "inter_chunk_gaps_ms": [],
                    "playout_wait_completed": False,
                }
        except asyncio.CancelledError:
            self._cancelled_ai_turns.add(turn_id)
            await self._cancel_tts_turn(turn_id)
            raise
        except Exception:
            self.state = "listening"
            event = failed_event(
                session_id=self.session_id,
                turn_id=turn_id,
                code="call_tts_failed",
                message="Speech playback failed. Please try again.",
                retry_allowed=True,
            )
            event["engine_id"] = engine_id
            if final_playback is not None:
                event["tts_playback_final"] = final_playback
            await self.emit_event(event)
            await self._release_tts_segment_attempt(turn_id, segment)
            if audio_started_event is not None:
                return {**event, "ai_audio_started_event": audio_started_event}
            return event
        finally:
            await self._release_speech_admission(admission)

        if turn_id in self._cancelled_ai_turns:
            self.state = "listening"
            await self._cancel_tts_turn(turn_id)
            if audio_started_event is not None:
                return {"status": "cancelled", "turn_id": turn_id, "ai_audio_started_event": audio_started_event}
            return {"status": "cancelled", "turn_id": turn_id}

        if final_chunk:
            self.state = "listening"
            done_event = await self.emit_event(
                simple_event(
                    AI_DONE_EVENT,
                    session_id=self.session_id,
                    turn_id=turn_id,
                    voice_id=voice_id,
                    engine_id=engine_id,
                    tts_playback_final=final_playback,
                )
            )
            if audio_started_event is not None:
                result = {**done_event, "ai_audio_started_event": audio_started_event}
            else:
                result = done_event
            await self._commit_tts_segment(turn_id, segment, result)
            return result

        queued_event = {
            "status": "queued",
            "session_id": self.session_id,
            "turn_id": turn_id,
            "engine_id": engine_id,
        }
        if audio_started_event is not None:
            queued_event["ai_audio_started_event"] = audio_started_event
        if final_playback is not None:
            queued_event["tts_playback_final"] = final_playback
        await self._commit_tts_segment(turn_id, segment, queued_event)
        return queued_event

    async def _claim_tts_segment(
        self,
        *,
        turn_id: str,
        text: str,
        final_chunk: bool,
        segment_id: str | None,
        requested_ordinal: int | None,
    ) -> tuple[_TtsSegmentLedgerEntry, dict[str, Any] | None]:
        content_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        while True:
            waiter: asyncio.Event | None = None
            async with self._lifecycle_lock:
                segment, cached_response, waiter = self._claim_tts_segment_locked(
                    turn_id=turn_id,
                    content_digest=content_digest,
                    final_chunk=final_chunk,
                    segment_id=segment_id,
                    requested_ordinal=requested_ordinal,
                )
                if waiter is None:
                    return segment, cached_response
            if waiter is not None:
                await waiter.wait()

    def _claim_tts_segment_locked(
        self,
        *,
        turn_id: str,
        content_digest: str,
        final_chunk: bool,
        segment_id: str | None,
        requested_ordinal: int | None,
    ) -> tuple[
        _TtsSegmentLedgerEntry,
        dict[str, Any] | None,
        asyncio.Event | None,
    ]:
        ledger = self._tts_turn_ledgers.setdefault(turn_id, _TtsTurnLedger())
        identity = segment_id
        if identity is None:
            ordinal_for_identity = (
                requested_ordinal
                if requested_ordinal is not None
                else ledger.next_ordinal
            )
            identity = (
                f"ordinal:{ordinal_for_identity}"
                if requested_ordinal is not None
                else f"legacy:{ordinal_for_identity}:{content_digest}:{int(final_chunk)}"
            )
        existing = ledger.segments.get(identity)
        if existing is not None:
            if (
                (requested_ordinal is not None and requested_ordinal != existing.ordinal)
                or existing.content_digest != content_digest
                or existing.final_chunk != final_chunk
            ):
                raise SpeechSegmentConflictError(
                    "segment identity was reused with different content"
                )
            if existing.state == "committed":
                if existing.response is None:
                    raise RuntimeError("committed segment has no cached response")
                return existing, dict(existing.response), None
            if ledger.state in {"cancelled", "completed"}:
                raise SpeechTurnTerminalError(f"speech turn is {ledger.state}")
            if existing.state == "in_flight":
                return existing, None, existing.attempt_done
            if existing.state == "reserved":
                existing.state = "in_flight"
                existing.attempt_done = asyncio.Event()
                existing.attempt_generation += 1
                existing.worker_request_id = self._worker_request_id_for_segment(
                    turn_id=turn_id,
                    segment_id=identity,
                    ordinal=existing.ordinal,
                    content_digest=content_digest,
                    attempt_generation=existing.attempt_generation,
                )
                return existing, None, None
            raise SpeechTurnTerminalError("speech segment is cancelled")

        if ledger.state in {"cancelled", "completed"}:
            raise SpeechTurnTerminalError(f"speech turn is {ledger.state}")
        ordinal = (
            requested_ordinal
            if requested_ordinal is not None
            else ledger.next_ordinal
        )
        if ordinal != ledger.next_ordinal:
            raise SpeechSegmentConflictError(
                "segment ordinal is not the next expected ordinal"
            )
        ordinal_owner = ledger.ordinal_owners.get(ordinal)
        if ordinal_owner is not None and ordinal_owner != identity:
            raise SpeechSegmentConflictError(
                "segment ordinal is already owned by another identity"
            )
        entry = _TtsSegmentLedgerEntry(
            segment_id=identity,
            ordinal=ordinal,
            content_digest=content_digest,
            final_chunk=final_chunk,
            worker_request_id=self._worker_request_id_for_segment(
                turn_id=turn_id,
                segment_id=identity,
                ordinal=ordinal,
                content_digest=content_digest,
                attempt_generation=1,
            ),
            state="in_flight",
        )
        ledger.segments[identity] = entry
        ledger.ordinal_owners[ordinal] = identity
        return entry, None, None

    async def _admit_tts_segment(
        self,
        *,
        turn_id: str,
        text: str,
        final_chunk: bool,
        segment_id: str | None,
        requested_ordinal: int | None,
        accepted_configuration: AcceptedSpeechConfiguration | None,
        adapter: Any,
        active_task: asyncio.Task[Any] | None,
    ) -> tuple[
        _TtsSegmentLedgerEntry,
        dict[str, Any] | None,
        _SpeechAdmission | None,
    ]:
        content_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        while True:
            waiter: asyncio.Event | None = None
            async with self._lifecycle_lock:
                if accepted_configuration is not None:
                    self._validate_accepted_speech_configuration_locked(
                        accepted_configuration
                    )
                elif (
                    self.ended_at is not None
                    or self._peer_lifecycle.phase != "stable"
                    or self.state in {"ended", "failed"}
                ):
                    raise SpeechSessionSelectionError(
                        "accepted call configuration changed before speech"
                    )

                current_admission = self._speech_admission
                if current_admission is not None:
                    waiter = current_admission.done
                else:
                    segment, cached_response, waiter = self._claim_tts_segment_locked(
                        turn_id=turn_id,
                        content_digest=content_digest,
                        final_chunk=final_chunk,
                        segment_id=segment_id,
                        requested_ordinal=requested_ordinal,
                    )
                    if waiter is None:
                        if cached_response is not None:
                            return segment, cached_response, None
                        self._speech_admission_generation += 1
                        admission = _SpeechAdmission(
                            token=self._speech_admission_generation,
                            lifecycle_epoch=self._peer_lifecycle.epoch,
                            turn_id=turn_id,
                            request_id=segment.worker_request_id,
                            adapter=adapter,
                            active_task=active_task,
                        )
                        self._speech_admission = admission
                        self.active_turn_task = active_task
                        self._active_tts_adapter = adapter
                        self._active_tts_request_id = segment.worker_request_id
                        self._active_tts_turn_id = turn_id
                        self._active_tts_cancel_requested = False
                        self._last_tts_cancel_context = None
                        self.state = "rehearsing"
                        return segment, None, admission
            if waiter is not None:
                await waiter.wait()

    async def _promote_speech_admission(
        self,
        admission: _SpeechAdmission,
        *,
        accepted_configuration: AcceptedSpeechConfiguration | None,
    ) -> None:
        async with self._lifecycle_lock:
            if accepted_configuration is not None:
                self._validate_accepted_speech_configuration_locked(
                    accepted_configuration
                )
            if (
                self._speech_admission is not admission
                or admission.lifecycle_epoch != self._peer_lifecycle.epoch
                or self._peer_lifecycle.phase != "stable"
                or admission.turn_id in self._cancelled_ai_turns
                or admission.turn_id in self._cancelling_ai_turns
            ):
                raise SpeechSessionSelectionError(
                    "accepted call configuration changed before speech generation"
                )

    async def _release_speech_admission(
        self,
        admission: _SpeechAdmission,
    ) -> None:
        async with self._lifecycle_lock:
            if self._speech_admission is not admission:
                return
            self._speech_admission = None
            if self.active_turn_task is admission.active_task:
                self.active_turn_task = None
            if (
                self._active_tts_turn_id == admission.turn_id
                and self._active_tts_request_id == admission.request_id
                and self._active_tts_adapter is admission.adapter
            ):
                self._active_tts_adapter = None
                self._active_tts_request_id = None
                self._active_tts_turn_id = None
                self._active_tts_cancel_requested = False
                self._active_tts_metrics_snapshot = None
            admission.done.set()

    @staticmethod
    def _tts_segment_result_succeeded(result: dict[str, Any]) -> bool:
        return (
            result.get("status") == "queued"
            or result.get("type") == AI_DONE_EVENT
        )

    @staticmethod
    def _worker_request_id_for_segment(
        *,
        turn_id: str,
        segment_id: str,
        ordinal: int,
        content_digest: str,
        attempt_generation: int,
    ) -> str:
        identity_digest = hashlib.sha256(
            (
                f"{turn_id}\0{segment_id}\0{ordinal}\0{content_digest}"
                f"\0attempt:{attempt_generation}"
            ).encode("utf-8")
        ).hexdigest()
        return f"tts-segment-{identity_digest[:32]}"

    async def _commit_tts_segment(
        self,
        turn_id: str,
        segment: _TtsSegmentLedgerEntry,
        response: dict[str, Any],
    ) -> None:
        async with self._lifecycle_lock:
            ledger = self._tts_turn_ledgers.get(turn_id)
            if ledger is None or ledger.segments.get(segment.segment_id) is not segment:
                raise RuntimeError("speech segment ledger ownership was lost")
            segment.state = "committed"
            segment.response = dict(response)
            ledger.next_ordinal = segment.ordinal + 1
            if segment.final_chunk:
                ledger.state = "completed"
                self._tts_turn_playback_seconds.pop(turn_id, None)
            segment.attempt_done.set()

    async def _release_tts_segment_attempt(
        self,
        turn_id: str,
        segment: _TtsSegmentLedgerEntry,
    ) -> None:
        async with self._lifecycle_lock:
            ledger = self._tts_turn_ledgers.get(turn_id)
            if (
                ledger is not None
                and ledger.state == "active"
                and ledger.segments.get(segment.segment_id) is segment
                and segment.state == "in_flight"
            ):
                segment.state = "reserved"
                segment.attempt_done.set()

    async def _cancel_tts_turn(self, turn_id: str) -> None:
        async with self._lifecycle_lock:
            self._cancel_tts_turn_locked(turn_id)

    def _cancel_tts_turn_locked(self, turn_id: str) -> None:
        ledger = self._tts_turn_ledgers.setdefault(turn_id, _TtsTurnLedger())
        if ledger.state == "completed":
            return
        ledger.state = "cancelled"
        for segment in ledger.segments.values():
            if segment.state != "committed":
                segment.state = "cancelled"
                segment.attempt_done.set()
        self._tts_turn_playback_seconds.pop(turn_id, None)

    def _record_tts_turn_playback(
        self,
        turn_id: str,
        playback_seconds: float,
    ) -> float:
        total = self._tts_turn_playback_seconds.get(turn_id, 0.0) + max(
            playback_seconds,
            0.0,
        )
        self._tts_turn_playback_seconds[turn_id] = total
        return total

    async def _speak_streaming_speech(
        self,
        *,
        turn_id: str,
        text: str,
        voice_id: str,
        engine_id: str,
        final_chunk: bool,
        adapter: TtsStreamingAdapter,
        reference_audio_b64: str | None,
        reference_transcript: str | None,
        reference_audio_content_type: str | None,
        voxcpm2_options: dict[str, Any],
        qwen3_release_evidence_mode: str | None,
        qwen3_release_evidence_seed: int | None,
        segment_ordinal: int,
        worker_request_id: str,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        queue: asyncio.Queue[Any] = asyncio.Queue(
            maxsize=CALL_TTS_STREAM_BRIDGE_CAPACITY
        )
        sentinel = object()
        audio_started_event: dict[str, Any] | None = None
        chunk_count = 0
        playback_seconds = 0.0
        generated_audio_seconds = 0.0
        generated_at_values: list[float] = []
        inter_chunk_gaps_ms: list[float] = []
        pending_chunks: list[dict[str, Any]] = []
        playback_started = False
        first_chunk_received_at: float | None = None
        producer_task: asyncio.Task[Any] | None = None
        bridge_queue_high_water = 0
        producer_block_time_ms = 0.0
        bridge_producer_block_count = 0
        bridge_discarded_item_count = 0
        generation_complete_ms: float | None = None
        playout_complete_ms: float | None = None
        playout_wait_completed: bool | None = None
        stream_completed_normally = False
        source_audio_hasher = (
            hashlib.sha256() if qwen3_release_evidence_mode is not None else None
        )
        startup_min_audio_seconds = (
            CALL_QWEN3_STREAM_START_MIN_AUDIO_SECONDS
            if engine_id == "qwen3_1_7b"
            else CALL_TTS_STREAM_START_MIN_AUDIO_SECONDS
        )
        first_chunk_preroll_seconds = (
            CALL_QWEN3_TTS_AUDIO_PREROLL_SECONDS
            if engine_id == "qwen3_1_7b"
            else CALL_TTS_AUDIO_PREROLL_SECONDS
        )

        reset_track_metrics = getattr(
            self.outbound_audio_track,
            "reset_playout_metrics",
            None,
        )
        if callable(reset_track_metrics):
            reset_track_metrics()

        def elapsed_ms() -> float:
            return round((time.perf_counter() - started_at) * 1000, 1)

        def track_metrics() -> dict[str, Any]:
            snapshot = getattr(self.outbound_audio_track, "playout_metrics", None)
            if not callable(snapshot):
                return {"track_metrics_present": False}
            return {
                "track_metrics_present": True,
                **{
                    f"track_{key}": value
                    for key, value in dict(snapshot()).items()
                },
            }

        def final_metrics() -> dict[str, Any]:
            generation_ms = (
                elapsed_ms()
                if generation_complete_ms is None
                else generation_complete_ms
            )
            generated_audio_ms = round(generated_audio_seconds * 1000, 1)
            total_playback_ms = round(playback_seconds * 1000, 1)
            native_generation_ms = (
                round(generated_at_values[-1], 1)
                if generated_at_values
                else round(generation_ms, 1)
            )
            ratio_generation_ms = (
                native_generation_ms
                if engine_id == "qwen3_1_7b"
                else generation_ms
            )
            realtime_generation_ratio = 0.0
            if ratio_generation_ms > 0:
                realtime_generation_ratio = round(
                    generated_audio_ms / ratio_generation_ms,
                    3,
                )
            metrics = {
                "streaming_used": True,
                "fallback_used": False,
                "whole_wav_fallback_used": False,
                "chunk_count": chunk_count,
                "total_generation_ms": round(generation_ms, 1),
                "total_playback_ms": total_playback_ms,
                "generated_audio_ms": generated_audio_ms,
                "native_generation_ms": native_generation_ms,
                "realtime_generation_ratio": realtime_generation_ratio,
                "under_realtime_generation": realtime_generation_ratio < 1.05,
                "inter_chunk_gaps_ms": list(inter_chunk_gaps_ms),
                "bridge_queue_capacity": CALL_TTS_STREAM_BRIDGE_CAPACITY,
                "bridge_queue_high_water": bridge_queue_high_water,
                "producer_block_time_ms": round(producer_block_time_ms, 1),
                "bridge_producer_block_count": bridge_producer_block_count,
                "generation_complete_ms": round(generation_ms, 1),
                "playout_complete_ms": (
                    round(playout_complete_ms, 1)
                    if playout_complete_ms is not None
                    else None
                ),
                "playout_wait_completed": playout_wait_completed,
                "natural_eos": stream_completed_normally,
                "bridge_discarded_item_count": bridge_discarded_item_count,
                **track_metrics(),
            }
            if source_audio_hasher is not None and chunk_count > 0:
                metrics["source_audio_sha256"] = source_audio_hasher.hexdigest()
            return metrics

        def pending_audio_seconds() -> float:
            return sum(float(chunk["playback_seconds"]) for chunk in pending_chunks)

        def startup_buffer_ready() -> bool:
            if not pending_chunks:
                return False
            buffered_enough = (
                len(pending_chunks) >= CALL_TTS_STREAM_START_MIN_CHUNKS
                and pending_audio_seconds() >= startup_min_audio_seconds
            )
            if buffered_enough:
                return True
            if first_chunk_received_at is None:
                return False
            waited = time.perf_counter() - first_chunk_received_at
            return waited >= CALL_TTS_STREAM_MAX_STARTUP_BUFFER_SECONDS

        async def enqueue_stream_chunk(chunk: dict[str, Any], *, first: bool) -> None:
            nonlocal playback_seconds
            playback_seconds += await self._queue_outbound_audio(
                bytes(chunk["wav_bytes"]),
                preroll_seconds=first_chunk_preroll_seconds if first else 0.0,
            )

        async def start_playback_from_buffer() -> None:
            nonlocal audio_started_event, playback_started
            if playback_started or not pending_chunks:
                return

            startup_chunks = list(pending_chunks)
            first_chunk = startup_chunks[0]
            startup_audio_seconds = sum(
                float(chunk["playback_seconds"])
                for chunk in startup_chunks
            )
            for index, chunk in enumerate(startup_chunks):
                await enqueue_stream_chunk(chunk, first=index == 0)
                if (
                    turn_id in self._cancelled_ai_turns
                    or turn_id in self._cancelling_ai_turns
                ):
                    pending_chunks.clear()
                    return

            first_chunk_enqueued_ms = elapsed_ms()
            self._reset_barge_in_onset()
            self.state = "speaking"
            ai_audio_started_ms = elapsed_ms()
            buffered_audio_ms = round(
                startup_audio_seconds * 1000,
                1,
            )
            startup_wait_ms = 0.0
            if first_chunk_received_at is not None:
                startup_wait_ms = round((time.perf_counter() - first_chunk_received_at) * 1000, 1)
            audio_started_event = simple_event(
                AI_AUDIO_STARTED_EVENT,
                session_id=self.session_id,
                turn_id=turn_id,
                voice_id=voice_id,
                engine_id=engine_id,
                audio=dict(first_chunk["audio_stats"]),
                tts_playback={
                    "streaming_used": True,
                    "fallback_used": False,
                    "whole_wav_fallback_used": False,
                    "first_chunk_generated_ms": first_chunk["generated_at_ms"],
                    "first_chunk_enqueued_ms": first_chunk_enqueued_ms,
                    "ai_audio_started_ms": ai_audio_started_ms,
                    "chunk_count_at_start": len(startup_chunks),
                    "startup_buffered_chunks": len(startup_chunks),
                    "startup_buffered_audio_ms": buffered_audio_ms,
                    "startup_buffer_wait_ms": startup_wait_ms,
                    "startup_buffer_target_ms": round(
                        startup_min_audio_seconds * 1000,
                        1,
                    ),
                    "startup_buffer_max_wait_ms": round(
                        CALL_TTS_STREAM_MAX_STARTUP_BUFFER_SECONDS * 1000,
                        1,
                    ),
                },
            )
            playback_started = True
            pending_chunks.clear()
            await self.emit_event(audio_started_event)

        async def next_stream_item() -> Any:
            if not playback_started and pending_chunks and first_chunk_received_at is not None:
                if startup_buffer_ready():
                    await start_playback_from_buffer()
                    return await queue.get()
                deadline = first_chunk_received_at + CALL_TTS_STREAM_MAX_STARTUP_BUFFER_SECONDS
                remaining = max(deadline - time.perf_counter(), 0.0)
                if remaining <= 0:
                    await start_playback_from_buffer()
                    return await queue.get()
                try:
                    return await asyncio.wait_for(queue.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    await start_playback_from_buffer()
                    return await queue.get()
            return await queue.get()

        try:
            request = self._build_tts_synthesis_input(
                turn_id=turn_id,
                voice_id=voice_id,
                text=text,
                reference_audio_b64=reference_audio_b64,
                reference_transcript=reference_transcript,
                reference_audio_content_type=reference_audio_content_type,
                voxcpm2_options=_voxcpm2_live_stream_options(engine_id, voxcpm2_options),
                qwen3_release_evidence_mode=qwen3_release_evidence_mode,
                qwen3_release_evidence_seed=qwen3_release_evidence_seed,
                segment_ordinal=segment_ordinal,
                request_id=worker_request_id,
            )
            loop = asyncio.get_running_loop()

            self._active_tts_adapter = adapter
            self._active_tts_request_id = worker_request_id
            self._active_tts_turn_id = turn_id
            self._active_tts_cancel_requested = False
            self._last_tts_cancel_context = None

            def cancellation_metrics_snapshot() -> dict[str, Any]:
                nonlocal bridge_discarded_item_count
                bridge_discarded_item_count = max(
                    bridge_discarded_item_count,
                    queue.qsize(),
                )
                return final_metrics()

            self._active_tts_metrics_snapshot = cancellation_metrics_snapshot

            async def put_bridge_item(item: Any) -> None:
                nonlocal bridge_queue_high_water
                await queue.put(item)
                bridge_queue_high_water = max(
                    bridge_queue_high_water,
                    queue.qsize(),
                )

            def put_threadsafe(item: Any) -> bool:
                nonlocal producer_block_time_ms, bridge_producer_block_count
                try:
                    publish = asyncio.run_coroutine_threadsafe(
                        put_bridge_item(item),
                        loop,
                    )
                except RuntimeError:
                    return False

                wait_started = time.perf_counter()
                blocked = False
                while True:
                    try:
                        publish.result(timeout=0.05)
                        producer_block_time_ms += (
                            time.perf_counter() - wait_started
                        ) * 1000
                        return True
                    except concurrent.futures.TimeoutError:
                        if not blocked:
                            blocked = True
                            bridge_producer_block_count += 1
                        if turn_id in self._cancelled_ai_turns:
                            publish.cancel()
                            producer_block_time_ms += (
                                time.perf_counter() - wait_started
                            ) * 1000
                            return False
                    except (concurrent.futures.CancelledError, RuntimeError):
                        return False

            def produce() -> None:
                terminal_item: Any = sentinel
                stream: Any | None = None
                try:
                    if engine_id == "qwen3_1_7b":
                        stream = adapter.stream(
                            request,
                            request_id=worker_request_id,
                            voice_key=voice_id,
                        )
                    else:
                        stream = adapter.stream(request)
                    for chunk in stream:
                        if turn_id in self._cancelled_ai_turns:
                            break
                        if not put_threadsafe(chunk):
                            break
                except Exception as exc:
                    terminal_item = exc
                finally:
                    close = getattr(stream, "close", None)
                    if callable(close):
                        try:
                            close()
                        except Exception as exc:
                            terminal_item = exc
                    # Always wake the async bridge. The consumer owns the
                    # cancelled/cancelling decision; suppressing this sentinel
                    # can strand an acknowledged engine-switch request forever.
                    put_threadsafe(terminal_item)

            producer_task = asyncio.create_task(asyncio.to_thread(produce))

            while True:
                item = await next_stream_item()
                if item is sentinel:
                    if (
                        turn_id in self._cancelled_ai_turns
                        or turn_id in self._cancelling_ai_turns
                    ):
                        break
                    stream_completed_normally = True
                    break
                if isinstance(item, Exception):
                    raise item
                if (
                    turn_id in self._cancelled_ai_turns
                    or turn_id in self._cancelling_ai_turns
                ):
                    break

                if isinstance(item, TtsAudioChunk):
                    wav_bytes = bytes(item.wav_bytes or b"")
                    generated_at_ms = float(item.generated_at_ms or 0.0)
                else:
                    wav_bytes = bytes(getattr(item, "wav_bytes", b"") or b"")
                    generated_at_ms = float(getattr(item, "generated_at_ms", elapsed_ms()) or 0.0)
                if not wav_bytes:
                    continue
                if source_audio_hasher is not None:
                    source_audio_hasher.update(len(wav_bytes).to_bytes(8, "big"))
                    source_audio_hasher.update(wav_bytes)
                if first_chunk_received_at is None:
                    first_chunk_received_at = time.perf_counter()
                if generated_at_values:
                    inter_chunk_gaps_ms.append(
                        round(max(generated_at_ms - generated_at_values[-1], 0.0), 1)
                    )
                generated_at_values.append(generated_at_ms)

                audio_stats = audio_stats_for_wav_bytes(
                    wav_bytes,
                    target_sample_rate=int(getattr(self.outbound_audio_track, "sample_rate", 48000)),
                )
                chunk_playback_seconds = float(audio_stats.get("duration_ms", 0.0)) / 1000.0
                current_chunk = {
                    "wav_bytes": wav_bytes,
                    "generated_at_ms": generated_at_ms,
                    "audio_stats": audio_stats,
                    "playback_seconds": chunk_playback_seconds,
                }
                generated_audio_seconds += chunk_playback_seconds
                chunk_count += 1

                if not playback_started:
                    pending_chunks.append(current_chunk)
                    # RayMe is a live phone call. Never wait for full TTS stream
                    # completion before first playback as a smoothness fix.
                    if startup_buffer_ready():
                        await start_playback_from_buffer()
                    continue

                await enqueue_stream_chunk(current_chunk, first=False)

            if producer_task is not None:
                await producer_task
            if chunk_count == 0:
                raise ValueError("Streaming synthesis failed")

            if not playback_started:
                await start_playback_from_buffer()

            generation_complete_ms = elapsed_ms()
            if generated_at_values:
                generation_complete_ms = max(generation_complete_ms, generated_at_values[-1])

            if stream_completed_normally and final_chunk:
                mark_track_input_complete = getattr(
                    self.outbound_audio_track,
                    "mark_playout_input_complete",
                    None,
                )
                if callable(mark_track_input_complete):
                    mark_track_input_complete()

            if (
                turn_id in self._cancelled_ai_turns
                or turn_id in self._cancelling_ai_turns
            ):
                self.state = "listening"
                cancelled_event = {"status": "cancelled", "turn_id": turn_id}
                if audio_started_event is not None:
                    cancelled_event["ai_audio_started_event"] = audio_started_event
                return cancelled_event

            turn_playback_seconds = self._record_tts_turn_playback(
                turn_id,
                playback_seconds,
            )
            if final_chunk:
                playout_wait_completed = await self._wait_for_outbound_audio_playback(
                    turn_playback_seconds
                )
                playout_complete_ms = elapsed_ms()
            playback_final = final_metrics()
            playback_final["turn_total_playback_ms"] = round(
                turn_playback_seconds * 1000,
                1,
            )

            if (
                turn_id in self._cancelled_ai_turns
                or turn_id in self._cancelling_ai_turns
            ):
                self.state = "listening"
                cancelled_event = {"status": "cancelled", "turn_id": turn_id}
                if audio_started_event is not None:
                    cancelled_event["ai_audio_started_event"] = audio_started_event
                cancelled_event["tts_playback_final"] = playback_final
                return cancelled_event

            if final_chunk:
                self._clear_pending_speech_terminal()
                self.state = "listening"
                done_event = await self.emit_event(
                    simple_event(
                        AI_DONE_EVENT,
                        session_id=self.session_id,
                        turn_id=turn_id,
                        voice_id=voice_id,
                        engine_id=engine_id,
                        tts_playback_final=playback_final,
                    )
                )
                if audio_started_event is not None:
                    return {**done_event, "ai_audio_started_event": audio_started_event}
                return done_event

            queued_event: dict[str, Any] = {
                "status": "queued",
                "session_id": self.session_id,
                "turn_id": turn_id,
                "engine_id": engine_id,
                "tts_playback_final": playback_final,
            }
            if audio_started_event is not None:
                queued_event["ai_audio_started_event"] = audio_started_event
            self._pending_speech_terminal_turn_id = turn_id
            self._pending_speech_terminal_voice_id = voice_id
            self._pending_speech_terminal_engine_id = engine_id
            self._pending_speech_playback_final = dict(playback_final)
            return queued_event
        except asyncio.CancelledError:
            self._cancelled_ai_turns.add(turn_id)
            await self._cancel_active_tts_generation(turn_id)
            raise
        except Exception:
            if (
                turn_id in self._cancelled_ai_turns
                or turn_id in self._cancelling_ai_turns
            ):
                if self.state not in {"ended", "failed"}:
                    self.state = "listening"
                cancelled_event: dict[str, Any] = {
                    "status": "cancelled",
                    "turn_id": turn_id,
                    "tts_playback_final": final_metrics(),
                }
                if audio_started_event is not None:
                    cancelled_event["ai_audio_started_event"] = audio_started_event
                return cancelled_event
            self.state = "listening"
            event = failed_event(
                session_id=self.session_id,
                turn_id=turn_id,
                code="call_tts_failed",
                message="Speech playback failed. Please try again.",
                retry_allowed=True,
            )
            event["engine_id"] = engine_id
            event["tts_playback_final"] = final_metrics()
            await self.emit_event(event)
            if audio_started_event is not None:
                return {**event, "ai_audio_started_event": audio_started_event}
            return event

        finally:
            if self._speech_admission is None and self._active_tts_turn_id == turn_id:
                self._active_tts_adapter = None
                self._active_tts_request_id = None
                self._active_tts_turn_id = None
                self._active_tts_cancel_requested = False
                self._active_tts_metrics_snapshot = None

    async def _cancel_active_tts_generation(
        self,
        turn_id: str | None,
        *,
        request_id: str | None = None,
        adapter: Any | None = None,
        cancel_started: asyncio.Event | None = None,
    ) -> bool | None:
        request_id = request_id or self._active_tts_request_id
        active_turn_id = turn_id or self._active_tts_turn_id
        adapter = adapter or self._active_tts_adapter
        is_current_generation = (
            request_id is not None
            and request_id == self._active_tts_request_id
            and adapter is self._active_tts_adapter
        )
        if (
            request_id is None
            or adapter is None
            or (is_current_generation and self._active_tts_cancel_requested)
        ):
            if cancel_started is not None:
                cancel_started.set()
            return None

        cancel = getattr(adapter, "cancel", None)
        if not callable(cancel):
            if cancel_started is not None:
                cancel_started.set()
            return None

        if is_current_generation:
            self._active_tts_cancel_requested = True
        loop = asyncio.get_running_loop()

        def cancel_exact_request() -> Any:
            if cancel_started is not None:
                loop.call_soon_threadsafe(cancel_started.set)
            return cancel(request_id)

        try:
            return bool(
                await asyncio.wait_for(
                    asyncio.to_thread(cancel_exact_request),
                    timeout=CALL_TTS_CANCEL_DRAIN_TIMEOUT_SECONDS,
                )
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[rayme-call] tts.cancel_timeout session=%s turn=%s engine=%s",
                self.session_id,
                active_turn_id or "",
                getattr(adapter, "engine_id", "unknown"),
            )
            return False
        except Exception as exc:
            logger.warning(
                "[rayme-call] tts.cancel_failed session=%s turn=%s engine=%s exc=%s",
                self.session_id,
                active_turn_id or "",
                getattr(adapter, "engine_id", "unknown"),
                exc.__class__.__name__,
            )
            return False

    async def _stop_and_drain_outbound_playout(
        self,
        *,
        tracks: tuple[Any | None, ...] | None = None,
    ) -> None:
        targets = tracks or (self.outbound_audio_track,)
        stopped_track_ids: set[int] = set()
        for track in targets:
            if track is None or id(track) in stopped_track_ids:
                continue
            stopped_track_ids.add(id(track))
            stop = getattr(track, "stop_current", None)
            if callable(stop):
                result = stop()
                if inspect.isawaitable(result):
                    await result
        self.outbound_audio_buffer.drain()

    async def cancel_ai_turn(
        self,
        turn_id: str | None = None,
        *,
        cause: str = "interrupt",
        playout_tracks: tuple[Any | None, ...] | None = None,
        playout_already_stopped: bool = False,
        captured: _CapturedTurnCancellation | None = None,
    ) -> dict[str, Any]:
        cancel_started_at = time.perf_counter()
        if captured is None:
            captured = self._capture_turn_cancellation_locked()
        active = captured.active_task
        resolved_turn_id = (
            turn_id
            or captured.turn_id
        )
        request_id = captured.request_id
        metrics_snapshot = captured.metrics_snapshot
        playback_final: dict[str, Any] | None = None
        if resolved_turn_id is not None:
            self._cancelling_ai_turns.add(resolved_turn_id)
            await self._cancel_tts_turn(resolved_turn_id)
        cancel_started = asyncio.Event()
        cancel_task = asyncio.create_task(
            self._cancel_active_tts_generation(
                resolved_turn_id,
                request_id=request_id,
                adapter=captured.adapter,
                cancel_started=cancel_started,
            )
        )
        try:
            # Start exact-request cancellation first, but silence paced playout
            # before waiting for the worker terminal. Adapter ownership and the
            # cancelling guard remain live until that terminal is drained.
            await cancel_started.wait()
            try:
                if not playout_already_stopped:
                    await self._stop_and_drain_outbound_playout(
                        tracks=playout_tracks,
                    )
                if callable(metrics_snapshot):
                    playback_final = metrics_snapshot()
            finally:
                cancel_acknowledged = await cancel_task
        finally:
            if resolved_turn_id is not None:
                self._cancelled_ai_turns.add(resolved_turn_id)
                self._cancelling_ai_turns.discard(resolved_turn_id)
        if playback_final is None and captured.pending_playback_final is not None:
            playback_final = dict(captured.pending_playback_final)
        cancel_context: dict[str, Any] = {"control_cause": cause}
        if resolved_turn_id is not None:
            cancel_context["cancelled_turn_id"] = resolved_turn_id
        if request_id is not None:
            cancel_context["cancelled_request_id"] = request_id
        if cancel_acknowledged is not None:
            cancel_context["cancel_acknowledged"] = cancel_acknowledged
        if playback_final is not None:
            cancel_context["tts_playback_final"] = playback_final
        self._last_tts_cancel_context = dict(cancel_context)
        if self._pending_speech_terminal_turn_id == captured.pending_terminal_turn_id:
            self._clear_pending_speech_terminal()

        graceful_engine_switch = (
            cause == "engine_switch"
            and cancel_acknowledged is True
            and isinstance(active, asyncio.Future)
        )
        if graceful_engine_switch:
            # An acknowledged exact worker cancel will make the captured speech
            # task return its stable {status: cancelled} result. Give that task
            # the remainder of the existing bounded drain window before using
            # task cancellation, so HTTP outcome does not depend on scheduler
            # timing around the worker terminal.
            deadline = cancel_started_at + CALL_TTS_CANCEL_DRAIN_TIMEOUT_SECONDS
            while not active.done() and time.perf_counter() < deadline:
                await asyncio.sleep(0.005)

        if active is not None and active is not asyncio.current_task():
            cancel = getattr(active, "cancel", None)
            if (
                callable(cancel)
                and not graceful_engine_switch
                and not (isinstance(active, asyncio.Future) and active.done())
            ):
                active_loop_getter = getattr(active, "get_loop", None)
                active_loop = active_loop_getter() if callable(active_loop_getter) else None
                current_loop = asyncio.get_running_loop()
                if active_loop is not None and active_loop is not current_loop:
                    if active_loop.is_running():
                        active_loop.call_soon_threadsafe(cancel)
                    else:
                        cancel()
                else:
                    cancel()
                    if isinstance(active, asyncio.Future):
                        remaining = max(
                            CALL_TTS_CANCEL_DRAIN_TIMEOUT_SECONDS
                            - (time.perf_counter() - cancel_started_at),
                            0.0,
                        )
                        try:
                            await asyncio.wait_for(
                                asyncio.shield(active),
                                timeout=remaining,
                            )
                        except (asyncio.CancelledError, asyncio.TimeoutError):
                            pass
        if self.active_turn_task is active:
            self.active_turn_task = None
        return cancel_context

    async def end(self, *, reason: str = "ended") -> dict[str, Any]:
        async with self._lifecycle_lock:
            self._transition_terminal_locked(
                target_state="ended",
                reason=reason,
            )
            if self._terminal_outcome is None and self.end_reason is None:
                self.end_reason = reason
            outcome = self._terminal_outcome
            transaction = outcome.transaction_task if outcome is not None else None
        if outcome is None or transaction is None:
            raise RuntimeError("terminal outcome was not recorded")
        if asyncio.current_task() is self._event_delivery_task:
            return self._terminal_event_before_delivery(outcome)
        return await asyncio.shield(transaction)

    def _clear_pending_speech_terminal(self) -> None:
        self._pending_speech_terminal_turn_id = None
        self._pending_speech_terminal_voice_id = None
        self._pending_speech_terminal_engine_id = None
        self._pending_speech_playback_final = None

    async def fail(self, *, reason: str = "connection_failed") -> dict[str, Any]:
        async with self._lifecycle_lock:
            self._transition_terminal_locked(
                target_state="failed",
                reason=reason,
            )
            outcome = self._terminal_outcome
            transaction = outcome.transaction_task if outcome is not None else None
        if outcome is None or transaction is None:
            raise RuntimeError("terminal outcome was not recorded")
        if asyncio.current_task() is self._event_delivery_task:
            return self._terminal_event_before_delivery(outcome)
        return await asyncio.shield(transaction)

    def _terminal_event_before_delivery(
        self,
        outcome: _TerminalOutcome,
    ) -> dict[str, Any]:
        """Return the committed terminal shape to a reentrant event sink."""

        if outcome.event is not None:
            return dict(outcome.event)
        if outcome.target_state == "failed":
            return simple_event(
                FAILED_EVENT,
                session_id=self.session_id,
                code=outcome.reason,
                message="Call session failed.",
                retry_allowed=True,
            )
        return simple_event(
            ENDED_EVENT,
            session_id=self.session_id,
            reason=outcome.reason,
        )

    def _transition_terminal_locked(
        self,
        *,
        target_state: str,
        reason: str,
        extra_peers: list[Any] | None = None,
        extra_tracks: list[Any] | None = None,
    ) -> _TerminalCleanup | None:
        if self.ended_at is not None or self._peer_lifecycle.phase == "terminal":
            return None
        lifecycle = self._peer_lifecycle
        switch = lifecycle.switch_transaction
        retiring_peer = lifecycle.retiring_peer
        candidate = lifecycle.candidate
        candidate_peer = candidate.peer_connection if candidate is not None else None
        terminal_extra_peers: list[Any] = []
        terminal_extra_tracks: list[Any] = []

        def add_unique_identity(items: list[Any], value: Any | None) -> None:
            if value is not None and not any(item is value for item in items):
                items.append(value)

        for peer in extra_peers or []:
            add_unique_identity(terminal_extra_peers, peer)
        for track in extra_tracks or []:
            add_unique_identity(terminal_extra_tracks, track)
        add_unique_identity(terminal_extra_peers, retiring_peer)
        if switch is not None:
            add_unique_identity(
                terminal_extra_peers,
                switch.previous_peer_connection,
            )
            add_unique_identity(terminal_extra_peers, switch.peer_connection)
            add_unique_identity(
                terminal_extra_tracks,
                switch.previous_outbound_audio_track,
            )
            add_unique_identity(
                terminal_extra_tracks,
                switch.accepted_outbound_audio_track,
            )
        if candidate is not None:
            add_unique_identity(
                terminal_extra_tracks,
                candidate.outbound_audio_track,
            )
        terminal_extra_peers = [
            peer
            for peer in terminal_extra_peers
            if peer is not self.peer_connection and peer is not candidate_peer
        ]

        lifecycle.epoch += 1
        lifecycle.phase = "terminal"
        lifecycle.switch_owner = None
        lifecycle.switch_task = None
        lifecycle.switch_transaction = None
        lifecycle.retiring_peer = None
        lifecycle.retiring_generation = None
        lifecycle.terminal_state = None
        lifecycle.state_before_reconnect = None
        lifecycle.grace_peer = None
        self._cancel_peer_reconnect_grace_locked()
        if candidate is not None:
            self._clear_pending_peer_locked(candidate.peer_connection)
        releaser = self._tts_prompt_lease_releaser
        self._tts_prompt_lease_releaser = None
        owned_prompt_cleanups = [
            cleanup
            for cleanup in self._owned_prompt_lease_cleanups
            if not cleanup.released
        ]
        owned_prompt_handoffs = [
            handoff
            for handoff in self._owned_prompt_lease_handoffs
            if not handoff.installed
            and not (
                handoff.release_cleanup is not None
                and handoff.release_cleanup.released
            )
        ]
        self.ended_at = datetime.now(timezone.utc)
        self.end_reason = reason
        self.state = target_state
        for turn_id in tuple(self._tts_turn_ledgers):
            self._cancel_tts_turn_locked(turn_id)
        cleanup = _TerminalCleanup(
            target_state=target_state,
            reason=reason,
            cancel_cause=(
                "connection_failure"
                if target_state == "failed"
                else ("session_close" if reason == "removed" else reason)
            ),
            active_peer=self.peer_connection,
            candidate_peer=candidate_peer,
            prompt_lease_releaser=releaser,
            owned_peer_ids={
                id(peer)
                for peer in (
                    self.peer_connection,
                    candidate_peer,
                    *terminal_extra_peers,
                )
                if peer is not None
            },
            owned_track_ids={id(track) for track in terminal_extra_tracks},
            owned_prompt_cleanups_pending=owned_prompt_cleanups,
            owned_prompt_handoffs_pending=owned_prompt_handoffs,
            cancel_pending=(
                self._speech_admission is not None
                or self.active_turn_task is not None
                or self._active_tts_turn_id is not None
                or self._pending_speech_terminal_turn_id is not None
            ),
            extra_peers_pending=terminal_extra_peers,
            extra_tracks_pending=terminal_extra_tracks,
            candidate_peer_pending=(
                candidate_peer is not None
                and candidate_peer is not self.peer_connection
            ),
            prompt_lease_pending=releaser is not None,
        )
        self._terminal_cleanup = cleanup
        outcome = _TerminalOutcome(
            target_state=target_state,
            reason=reason,
        )
        outcome.event_commit = self._commit_event()
        self._terminal_outcome = outcome
        outcome.transaction_task = asyncio.create_task(
            self._run_terminal_transaction(cleanup, outcome)
        )
        return cleanup

    async def _run_terminal_transaction(
        self,
        cleanup: _TerminalCleanup,
        outcome: _TerminalOutcome,
    ) -> dict[str, Any]:
        """Finish one terminal transition independently of request cancellation."""

        try:
            cancel_context: dict[str, Any] = {}
            # Individual cleanup steps retain their ledger bit on failure. A
            # bounded retry inside the persistent task handles transient close,
            # cancellation, and lease errors without replaying successful work.
            for attempt in range(3):
                cancel_context = await self._run_terminal_cleanup(cleanup)
                if not self._terminal_cleanup_pending(cleanup):
                    break
                if cleanup.last_attempt_timed_out:
                    break
                if attempt < 2:
                    await asyncio.sleep(0)
            event = await self._publish_terminal_outcome(
                outcome,
                cancel_context=cancel_context,
            )
            if self._terminal_cleanup_pending(cleanup):
                self._terminal_cleanup_task = asyncio.create_task(
                    self._retry_terminal_cleanup_until_resolved(cleanup)
                )
            return event
        except BaseException as exc:
            outcome.error = exc
            raise
        finally:
            outcome.ready.set()

    @staticmethod
    def _terminal_cleanup_pending(cleanup: _TerminalCleanup) -> bool:
        return any(
            (
                cleanup.cancel_pending,
                cleanup.active_peer_pending,
                cleanup.candidate_peer_pending,
                cleanup.prompt_lease_pending,
                bool(cleanup.owned_prompt_cleanups_pending),
                bool(cleanup.owned_prompt_handoffs_pending),
                bool(cleanup.extra_peers_pending),
                bool(cleanup.extra_tracks_pending),
            )
        )

    async def _publish_terminal_outcome(
        self,
        outcome: _TerminalOutcome,
        *,
        cancel_context: dict[str, Any],
    ) -> dict[str, Any]:
        async with outcome.emission_lock:
            if outcome.event is None:
                if outcome.target_state == "failed":
                    event = simple_event(
                        FAILED_EVENT,
                        session_id=self.session_id,
                        code=outcome.reason,
                        message="Call session failed.",
                        retry_allowed=True,
                        **cancel_context,
                    )
                else:
                    event = simple_event(
                        ENDED_EVENT,
                        session_id=self.session_id,
                        reason=outcome.reason,
                        **cancel_context,
                    )
                if outcome.event_commit is None:
                    outcome.event_commit = self._commit_event()
                self._resolve_event_commit(outcome.event_commit, event)
                outcome.event = dict(
                    await self._await_event_commit(outcome.event_commit)
                )
        return dict(outcome.event)

    async def _run_terminal_cleanup(
        self,
        cleanup: _TerminalCleanup,
    ) -> dict[str, Any]:
        async with cleanup.lock:
            cleanup.attempts += 1
            cleanup.last_attempt_timed_out = False
            if cleanup.cancel_pending:
                try:
                    cleanup.cancel_context = await asyncio.wait_for(
                        self.cancel_ai_turn(cause=cleanup.cancel_cause),
                        timeout=CALL_TERMINAL_CLEANUP_STEP_TIMEOUT_SECONDS,
                    )
                except Exception as exc:
                    cleanup.last_attempt_timed_out = (
                        cleanup.last_attempt_timed_out
                        or isinstance(exc, asyncio.TimeoutError)
                    )
                    logger.exception(
                        "[rayme-call] terminal.cleanup_failed session=%s step=cancel exc=%s",
                        self.session_id,
                        exc.__class__.__name__,
                    )
                else:
                    cleanup.cancel_pending = False
            if cleanup.active_peer_pending:
                try:
                    await asyncio.wait_for(
                        self._close_peer(cleanup.active_peer),
                        timeout=CALL_TERMINAL_CLEANUP_STEP_TIMEOUT_SECONDS,
                    )
                except Exception as exc:
                    cleanup.last_attempt_timed_out = (
                        cleanup.last_attempt_timed_out
                        or isinstance(exc, asyncio.TimeoutError)
                    )
                    logger.exception(
                        "[rayme-call] terminal.cleanup_failed session=%s step=active_peer exc=%s",
                        self.session_id,
                        exc.__class__.__name__,
                    )
                else:
                    cleanup.active_peer_pending = False
            try:
                if cleanup.candidate_peer_pending and cleanup.candidate_peer is not None:
                    try:
                        await asyncio.wait_for(
                            self._close_peer(cleanup.candidate_peer),
                            timeout=CALL_TERMINAL_CLEANUP_STEP_TIMEOUT_SECONDS,
                        )
                    except Exception as exc:
                        cleanup.last_attempt_timed_out = (
                            cleanup.last_attempt_timed_out
                            or isinstance(exc, asyncio.TimeoutError)
                        )
                        logger.exception(
                            "[rayme-call] terminal.cleanup_failed session=%s step=candidate_peer exc=%s",
                            self.session_id,
                            exc.__class__.__name__,
                        )
                    else:
                        cleanup.candidate_peer_pending = False
                for peer in list(cleanup.extra_peers_pending):
                    try:
                        await asyncio.wait_for(
                            self._close_peer(peer),
                            timeout=CALL_TERMINAL_CLEANUP_STEP_TIMEOUT_SECONDS,
                        )
                    except Exception as exc:
                        cleanup.last_attempt_timed_out = (
                            cleanup.last_attempt_timed_out
                            or isinstance(exc, asyncio.TimeoutError)
                        )
                        logger.exception(
                            "[rayme-call] terminal.cleanup_failed session=%s "
                            "step=extra_peer exc=%s",
                            self.session_id,
                            exc.__class__.__name__,
                        )
                    else:
                        cleanup.extra_peers_pending.remove(peer)
                for track in list(cleanup.extra_tracks_pending):
                    stop = getattr(track, "stop_current", None)
                    if not callable(stop):
                        cleanup.extra_tracks_pending.remove(track)
                        continue
                    try:
                        result = stop()
                        if inspect.isawaitable(result):
                            await asyncio.wait_for(
                                result,
                                timeout=CALL_TERMINAL_CLEANUP_STEP_TIMEOUT_SECONDS,
                            )
                    except Exception as exc:
                        cleanup.last_attempt_timed_out = (
                            cleanup.last_attempt_timed_out
                            or isinstance(exc, asyncio.TimeoutError)
                        )
                        logger.exception(
                            "[rayme-call] terminal.cleanup_failed session=%s "
                            "step=extra_track exc=%s",
                            self.session_id,
                            exc.__class__.__name__,
                        )
                    else:
                        cleanup.extra_tracks_pending.remove(track)
            finally:
                if (
                    cleanup.prompt_lease_pending
                    and cleanup.prompt_lease_releaser is not None
                ):
                    try:
                        await asyncio.wait_for(
                            self._invoke_tts_prompt_lease_releaser(
                                cleanup.prompt_lease_releaser
                            ),
                            timeout=CALL_TERMINAL_CLEANUP_STEP_TIMEOUT_SECONDS,
                        )
                    except Exception as exc:
                        cleanup.last_attempt_timed_out = (
                            cleanup.last_attempt_timed_out
                            or isinstance(exc, asyncio.TimeoutError)
                        )
                        logger.exception(
                            "[rayme-call] terminal.cleanup_failed session=%s step=prompt_lease exc=%s",
                            self.session_id,
                            exc.__class__.__name__,
                        )
                    else:
                        cleanup.prompt_lease_pending = False
                for owned_cleanup in list(
                    cleanup.owned_prompt_cleanups_pending
                ):
                    task = owned_cleanup.task
                    if owned_cleanup.released:
                        cleanup.owned_prompt_cleanups_pending.remove(
                            owned_cleanup
                        )
                        continue
                    if task is None:
                        continue
                    if not task.done():
                        try:
                            await asyncio.wait_for(
                                asyncio.shield(task),
                                timeout=CALL_SWITCH_CLEANUP_STEP_TIMEOUT_SECONDS,
                            )
                        except asyncio.TimeoutError:
                            cleanup.last_attempt_timed_out = True
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            pass
                    if owned_cleanup.released:
                        cleanup.owned_prompt_cleanups_pending.remove(
                            owned_cleanup
                        )
                for handoff in list(cleanup.owned_prompt_handoffs_pending):
                    task = handoff.task
                    release_cleanup = handoff.release_cleanup
                    if (
                        task is not None
                        and task.done()
                        and not task.cancelled()
                    ):
                        task.exception()
                    if handoff.installed or (
                        release_cleanup is not None
                        and release_cleanup.released
                    ):
                        cleanup.owned_prompt_handoffs_pending.remove(handoff)
                        continue
                    if task is None:
                        continue
                    if not task.done():
                        try:
                            await asyncio.wait_for(
                                asyncio.shield(task),
                                timeout=CALL_SWITCH_CLEANUP_STEP_TIMEOUT_SECONDS,
                            )
                        except asyncio.TimeoutError:
                            cleanup.last_attempt_timed_out = True
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            pass
                    if task.done() and not task.cancelled():
                        task.exception()
                    release_cleanup = handoff.release_cleanup
                    if handoff.installed or (
                        release_cleanup is not None
                        and release_cleanup.released
                    ):
                        cleanup.owned_prompt_handoffs_pending.remove(handoff)
                        continue
                    if (
                        task.done()
                        and release_cleanup is not None
                    ):
                        if release_cleanup not in cleanup.owned_prompt_cleanups_pending:
                            cleanup.owned_prompt_cleanups_pending.append(
                                release_cleanup
                            )
                        cleanup.owned_prompt_handoffs_pending.remove(handoff)
        return dict(cleanup.cancel_context)

    async def _retry_terminal_cleanup_until_resolved(
        self,
        cleanup: _TerminalCleanup,
    ) -> None:
        """Keep terminal resource ownership live after outcome publication."""

        try:
            while (
                self._terminal_cleanup_pending(cleanup)
                and cleanup.attempts < CALL_TERMINAL_CLEANUP_RETRY_LIMIT
            ):
                exponent = max(cleanup.attempts - 1, 0)
                delay = min(
                    CALL_TERMINAL_CLEANUP_RETRY_BASE_SECONDS * (2**exponent),
                    CALL_TERMINAL_CLEANUP_RETRY_MAX_SECONDS,
                )
                if delay > 0:
                    await asyncio.sleep(delay)
                await self._run_terminal_cleanup(cleanup)

            if self._terminal_cleanup_pending(cleanup):
                self._terminal_cleanup_failure_state = {
                    "status": "retry_exhausted",
                    "attempts": cleanup.attempts,
                    "pending_steps": self._terminal_cleanup_pending_steps(cleanup),
                }
                logger.error(
                    "[rayme-call] terminal.cleanup_exhausted session=%s "
                    "attempts=%d pending=%s",
                    self.session_id,
                    cleanup.attempts,
                    ",".join(self._terminal_cleanup_pending_steps(cleanup)),
                )
            else:
                self._terminal_cleanup_failure_state = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._terminal_cleanup_failure_state = {
                "status": "retry_task_failed",
                "attempts": cleanup.attempts,
                "pending_steps": self._terminal_cleanup_pending_steps(cleanup),
                "error": exc.__class__.__name__,
            }
            logger.exception(
                "[rayme-call] terminal.cleanup_retry_failed session=%s exc=%s",
                self.session_id,
                exc.__class__.__name__,
            )

    @staticmethod
    def _terminal_cleanup_pending_steps(
        cleanup: _TerminalCleanup,
    ) -> list[str]:
        pending: list[str] = []
        if cleanup.cancel_pending:
            pending.append("cancel")
        if cleanup.active_peer_pending:
            pending.append("active_peer")
        if cleanup.candidate_peer_pending:
            pending.append("candidate_peer")
        if cleanup.prompt_lease_pending:
            pending.append("prompt_lease")
        if cleanup.owned_prompt_cleanups_pending:
            pending.append(
                "owned_prompt_lease:"
                f"{len(cleanup.owned_prompt_cleanups_pending)}"
            )
        if cleanup.owned_prompt_handoffs_pending:
            pending.append(
                "prompt_lease_handoff:"
                f"{len(cleanup.owned_prompt_handoffs_pending)}"
            )
        if cleanup.extra_peers_pending:
            pending.append(f"extra_peer:{len(cleanup.extra_peers_pending)}")
        if cleanup.extra_tracks_pending:
            pending.append(f"extra_track:{len(cleanup.extra_tracks_pending)}")
        return pending

    async def _release_tts_prompt_lease(self) -> None:
        async with self._lifecycle_lock:
            releaser = self._tts_prompt_lease_releaser
            self._tts_prompt_lease_releaser = None
        if releaser is None:
            return
        await self._invoke_tts_prompt_lease_releaser(releaser)

    async def _invoke_tts_prompt_lease_releaser(
        self,
        releaser: PromptLeaseReleaser,
    ) -> None:
        result = releaser(self.session_id)
        if inspect.isawaitable(result):
            await result

    async def handle_connection_state_change(
        self,
        peer_connection: Any | None = None,
        *,
        terminal_state: str | None = None,
        peer_generation: int | None = None,
    ) -> None:
        peer = peer_connection or self.peer_connection
        connection_state = terminal_state or getattr(peer, "connectionState", None)
        if connection_state in {"failed", "closed"}:
            await self._begin_transport_reconnect(
                peer,
                connection_state,
                peer_generation=peer_generation,
            )
        elif connection_state in {"connected", "completed"}:
            await self._recover_active_transport(
                peer,
                peer_generation=peer_generation,
            )

    async def _begin_transport_reconnect(
        self,
        peer_connection: Any,
        terminal_state: str,
        *,
        peer_generation: int | None = None,
    ) -> None:
        async with self._lifecycle_lock:
            lifecycle = self._peer_lifecycle
            if (
                lifecycle.phase == "switching"
                and lifecycle.retiring_peer is peer_connection
                and (
                    peer_generation is None
                    or peer_generation == lifecycle.retiring_generation
                )
            ):
                logger.info(
                    "[rayme-call] peer.retiring.terminal_ignored session=%s "
                    "switch_generation=%d peer_generation=%s state=%s",
                    self.session_id,
                    lifecycle.switch_generation,
                    peer_generation,
                    terminal_state,
                )
                return
            if (
                self.ended_at is not None
                or lifecycle.phase == "terminal"
                or peer_connection is not self.peer_connection
                or (
                    peer_generation is not None
                    and peer_generation != lifecycle.active_generation
                )
            ):
                return
            if lifecycle.phase != "reconnecting" or lifecycle.grace_peer is not peer_connection:
                lifecycle.epoch += 1
                for admission in self._reconnect_backfill_admissions.values():
                    admission.lifecycle_epoch = lifecycle.epoch
                for admission in self._stt_admissions.values():
                    if admission.allow_transport_reconnect:
                        admission.lifecycle_epoch = lifecycle.epoch
                lifecycle.phase = "reconnecting"
                lifecycle.state_before_reconnect = self.state
                lifecycle.grace_peer = peer_connection
                candidate = lifecycle.candidate
                if candidate is not None:
                    candidate.epoch = lifecycle.epoch
            if terminal_state == "failed" or lifecycle.terminal_state is None:
                lifecycle.terminal_state = terminal_state
            self.state = "reconnecting"
            if (
                lifecycle.grace_task is None
                or lifecycle.grace_task.done()
            ):
                lifecycle.grace_task = asyncio.create_task(
                    self._expire_peer_reconnect_grace(
                        lifecycle.epoch,
                        peer_connection,
                    )
                )
        logger.info(
            "[rayme-call] peer.active.terminal_deferred session=%s state=%s "
            "grace_seconds=%.1f",
            self.session_id,
            terminal_state,
            CALL_PEER_RECONNECT_GRACE_SECONDS,
        )

    async def _expire_peer_reconnect_grace(
        self,
        epoch: int,
        peer_connection: Any,
    ) -> None:
        try:
            await asyncio.sleep(CALL_PEER_RECONNECT_GRACE_SECONDS)
            await self.resolve_deferred_connection_state(
                epoch=epoch,
                peer_connection=peer_connection,
            )
        except asyncio.CancelledError:
            return

    async def resolve_deferred_connection_state(
        self,
        *,
        epoch: int | None = None,
        peer_connection: Any | None = None,
    ) -> bool:
        async with self._lifecycle_lock:
            lifecycle = self._peer_lifecycle
            terminal_state = lifecycle.terminal_state
            if (
                lifecycle.phase != "reconnecting"
                or terminal_state is None
                or self.ended_at is not None
                or (epoch is not None and epoch != lifecycle.epoch)
                or (
                    peer_connection is not None
                    and peer_connection is not lifecycle.grace_peer
                )
            ):
                return False
            if self._active_reconnect_backfills > 0:
                # An admitted backfill owns the missing audio and may be inside
                # slow STT. Do not terminalize underneath that user turn. The
                # finalizer rearms a full grace window if transport is still
                # reconnecting after the backfill completes.
                lifecycle.grace_task = None
                return False
            target_state = "failed" if terminal_state == "failed" else "ended"
            reason = (
                "connection_failed"
                if terminal_state == "failed"
                else "connection_closed"
            )
            cleanup = self._transition_terminal_locked(
                target_state=target_state,
                reason=reason,
            )
        if cleanup is None:
            return False
        outcome = self._terminal_outcome
        transaction = outcome.transaction_task if outcome is not None else None
        if outcome is None or transaction is None:
            raise RuntimeError("terminal outcome was not recorded")
        await asyncio.shield(transaction)
        return True

    async def complete_transport_reconnect(self) -> None:
        async with self._lifecycle_lock:
            self._complete_transport_reconnect_locked()

    async def _recover_active_transport(
        self,
        peer_connection: Any,
        *,
        peer_generation: int | None = None,
    ) -> bool:
        async with self._lifecycle_lock:
            lifecycle = self._peer_lifecycle
            if (
                lifecycle.phase != "reconnecting"
                or lifecycle.grace_peer is not peer_connection
                or peer_connection is not self.peer_connection
                or (
                    peer_generation is not None
                    and peer_generation != lifecycle.active_generation
                )
            ):
                return False
            self._complete_transport_reconnect_locked()
            return True

    def _complete_transport_reconnect_locked(self) -> None:
        lifecycle = self._peer_lifecycle
        lifecycle.terminal_state = None
        restored_state = lifecycle.state_before_reconnect
        lifecycle.state_before_reconnect = None
        lifecycle.grace_peer = None
        self._cancel_peer_reconnect_grace_locked()
        lifecycle.phase = "stable"
        if self.state == "reconnecting":
            self.state = restored_state or "listening"

    def _cancel_peer_reconnect_grace_locked(self) -> None:
        task = self._peer_lifecycle.grace_task
        self._peer_lifecycle.grace_task = None
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()

    def stats(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "muted": self.muted,
            "incoming_audio_frames": self.incoming_audio_frames,
            "dropped_audio_frames": self.dropped_audio_frames,
            "late_tts_event_discard_count": self._late_tts_event_discard_count,
        }

    def _accept_vad_frame(self, frame: PcmAudioFrame) -> dict[str, bool]:
        adapter = self.vad_adapter
        if adapter is not None and hasattr(adapter, "accept_audio_frame"):
            return dict(adapter.accept_audio_frame(frame.pcm))

        if len(frame.pcm) < 2 or len(frame.pcm) % 2 != 0:
            return {
                "speech_detected": self._speech_seen or True,
                "end_of_turn": False,
            }

        samples = np.frombuffer(frame.pcm, dtype=np.int16).astype(np.float32)
        frame_ms = int((len(samples) / max(frame.sample_rate, 1)) * 1000)
        end_silence_ms = self._call_end_silence_ms()

        # DIAG: log per-frame energy for first frame + frame 10
        frame_idx = len(self._turn_frames)
        rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
        peak = float(np.max(np.abs(samples))) if samples.size else 0.0
        reconnect_diag_frame = self._next_media_reconnect_grace_audio_diag_frame()
        reconnect_remaining_ms = self._media_reconnect_grace_remaining_ms()
        if frame_idx == 1 or frame_idx == 10:
            logger.info(
                "[rayme-call] vad.diag session=%s frame=%d samples=%d "
                "rms=%.1f peak=%.1f",
                self.session_id,
                frame_idx,
                len(samples),
                rms,
                peak,
            )

        if adapter is not None and hasattr(adapter, "speech_timestamps"):
            buffered_samples = self._buffered_turn_samples()
            buf_rms = float(np.sqrt(np.mean(np.square(buffered_samples)))) if buffered_samples.size else 0.0
            buf_peak = float(np.max(np.abs(buffered_samples))) if buffered_samples.size else 0.0

            if frame_idx == 10:
                logger.info(
                    "[rayme-call] vad.bufdiag session=%s buf_samples=%d "
                    "buf_rms=%.4f buf_peak=%.4f dur_ms=%d",
                    self.session_id,
                    len(buffered_samples),
                    buf_rms,
                    buf_peak,
                    int(len(buffered_samples) * 1000 / max(
                        getattr(adapter, "sampling_rate", 16000), 1
                    )),
                )

            vad_samples = self._recent_vad_samples(buffered_samples, adapter)
            timestamps = list(adapter.speech_timestamps(vad_samples))
            if frame_idx == 10:
                logger.info(
                    "[rayme-call] vad.silero session=%s ts_count=%d "
                    "threshold=%.2f sr=%d analysis_samples=%d",
                    self.session_id,
                    len(timestamps),
                    adapter.threshold,
                    adapter.sampling_rate,
                    len(vad_samples),
                )
                if timestamps:
                    logger.info(
                        "[rayme-call] vad.silero.first session=%s "
                        "start=%s end=%s",
                        self.session_id,
                        timestamps[0].get("start", "?"),
                        timestamps[0].get("end", "?"),
                    )
            sampling_rate = int(getattr(adapter, "sampling_rate", 16000)) or 16000
            if timestamps:
                self._speech_seen = True
                if self._speech_start_frame is None:
                    self._speech_start_frame = frame_idx
                last_end_sample = int(timestamps[-1].get("end", 0))
                silence_samples = max(len(vad_samples) - last_end_sample, 0)
                self._silence_ms = int(silence_samples * 1000 / sampling_rate)
            elif self._speech_seen:
                self._silence_ms += frame_ms
            if reconnect_diag_frame is not None:
                last_end_sample = (
                    int(timestamps[-1].get("end", 0)) if timestamps else None
                )
                logger.info(
                    "[rayme-call] vad.reconnect_grace.audio session=%s "
                    "diag_frame=%d turn_frame=%d frame_ms=%d rms=%.1f "
                    "peak=%.1f speech_now=%s speech_seen=%s silence_ms=%d "
                    "remaining_ms=%d ts_count=%d analysis_samples=%d "
                    "last_ts_end=%s threshold=%.2f",
                    self.session_id,
                    reconnect_diag_frame,
                    frame_idx,
                    frame_ms,
                    rms,
                    peak,
                    bool(timestamps),
                    self._speech_seen,
                    self._silence_ms,
                    reconnect_remaining_ms,
                    len(timestamps),
                    len(vad_samples),
                    last_end_sample if last_end_sample is not None else "none",
                    adapter.threshold,
                )

            # Max turn duration safety net: force end if Silero keeps
            # classifying everything as continuous speech beyond the call cap.
            max_turn_ms = self._call_max_turn_ms()
            turn_duration_ms = frame_idx * frame_ms
            forced_end = turn_duration_ms >= max_turn_ms

            silence_end = self._speech_seen and self._silence_ms >= end_silence_ms
            reconnect_grace = silence_end and self._in_media_reconnect_grace()

            # Max turn duration forces end even if no speech was detected
            # (ambient noise only). Without this, turns with zero speech
            # would never finalize.
            return {
                "speech_detected": self._speech_seen,
                "end_of_turn": forced_end or (silence_end and not reconnect_grace),
            }

        energy = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
        threshold = float(self.settings.vad_threshold) * 1000.0

        if energy >= threshold:
            self._speech_seen = True
            self._silence_ms = 0
        elif self._speech_seen:
            self._silence_ms += frame_ms
        if reconnect_diag_frame is not None:
            logger.info(
                "[rayme-call] vad.reconnect_grace.audio session=%s "
                "diag_frame=%d turn_frame=%d frame_ms=%d rms=%.1f "
                "peak=%.1f speech_now=%s speech_seen=%s silence_ms=%d "
                "remaining_ms=%d energy_threshold=%.1f",
                self.session_id,
                reconnect_diag_frame,
                frame_idx,
                frame_ms,
                rms,
                peak,
                energy >= threshold,
                self._speech_seen,
                self._silence_ms,
                reconnect_remaining_ms,
                threshold,
            )

        max_turn_ms = self._call_max_turn_ms()
        turn_duration_ms = frame_idx * frame_ms
        silence_end = self._speech_seen and self._silence_ms >= end_silence_ms
        reconnect_grace = silence_end and self._in_media_reconnect_grace()

        return {
            "speech_detected": self._speech_seen or energy >= threshold,
            "end_of_turn": turn_duration_ms >= max_turn_ms
            or (silence_end and not reconnect_grace),
        }

    def _buffered_turn_samples(self) -> np.ndarray:
        chunks: list[np.ndarray] = []
        for frame in self._turn_frames:
            if len(frame.pcm) < 2 or len(frame.pcm) % 2 != 0:
                continue
            samples = np.frombuffer(frame.pcm, dtype=np.int16).astype(np.float32)
            chunks.append(samples / float(np.iinfo(np.int16).max))
        if not chunks:
            return np.asarray([], dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32, copy=False)

    def _recent_vad_samples(self, samples: np.ndarray, adapter: Any) -> np.ndarray:
        sampling_rate = int(getattr(adapter, "sampling_rate", 16000)) or 16000
        end_silence_ms = self._call_end_silence_ms()
        window_seconds = max(2.0, (end_silence_ms + 500) / 1000.0)
        max_samples = max(int(sampling_rate * window_seconds), 1)
        if len(samples) <= max_samples:
            return samples
        return samples[-max_samples:]

    def _call_end_silence_ms(self) -> int:
        return int(
            getattr(
                self.settings,
                "call_vad_end_silence_ms",
                self.settings.vad_end_silence_ms,
            )
        )

    def _call_max_turn_ms(self) -> int:
        return int(
            getattr(
                self.settings,
                "call_vad_max_turn_ms",
                self.settings.vad_max_turn_ms,
            )
        )

    def _call_media_reconnect_grace_ms(self) -> int:
        return int(getattr(self.settings, "call_media_reconnect_grace_ms", 0))

    def _media_reconnect_grace_remaining_ms(self) -> int:
        until = self._media_reconnect_grace_until
        if until <= 0:
            return 0
        return max(int((until - time.monotonic()) * 1000), 0)

    def _next_media_reconnect_grace_audio_diag_frame(self) -> int | None:
        if self._media_reconnect_grace_remaining_ms() <= 0:
            return None
        self._media_reconnect_grace_audio_diag_count += 1
        diag_frame = self._media_reconnect_grace_audio_diag_count
        if diag_frame <= 10 or diag_frame % 25 == 0:
            return diag_frame
        return None

    def _in_media_reconnect_grace(self) -> bool:
        until = self._media_reconnect_grace_until
        if until <= 0:
            return False
        now = time.monotonic()
        if now >= until:
            self._media_reconnect_grace_until = 0.0
            logger.info(
                "[rayme-call] vad.reconnect_grace.expired session=%s "
                "silence_ms=%d",
                self.session_id,
                self._silence_ms,
            )
            self._media_reconnect_grace_logged = False
            return False
        if not self._media_reconnect_grace_logged:
            self._media_reconnect_grace_logged = True
            logger.info(
                "[rayme-call] vad.reconnect_grace.hold session=%s "
                "silence_ms=%d remaining_ms=%d",
                self.session_id,
                self._silence_ms,
                int((until - now) * 1000),
            )
        return True

    def _transcribe_turn(self, frames: list[PcmAudioFrame]) -> dict[str, Any]:
        adapter = self.stt_adapter
        if adapter is None:
            return {
                "status": "accepted",
                "transcript": "",
                "language": "en",
            }

        if hasattr(adapter, "transcribe_pcm"):
            return dict(
                adapter.transcribe_pcm(
                    [frame.pcm for frame in frames],
                    language="en",
                    vad_threshold=self.settings.vad_threshold,
                    vad_end_silence_ms=self.settings.vad_end_silence_ms,
                )
            )

        audio = write_pcm_frames_to_temp_wav(frames)
        try:
            result = adapter.transcribe(
                audio=audio.path,
                vad_adapter=None,
                vad_threshold=self.settings.vad_threshold,
                vad_end_silence_ms=self.settings.vad_end_silence_ms,
                apply_vad_filter=False,
            )
            return self._mapping_from_result(result)
        finally:
            audio.cleanup()

    def _mapping_from_result(self, result: Any) -> dict[str, Any]:
        if hasattr(result, "model_dump"):
            return dict(result.model_dump())
        return dict(result)

    def _trim_trailing_silence_for_stt(
        self,
        frames: list[PcmAudioFrame],
    ) -> list[PcmAudioFrame]:
        if not frames:
            return frames

        silence_threshold = max(float(self.settings.call_min_turn_rms), 1.0)
        trailing_silence_frames = 0
        for frame in reversed(frames):
            rms, _ = self._pcm_frame_rms_peak(frame)
            if rms >= silence_threshold:
                break
            trailing_silence_frames += 1

        if trailing_silence_frames <= 0:
            return frames

        frame_ms = int((len(frames[-1].pcm) // 2) * 1000 / max(frames[-1].sample_rate, 1))
        frame_ms = max(frame_ms, 1)
        keep_silence_frames = max(int(CALL_STT_TRAILING_SILENCE_KEEP_MS / frame_ms), 1)
        trim_frames = max(trailing_silence_frames - keep_silence_frames, 0)
        if trim_frames <= 0 or trim_frames >= len(frames):
            return frames

        logger.info(
            "[rayme-call] stt.trailing_silence_trim session=%s "
            "trimmed_frames=%d kept_silence_frames=%d",
            self.session_id,
            trim_frames,
            keep_silence_frames,
        )
        return frames[:-trim_frames]

    def _trim_reconnect_backfill_overlap(
        self,
        frames: list[PcmAudioFrame],
    ) -> tuple[list[PcmAudioFrame], int]:
        if not self._turn_frames or not frames:
            return frames, 0

        target_rate = int(self._normalizer.target_sample_rate)
        max_overlap_frames = int(CALL_RECONNECT_BACKFILL_MAX_OVERLAP_SECONDS * target_rate / 320)
        max_overlap = min(len(self._turn_frames), len(frames), max_overlap_frames)
        if max_overlap < CALL_RECONNECT_BACKFILL_MIN_OVERLAP_FRAMES:
            return frames, 0

        live_rms = self._frame_rms_series(self._turn_frames[-max_overlap:])
        backfill_rms = self._frame_rms_series(frames[:max_overlap])
        best_overlap = 0
        for overlap in range(max_overlap, CALL_RECONNECT_BACKFILL_MIN_OVERLAP_FRAMES - 1, -1):
            if self._rms_windows_match(live_rms[-overlap:], backfill_rms[:overlap]):
                best_overlap = overlap
                break

        if best_overlap <= 0:
            return frames, 0

        logger.info(
            "[rayme-call] reconnect_audio.backfill.overlap_trim session=%s "
            "trimmed_frames=%d incoming_frames=%d existing_turn_frames=%d",
            self.session_id,
            best_overlap,
            len(frames),
            len(self._turn_frames),
        )
        return frames[best_overlap:], best_overlap

    def _frame_rms_series(self, frames: list[PcmAudioFrame]) -> np.ndarray:
        values = [self._pcm_frame_rms_peak(frame)[0] for frame in frames]
        return np.asarray(values, dtype=np.float32)

    def _rms_windows_match(self, live: np.ndarray, backfill: np.ndarray) -> bool:
        if live.size != backfill.size or live.size == 0:
            return False
        if float(max(np.max(live), np.max(backfill))) < float(self.settings.call_min_turn_rms):
            return False

        live_mean = float(np.mean(live))
        backfill_mean = float(np.mean(backfill))
        mean_denominator = max(live_mean, backfill_mean, 1.0)
        mean_ratio = abs(live_mean - backfill_mean) / mean_denominator
        if mean_ratio > CALL_RECONNECT_BACKFILL_OVERLAP_MEAN_RATIO:
            return False
        max_error_ratio = float(np.max(np.abs(live - backfill))) / mean_denominator
        if max_error_ratio > 0.20:
            return False

        live_centered = live - live_mean
        backfill_centered = backfill - backfill_mean
        denominator = float(np.linalg.norm(live_centered) * np.linalg.norm(backfill_centered))
        if denominator <= 1e-6:
            return bool(np.allclose(live, backfill, rtol=0.08, atol=80.0))

        correlation = float(np.dot(live_centered, backfill_centered) / denominator)
        return correlation >= CALL_RECONNECT_BACKFILL_OVERLAP_CORRELATION

    def _turn_audio_stats(self, frames: list[PcmAudioFrame]) -> dict[str, float] | None:
        chunks: list[np.ndarray] = []
        for frame in frames:
            if len(frame.pcm) < 2 or len(frame.pcm) % 2 != 0:
                continue
            chunks.append(np.frombuffer(frame.pcm, dtype=np.int16).astype(np.float32))
        if not chunks:
            return None
        samples = np.concatenate(chunks)
        if samples.size == 0:
            return None
        return {
            "rms": float(np.sqrt(np.mean(np.square(samples)))),
            "peak": float(np.max(np.abs(samples))),
        }

    def _pcm_frame_rms_peak(self, frame: PcmAudioFrame) -> tuple[float, float]:
        if len(frame.pcm) < 2 or len(frame.pcm) % 2 != 0:
            return 0.0, 0.0
        samples = np.frombuffer(frame.pcm, dtype=np.int16).astype(np.float32)
        if samples.size == 0:
            return 0.0, 0.0
        return (
            float(np.sqrt(np.mean(np.square(samples)))),
            float(np.max(np.abs(samples))),
        )

    def _pcm_backfill_frames(
        self,
        pcm: bytes,
        *,
        sample_rate: int,
        channels: int,
    ) -> list[PcmAudioFrame]:
        if not pcm:
            return []
        if len(pcm) % 2 != 0:
            raise ValueError("PCM backfill must contain 16-bit samples")
        if sample_rate <= 0:
            raise ValueError("PCM backfill sample_rate must be positive")
        if channels <= 0:
            raise ValueError("PCM backfill channels must be positive")

        samples = np.frombuffer(pcm, dtype=np.int16)
        if channels > 1:
            usable = (samples.size // channels) * channels
            samples = samples[:usable]
            if samples.size == 0:
                return []
            samples_float = samples.reshape(-1, channels).astype(np.float32).mean(axis=1)
        else:
            samples_float = samples.astype(np.float32)

        target_rate = int(self._normalizer.target_sample_rate)
        if sample_rate != target_rate:
            samples_float = self._resample_backfill_samples(
                samples_float,
                source_rate=sample_rate,
                target_rate=target_rate,
            )
        samples_int16 = np.clip(
            np.rint(samples_float),
            np.iinfo(np.int16).min,
            np.iinfo(np.int16).max,
        ).astype(np.int16)

        frame_samples = max(int(target_rate * 20 / 1000), 1)
        return [
            PcmAudioFrame(
                pcm=samples_int16[offset : offset + frame_samples].tobytes(),
                sample_rate=target_rate,
                channels=1,
            )
            for offset in range(0, samples_int16.size, frame_samples)
            if samples_int16[offset : offset + frame_samples].size
        ]

    def _resample_backfill_samples(
        self,
        samples: np.ndarray,
        *,
        source_rate: int,
        target_rate: int,
    ) -> np.ndarray:
        if samples.size == 0:
            return samples.astype(np.float32, copy=False)
        duration = samples.size / max(source_rate, 1)
        target_length = max(int(round(duration * target_rate)), 1)
        source_positions = np.linspace(0.0, duration, num=samples.size, endpoint=False)
        target_positions = np.linspace(0.0, duration, num=target_length, endpoint=False)
        return np.interp(target_positions, source_positions, samples).astype(np.float32)

    def _outbound_audio_stats(self) -> dict[str, float | int] | None:
        stats = getattr(self.outbound_audio_track, "last_enqueue_stats", None)
        if isinstance(stats, dict):
            return {
                "duration_ms": int(stats.get("duration_ms") or 0),
                "samples": int(stats.get("samples") or 0),
                "rms": float(stats.get("rms") or 0.0),
                "peak": float(stats.get("peak") or 0.0),
            }
        return None

    def _build_tts_synthesis_input(
        self,
        *,
        turn_id: str,
        voice_id: str,
        text: str,
        reference_audio_b64: str | None,
        reference_transcript: str | None,
        reference_audio_content_type: str | None,
        voxcpm2_options: dict[str, Any],
        qwen3_release_evidence_mode: str | None = None,
        qwen3_release_evidence_seed: int | None = None,
        segment_ordinal: int = 0,
        request_id: str | None = None,
    ) -> TtsSynthesisInput:
        if not reference_audio_b64:
            raise ValueError("call TTS reference audio is required")
        return TtsSynthesisInput(
            text=text,
            reference_audio=_decode_reference_audio_b64(reference_audio_b64),
            reference_transcript=reference_transcript,
            reference_audio_content_type=reference_audio_content_type,
            request_id=request_id or turn_id,
            turn_id=turn_id,
            segment_ordinal=segment_ordinal,
            voice_key=voice_id,
            speech_speed=1.0,
            qwen3_release_evidence_mode=qwen3_release_evidence_mode,
            qwen3_release_evidence_seed=qwen3_release_evidence_seed,
            **voxcpm2_options,
        )

    async def _synthesize_speech(
        self,
        *,
        turn_id: str,
        text: str,
        voice_id: str,
        engine_id: str,
        tts_adapter: Any | None,
        reference_audio_b64: str | None,
        reference_transcript: str | None,
        reference_audio_content_type: str | None,
        voxcpm2_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        adapter = tts_adapter or self.tts_adapter
        if adapter is None:
            return {"wav_bytes": b"", "sample_rate": 24000, "duration_ms": 0}

        # Determine if the TTS method is async. If sync, run it off the event
        # loop thread so aiortc can continue polling outbound tracks and sending
        # RTP keepalive packets during the (potentially 10+ second) GPU synthesis
        # window. If async, await directly (async adapters yield to the loop).
        is_async = self._is_tts_method_async(adapter, reference_audio_b64)
        if is_async:
            result = await self._do_async_synthesis(
                adapter,
                turn_id,
                text,
                voice_id,
                engine_id,
                reference_audio_b64,
                reference_transcript,
                reference_audio_content_type,
                voxcpm2_options or {},
            )
        else:
            result = await asyncio.to_thread(
                self._run_sync_synthesis,
                adapter,
                turn_id,
                text,
                voice_id,
                engine_id,
                reference_audio_b64,
                reference_transcript,
                reference_audio_content_type,
                voxcpm2_options or {},
            )
        if hasattr(result, "model_dump"):
            result = result.model_dump()
        return dict(result)

    def _is_tts_method_async(self, adapter: Any, reference_audio_b64: str | None) -> bool:
        """Check if the TTS adapter's synthesis method is a coroutine function."""
        if hasattr(adapter, "synthesize_call_text"):
            return inspect.iscoroutinefunction(adapter.synthesize_call_text)
        return inspect.iscoroutinefunction(getattr(adapter, "synthesize", None))

    async def _do_async_synthesis(
        self,
        adapter: Any,
        turn_id: str,
        text: str,
        voice_id: str,
        engine_id: str,
        reference_audio_b64: str | None,
        reference_transcript: str | None,
        reference_audio_content_type: str | None,
        voxcpm2_options: dict[str, Any],
    ) -> Any:
        """Await an async TTS adapter."""
        if hasattr(adapter, "synthesize_call_text"):
            return await adapter.synthesize_call_text(
                turn_id=turn_id,
                text=text,
                voice_id=voice_id,
                engine_id=engine_id,
                **_voxcpm2_call_text_options(adapter, engine_id, voxcpm2_options),
            )
        if not reference_audio_b64:
            raise ValueError("call TTS reference audio is required")
        return await adapter.synthesize(
            self._build_tts_synthesis_input(
                turn_id=turn_id,
                voice_id=voice_id,
                text=text,
                reference_audio_b64=reference_audio_b64,
                reference_transcript=reference_transcript,
                reference_audio_content_type=reference_audio_content_type,
                voxcpm2_options=voxcpm2_options,
            )
        )

    def _run_sync_synthesis(
        self,
        adapter: Any,
        turn_id: str,
        text: str,
        voice_id: str,
        engine_id: str,
        reference_audio_b64: str | None,
        reference_transcript: str | None,
        reference_audio_content_type: str | None,
        voxcpm2_options: dict[str, Any],
    ) -> dict[str, Any]:
        """Synchronous TTS synthesis, called from asyncio.to_thread()."""
        if hasattr(adapter, "synthesize_call_text"):
            result = adapter.synthesize_call_text(
                turn_id=turn_id,
                text=text,
                voice_id=voice_id,
                engine_id=engine_id,
                **_voxcpm2_call_text_options(adapter, engine_id, voxcpm2_options),
            )
        else:
            if not reference_audio_b64:
                raise ValueError("call TTS reference audio is required")
            result = adapter.synthesize(
                self._build_tts_synthesis_input(
                    turn_id=turn_id,
                    voice_id=voice_id,
                    text=text,
                    reference_audio_b64=reference_audio_b64,
                    reference_transcript=reference_transcript,
                    reference_audio_content_type=reference_audio_content_type,
                    voxcpm2_options=voxcpm2_options,
                )
            )
        if hasattr(result, "model_dump"):
            result = result.model_dump()
        return dict(result)

    async def _queue_outbound_audio(self, wav_bytes: bytes, *, preroll_seconds: float = 0.0) -> float:
        if not wav_bytes:
            logger.info(
                "[rayme-call] tts.enqueue_empty session=%s",
                self.session_id,
            )
            return 0.0
        enqueue = getattr(self.outbound_audio_track, "enqueue", None)
        if callable(enqueue):
            logger.info(
                "[rayme-call] tts.enqueue session=%s wav_bytes=%d preroll_ms=%d target=track",
                self.session_id,
                len(wav_bytes),
                int(preroll_seconds * 1000),
            )
            result = self._call_track_enqueue(
                enqueue,
                wav_bytes,
                preroll_seconds=preroll_seconds,
            )
            if inspect.isawaitable(result):
                result = await result
            return float(result or 0.0)
        logger.info(
            "[rayme-call] tts.enqueue session=%s wav_bytes=%d target=buffer",
            self.session_id,
            len(wav_bytes),
        )
        self.outbound_audio_buffer.append(wav_bytes)
        return 0.0

    def _call_track_enqueue(
        self,
        enqueue: Callable[..., Any],
        wav_bytes: bytes,
        *,
        preroll_seconds: float,
    ) -> Any:
        try:
            parameters = inspect.signature(enqueue).parameters
        except (TypeError, ValueError):
            parameters = {}
        if "preroll_seconds" in parameters:
            return enqueue(wav_bytes, preroll_seconds=preroll_seconds)
        return enqueue(wav_bytes)

    async def _wait_for_outbound_audio_playback(self, playback_seconds: float) -> bool:
        wait_until_idle = getattr(self.outbound_audio_track, "wait_until_idle", None)
        if not callable(wait_until_idle):
            return True
        timeout = max(playback_seconds + 2.0, 2.0)
        logger.info(
            "[rayme-call] tts.playback_wait session=%s expected_ms=%d timeout_ms=%d",
            self.session_id,
            int(playback_seconds * 1000),
            int(timeout * 1000),
        )
        result = wait_until_idle(timeout=timeout)
        completed = await result if inspect.isawaitable(result) else bool(result)
        logger.info(
            "[rayme-call] tts.playback_wait.done session=%s completed=%s",
            self.session_id,
            completed,
        )
        if CALL_TTS_REMOTE_PLAYOUT_HOLD_SECONDS > 0:
            logger.info(
                "[rayme-call] tts.playout_hold session=%s hold_ms=%d",
                self.session_id,
                int(CALL_TTS_REMOTE_PLAYOUT_HOLD_SECONDS * 1000),
            )
            await asyncio.sleep(CALL_TTS_REMOTE_PLAYOUT_HOLD_SECONDS)
        return bool(completed)


class CallSessionManager:
    def __init__(
        self,
        *,
        settings: AiBackendSettings | None = None,
        vad_adapter: Any | None = None,
        stt_adapter: Any | None = None,
    ) -> None:
        self.settings = settings or AiBackendSettings()
        self.vad_adapter = vad_adapter
        self.stt_adapter = stt_adapter
        self._sessions: dict[str, CallSession] = {}
        self._ended_session_recovery_deadlines: dict[str, float] = {}

    def _expire_retained_sessions(self) -> None:
        now = time.monotonic()
        for session_id, deadline in list(self._ended_session_recovery_deadlines.items()):
            if deadline > now:
                continue
            self._ended_session_recovery_deadlines.pop(session_id, None)
            session = self._sessions.get(session_id)
            if session is not None and session.state in {"ended", "failed"}:
                self._sessions.pop(session_id, None)

    async def create_session(
        self,
        *,
        session_id: str,
        thread_id: str | None = None,
        voice_id: str | None = None,
        engine_id: str | None = None,
        prompt_messages: list[dict[str, Any]] | None = None,
        peer_connection: Any | None = None,
        data_channel: Any | None = None,
        event_sink: EventSink | None = None,
        vad_adapter: Any | None = None,
        stt_adapter: Any | None = None,
        tts_adapter: Any | None = None,
        outbound_audio_track: Any | None = None,
        close_previous_peer: bool = True,
    ) -> CallSession:
        self._expire_retained_sessions()
        existing = self._sessions.get(session_id)
        if existing is not None:
            if (
                peer_connection is not None
                and peer_connection is not existing.peer_connection
            ):
                previous_peer = existing.peer_connection
                existing.peer_connection = peer_connection
                await existing.complete_transport_reconnect()
                existing.mark_media_reconnect_pending()
                if close_previous_peer:
                    close = getattr(previous_peer, "close", None)
                    if callable(close):
                        result = close()
                        if inspect.isawaitable(result):
                            await result
            if data_channel is not None:
                existing.data_channel = data_channel
            if event_sink is not None:
                existing.event_sink = event_sink
            if vad_adapter is not None:
                existing.vad_adapter = vad_adapter
            if stt_adapter is not None:
                existing.stt_adapter = stt_adapter
            if tts_adapter is not None:
                existing.tts_adapter = tts_adapter
            if voice_id is not None or engine_id is not None:
                await existing.update_call_selection(
                    voice_id=voice_id if voice_id is not None else existing.voice_id,
                    engine_id=engine_id if engine_id is not None else existing.engine_id,
                )
            if outbound_audio_track is not None:
                existing.outbound_audio_track = outbound_audio_track
            return existing

        session = CallSession(
            session_id=session_id,
            thread_id=thread_id,
            voice_id=voice_id,
            engine_id=engine_id,
            prompt_messages=prompt_messages,
            peer_connection=peer_connection,
            data_channel=data_channel,
            vad_adapter=vad_adapter if vad_adapter is not None else self.vad_adapter,
            stt_adapter=stt_adapter if stt_adapter is not None else self.stt_adapter,
            settings=self.settings,
            event_sink=event_sink,
            tts_adapter=tts_adapter,
            outbound_audio_track=outbound_audio_track,
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> CallSession | None:
        self._expire_retained_sessions()
        return self._sessions.get(session_id)

    async def end_session(
        self,
        session_id: str,
        *,
        reason: str = "ended",
        recovery_grace_seconds: float = CALL_ENDED_EVENT_RECOVERY_GRACE_SECONDS,
    ) -> CallSession | None:
        self._expire_retained_sessions()
        session = self._sessions.get(session_id)
        if session is None:
            return None
        await session.end(reason=reason)
        if recovery_grace_seconds > 0:
            self._ended_session_recovery_deadlines[session_id] = (
                time.monotonic() + recovery_grace_seconds
            )
        else:
            self._sessions.pop(session_id, None)
            self._ended_session_recovery_deadlines.pop(session_id, None)
        return session

    async def remove_session(self, session_id: str) -> None:
        self._ended_session_recovery_deadlines.pop(session_id, None)
        session = self._sessions.pop(session_id, None)
        if session is not None and session.state not in {"ended", "failed"}:
            await session.end(reason="removed")

    def stats(self) -> dict[str, Any]:
        self._expire_retained_sessions()
        active_sessions = [
            session
            for session_id, session in self._sessions.items()
            if session_id not in self._ended_session_recovery_deadlines
        ]
        return {
            "active_sessions": len(active_sessions),
            "sessions": [session.stats() for session in active_sessions],
        }
