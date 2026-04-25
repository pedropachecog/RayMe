from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

import numpy as np

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
    normalize_inbound_audio_frame,
    write_pcm_frames_to_temp_wav,
)
from app.config import AiBackendSettings
from app.models.tts_registry import TtsSynthesisInput

EventSink = Callable[[dict[str, Any]], Awaitable[None] | None]


class NullPeerConnection:
    connectionState = "new"

    async def close(self) -> None:
        return None


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
        self._speech_seen = False
        self._silence_ms = 0
        self._cancelled_ai_turns: set[str] = set()

    @property
    def active_ai_turn(self) -> Any | None:
        return self.active_turn_task

    @active_ai_turn.setter
    def active_ai_turn(self, value: Any | None) -> None:
        self.active_turn_task = value

    async def handle_inbound_audio_frame(self, frame: Any) -> dict[str, Any] | bool | None:
        self.incoming_audio_frames += 1
        was_raw_bytes = isinstance(frame, bytes)
        if self.muted or self.state in {"ended", "failed"}:
            self.dropped_audio_frames += 1
            return False if was_raw_bytes else None

        normalized = normalize_inbound_audio_frame(frame)
        self._turn_frames.append(normalized)
        if self._turn_started_at is None:
            self._turn_started_at = utc_timestamp()

        vad_result = self._accept_vad_frame(normalized)
        if not vad_result.get("speech_detected", True):
            return None
        if not vad_result.get("end_of_turn", False):
            return None

        return await self.finalize_user_turn()

    async def finalize_user_turn(self) -> dict[str, Any] | None:
        if not self._turn_frames:
            return None

        self._turn_index += 1
        turn_id = f"user-turn-{self._turn_index}"
        frames = list(self._turn_frames)
        started_at = self._turn_started_at or utc_timestamp()
        ended_at = utc_timestamp()
        self._turn_frames.clear()
        self._turn_started_at = None
        self._speech_seen = False
        self._silence_ms = 0

        try:
            transcription = self._transcribe_turn(frames)
        except Exception:
            event = failed_event(
                session_id=self.session_id,
                turn_id=turn_id,
                code="call_stt_failed",
                message="Speech transcription failed. Please try speaking again.",
                retry_allowed=True,
            )
            await self.emit_event(event)
            self.state = "listening"
            return event

        text = str(transcription.get("transcript") or "").strip()
        event = user_final_event(
            session_id=self.session_id,
            turn_id=turn_id,
            text=text,
            started_at=started_at,
            ended_at=ended_at,
        )
        await self.emit_event(event)
        self.state = "listening"
        return {
            "type": event["type"],
            "session_id": event["session_id"],
            "turn_id": event["turn_id"],
            "text": event["text"],
        }

    async def emit_event(self, event: dict[str, Any]) -> dict[str, Any]:
        if self.event_sink is not None:
            result = self.event_sink(event)
            if inspect.isawaitable(result):
                await result

        channel = self.data_channel
        if channel is not None and getattr(channel, "readyState", "open") == "open":
            send = getattr(channel, "send", None)
            if callable(send):
                send(json.dumps(event, separators=(",", ":")))
        return event

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

    async def interrupt(self) -> dict[str, Any]:
        self.interrupted = True
        await self.cancel_ai_turn()
        self.state = "interrupted"
        event = await self.emit_event(
            simple_event(INTERRUPTED_EVENT, session_id=self.session_id)
        )
        self.state = "listening"
        return event

    async def speak_text(
        self,
        turn_id: str,
        text: str,
        voice_id: str,
        engine_id: str,
        final_chunk: bool = False,
        *,
        tts_adapter: Any | None = None,
    ) -> dict[str, Any]:
        self._cancelled_ai_turns.discard(turn_id)
        self.state = "speaking"
        current_task = asyncio.current_task()
        if current_task is not None:
            self.active_turn_task = current_task

        await self.emit_event(
            simple_event(
                AI_AUDIO_STARTED_EVENT,
                session_id=self.session_id,
                turn_id=turn_id,
                voice_id=voice_id,
                engine_id=engine_id,
            )
        )

        try:
            result = await self._synthesize_speech(
                turn_id=turn_id,
                text=text,
                voice_id=voice_id,
                engine_id=engine_id,
                tts_adapter=tts_adapter,
            )
            if turn_id in self._cancelled_ai_turns:
                return {"status": "cancelled", "turn_id": turn_id}
            wav_bytes = bytes(result.get("wav_bytes") or b"")
            await self._queue_outbound_audio(wav_bytes)
        except asyncio.CancelledError:
            self._cancelled_ai_turns.add(turn_id)
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
            await self.emit_event(event)
            return event
        finally:
            if self.active_turn_task is current_task:
                self.active_turn_task = None

        if turn_id in self._cancelled_ai_turns:
            self.state = "listening"
            return {"status": "cancelled", "turn_id": turn_id}

        if final_chunk:
            self.state = "listening"
            return await self.emit_event(
                simple_event(
                    AI_DONE_EVENT,
                    session_id=self.session_id,
                    turn_id=turn_id,
                    voice_id=voice_id,
                    engine_id=engine_id,
                )
            )

        return {
            "status": "queued",
            "session_id": self.session_id,
            "turn_id": turn_id,
            "engine_id": engine_id,
        }

    async def cancel_ai_turn(self, turn_id: str | None = None) -> None:
        active = self.active_turn_task
        if turn_id is not None:
            self._cancelled_ai_turns.add(turn_id)
        if active is not None:
            cancel = getattr(active, "cancel", None)
            if callable(cancel):
                cancel()
        self.active_turn_task = None
        stop = getattr(self.outbound_audio_track, "stop_current", None)
        if callable(stop):
            result = stop()
            if inspect.isawaitable(result):
                await result
        self.outbound_audio_buffer.drain()

    async def end(self, *, reason: str = "ended") -> dict[str, Any]:
        if self.ended_at is None:
            self.ended_at = datetime.now(timezone.utc)
            self.end_reason = reason
            self.state = "ended"
            active = self.active_turn_task
            if active is not None:
                cancel = getattr(active, "cancel", None)
                if callable(cancel):
                    cancel()
            self.active_turn_task = None
            close = getattr(self.peer_connection, "close", None)
            if callable(close):
                result = close()
                if inspect.isawaitable(result):
                    await result
        elif self.end_reason is None:
            self.end_reason = reason

        return await self.emit_event(
            simple_event(
                ENDED_EVENT,
                session_id=self.session_id,
                reason=self.end_reason or reason,
            )
        )

    async def fail(self, *, reason: str = "connection_failed") -> dict[str, Any]:
        self.state = "failed"
        self.end_reason = reason
        if self.ended_at is None:
            self.ended_at = datetime.now(timezone.utc)
        close = getattr(self.peer_connection, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result
        return await self.emit_event(
            simple_event(
                FAILED_EVENT,
                session_id=self.session_id,
                code=reason,
                message="Call session failed.",
                retry_allowed=True,
            )
        )

    async def handle_connection_state_change(self) -> None:
        if getattr(self.peer_connection, "connectionState", None) == "failed":
            await self.fail(reason="connection_failed")

    def stats(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "muted": self.muted,
            "incoming_audio_frames": self.incoming_audio_frames,
            "dropped_audio_frames": self.dropped_audio_frames,
        }

    def _accept_vad_frame(self, frame: PcmAudioFrame) -> dict[str, bool]:
        adapter = self.vad_adapter
        if adapter is not None and hasattr(adapter, "accept_audio_frame"):
            return dict(adapter.accept_audio_frame(frame.pcm))

        buffered_samples = self._buffered_turn_samples()
        if adapter is not None and hasattr(adapter, "speech_timestamps"):
            timestamps = adapter.speech_timestamps(buffered_samples)
            if timestamps:
                self._speech_seen = True

        if len(frame.pcm) < 2 or len(frame.pcm) % 2 != 0:
            return {
                "speech_detected": self._speech_seen or True,
                "end_of_turn": False,
            }

        samples = np.frombuffer(frame.pcm, dtype=np.int16).astype(np.float32)
        energy = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
        threshold = float(self.settings.vad_threshold) * 1000.0
        frame_ms = int((len(samples) / max(frame.sample_rate, 1)) * 1000)

        if energy >= threshold:
            self._speech_seen = True
            self._silence_ms = 0
        elif self._speech_seen:
            self._silence_ms += frame_ms

        return {
            "speech_detected": self._speech_seen or energy >= threshold,
            "end_of_turn": self._speech_seen
            and self._silence_ms >= int(self.settings.vad_end_silence_ms),
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
            )
            return self._mapping_from_result(result)
        finally:
            audio.cleanup()

    def _mapping_from_result(self, result: Any) -> dict[str, Any]:
        if hasattr(result, "model_dump"):
            return dict(result.model_dump())
        return dict(result)

    async def _synthesize_speech(
        self,
        *,
        turn_id: str,
        text: str,
        voice_id: str,
        engine_id: str,
        tts_adapter: Any | None,
    ) -> dict[str, Any]:
        adapter = tts_adapter or self.tts_adapter
        if adapter is None:
            return {"wav_bytes": b"", "sample_rate": 24000, "duration_ms": 0}

        if hasattr(adapter, "synthesize_call_text"):
            result = adapter.synthesize_call_text(
                turn_id=turn_id,
                text=text,
                voice_id=voice_id,
                engine_id=engine_id,
            )
        else:
            result = adapter.synthesize(
                TtsSynthesisInput(
                    text=text,
                    reference_audio=b"rayme-call-reference-placeholder",
                    speech_speed=1.0,
                )
            )
        if inspect.isawaitable(result):
            result = await result
        if hasattr(result, "model_dump"):
            result = result.model_dump()
        return dict(result)

    async def _queue_outbound_audio(self, wav_bytes: bytes) -> None:
        if not wav_bytes:
            return
        enqueue = getattr(self.outbound_audio_track, "enqueue", None)
        if callable(enqueue):
            result = enqueue(wav_bytes)
            if inspect.isawaitable(result):
                await result
            return
        self.outbound_audio_buffer.append(wav_bytes)


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
    ) -> CallSession:
        existing = self._sessions.get(session_id)
        if existing is not None:
            if data_channel is not None:
                existing.data_channel = data_channel
            if event_sink is not None:
                existing.event_sink = event_sink
            if tts_adapter is not None:
                existing.tts_adapter = tts_adapter
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
        return self._sessions.get(session_id)

    async def remove_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is not None and session.state not in {"ended", "failed"}:
            await session.end(reason="removed")

    def stats(self) -> dict[str, Any]:
        return {
            "active_sessions": len(self._sessions),
            "sessions": [session.stats() for session in self._sessions.values()],
        }
