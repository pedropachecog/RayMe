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


class SpeechSessionSelectionError(RuntimeError):
    """Raised when speech does not match the accepted call configuration."""


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
    active_peer_pending: bool = True
    candidate_peer_pending: bool = True
    prompt_lease_pending: bool = True
    cancel_context: dict[str, Any] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class _TerminalOutcome:
    target_state: str
    reason: str
    event: dict[str, Any] | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    emission_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


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
        self._tts_turn_segment_ordinals: dict[str, int] = {}
        self._tts_segment_reservations: dict[tuple[str, str], int] = {}
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
        self._last_tts_cancel_context: dict[str, Any] | None = None
        self._pending_speech_terminal_turn_id: str | None = None
        self._pending_speech_terminal_voice_id: str | None = None
        self._pending_speech_terminal_engine_id: str | None = None
        self._pending_speech_playback_final: dict[str, Any] | None = None
        self._late_tts_event_discard_count = 0
        self._undelivered_events: list[dict[str, Any]] = []
        self._media_reconnect_grace_pending = False
        self._media_reconnect_grace_until = 0.0
        self._media_reconnect_grace_logged = False
        self._media_reconnect_grace_audio_diag_count = 0
        self._reconnect_audio_backfill_ids: set[str] = set()
        self._reconnect_live_frame_hold_until = 0.0
        self._reconnect_live_frame_hold_logged = False
        self._reconnect_live_frame_hold_frames: list[PcmAudioFrame] = []
        self._lifecycle_lock = asyncio.Lock()
        self._peer_lifecycle = _PeerLifecycle()
        self._tts_prompt_lease_releaser: PromptLeaseReleaser | None = None
        self._terminal_cleanup: _TerminalCleanup | None = None
        self._terminal_outcome: _TerminalOutcome | None = None

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
    ) -> bool:
        async with self._lifecycle_lock:
            if self.ended_at is None and self.state not in {"ended", "failed"}:
                self._tts_prompt_lease_releaser = releaser
                return True
        await self._invoke_tts_prompt_lease_releaser(releaser)
        return False

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
            lifecycle = self._peer_lifecycle
            if (
                self.ended_at is not None
                or lifecycle.phase == "terminal"
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
        if self.muted or self.state in {"ended", "failed", "rehearsing"}:
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
        for superseded_peer in superseded_peers:
            await self._close_peer(superseded_peer)
        return generation

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
        )

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
        selection_changed = False
        cancel_selection = False
        previous_outbound_audio_track: Any | None = None
        accepted_outbound_audio_track: Any | None = None
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
            self.peer_connection = peer_connection
            if outbound_audio_track is None:
                outbound_audio_track = candidate.outbound_audio_track
            if outbound_audio_track is not None:
                self.outbound_audio_track = outbound_audio_track
            accepted_outbound_audio_track = self.outbound_audio_track
            if candidate.data_channel is not None:
                self.data_channel = candidate.data_channel
            configuration = candidate.configuration
            if configuration is not None:
                selection_changed = (
                    configuration.voice_id != self.voice_id
                    or configuration.engine_id != self.engine_id
                )
                self.thread_id = configuration.thread_id
                self.voice_id = configuration.voice_id
                self.engine_id = configuration.engine_id
                self.prompt_messages = [
                    dict(message) for message in configuration.prompt_messages
                ]
                self.vad_adapter = configuration.vad_adapter
                self.stt_adapter = configuration.stt_adapter
            cancel_selection = selection_changed and (
                self.active_turn_task is not None
                or self._active_tts_turn_id is not None
                or self._pending_speech_terminal_turn_id is not None
            )
            if cancel_selection:
                cancelling_turn_id = (
                    self._active_tts_turn_id
                    or self._pending_speech_terminal_turn_id
                )
                if cancelling_turn_id is not None:
                    self._cancelling_ai_turns.add(cancelling_turn_id)
            self._clear_pending_peer_locked(peer_connection)
            self._complete_transport_reconnect_locked()
        if cancel_selection:
            playout_tracks = (
                previous_outbound_audio_track,
                accepted_outbound_audio_track,
            )
            await self._stop_and_drain_outbound_playout(
                tracks=playout_tracks,
            )
            cancel_task = asyncio.create_task(
                self.cancel_ai_turn(
                    cause="engine_switch",
                    playout_tracks=playout_tracks,
                    playout_already_stopped=True,
                )
            )
            if previous_peer_connection is not None:
                await self._close_peer(previous_peer_connection)
            await cancel_task
            if self.state not in {"ended", "failed"}:
                self.state = "listening"
        elif previous_peer_connection is not None:
            await self._close_peer(previous_peer_connection)
        return True, previous_peer_connection

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
        await self._close_peer(peer_connection)
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
        if (
            self.state == "failed"
            and self.end_reason == "connection_failed"
            and (self._turn_frames or pcm)
        ):
            self.state = "listening"
            self.end_reason = None
            self.ended_at = None

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
                    event = await self.finalize_user_turn()
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
                    event = await self.finalize_user_turn()
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
            event = await self.finalize_user_turn()

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

    async def finalize_user_turn(self) -> dict[str, Any] | None:
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

        try:
            transcription = await asyncio.to_thread(self._transcribe_turn, frames)
        except Exception as exc:
            logger.exception(
                "[rayme-call] stt.failed session=%s turn=%s elapsed_ms=%d exc=%s",
                self.session_id,
                turn_id,
                int((time.perf_counter() - stt_started) * 1000),
                exc.__class__.__name__,
            )
            event = failed_event(
                session_id=self.session_id,
                turn_id=turn_id,
                code="call_stt_failed",
                message="Speech transcription failed. Please try speaking again.",
                retry_allowed=True,
            )
            await self.emit_event(event)
            if self.ended_at is None:
                self.state = "listening"
            return event

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
            await self.emit_event(event)
            if self.ended_at is None:
                self.state = "listening"
            return event
        event = user_final_event(
            session_id=self.session_id,
            turn_id=turn_id,
            text=text,
            started_at=started_at,
            ended_at=ended_at,
        )
        await self.emit_event(event)
        # Transition to "thinking" — the AI is now generating LLM text.
        # Inbound audio during this window would be ambient noise that Whisper
        # hallucinates into phantom transcriptions ("thank you" from silence).
        # Dropped by the guard in handle_inbound_audio_frame.
        if self.ended_at is None:
            self.state = "thinking"
        return {
            "type": event["type"],
            "session_id": event["session_id"],
            "turn_id": event["turn_id"],
            "text": event["text"],
        }

    async def emit_event(self, event: dict[str, Any]) -> dict[str, Any]:
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
        self.muted = muted
        self.state = "muted" if muted else "listening"
        return await self.emit_event(
            simple_event(
                MUTED_EVENT,
                session_id=self.session_id,
                muted=muted,
            )
        )

    async def interrupt(self, *, cause: str = "button_interrupt") -> dict[str, Any]:
        self.interrupted = True
        cancel_context = await self.cancel_ai_turn(cause=cause)
        self.state = "interrupted"
        event = await self.emit_event(
            simple_event(
                INTERRUPTED_EVENT,
                session_id=self.session_id,
                receiver_drain_ms=CALL_INTERRUPT_RECEIVER_DRAIN_MS,
                **cancel_context,
            )
        )
        self.state = "listening"
        return event

    async def update_call_selection(
        self,
        *,
        voice_id: str | None,
        engine_id: str | None,
    ) -> None:
        changed = voice_id != self.voice_id or engine_id != self.engine_id
        if changed and (
            self.active_turn_task is not None
            or self._active_tts_turn_id is not None
            or self._pending_speech_terminal_turn_id is not None
        ):
            await self.cancel_ai_turn(cause="engine_switch")
            if self.state not in {"ended", "failed"}:
                self.state = "listening"
        self.voice_id = voice_id
        self.engine_id = engine_id

    async def complete_speech_turn(
        self,
        *,
        turn_id: str,
        voice_id: str,
        engine_id: str,
        accepted_configuration: AcceptedSpeechConfiguration | None = None,
    ) -> dict[str, Any]:
        """Terminalize a fully played incremental turn without synthesizing again."""
        if accepted_configuration is not None:
            await self._validate_accepted_speech_configuration(
                accepted_configuration
            )
        if (
            turn_id in self._cancelled_ai_turns
            or turn_id in self._cancelling_ai_turns
        ):
            return {"status": "cancelled", "turn_id": turn_id}

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
            return event

        self._clear_tts_segment_state(turn_id)
        playback_final = dict(self._pending_speech_playback_final or {})
        self._clear_pending_speech_terminal()
        self.state = "listening"
        return await self.emit_event(
            simple_event(
                AI_DONE_EVENT,
                session_id=self.session_id,
                turn_id=turn_id,
                voice_id=voice_id,
                engine_id=engine_id,
                tts_playback_final=playback_final,
            )
        )

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
        if accepted_configuration is not None:
            await self._validate_accepted_speech_configuration(
                accepted_configuration
            )
        self._cancelled_ai_turns.discard(turn_id)
        self._cancelling_ai_turns.discard(turn_id)
        reserved_segment_ordinal, segment_reservation_key = (
            self._reserve_tts_segment_ordinal(
                turn_id=turn_id,
                text=text,
                final_chunk=final_chunk,
                segment_id=segment_id,
                requested_ordinal=segment_ordinal,
            )
        )
        self.state = "rehearsing"
        current_task = asyncio.current_task()
        if current_task is not None:
            self.active_turn_task = current_task

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
        adapter = tts_adapter or self.tts_adapter

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
                )
                if self._tts_segment_result_succeeded(result):
                    self._commit_tts_segment_ordinal(
                        turn_id=turn_id,
                        reservation_key=segment_reservation_key,
                        segment_ordinal=reserved_segment_ordinal,
                        final_chunk=final_chunk,
                    )
                elif result.get("status") == "cancelled":
                    self._clear_tts_segment_state(turn_id)
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
                self._clear_tts_segment_state(turn_id)
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
                playout_wait_completed = await self._wait_for_outbound_audio_playback(
                    playback_seconds
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
            self._clear_tts_segment_state(turn_id)
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
            if audio_started_event is not None:
                return {**event, "ai_audio_started_event": audio_started_event}
            return event
        finally:
            if self.active_turn_task is current_task:
                self.active_turn_task = None

        if turn_id in self._cancelled_ai_turns:
            self.state = "listening"
            self._clear_tts_segment_state(turn_id)
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
            self._commit_tts_segment_ordinal(
                turn_id=turn_id,
                reservation_key=segment_reservation_key,
                segment_ordinal=reserved_segment_ordinal,
                final_chunk=True,
            )
            if audio_started_event is not None:
                return {**done_event, "ai_audio_started_event": audio_started_event}
            return done_event

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
        self._commit_tts_segment_ordinal(
            turn_id=turn_id,
            reservation_key=segment_reservation_key,
            segment_ordinal=reserved_segment_ordinal,
            final_chunk=False,
        )
        return queued_event

    def _reserve_tts_segment_ordinal(
        self,
        *,
        turn_id: str,
        text: str,
        final_chunk: bool,
        segment_id: str | None,
        requested_ordinal: int | None,
    ) -> tuple[int, tuple[str, str]]:
        if segment_id is not None:
            identity = f"id:{segment_id}"
        elif requested_ordinal is not None:
            identity = f"ordinal:{requested_ordinal}"
        else:
            digest = hashlib.sha256(
                f"{int(final_chunk)}\0{text}".encode("utf-8")
            ).hexdigest()
            identity = f"legacy:{digest}"
        reservation_key = (turn_id, identity)
        reserved = self._tts_segment_reservations.get(reservation_key)
        if reserved is not None:
            return reserved, reservation_key
        ordinal = (
            requested_ordinal
            if requested_ordinal is not None
            else self._tts_turn_segment_ordinals.get(turn_id, 0)
        )
        self._tts_segment_reservations[reservation_key] = ordinal
        return ordinal, reservation_key

    @staticmethod
    def _tts_segment_result_succeeded(result: dict[str, Any]) -> bool:
        return (
            result.get("status") == "queued"
            or result.get("type") == AI_DONE_EVENT
        )

    def _commit_tts_segment_ordinal(
        self,
        *,
        turn_id: str,
        reservation_key: tuple[str, str],
        segment_ordinal: int,
        final_chunk: bool,
    ) -> None:
        if final_chunk:
            self._clear_tts_segment_state(turn_id)
            return
        self._tts_segment_reservations[reservation_key] = segment_ordinal
        self._tts_turn_segment_ordinals[turn_id] = max(
            self._tts_turn_segment_ordinals.get(turn_id, 0),
            segment_ordinal + 1,
        )

    def _clear_tts_segment_state(self, turn_id: str) -> None:
        self._tts_turn_segment_ordinals.pop(turn_id, None)
        for reservation_key in tuple(self._tts_segment_reservations):
            if reservation_key[0] == turn_id:
                self._tts_segment_reservations.pop(reservation_key, None)

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
            )
            loop = asyncio.get_running_loop()

            self._active_tts_adapter = adapter
            self._active_tts_request_id = turn_id
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
                            request_id=turn_id,
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
                    if turn_id not in self._cancelled_ai_turns:
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

            if stream_completed_normally:
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

            playout_wait_completed = await self._wait_for_outbound_audio_playback(
                playback_seconds
            )
            playout_complete_ms = elapsed_ms()
            playback_final = final_metrics()

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
            if self._active_tts_turn_id == turn_id:
                self._active_tts_adapter = None
                self._active_tts_request_id = None
                self._active_tts_turn_id = None
                self._active_tts_cancel_requested = False
                self._active_tts_metrics_snapshot = None

    async def _cancel_active_tts_generation(
        self,
        turn_id: str | None,
        *,
        cancel_started: asyncio.Event | None = None,
    ) -> bool | None:
        request_id = self._active_tts_request_id
        active_turn_id = self._active_tts_turn_id
        adapter = self._active_tts_adapter
        if (
            request_id is None
            or adapter is None
            or self._active_tts_cancel_requested
            or (turn_id is not None and active_turn_id != turn_id)
        ):
            if cancel_started is not None:
                cancel_started.set()
            return None

        cancel = getattr(adapter, "cancel", None)
        if not callable(cancel):
            if cancel_started is not None:
                cancel_started.set()
            return None

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
    ) -> dict[str, Any]:
        cancel_started_at = time.perf_counter()
        active = self.active_turn_task
        resolved_turn_id = (
            turn_id
            or self._active_tts_turn_id
            or self._pending_speech_terminal_turn_id
        )
        request_id = self._active_tts_request_id
        metrics_snapshot = (
            self._active_tts_metrics_snapshot
            if request_id is not None and resolved_turn_id == self._active_tts_turn_id
            else None
        )
        playback_final: dict[str, Any] | None = None
        if resolved_turn_id is not None:
            self._cancelling_ai_turns.add(resolved_turn_id)
            self._clear_tts_segment_state(resolved_turn_id)
        cancel_started = asyncio.Event()
        cancel_task = asyncio.create_task(
            self._cancel_active_tts_generation(
                resolved_turn_id,
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
        if playback_final is None and self._pending_speech_playback_final is not None:
            playback_final = dict(self._pending_speech_playback_final)
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
        self._clear_pending_speech_terminal()

        if active is not None and active is not asyncio.current_task():
            cancel = getattr(active, "cancel", None)
            if callable(cancel):
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
        cancel_context: dict[str, Any] = {}
        async with self._lifecycle_lock:
            cleanup = self._transition_terminal_locked(
                target_state="ended",
                reason=reason,
            )
            owns_emission = cleanup is not None
            if cleanup is None and self.end_reason is None:
                self.end_reason = reason
            cleanup = cleanup or self._terminal_cleanup
            outcome = self._terminal_outcome
        if cleanup is not None:
            cancel_context = await self._run_terminal_cleanup(cleanup)
        if outcome is None:
            raise RuntimeError("terminal outcome was not recorded")
        return await self._publish_terminal_outcome(
            outcome,
            cancel_context=cancel_context,
            owns_emission=owns_emission,
        )

    def _clear_pending_speech_terminal(self) -> None:
        self._pending_speech_terminal_turn_id = None
        self._pending_speech_terminal_voice_id = None
        self._pending_speech_terminal_engine_id = None
        self._pending_speech_playback_final = None

    async def fail(self, *, reason: str = "connection_failed") -> dict[str, Any]:
        cancel_context: dict[str, Any] = {}
        async with self._lifecycle_lock:
            cleanup = self._transition_terminal_locked(
                target_state="failed",
                reason=reason,
            )
            owns_emission = cleanup is not None
            cleanup = cleanup or self._terminal_cleanup
            outcome = self._terminal_outcome
        if cleanup is not None:
            cancel_context = await self._run_terminal_cleanup(cleanup)
        if outcome is None:
            raise RuntimeError("terminal outcome was not recorded")
        return await self._publish_terminal_outcome(
            outcome,
            cancel_context=cancel_context,
            owns_emission=owns_emission,
        )

    def _transition_terminal_locked(
        self,
        *,
        target_state: str,
        reason: str,
    ) -> _TerminalCleanup | None:
        if self.ended_at is not None or self._peer_lifecycle.phase == "terminal":
            return None
        lifecycle = self._peer_lifecycle
        lifecycle.epoch += 1
        lifecycle.phase = "terminal"
        lifecycle.terminal_state = None
        lifecycle.state_before_reconnect = None
        lifecycle.grace_peer = None
        self._cancel_peer_reconnect_grace_locked()
        candidate = lifecycle.candidate
        candidate_peer = candidate.peer_connection if candidate is not None else None
        if candidate is not None:
            self._clear_pending_peer_locked(candidate.peer_connection)
        releaser = self._tts_prompt_lease_releaser
        self._tts_prompt_lease_releaser = None
        self.ended_at = datetime.now(timezone.utc)
        self.end_reason = reason
        self.state = target_state
        self._tts_turn_segment_ordinals.clear()
        self._tts_segment_reservations.clear()
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
            cancel_pending=(
                self.active_turn_task is not None
                or self._active_tts_turn_id is not None
                or self._pending_speech_terminal_turn_id is not None
            ),
            candidate_peer_pending=(
                candidate_peer is not None
                and candidate_peer is not self.peer_connection
            ),
            prompt_lease_pending=releaser is not None,
        )
        self._terminal_cleanup = cleanup
        self._terminal_outcome = _TerminalOutcome(
            target_state=target_state,
            reason=reason,
        )
        return cleanup

    async def _publish_terminal_outcome(
        self,
        outcome: _TerminalOutcome,
        *,
        cancel_context: dict[str, Any],
        owns_emission: bool,
    ) -> dict[str, Any]:
        if not owns_emission:
            await outcome.ready.wait()
            if outcome.event is None:
                raise RuntimeError("terminal outcome emission did not complete")
            return dict(outcome.event)
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
                outcome.event = dict(await self.emit_event(event))
                outcome.ready.set()
        return dict(outcome.event)

    async def _run_terminal_cleanup(
        self,
        cleanup: _TerminalCleanup,
    ) -> dict[str, Any]:
        async with cleanup.lock:
            if cleanup.cancel_pending:
                try:
                    cleanup.cancel_context = await self.cancel_ai_turn(
                        cause=cleanup.cancel_cause
                    )
                except Exception as exc:
                    logger.exception(
                        "[rayme-call] terminal.cleanup_failed session=%s step=cancel exc=%s",
                        self.session_id,
                        exc.__class__.__name__,
                    )
                else:
                    cleanup.cancel_pending = False
            if cleanup.active_peer_pending:
                try:
                    await self._close_peer(cleanup.active_peer)
                except Exception as exc:
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
                        await self._close_peer(cleanup.candidate_peer)
                    except Exception as exc:
                        logger.exception(
                            "[rayme-call] terminal.cleanup_failed session=%s step=candidate_peer exc=%s",
                            self.session_id,
                            exc.__class__.__name__,
                        )
                    else:
                        cleanup.candidate_peer_pending = False
            finally:
                if (
                    cleanup.prompt_lease_pending
                    and cleanup.prompt_lease_releaser is not None
                ):
                    try:
                        await self._invoke_tts_prompt_lease_releaser(
                            cleanup.prompt_lease_releaser
                        )
                    except Exception as exc:
                        logger.exception(
                            "[rayme-call] terminal.cleanup_failed session=%s step=prompt_lease exc=%s",
                            self.session_id,
                            exc.__class__.__name__,
                        )
                    else:
                        cleanup.prompt_lease_pending = False
        return dict(cleanup.cancel_context)

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
    ) -> None:
        peer = peer_connection or self.peer_connection
        if peer is not self.peer_connection:
            return
        connection_state = terminal_state or getattr(peer, "connectionState", None)
        if connection_state in {"failed", "closed"}:
            await self._begin_transport_reconnect(peer, connection_state)
        elif connection_state in {"connected", "completed"}:
            await self._recover_active_transport(peer)

    async def _begin_transport_reconnect(
        self,
        peer_connection: Any,
        terminal_state: str,
    ) -> None:
        async with self._lifecycle_lock:
            lifecycle = self._peer_lifecycle
            if (
                self.ended_at is not None
                or lifecycle.phase == "terminal"
                or peer_connection is not self.peer_connection
            ):
                return
            if lifecycle.phase != "reconnecting" or lifecycle.grace_peer is not peer_connection:
                lifecycle.epoch += 1
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
        cancel_context = await self._run_terminal_cleanup(cleanup)
        outcome = self._terminal_outcome
        if outcome is None:
            raise RuntimeError("terminal outcome was not recorded")
        await self._publish_terminal_outcome(
            outcome,
            cancel_context=cancel_context,
            owns_emission=True,
        )
        return True

    async def complete_transport_reconnect(self) -> None:
        async with self._lifecycle_lock:
            self._complete_transport_reconnect_locked()

    async def _recover_active_transport(self, peer_connection: Any) -> bool:
        async with self._lifecycle_lock:
            lifecycle = self._peer_lifecycle
            if (
                lifecycle.phase != "reconnecting"
                or lifecycle.grace_peer is not peer_connection
                or peer_connection is not self.peer_connection
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
    ) -> TtsSynthesisInput:
        if not reference_audio_b64:
            raise ValueError("call TTS reference audio is required")
        return TtsSynthesisInput(
            text=text,
            reference_audio=_decode_reference_audio_b64(reference_audio_b64),
            reference_transcript=reference_transcript,
            reference_audio_content_type=reference_audio_content_type,
            request_id=turn_id,
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
