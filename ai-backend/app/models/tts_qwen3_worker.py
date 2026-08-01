from __future__ import annotations

import base64
import contextlib
import importlib.metadata
import json
import os
import queue
import random
import sys
import threading
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Iterator

from app.models.tts_qwen3_protocol import (
    ENGINE_ID,
    SAMPLE_RATE,
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
    QwenTerminalEvent,
    QwenUnloadCommand,
    QwenWorkerCommand,
    QwenWorkerEvent,
    parse_command,
)


WORKER_EVENT_PREFIX = "__RAYME_QWEN3__"
RUNTIME_VERSION = "0.3.2"
RUNTIME_REPOSITORY = "https://github.com/andimarafioti/faster-qwen3-tts"
RUNTIME_COMMIT = "a70afc0f81f7f5f8801c3227968f1102f43f211c"
MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
MODEL_REVISION = "fd4b254389122332181a7c3db7f27e918eec64e3"
MODEL_MANIFEST_FILENAME = "rayme-model-revision.json"
MODEL_DIR_ENV = "RAYME_QWEN3_MODEL_DIR"
MODEL_REVISION_ENV = "RAYME_QWEN3_MODEL_REVISION"
WARMUP_PREFILL = 100
MAX_SEQUENCE_LENGTH = 1536
CHUNK_SIZE = 4


@dataclass(frozen=True)
class PreparedVoicePrompt:
    voice_key: str
    reference_transcript: str
    prompt_items: list[Any]


_RUNTIME: Any | None = None
_PREPARED_PROMPT: PreparedVoicePrompt | None = None
_ACTIVE_REQUEST_ID: str | None = None
_ACTIVE_CANCEL: threading.Event | None = None
_ACTIVE_LOCK = threading.Lock()
_PENDING_CANCELS: set[str] = set()
_EMIT_LOCK = threading.Lock()
_COMMANDS: queue.Queue[QwenWorkerCommand | None] = queue.Queue(maxsize=8)


def main() -> int:
    initial_command = _read_initial_command()
    if initial_command is None:
        return 0
    if not _dispatch(initial_command):
        return 0
    reader = threading.Thread(
        target=_read_commands,
        name="rayme-qwen3-command-reader",
        daemon=True,
    )
    reader.start()
    while True:
        command = _COMMANDS.get()
        if command is None:
            return 0
        keep_running = _dispatch(command)
        if not keep_running:
            return 0


def _read_initial_command() -> QwenWorkerCommand | None:
    """Read the mandatory first control command before CUDA starts any threads."""
    for raw_line in sys.stdin:
        command = _parse_command_line(raw_line)
        if command is None:
            continue
        if isinstance(command, QwenCancelCommand):
            _signal_cancel(command)
            continue
        return command
    return None


def _read_commands() -> None:
    for raw_line in sys.stdin:
        command = _parse_command_line(raw_line)
        if command is None:
            continue
        if isinstance(command, QwenCancelCommand):
            _signal_cancel(command)
            continue
        _COMMANDS.put(command)
    _COMMANDS.put(None)


def _parse_command_line(raw_line: str) -> QwenWorkerCommand | None:
    line = raw_line.strip()
    if not line.startswith(WORKER_EVENT_PREFIX):
        return None
    try:
        return parse_command(json.loads(line[len(WORKER_EVENT_PREFIX) :]))
    except Exception:
        return None


def _torch_reserved_mib() -> float:
    """Return allocator-owned CUDA memory from inside the Qwen worker."""
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("Qwen3 CUDA allocator is unavailable")
    reserved_bytes = int(torch.cuda.memory_reserved())
    if reserved_bytes <= 0:
        raise RuntimeError("Qwen3 CUDA allocator reported no reserved memory")
    return round(reserved_bytes / (1024 * 1024), 3)


def _signal_cancel(command: QwenCancelCommand) -> None:
    with _ACTIVE_LOCK:
        cancel_event = (
            _ACTIVE_CANCEL if _ACTIVE_REQUEST_ID == command.request_id else None
        )
        if cancel_event is None:
            # A request-scoped interrupt can beat the main thread between queueing
            # generate and installing its active event. Preserve that interrupt.
            if len(_PENDING_CANCELS) >= 8:
                _PENDING_CANCELS.clear()
            _PENDING_CANCELS.add(command.request_id)
        else:
            cancel_event.set()


def _dispatch(command: QwenWorkerCommand) -> bool:
    global _RUNTIME, _PREPARED_PROMPT
    if isinstance(command, QwenLoadCommand):
        try:
            _RUNTIME = _load_runtime_from_environment()
            _emit_event(
                QwenLoadedEvent(
                    event="loaded",
                    request_id=command.request_id,
                    engine_id=ENGINE_ID,
                    runtime_version=RUNTIME_VERSION,
                    model_revision=MODEL_REVISION,
                    device="cuda",
                    sample_rate=SAMPLE_RATE,
                    warmup_prefill=WARMUP_PREFILL,
                    torch_reserved_mib=_torch_reserved_mib(),
                )
            )
        except Exception:
            _emit_error(command.request_id, "qwen3_load_failed")
        return True

    if isinstance(command, QwenPrewarmCommand):
        try:
            if _RUNTIME is None:
                raise RuntimeError("runtime not loaded")
            # Capacity one means a failed replacement can never leave the
            # previous prompt silently selectable under a changed reference.
            _PREPARED_PROMPT = None
            prepared = prepare_voice_prompt(_RUNTIME, command)
            _PREPARED_PROMPT = prepared
            _emit_event(
                QwenPromptReadyEvent(
                    event="prompt_ready",
                    request_id=command.request_id,
                    voice_key=prepared.voice_key,
                )
            )
        except Exception:
            _emit_event(
                QwenPromptFailedEvent(
                    event="prompt_failed",
                    request_id=command.request_id,
                    voice_key=command.voice_key,
                    error_code="qwen3_prompt_failed",
                )
            )
        return True

    if isinstance(command, QwenGenerateCommand):
        if _RUNTIME is None or _PREPARED_PROMPT is None:
            _emit_error(command.request_id, "qwen3_not_ready")
            return True
        if _PREPARED_PROMPT.voice_key != command.voice_key:
            _emit_error(command.request_id, "qwen3_prompt_not_ready")
            return True
        cancelled = threading.Event()
        with _ACTIVE_LOCK:
            global _ACTIVE_REQUEST_ID, _ACTIVE_CANCEL
            _ACTIVE_REQUEST_ID = command.request_id
            _ACTIVE_CANCEL = cancelled
            if command.request_id in _PENDING_CANCELS:
                _PENDING_CANCELS.remove(command.request_id)
                cancelled.set()
        try:
            rng_scope = (
                _release_evidence_rng_scope(command.release_evidence_seed)
                if command.release_evidence_seed is not None
                else contextlib.nullcontext()
            )
            with rng_scope:
                for event in iter_generation_events(
                    _RUNTIME,
                    _PREPARED_PROMPT,
                    command,
                    cancelled,
                ):
                    _emit_event(event)
        except Exception:
            _emit_error(command.request_id, "qwen3_generation_failed")
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE_REQUEST_ID = None
                _ACTIVE_CANCEL = None
        return True

    if isinstance(command, QwenInvalidateCommand):
        matched = (
            _PREPARED_PROMPT is not None
            and _PREPARED_PROMPT.voice_key == command.voice_key
        )
        if matched:
            _PREPARED_PROMPT = None
        _emit_event(
            QwenInvalidatedEvent(
                event="invalidated",
                request_id=command.request_id,
                voice_key=command.voice_key,
                matched=matched,
            )
        )
        return True

    if isinstance(command, QwenUnloadCommand):
        _PREPARED_PROMPT = None
        _RUNTIME = None
        _emit_event(
            QwenTerminalEvent(
                event="done",
                request_id=command.request_id,
                chunk_count=0,
                natural_eos=True,
            )
        )
        return False

    return True


@contextlib.contextmanager
def _release_evidence_rng_scope(seed: int) -> Iterator[None]:
    """Reset all generation RNGs for one evidence request, then restore them."""

    import numpy as np
    import torch

    python_state = random.getstate()
    numpy_state = np.random.get_state()
    torch_state = torch.random.get_rng_state()
    cuda_states = torch.cuda.get_rng_state_all()
    try:
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        yield
    finally:
        random.setstate(python_state)
        np.random.set_state(numpy_state)
        torch.random.set_rng_state(torch_state)
        torch.cuda.set_rng_state_all(cuda_states)


def _load_runtime_from_environment() -> Any:
    raw_model_dir = os.environ.get(MODEL_DIR_ENV, "").strip()
    declared_revision = os.environ.get(MODEL_REVISION_ENV, MODEL_REVISION).strip()
    if not raw_model_dir or declared_revision != MODEL_REVISION:
        raise RuntimeError("exact Qwen3 model snapshot unavailable")
    model_dir = Path(raw_model_dir).resolve(strict=True)
    if not model_dir.is_dir():
        raise RuntimeError("exact Qwen3 model snapshot unavailable")
    _verify_model_manifest(model_dir)
    return load_runtime(model_dir)


def _verify_model_manifest(model_dir: Path) -> None:
    manifest_path = model_dir / MODEL_MANIFEST_FILENAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("exact Qwen3 model identity unavailable") from exc
    if not isinstance(manifest, dict) or (
        manifest.get("model_id") != MODEL_ID
        or manifest.get("model_revision") != MODEL_REVISION
        or not (model_dir / "config.json").is_file()
    ):
        raise RuntimeError("unexpected Qwen3 model identity")


def _verify_runtime_distribution() -> None:
    try:
        distribution = importlib.metadata.distribution("faster-qwen3-tts")
        installed_version = distribution.version
        direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
    except (
        importlib.metadata.PackageNotFoundError,
        AttributeError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError("unexpected Faster Qwen3-TTS runtime") from exc
    vcs_info = direct_url.get("vcs_info") if isinstance(direct_url, dict) else None
    source_url = str(direct_url.get("url", "")).rstrip("/")
    normalized_source = source_url.removesuffix(".git").lower()
    if (
        installed_version != RUNTIME_VERSION
        or normalized_source != RUNTIME_REPOSITORY.lower()
        or not isinstance(vcs_info, dict)
        or vcs_info.get("vcs") != "git"
        or vcs_info.get("commit_id") != RUNTIME_COMMIT
    ):
        raise RuntimeError("unexpected Faster Qwen3-TTS runtime")


def load_runtime(
    model_dir: Path,
    *,
    runtime_class: Any | None = None,
    torch_module: Any | None = None,
) -> Any:
    """Load the immutable CUDA runtime; imports stay worker-local for Windows spawn."""
    from app.models.gpu_runtime import require_torch_cuda_runtime

    require_torch_cuda_runtime("Qwen3-TTS 1.7B")
    if torch_module is None:
        import torch as torch_module
    if runtime_class is None:
        from faster_qwen3_tts import FasterQwen3TTS as runtime_class

    _verify_runtime_distribution()
    runtime = runtime_class.from_pretrained(
        str(model_dir),
        device="cuda",
        dtype=torch_module.bfloat16,
        attn_implementation="sdpa",
        max_seq_len=MAX_SEQUENCE_LENGTH,
        backend="torch",
    )
    _assert_runtime_cuda(runtime)
    runtime.warmup(prefill_len=WARMUP_PREFILL)
    return runtime


def _assert_runtime_cuda(runtime: Any) -> None:
    qwen_wrapper = getattr(runtime, "model", None)
    candidates = (
        runtime,
        qwen_wrapper,
        getattr(qwen_wrapper, "model", None),
    )
    for candidate in candidates:
        if candidate is None or not hasattr(candidate, "parameters"):
            continue
        try:
            parameters = iter(candidate.parameters())
        except TypeError:
            continue
        found_parameter = False
        for parameter in parameters:
            found_parameter = True
            device = getattr(parameter, "device", None)
            if str(getattr(device, "type", device)) != "cuda":
                raise RuntimeError("Qwen3-TTS runtime did not expose CUDA parameters")
        if found_parameter:
            return
    raise RuntimeError("Qwen3-TTS runtime did not expose CUDA parameters")


def prepare_voice_prompt(runtime: Any, command: QwenPrewarmCommand) -> PreparedVoicePrompt:
    import numpy as np
    import soundfile as sf

    reference_audio, sample_rate = sf.read(
        BytesIO(command.reference_audio_bytes()),
        dtype="float32",
        always_2d=False,
    )
    audio = np.asarray(reference_audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = audio.reshape(-1)
    if audio.size == 0 or not np.isfinite(audio).all() or int(sample_rate) <= 0:
        raise ValueError("invalid reference audio")
    audio = np.concatenate(
        [audio, np.zeros(round(int(sample_rate) * 0.5), dtype=np.float32)]
    )
    prompt_items = runtime.model.create_voice_clone_prompt(
        ref_audio=(audio, int(sample_rate)),
        ref_text=command.reference_transcript,
        x_vector_only_mode=False,
    )
    return PreparedVoicePrompt(
        voice_key=command.voice_key,
        reference_transcript=command.reference_transcript,
        prompt_items=prompt_items,
    )


def iter_generation_events(
    runtime: Any,
    prompt: PreparedVoicePrompt,
    command: QwenGenerateCommand,
    cancelled: threading.Event,
) -> Iterator[QwenChunkEvent | QwenTerminalEvent]:
    started_at = time.perf_counter()
    chunk_count = 0
    cumulative_seconds = 0.0
    last_steps = 0
    stream: Any | None = None
    try:
        stream = runtime.generate_voice_clone_streaming(
            text=command.text,
            language="English",
            ref_text=prompt.reference_transcript,
            voice_clone_prompt=prompt.prompt_items,
            chunk_size=CHUNK_SIZE,
            max_new_tokens=command.max_new_tokens,
            min_new_tokens=2,
            xvec_only=False,
            non_streaming_mode=True,
            append_silence=True,
            parity_mode=False,
            temperature=0.9,
            top_k=50,
            top_p=1.0,
            do_sample=True,
            repetition_penalty=1.05,
        )
        for generated in stream:
            if cancelled.is_set():
                yield _cancelled_terminal(command.request_id, chunk_count)
                return
            audio, sample_rate, timing = _split_stream_chunk(generated)
            if sample_rate != SAMPLE_RATE:
                raise ValueError("unexpected Qwen3 sample rate")
            sample_count = _sample_count(audio)
            duration_seconds = sample_count / float(sample_rate)
            if sample_count <= 0 or duration_seconds <= 0:
                raise ValueError("empty Qwen3 audio chunk")
            cumulative_seconds += duration_seconds
            if cumulative_seconds > command.hard_audio_seconds:
                yield QwenTerminalEvent(
                    event="error",
                    request_id=command.request_id,
                    chunk_count=chunk_count,
                    natural_eos=False,
                    error_code="qwen3_generation_ceiling",
                )
                return
            timing_steps = _timing_steps(timing)
            total_steps = max(last_steps + CHUNK_SIZE, timing_steps)
            if total_steps >= command.max_new_tokens:
                yield QwenTerminalEvent(
                    event="error",
                    request_id=command.request_id,
                    chunk_count=chunk_count,
                    natural_eos=False,
                    error_code="qwen3_generation_ceiling",
                )
                return
            if total_steps <= last_steps:
                raise ValueError("non-monotonic Qwen3 generation steps")
            last_steps = total_steps
            wav_bytes = _wav_bytes(audio, sample_rate)
            event = QwenChunkEvent(
                event="chunk",
                request_id=command.request_id,
                chunk_index=chunk_count,
                wav_b64=base64.b64encode(wav_bytes).decode("ascii"),
                sample_rate=SAMPLE_RATE,
                duration_ms=round(duration_seconds * 1000, 3),
                generated_at_ms=round((time.perf_counter() - started_at) * 1000, 3),
                total_steps_so_far=total_steps,
                torch_reserved_mib=_torch_reserved_mib(),
            )
            if cancelled.is_set():
                yield _cancelled_terminal(command.request_id, chunk_count)
                return
            yield event
            chunk_count += 1
        if cancelled.is_set():
            yield _cancelled_terminal(command.request_id, chunk_count)
            return
        if last_steps >= command.max_new_tokens:
            yield QwenTerminalEvent(
                event="error",
                request_id=command.request_id,
                chunk_count=chunk_count,
                natural_eos=False,
                error_code="qwen3_generation_ceiling",
            )
            return
        yield QwenTerminalEvent(
            event="done",
            request_id=command.request_id,
            chunk_count=chunk_count,
            natural_eos=True,
        )
    except Exception:
        yield QwenTerminalEvent(
            event="error",
            request_id=command.request_id,
            chunk_count=chunk_count,
            natural_eos=False,
            error_code="qwen3_generation_failed",
        )
    finally:
        close = getattr(stream, "close", None) if stream is not None else None
        if callable(close):
            close()


def _split_stream_chunk(generated: Any) -> tuple[Any, int, dict[str, Any]]:
    if not isinstance(generated, tuple) or len(generated) < 2:
        raise ValueError("malformed Qwen3 stream chunk")
    timing = generated[2] if len(generated) >= 3 and isinstance(generated[2], dict) else {}
    return generated[0], int(generated[1]), timing


def _sample_count(audio: Any) -> int:
    try:
        size = getattr(audio, "size", None)
        return int(size if size is not None else len(audio))
    except (TypeError, ValueError):
        return 0


def _timing_steps(timing: dict[str, Any]) -> int:
    for key in ("total_steps", "total_steps_so_far", "steps"):
        try:
            value = int(timing.get(key, 0))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0


def _wav_bytes(audio: Any, sample_rate: int) -> bytes:
    import numpy as np
    import soundfile as sf

    wav = np.asarray(audio, dtype=np.float32).reshape(-1)
    if (
        wav.size == 0
        or not np.isfinite(wav).all()
        or float(np.max(np.abs(wav))) <= 1e-5
    ):
        raise ValueError("invalid Qwen3 audio chunk")
    buffer = BytesIO()
    sf.write(buffer, wav, sample_rate, format="WAV")
    return buffer.getvalue()


def _cancelled_terminal(request_id: str, chunk_count: int) -> QwenTerminalEvent:
    return QwenTerminalEvent(
        event="cancelled",
        request_id=request_id,
        chunk_count=chunk_count,
        natural_eos=False,
    )


def _emit_error(request_id: str, error_code: str) -> None:
    _emit_event(
        QwenTerminalEvent(
            event="error",
            request_id=request_id,
            chunk_count=0,
            natural_eos=False,
            error_code=error_code,
        )
    )


def _emit_event(event: QwenWorkerEvent) -> None:
    line = WORKER_EVENT_PREFIX + event.model_dump_json() + "\n"
    with _EMIT_LOCK:
        sys.stdout.write(line)
        sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
