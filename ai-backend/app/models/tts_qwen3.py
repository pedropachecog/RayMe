from __future__ import annotations

import base64
import json
import math
import os
import queue as thread_queue
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from app.models.tts_qwen3_protocol import (
    QwenChunkEvent,
    QwenGenerateCommand,
    QwenInvalidatedEvent,
    QwenInvalidateCommand,
    QwenLoadCommand,
    QwenLoadedEvent,
    QwenPrewarmCommand,
    QwenPromptFailedEvent,
    QwenPromptReadyEvent,
    QwenStreamEventValidator,
    QwenTerminalEvent,
    QwenUnloadCommand,
    QwenWorkerCommand,
    QwenWorkerEvent,
    parse_event,
)
from app.models.tts_registry import (
    ImportGatedTtsAdapter,
    TtsAdapterUnavailable,
    TtsAudioChunk,
    TtsSynthesisInput,
    TtsSynthesisOutput,
)


WORKER_EVENT_PREFIX = "__RAYME_QWEN3__"
WORKER_LOAD_TIMEOUT_SECONDS = 180.0
WORKER_PREWARM_TIMEOUT_SECONDS = 120.0
WORKER_STREAM_EVENT_TIMEOUT_SECONDS = 60.0
WORKER_CONTROL_TIMEOUT_SECONDS = 5.0
WORKER_CANCEL_TIMEOUT_SECONDS = 2.0

ProcessFactory = Callable[..., subprocess.Popen[str]]


class Qwen3WorkerError(ValueError):
    """A sanitized engine-scoped worker failure."""


class Qwen3WorkerProtocolError(Qwen3WorkerError):
    """The worker violated the validated request-scoped IPC contract."""


class Qwen3TtsAdapter(ImportGatedTtsAdapter):
    engine_id = "qwen3_1_7b"
    required_modules = ("faster_qwen3_tts",)
    synthesis_enabled = True

    def __init__(self, process_factory: ProcessFactory | None = None) -> None:
        super().__init__()
        self._process_factory = process_factory or subprocess.Popen
        self._worker: subprocess.Popen[str] | None = None
        self._worker_lines: thread_queue.Queue[str | None] | None = None
        self._operation_lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._active_lock = threading.Lock()
        self._active_request_id: str | None = None
        self._cancel_acknowledgements: dict[str, threading.Event] = {}
        self._cancelled_terminals: set[str] = set()
        self._selected_voice_key: str | None = None

    @property
    def selected_voice_key(self) -> str | None:
        return self._selected_voice_key

    @property
    def active_request_id(self) -> str | None:
        with self._active_lock:
            return self._active_request_id

    def startup_self_test(self) -> None:
        self._ensure_runtime_available()

    def load(self) -> None:
        with self._operation_lock:
            if self.loaded and self._worker is not None and self._worker.poll() is None:
                return
            self._ensure_runtime_available()
            self._ensure_worker()
            request_id = _new_request_id("load")
            self._send_command(QwenLoadCommand(op="load", request_id=request_id))
            event = self._read_event(timeout_seconds=WORKER_LOAD_TIMEOUT_SECONDS)
            if not isinstance(event, QwenLoadedEvent) or event.request_id != request_id:
                self._fail_protocol("invalid Qwen3 load acknowledgement")
            self.loaded = True

    def prewarm(
        self,
        *,
        voice_key: str,
        reference_audio: bytes,
        reference_transcript: str,
    ) -> QwenPromptReadyEvent:
        with self._operation_lock:
            if not self.loaded:
                self.load()
            request_id = _new_request_id("prewarm")
            command = QwenPrewarmCommand(
                op="prewarm",
                request_id=request_id,
                voice_key=voice_key,
                reference_audio_b64=base64.b64encode(reference_audio).decode("ascii"),
                reference_transcript=reference_transcript,
            )
            self._send_command(command)
            event = self._read_event(timeout_seconds=WORKER_PREWARM_TIMEOUT_SECONDS)
            if event.request_id != request_id:
                self._fail_protocol("invalid Qwen3 prewarm request identity")
            if isinstance(event, QwenPromptFailedEvent):
                raise Qwen3WorkerError("Qwen3 voice prompt preparation failed")
            if not isinstance(event, QwenPromptReadyEvent) or event.voice_key != voice_key:
                self._fail_protocol("invalid Qwen3 prewarm acknowledgement")
            self._selected_voice_key = voice_key
            return event

    def stream(
        self,
        request: TtsSynthesisInput,
        *,
        request_id: str | None = None,
        voice_key: str | None = None,
    ) -> Iterable[TtsAudioChunk]:
        with self._operation_lock:
            if not self.loaded:
                self.load()
            selected_voice_key = voice_key or self._selected_voice_key
            if not selected_voice_key or selected_voice_key != self._selected_voice_key:
                raise Qwen3WorkerError("Qwen3 voice prompt is not ready")
            generation_request_id = request_id or _new_request_id("generate")
            max_new_tokens, hard_audio_seconds = _generation_limits(request.text)
            command = QwenGenerateCommand(
                op="generate",
                request_id=generation_request_id,
                voice_key=selected_voice_key,
                text=request.text,
                max_new_tokens=max_new_tokens,
                hard_audio_seconds=hard_audio_seconds,
            )
            validator = QwenStreamEventValidator(
                request_id=generation_request_id,
                max_cumulative_duration_ms=hard_audio_seconds * 1000,
            )
            cancel_ack = threading.Event()
            with self._active_lock:
                if self._active_request_id is not None:
                    raise Qwen3WorkerError("Qwen3 generation is already active")
                self._active_request_id = generation_request_id
                self._cancel_acknowledgements[generation_request_id] = cancel_ack
            try:
                self._send_command(command)
                while validator.terminal is None:
                    event = self._read_event(
                        timeout_seconds=WORKER_STREAM_EVENT_TIMEOUT_SECONDS
                    )
                    try:
                        validator.accept(event)
                    except Exception as exc:
                        self._fail_protocol(
                            "invalid Qwen3 stream event sequence",
                            cause=exc,
                        )
                    if isinstance(event, QwenChunkEvent):
                        yield TtsAudioChunk(
                            engine_id=self.engine_id,
                            chunk_index=event.chunk_index,
                            wav_bytes=event.wav_bytes(),
                            sample_rate=event.sample_rate,
                            duration_ms=event.duration_ms,
                            generated_at_ms=event.generated_at_ms,
                        )
                        continue
                    if not isinstance(event, QwenTerminalEvent):
                        self._fail_protocol("unexpected Qwen3 stream event")
                    if event.event == "cancelled":
                        with self._active_lock:
                            self._cancelled_terminals.add(generation_request_id)
                            cancel_ack.set()
                        return
                    if event.event == "error":
                        raise Qwen3WorkerError("Qwen3 streaming generation failed")
                    if event.chunk_count == 0:
                        raise Qwen3WorkerError("Qwen3 stream produced no audio")
                    return
            finally:
                with self._active_lock:
                    self._active_request_id = None
                    self._cancel_acknowledgements.pop(generation_request_id, None)

    def synthesize(self, request: TtsSynthesisInput) -> TtsSynthesisOutput:
        raise TtsAdapterUnavailable(
            "Qwen3-TTS live synthesis requires the native streaming path"
        )

    def cancel(self, request_id: str) -> bool:
        with self._active_lock:
            if request_id != self._active_request_id:
                return False
            acknowledgement = self._cancel_acknowledgements.get(request_id)
        if acknowledgement is None:
            return False
        from app.models.tts_qwen3_protocol import QwenCancelCommand

        try:
            self._send_command(QwenCancelCommand(op="cancel", request_id=request_id))
        except Qwen3WorkerError:
            self._stop_worker()
            return False
        acknowledgement.wait(timeout=WORKER_CANCEL_TIMEOUT_SECONDS)
        with self._active_lock:
            acknowledged = request_id in self._cancelled_terminals
            self._cancelled_terminals.discard(request_id)
        if acknowledged:
            return True
        self._stop_worker()
        return False

    def invalidate(self, voice_key: str) -> None:
        with self._operation_lock:
            if not self.loaded:
                self._selected_voice_key = None
                return
            request_id = _new_request_id("invalidate")
            self._send_command(
                QwenInvalidateCommand(
                    op="invalidate",
                    request_id=request_id,
                    voice_key=voice_key,
                )
            )
            event = self._read_event(timeout_seconds=WORKER_CONTROL_TIMEOUT_SECONDS)
            if (
                not isinstance(event, QwenInvalidatedEvent)
                or event.request_id != request_id
                or event.voice_key != voice_key
            ):
                self._fail_protocol("invalid Qwen3 invalidate acknowledgement")
            if self._selected_voice_key == voice_key:
                self._selected_voice_key = None

    def unload(self) -> None:
        active_request_id = self.active_request_id
        if active_request_id is not None:
            self.cancel(active_request_id)
        with self._operation_lock:
            worker = self._worker
            if worker is not None and worker.poll() is None and self.loaded:
                request_id = _new_request_id("unload")
                try:
                    self._send_command(
                        QwenUnloadCommand(op="unload", request_id=request_id)
                    )
                    event = self._read_event(
                        timeout_seconds=WORKER_CONTROL_TIMEOUT_SECONDS
                    )
                    if (
                        not isinstance(event, QwenTerminalEvent)
                        or event.request_id != request_id
                        or event.event != "done"
                    ):
                        self._fail_protocol("invalid Qwen3 unload acknowledgement")
                except Qwen3WorkerError:
                    pass
            self.loaded = False
            self._selected_voice_key = None
            self._stop_worker()

    def _ensure_worker(self) -> subprocess.Popen[str]:
        if self._worker is not None and self._worker.poll() is None:
            return self._worker
        ai_backend_root = Path(__file__).resolve().parents[2]
        env = dict(os.environ)
        _sanitize_python_hash_seed(env)
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(ai_backend_root)
            if not existing_pythonpath
            else f"{ai_backend_root}{os.pathsep}{existing_pythonpath}"
        )
        self._worker = self._process_factory(
            [sys.executable, "-m", "app.models.tts_qwen3_worker"],
            cwd=str(ai_backend_root),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._worker_lines = thread_queue.Queue()
        self._start_worker_reader(self._worker)
        return self._worker

    def _start_worker_reader(self, worker: subprocess.Popen[str]) -> None:
        lines = self._worker_lines
        stdout = worker.stdout
        if lines is None or stdout is None:
            return

        def read_stdout() -> None:
            try:
                for line in stdout:
                    lines.put(line.rstrip("\r\n"))
            finally:
                lines.put(None)

        threading.Thread(
            target=read_stdout,
            name="rayme-qwen3-worker-stdout",
            daemon=True,
        ).start()

    def _send_command(self, command: QwenWorkerCommand) -> None:
        worker = self._ensure_worker()
        if worker.stdin is None:
            self._stop_worker()
            raise Qwen3WorkerError("Qwen3 worker unavailable")
        line = WORKER_EVENT_PREFIX + command.model_dump_json() + "\n"
        try:
            with self._write_lock:
                worker.stdin.write(line)
                worker.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            self._stop_worker()
            raise Qwen3WorkerError("Qwen3 worker unavailable") from exc

    def _read_event(self, *, timeout_seconds: float) -> QwenWorkerEvent:
        lines = self._worker_lines
        if lines is None:
            raise Qwen3WorkerError("Qwen3 worker unavailable")
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._stop_worker()
                raise Qwen3WorkerError("Qwen3 worker timed out")
            try:
                line = lines.get(timeout=remaining)
            except thread_queue.Empty as exc:
                self._stop_worker()
                raise Qwen3WorkerError("Qwen3 worker timed out") from exc
            if line is None:
                self._stop_worker()
                raise Qwen3WorkerError("Qwen3 worker stopped")
            if not line.startswith(WORKER_EVENT_PREFIX):
                continue
            try:
                payload = json.loads(line[len(WORKER_EVENT_PREFIX) :])
                return parse_event(payload)
            except Exception as exc:
                self._fail_protocol("malformed Qwen3 worker event", cause=exc)

    def _fail_protocol(self, message: str, *, cause: Exception | None = None) -> None:
        self._stop_worker()
        if cause is None:
            raise Qwen3WorkerProtocolError(message)
        raise Qwen3WorkerProtocolError(message) from cause

    def _stop_worker(self) -> None:
        worker = self._worker
        self._worker = None
        self._worker_lines = None
        self.loaded = False
        self._selected_voice_key = None
        with self._active_lock:
            acknowledgements = list(self._cancel_acknowledgements.values())
        for acknowledgement in acknowledgements:
            acknowledgement.set()
        if worker is None:
            return
        try:
            if worker.stdin is not None:
                worker.stdin.close()
        except OSError:
            pass
        if worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)


def _generation_limits(text: str) -> tuple[int, float]:
    word_count = len(text.split())
    if word_count == 0:
        raise Qwen3WorkerError("Qwen3 target text is required")
    if word_count > 60:
        raise Qwen3WorkerError("Qwen3 target segment is too long")
    expected_seconds = max(1.0, word_count / 2.2)
    hard_audio_seconds = min(32.0, max(6.0, expected_seconds * 2.25 + 2.0))
    max_new_tokens = min(384, math.ceil(hard_audio_seconds * 12 / 4) * 4)
    return max_new_tokens, round(hard_audio_seconds, 3)


def _new_request_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _sanitize_python_hash_seed(env: dict[str, str]) -> None:
    value = env.get("PYTHONHASHSEED")
    if value is None or value == "random":
        return
    try:
        parsed = int(value)
    except ValueError:
        env["PYTHONHASHSEED"] = "random"
        return
    if parsed < 0 or parsed > (2**32 - 1):
        env["PYTHONHASHSEED"] = "random"
