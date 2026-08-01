from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import queue as thread_queue
import re
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from app.models.tts_qwen3_protocol import (
    QwenCancelCommand,
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
QWEN_MODEL_REVISION = "fd4b254389122332181a7c3db7f27e918eec64e3"


def _voice_generation_seed(prompt_key: str) -> int:
    """Return the stable identity seed for one prepared speaker prompt."""

    digest = hashlib.sha256(
        f"rayme-qwen3-speaker-v1:{prompt_key}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:4], byteorder="big", signed=False)


QWEN_CLONE_MODE = "full_icl"
QWEN_APPEND_SILENCE = True
QWEN_MIN_AUDIO_PEAK = 1e-5
QWEN_AUDIO_DURATION_TOLERANCE_MS = 10.0

ProcessFactory = Callable[..., subprocess.Popen[str]]


class Qwen3WorkerError(ValueError):
    """A sanitized engine-scoped worker failure."""

    default_code = "qwen3_worker_failed"
    marks_engine_unavailable = False

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.default_code


class Qwen3ValidationError(Qwen3WorkerError):
    """The request can be corrected without reloading the Qwen runtime."""

    default_code = "qwen3_validation_failed"


class Qwen3PromptError(Qwen3WorkerError):
    """Prompt preparation failed for one content-bound voice identity."""

    default_code = "qwen3_prompt_failed"


class Qwen3PromptLeaseError(Qwen3PromptError):
    """A live call owns the capacity-one prompt slot."""

    default_code = "qwen3_prompt_leased"


class Qwen3GenerationError(Qwen3WorkerError):
    """One generation failed without proving the worker identity is corrupt."""

    default_code = "qwen3_generation_failed"


class Qwen3GenerationCeilingError(Qwen3GenerationError):
    """The request hit its text-relative audio/token safety ceiling."""

    default_code = "qwen3_generation_ceiling"


class Qwen3RuntimeError(Qwen3WorkerError):
    """The isolated worker/runtime failed and must be explicitly reloaded."""

    default_code = "qwen3_runtime_failed"
    marks_engine_unavailable = True


class Qwen3WorkerProtocolError(Qwen3RuntimeError):
    """The worker violated the validated request-scoped IPC contract."""

    default_code = "qwen3_worker_protocol"


@dataclass(frozen=True, slots=True)
class QwenPromptInvalidationResult:
    voice_key: str
    matched: bool
    active_cancelled: bool


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
        self._prompt_lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        self._active_lock = threading.Lock()
        self._active_request_id: str | None = None
        self._cancel_acknowledgements: dict[str, threading.Event] = {}
        self._cancelled_terminals: set[str] = set()
        self._selected_voice_key: str | None = None
        self._selected_prompt_key: str | None = None
        self._torch_reserved_mib: float | None = None

    @property
    def selected_voice_key(self) -> str | None:
        with self._prompt_lock:
            return self._selected_voice_key

    @property
    def active_request_id(self) -> str | None:
        with self._active_lock:
            return self._active_request_id

    @property
    def torch_reserved_mib(self) -> float | None:
        with self._metrics_lock:
            return self._torch_reserved_mib

    def _record_torch_reserved_mib(self, value: float) -> None:
        with self._metrics_lock:
            self._torch_reserved_mib = value

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
            if event.request_id != request_id:
                self._fail_protocol("invalid Qwen3 load request identity")
            if isinstance(event, QwenTerminalEvent) and event.event == "error":
                self._stop_worker()
                raise Qwen3RuntimeError(
                    "Qwen3 runtime load failed",
                    code=event.error_code,
                )
            if not isinstance(event, QwenLoadedEvent):
                self._fail_protocol("invalid Qwen3 load acknowledgement")
            self._record_torch_reserved_mib(event.torch_reserved_mib)
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
            if not reference_audio:
                raise Qwen3ValidationError(
                    "Qwen3 reference audio is required",
                    code="qwen3_reference_audio_required",
                )
            if not reference_transcript.strip():
                raise Qwen3ValidationError(
                    "Qwen3 reference transcript is required",
                    code="qwen3_transcript_required",
                )
            prompt_key = qwen_prompt_cache_key(
                reference_audio,
                reference_transcript,
            )
            request_id = _new_request_id("prewarm")
            command = QwenPrewarmCommand(
                op="prewarm",
                request_id=request_id,
                voice_key=prompt_key,
                reference_audio_b64=base64.b64encode(reference_audio).decode("ascii"),
                reference_transcript=reference_transcript,
            )
            self._clear_selected_prompt()
            self._send_command(command)
            event = self._read_event(timeout_seconds=WORKER_PREWARM_TIMEOUT_SECONDS)
            if event.request_id != request_id:
                self._fail_protocol("invalid Qwen3 prewarm request identity")
            if isinstance(event, QwenPromptFailedEvent):
                raise Qwen3PromptError(
                    "Qwen3 voice prompt preparation failed",
                    code=event.error_code,
                )
            if (
                not isinstance(event, QwenPromptReadyEvent)
                or event.voice_key != prompt_key
            ):
                self._fail_protocol("invalid Qwen3 prewarm acknowledgement")
            with self._prompt_lock:
                self._selected_voice_key = voice_key
                self._selected_prompt_key = prompt_key
            return event.model_copy(update={"voice_key": voice_key})

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
            with self._prompt_lock:
                current_voice_key = self._selected_voice_key
                selected_voice_key = voice_key or current_voice_key
                selected_prompt_key = self._selected_prompt_key
            if (
                not selected_voice_key
                or selected_voice_key != current_voice_key
                or selected_prompt_key is None
            ):
                raise Qwen3PromptError(
                    "Qwen3 voice prompt is not ready",
                    code="qwen3_prompt_not_ready",
                )
            generation_request_id = request_id or _new_request_id("generate")
            max_new_tokens, hard_audio_seconds = _generation_limits(request.text)
            speaker_seed = _voice_generation_seed(selected_prompt_key)
            generation_seed = (
                request.qwen3_release_evidence_seed
                if request.qwen3_release_evidence_seed is not None
                else speaker_seed
            )
            command = QwenGenerateCommand(
                op="generate",
                request_id=generation_request_id,
                voice_key=selected_prompt_key,
                text=request.text,
                max_new_tokens=max_new_tokens,
                hard_audio_seconds=hard_audio_seconds,
                speaker_seed=speaker_seed,
                generation_seed=generation_seed,
                release_evidence_mode=request.qwen3_release_evidence_mode,
                release_evidence_seed=request.qwen3_release_evidence_seed,
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
                        self._record_torch_reserved_mib(event.torch_reserved_mib)
                        try:
                            wav_bytes = _validate_worker_wav(event)
                        except Exception as exc:
                            self._fail_protocol(
                                "invalid Qwen3 worker audio",
                                cause=exc,
                            )
                        yield TtsAudioChunk(
                            engine_id=self.engine_id,
                            chunk_index=event.chunk_index,
                            wav_bytes=wav_bytes,
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
                        error = _generation_terminal_error(event.error_code)
                        if error.marks_engine_unavailable:
                            self._stop_worker()
                        raise error
                    if event.chunk_count == 0:
                        raise Qwen3GenerationError(
                            "Qwen3 stream produced no audio",
                            code="qwen3_no_audio",
                        )
                    return
            finally:
                if validator.terminal is None:
                    self._cancel_and_drain_abandoned_stream(
                        generation_request_id,
                        validator,
                        cancel_ack,
                    )
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

    def _cancel_and_drain_abandoned_stream(
        self,
        request_id: str,
        validator: QwenStreamEventValidator,
        acknowledgement: threading.Event,
    ) -> None:
        """Own worker cleanup when a consumer closes a live generator early."""
        worker = self._worker
        if worker is None or worker.poll() is not None:
            return
        with self._active_lock:
            if self._active_request_id != request_id:
                return
        try:
            self._send_command(QwenCancelCommand(op="cancel", request_id=request_id))
            while validator.terminal is None:
                event = self._read_event(
                    timeout_seconds=WORKER_CANCEL_TIMEOUT_SECONDS
                )
                validator.accept(event)
                if isinstance(event, QwenTerminalEvent):
                    if event.event == "cancelled":
                        with self._active_lock:
                            self._cancelled_terminals.add(request_id)
                            acknowledgement.set()
                    return
        except Exception:
            # A missing/malformed terminal cannot be allowed to outlive its
            # request and contaminate the next generation.
            self._stop_worker()

    def invalidate(self, voice_key: str) -> QwenPromptInvalidationResult:
        with self._prompt_lock:
            matched = self._selected_voice_key == voice_key
        if not matched:
            return QwenPromptInvalidationResult(
                voice_key=voice_key,
                matched=False,
                active_cancelled=False,
            )

        active_request_id = self.active_request_id
        active_cancelled = False
        if active_request_id is not None:
            active_cancelled = self.cancel(active_request_id)

        with self._operation_lock:
            with self._prompt_lock:
                still_selected = self._selected_voice_key == voice_key
                prompt_key = self._selected_prompt_key if still_selected else None
            if not still_selected:
                # Cancellation timeout terminates the worker and clears prompt
                # ownership. That is still a successful privacy eviction.
                return QwenPromptInvalidationResult(
                    voice_key=voice_key,
                    matched=True,
                    active_cancelled=active_cancelled,
                )
            if not self.loaded:
                self._clear_selected_prompt()
                return QwenPromptInvalidationResult(
                    voice_key=voice_key,
                    matched=True,
                    active_cancelled=active_cancelled,
                )
            if prompt_key is None:
                self._clear_selected_prompt()
                return QwenPromptInvalidationResult(
                    voice_key=voice_key,
                    matched=True,
                    active_cancelled=active_cancelled,
                )
            request_id = _new_request_id("invalidate")
            self._send_command(
                QwenInvalidateCommand(
                    op="invalidate",
                    request_id=request_id,
                    voice_key=prompt_key,
                )
            )
            event = self._read_event(timeout_seconds=WORKER_CONTROL_TIMEOUT_SECONDS)
            if (
                not isinstance(event, QwenInvalidatedEvent)
                or event.request_id != request_id
                or event.voice_key != prompt_key
                or event.matched is not True
            ):
                self._fail_protocol("invalid Qwen3 invalidate acknowledgement")
            self._clear_selected_prompt()
            return QwenPromptInvalidationResult(
                voice_key=voice_key,
                matched=True,
                active_cancelled=active_cancelled,
            )

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
            self._clear_selected_prompt()
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
        try:
            self._worker = self._process_factory(
                [_worker_python_executable(), "-m", "app.models.tts_qwen3_worker"],
                cwd=str(ai_backend_root),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except Qwen3WorkerError:
            raise
        except Exception as exc:
            self._stop_worker()
            raise Qwen3RuntimeError(
                "Qwen3 worker unavailable",
                code="qwen3_worker_unavailable",
            ) from exc
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
            raise Qwen3RuntimeError(
                "Qwen3 worker unavailable",
                code="qwen3_worker_unavailable",
            ) from exc

    def _read_event(self, *, timeout_seconds: float) -> QwenWorkerEvent:
        lines = self._worker_lines
        if lines is None:
            raise Qwen3RuntimeError(
                "Qwen3 worker unavailable",
                code="qwen3_worker_unavailable",
            )
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._stop_worker()
                raise Qwen3RuntimeError(
                    "Qwen3 worker timed out",
                    code="qwen3_worker_timeout",
                )
            try:
                line = lines.get(timeout=remaining)
            except thread_queue.Empty as exc:
                self._stop_worker()
                raise Qwen3RuntimeError(
                    "Qwen3 worker timed out",
                    code="qwen3_worker_timeout",
                ) from exc
            if line is None:
                self._stop_worker()
                raise Qwen3RuntimeError(
                    "Qwen3 worker stopped",
                    code="qwen3_worker_stopped",
                )
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
        with self._metrics_lock:
            self._torch_reserved_mib = None
        self._clear_selected_prompt()
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

    def _clear_selected_prompt(self) -> None:
        with self._prompt_lock:
            self._selected_voice_key = None
            self._selected_prompt_key = None


def _generation_limits(text: str) -> tuple[int, float]:
    word_count = len(text.split())
    if word_count == 0:
        raise Qwen3ValidationError(
            "Qwen3 target text is required",
            code="qwen3_target_required",
        )
    if word_count > 60:
        raise Qwen3ValidationError(
            "Qwen3 target segment is too long",
            code="qwen3_target_too_long",
        )
    expected_seconds = max(1.0, word_count / 2.2)
    hard_audio_seconds = min(32.0, max(6.0, expected_seconds * 2.25 + 2.0))
    max_new_tokens = min(384, math.ceil(hard_audio_seconds * 12 / 4) * 4)
    return max_new_tokens, round(hard_audio_seconds, 3)


def qwen_prompt_cache_key(reference_audio: bytes, reference_transcript: str) -> str:
    """Return the capacity-one worker identity without exposing clone material."""
    normalized_transcript = normalize_qwen_comparison_text(reference_transcript)
    if not reference_audio:
        raise Qwen3ValidationError(
            "Qwen3 reference audio is required",
            code="qwen3_reference_audio_required",
        )
    if not normalized_transcript:
        raise Qwen3ValidationError(
            "Qwen3 reference transcript is required",
            code="qwen3_transcript_required",
        )
    reference_digest = hashlib.sha256(reference_audio).hexdigest()
    identity = "\0".join(
        (
            reference_digest,
            normalized_transcript,
            QWEN_MODEL_REVISION,
            QWEN_CLONE_MODE,
            f"append_silence={str(QWEN_APPEND_SILENCE).lower()}",
        )
    ).encode("utf-8")
    return "prompt_" + hashlib.sha256(identity).hexdigest()


def normalize_qwen_comparison_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(re.findall(r"[a-z0-9]+", without_marks))


def _validate_worker_wav(event: QwenChunkEvent) -> bytes:
    import numpy as np
    import soundfile as sf

    wav_bytes = event.wav_bytes()
    try:
        audio, sample_rate = sf.read(
            BytesIO(wav_bytes),
            dtype="float32",
            always_2d=True,
        )
    except Exception as exc:
        raise ValueError("invalid worker WAV") from exc
    samples = np.asarray(audio, dtype=np.float32)
    if int(sample_rate) != event.sample_rate or samples.ndim != 2:
        raise ValueError("invalid worker WAV format")
    if samples.shape[0] == 0 or samples.shape[1] != 1:
        raise ValueError("invalid worker WAV channels")
    if not np.isfinite(samples).all():
        raise ValueError("non-finite worker WAV")
    if float(np.max(np.abs(samples))) <= QWEN_MIN_AUDIO_PEAK:
        raise ValueError("silent worker WAV")
    actual_duration_ms = samples.shape[0] * 1000.0 / float(sample_rate)
    tolerance_ms = max(
        QWEN_AUDIO_DURATION_TOLERANCE_MS,
        actual_duration_ms * 0.02,
    )
    if abs(actual_duration_ms - event.duration_ms) > tolerance_ms:
        raise ValueError("worker WAV duration mismatch")
    return wav_bytes


def _generation_terminal_error(error_code: str | None) -> Qwen3WorkerError:
    code = error_code or "qwen3_generation_failed"
    if code == "qwen3_generation_ceiling":
        return Qwen3GenerationCeilingError(
            "Qwen3 generation exceeded its safety ceiling",
            code=code,
        )
    if code in {"qwen3_not_ready", "qwen3_prompt_not_ready"}:
        return Qwen3PromptError(
            "Qwen3 voice prompt is not ready",
            code=code,
        )
    return Qwen3RuntimeError(
        "Qwen3 streaming runtime failed",
        code=code,
    )


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


def _worker_python_executable() -> str:
    executable = Path(sys.executable)
    if executable.name.casefold() != "pythonw.exe":
        return str(executable)
    console_executable = executable.with_name("python.exe")
    if not console_executable.is_file():
        raise Qwen3RuntimeError(
            "Qwen3 console worker runtime unavailable",
            code="qwen3_worker_unavailable",
        )
    return str(console_executable)
