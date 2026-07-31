from __future__ import annotations

import base64
import importlib.machinery
import importlib.util
import json
import queue
import threading
import time
import wave
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError


def _protocol_module():
    from app.models import tts_qwen3_protocol

    return tts_qwen3_protocol


def _audio_b64(payload: bytes = b"RIFF-valid-wav-chunk") -> str:
    return base64.b64encode(payload).decode("ascii")


def _valid_wav_bytes(*, amplitude: int = 2048, frames: int = 7680) -> bytes:
    payload = BytesIO()
    with wave.open(payload, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        sample = int(amplitude).to_bytes(2, "little", signed=True)
        wav.writeframes(sample * frames)
    return payload.getvalue()


@pytest.mark.parametrize(
    ("payload", "model_name"),
    [
        (
            {"schema_version": 1, "op": "load", "request_id": "load-1"},
            "QwenLoadCommand",
        ),
        (
            {
                "schema_version": 1,
                "op": "prewarm",
                "request_id": "prewarm-1",
                "voice_key": "voice_0123456789abcdef",
                "reference_audio_b64": _audio_b64(),
                "reference_transcript": "The exact spoken reference.",
            },
            "QwenPrewarmCommand",
        ),
        (
            {
                "schema_version": 1,
                "op": "generate",
                "request_id": "turn-1",
                "voice_key": "voice_0123456789abcdef",
                "text": "This audio must stream.",
                "max_new_tokens": 48,
                "hard_audio_seconds": 6.0,
            },
            "QwenGenerateCommand",
        ),
        (
            {"schema_version": 1, "op": "cancel", "request_id": "turn-1"},
            "QwenCancelCommand",
        ),
        (
            {
                "schema_version": 1,
                "op": "invalidate",
                "request_id": "invalidate-1",
                "voice_key": "voice_0123456789abcdef",
            },
            "QwenInvalidateCommand",
        ),
        (
            {"schema_version": 1, "op": "unload", "request_id": "unload-1"},
            "QwenUnloadCommand",
        ),
    ],
)
def test_qwen_protocol_command_schema_is_versioned_and_discriminated(
    payload: dict[str, object], model_name: str
) -> None:
    protocol = _protocol_module()

    command = protocol.parse_command(payload)

    assert type(command).__name__ == model_name
    assert command.schema_version == 1
    assert command.request_id == payload["request_id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 2, "op": "load", "request_id": "load-1"},
        {"schema_version": 1, "op": "load", "request_id": "x" * 129},
        {"schema_version": 1, "op": "load", "request_id": "unsafe request"},
        {"schema_version": 1, "op": "unknown", "request_id": "load-1"},
        {
            "schema_version": 1,
            "op": "prewarm",
            "request_id": "prewarm-1",
            "voice_key": "voice_0123456789abcdef",
            "reference_audio_b64": "not-base64!!!",
            "reference_transcript": "Spoken words.",
        },
        {
            "schema_version": 1,
            "op": "prewarm",
            "request_id": "prewarm-1",
            "voice_key": "voice_0123456789abcdef",
            "reference_audio_b64": base64.b64encode(b"x" * 65).decode("ascii"),
            "reference_transcript": "Spoken words.",
        },
    ],
)
def test_qwen_protocol_command_schema_rejects_wrong_or_oversized_data(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    protocol = _protocol_module()
    monkeypatch.setattr(protocol, "MAX_REFERENCE_AUDIO_BYTES", 64)

    with pytest.raises(ValidationError):
        protocol.parse_command(payload)


@pytest.mark.parametrize(
    ("payload", "model_name"),
    [
        (
            {
                "schema_version": 1,
                "event": "loaded",
                "request_id": "load-1",
                "engine_id": "qwen3_1_7b",
                "runtime_version": "0.3.2",
                "model_revision": "fd4b254389122332181a7c3db7f27e918eec64e3",
                "device": "cuda",
                "sample_rate": 24000,
                "warmup_prefill": 100,
            },
            "QwenLoadedEvent",
        ),
        (
            {
                "schema_version": 1,
                "event": "prompt_ready",
                "request_id": "prewarm-1",
                "voice_key": "voice_0123456789abcdef",
            },
            "QwenPromptReadyEvent",
        ),
        (
            {
                "schema_version": 1,
                "event": "prompt_failed",
                "request_id": "prewarm-1",
                "voice_key": "voice_0123456789abcdef",
                "error_code": "qwen3_prompt_failed",
            },
            "QwenPromptFailedEvent",
        ),
        (
            {
                "schema_version": 1,
                "event": "invalidated",
                "request_id": "invalidate-1",
                "voice_key": "voice_0123456789abcdef",
            },
            "QwenInvalidatedEvent",
        ),
        (
            {
                "schema_version": 1,
                "event": "chunk",
                "request_id": "turn-1",
                "chunk_index": 0,
                "wav_b64": _audio_b64(),
                "sample_rate": 24000,
                "duration_ms": 320.0,
                "generated_at_ms": 369.0,
                "total_steps_so_far": 4,
            },
            "QwenChunkEvent",
        ),
        (
            {
                "schema_version": 1,
                "event": "done",
                "request_id": "turn-1",
                "chunk_count": 1,
                "natural_eos": True,
            },
            "QwenTerminalEvent",
        ),
    ],
)
def test_qwen_protocol_event_schema_is_versioned_and_bounded(
    payload: dict[str, object], model_name: str
) -> None:
    protocol = _protocol_module()

    event = protocol.parse_event(payload)

    assert type(event).__name__ == model_name
    assert event.schema_version == 1


@pytest.mark.parametrize(
    "payload",
    [
        {
            "schema_version": 2,
            "event": "chunk",
            "request_id": "turn-1",
            "chunk_index": 0,
            "wav_b64": _audio_b64(),
            "sample_rate": 24000,
            "duration_ms": 320.0,
            "generated_at_ms": 369.0,
            "total_steps_so_far": 4,
        },
        {
            "schema_version": 1,
            "event": "chunk",
            "request_id": "turn-1",
            "chunk_index": 0,
            "wav_b64": "%%%%",
            "sample_rate": 24000,
            "duration_ms": 320.0,
            "generated_at_ms": 369.0,
            "total_steps_so_far": 4,
        },
        {
            "schema_version": 1,
            "event": "chunk",
            "request_id": "turn-1",
            "chunk_index": 0,
            "wav_b64": _audio_b64(),
            "sample_rate": 48000,
            "duration_ms": 320.0,
            "generated_at_ms": 369.0,
            "total_steps_so_far": 4,
        },
        {
            "schema_version": 1,
            "event": "error",
            "request_id": "turn-1",
            "chunk_count": 0,
            "natural_eos": True,
            "error_code": "qwen3_worker_failed",
        },
    ],
)
def test_qwen_protocol_event_schema_rejects_malformed_data(payload: dict[str, object]) -> None:
    protocol = _protocol_module()

    with pytest.raises(ValidationError):
        protocol.parse_event(payload)


def test_qwen_event_sequence_rejects_wrong_request_non_monotonic_and_late_events() -> None:
    protocol = _protocol_module()
    state = protocol.QwenStreamEventValidator(request_id="turn-1")
    first = protocol.parse_event(
        {
            "schema_version": 1,
            "event": "chunk",
            "request_id": "turn-1",
            "chunk_index": 0,
            "wav_b64": _audio_b64(),
            "sample_rate": 24000,
            "duration_ms": 320.0,
            "generated_at_ms": 400.0,
            "total_steps_so_far": 4,
        }
    )
    state.accept(first)

    for bad_payload in (
        {
            "schema_version": 1,
            "event": "chunk",
            "request_id": "other-turn",
            "chunk_index": 1,
            "wav_b64": _audio_b64(),
            "sample_rate": 24000,
            "duration_ms": 320.0,
            "generated_at_ms": 700.0,
            "total_steps_so_far": 8,
        },
        {
            "schema_version": 1,
            "event": "chunk",
            "request_id": "turn-1",
            "chunk_index": 0,
            "wav_b64": _audio_b64(),
            "sample_rate": 24000,
            "duration_ms": 320.0,
            "generated_at_ms": 300.0,
            "total_steps_so_far": 4,
        },
    ):
        with pytest.raises(protocol.QwenProtocolError):
            state.accept(protocol.parse_event(bad_payload))

    terminal = protocol.parse_event(
        {
            "schema_version": 1,
            "event": "done",
            "request_id": "turn-1",
            "chunk_count": 1,
            "natural_eos": True,
        }
    )
    state.accept(terminal)
    assert state.terminal is terminal

    with pytest.raises(protocol.QwenProtocolError):
        state.accept(terminal)
    with pytest.raises(protocol.QwenProtocolError):
        state.accept(first)


def test_qwen_invalidate_acknowledgement_contains_only_opaque_identity() -> None:
    protocol = _protocol_module()

    event = protocol.parse_event(
        {
            "schema_version": 1,
            "event": "invalidated",
            "request_id": "invalidate-1",
            "voice_key": "voice_0123456789abcdef",
            "matched": True,
        }
    )

    dumped = event.model_dump()
    assert dumped["voice_key"] == "voice_0123456789abcdef"
    assert dumped["matched"] is True
    assert "reference_audio" not in dumped
    assert "reference_transcript" not in dumped
    assert "model_path" not in dumped


class ScriptedQwenWorkerProcess:
    def __init__(
        self,
        *,
        hang_generate: bool = False,
        acknowledge_cancel: bool = True,
        generate_mutation: str | None = None,
    ) -> None:
        self.returncode: int | None = None
        self.ops: list[dict[str, Any]] = []
        self.stdout = self.ScriptedStdout()
        self.stdin = self.ScriptedStdin(self)
        self.hang_generate = hang_generate
        self.acknowledge_cancel = acknowledge_cancel
        self.generate_mutation = generate_mutation
        self.prepared_prompt_key: str | None = None
        self.terminated = False
        self.killed = False

    class ScriptedStdout:
        def __init__(self) -> None:
            self.lines: queue.Queue[str | None] = queue.Queue()

        def __iter__(self):
            return self

        def __next__(self) -> str:
            line = self.lines.get()
            if line is None:
                raise StopIteration
            return line

    class ScriptedStdin:
        def __init__(self, process: "ScriptedQwenWorkerProcess") -> None:
            self.process = process
            self.closed = False

        def write(self, line: str) -> int:
            qwen = _qwen_module()
            assert line.startswith(qwen.WORKER_EVENT_PREFIX)
            payload = json.loads(line[len(qwen.WORKER_EVENT_PREFIX) :])
            self.process.ops.append(payload)
            request_id = payload["request_id"]
            if payload["op"] == "load":
                self.process.emit(
                    {
                        "schema_version": 1,
                        "event": "loaded",
                        "request_id": request_id,
                        "engine_id": "qwen3_1_7b",
                        "runtime_version": "0.3.2",
                        "model_revision": "fd4b254389122332181a7c3db7f27e918eec64e3",
                        "device": "cuda",
                        "sample_rate": 24000,
                        "warmup_prefill": 100,
                    }
                )
            elif payload["op"] == "prewarm":
                self.process.prepared_prompt_key = payload["voice_key"]
                self.process.emit(
                    {
                        "schema_version": 1,
                        "event": "prompt_ready",
                        "request_id": request_id,
                        "voice_key": payload["voice_key"],
                    }
                )
            elif payload["op"] == "generate":
                if self.process.generate_mutation == "wrong_request":
                    self.process.emit(
                        {
                            "schema_version": 1,
                            "event": "chunk",
                            "request_id": "wrong-turn",
                            "chunk_index": 0,
                            "wav_b64": _audio_b64(_valid_wav_bytes()),
                            "sample_rate": 24000,
                            "duration_ms": 320.0,
                            "generated_at_ms": 370.0,
                            "total_steps_so_far": 4,
                        }
                    )
                elif not self.process.hang_generate:
                    for index in range(2):
                        wav_bytes = _valid_wav_bytes()
                        if self.process.generate_mutation == "non_wav":
                            wav_bytes = b"not-a-wav"
                        elif self.process.generate_mutation == "silent":
                            wav_bytes = _valid_wav_bytes(amplitude=0)
                        self.process.emit(
                            {
                                "schema_version": 1,
                                "event": "chunk",
                                "request_id": request_id,
                                "chunk_index": index,
                                "wav_b64": _audio_b64(wav_bytes),
                                "sample_rate": 24000,
                                "duration_ms": (
                                    120.0
                                    if self.process.generate_mutation == "duration_mismatch"
                                    else 320.0
                                ),
                                "generated_at_ms": 370.0 + 320.0 * index,
                                "total_steps_so_far": 4 * (index + 1),
                            }
                        )
                    self.process.emit(
                        {
                            "schema_version": 1,
                            "event": (
                                "error"
                                if self.process.generate_mutation == "ceiling"
                                else "done"
                            ),
                            "request_id": request_id,
                            "chunk_count": 2,
                            "natural_eos": self.process.generate_mutation != "ceiling",
                            **(
                                {"error_code": "qwen3_generation_ceiling"}
                                if self.process.generate_mutation == "ceiling"
                                else {}
                            ),
                        }
                    )
            elif payload["op"] == "cancel" and self.process.acknowledge_cancel:
                self.process.emit(
                    {
                        "schema_version": 1,
                        "event": "cancelled",
                        "request_id": request_id,
                        "chunk_count": 0,
                        "natural_eos": False,
                    }
                )
            elif payload["op"] == "invalidate":
                matched = self.process.prepared_prompt_key == payload["voice_key"]
                if matched:
                    self.process.prepared_prompt_key = None
                self.process.emit(
                    {
                        "schema_version": 1,
                        "event": "invalidated",
                        "request_id": request_id,
                        "voice_key": payload["voice_key"],
                        "matched": matched,
                    }
                )
            elif payload["op"] == "unload":
                self.process.emit(
                    {
                        "schema_version": 1,
                        "event": "done",
                        "request_id": request_id,
                        "chunk_count": 0,
                        "natural_eos": True,
                    }
                )
            return len(line)

        def flush(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    def emit(self, payload: dict[str, Any]) -> None:
        qwen = _qwen_module()
        self.stdout.lines.put(
            qwen.WORKER_EVENT_PREFIX + json.dumps(payload, separators=(",", ":")) + "\n"
        )

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15
        self.stdout.lines.put(None)

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self.stdout.lines.put(None)

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = self.returncode if self.returncode is not None else 0
        return self.returncode


def _qwen_module():
    from app.models import tts_qwen3

    return tts_qwen3


def _request():
    from app.models.tts_registry import TtsSynthesisInput

    return TtsSynthesisInput(
        text="RayMe must pull native chunks without collecting them.",
        reference_audio=b"RIFF-reference",
        reference_audio_content_type="audio/wav",
        reference_transcript="The exact spoken reference.",
    )


@pytest.fixture
def qwen_runtime_available(monkeypatch: pytest.MonkeyPatch) -> None:
    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: Any, **kwargs: Any):
        if name == "faster_qwen3_tts":
            return importlib.machinery.ModuleSpec(name, loader=None)
        return original_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)


def test_qwen_adapter_owns_spawned_load_prewarm_stream_invalidate_unload_lifecycle(
    qwen_runtime_available: None,
) -> None:
    qwen = _qwen_module()
    process = ScriptedQwenWorkerProcess()
    adapter = qwen.Qwen3TtsAdapter(process_factory=lambda *_args, **_kwargs: process)

    adapter.load()
    ready = adapter.prewarm(
        voice_key="voice_0123456789abcdef",
        reference_audio=b"RIFF-reference",
        reference_transcript="The exact spoken reference.",
    )
    chunks = list(adapter.stream(_request(), request_id="turn-1"))
    adapter.invalidate("voice_0123456789abcdef")
    adapter.unload()

    assert adapter.engine_id == "qwen3_1_7b"
    assert adapter.required_modules == ("faster_qwen3_tts",)
    assert ready.voice_key == "voice_0123456789abcdef"
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert [chunk.sample_rate for chunk in chunks] == [24000, 24000]
    assert [payload["op"] for payload in process.ops] == [
        "load",
        "prewarm",
        "generate",
        "invalidate",
        "unload",
    ]
    generate = process.ops[2]
    assert generate["voice_key"] == qwen.qwen_prompt_cache_key(
        b"RIFF-reference",
        "The exact spoken reference.",
    )
    assert generate["max_new_tokens"] <= 384
    assert generate["hard_audio_seconds"] <= 32.0
    assert "reference_audio_b64" not in generate
    assert "reference_transcript" not in generate
    # Unload is process ownership cleanup, not just a logical model flag.
    assert process.terminated is True


def test_qwen_worker_invalidate_drops_matching_prompt_tensors_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import tts_qwen3_worker as worker
    from app.models.tts_qwen3_protocol import QwenInvalidateCommand

    tensor_sentinel = object()
    prompt = worker.PreparedVoicePrompt(
        voice_key="prompt_" + "a" * 64,
        reference_transcript="Private prompt text stays worker-local.",
        prompt_items=[tensor_sentinel],
    )
    emitted: list[Any] = []
    monkeypatch.setattr(worker, "_PREPARED_PROMPT", prompt)
    monkeypatch.setattr(worker, "_emit_event", emitted.append)

    command = QwenInvalidateCommand(
        op="invalidate",
        request_id="invalidate-matching",
        voice_key=prompt.voice_key,
    )
    assert worker._dispatch(command) is True
    assert worker._PREPARED_PROMPT is None
    assert emitted[-1].matched is True

    assert worker._dispatch(command.model_copy(update={"request_id": "invalidate-again"})) is True
    assert worker._PREPARED_PROMPT is None
    assert emitted[-1].matched is False
    assert "prompt_items" not in emitted[-1].model_dump()


def test_qwen_worker_invalidate_unrelated_key_preserves_selected_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import tts_qwen3_worker as worker
    from app.models.tts_qwen3_protocol import QwenInvalidateCommand

    prompt = worker.PreparedVoicePrompt(
        voice_key="prompt_" + "b" * 64,
        reference_transcript="Selected prompt remains usable.",
        prompt_items=[object()],
    )
    emitted: list[Any] = []
    monkeypatch.setattr(worker, "_PREPARED_PROMPT", prompt)
    monkeypatch.setattr(worker, "_emit_event", emitted.append)

    worker._dispatch(
        QwenInvalidateCommand(
            op="invalidate",
            request_id="invalidate-unrelated",
            voice_key="prompt_" + "c" * 64,
        )
    )

    assert worker._PREPARED_PROMPT is prompt
    assert worker._PREPARED_PROMPT.prompt_items
    assert emitted[-1].matched is False


def test_qwen_adapter_invalidate_matches_owner_only_and_allows_later_voice(
    qwen_runtime_available: None,
) -> None:
    qwen = _qwen_module()
    process = ScriptedQwenWorkerProcess()
    adapter = qwen.Qwen3TtsAdapter(process_factory=lambda *_args, **_kwargs: process)
    first_owner = "a" * 64
    unrelated_owner = "b" * 64

    adapter.load()
    adapter.prewarm(
        voice_key=first_owner,
        reference_audio=_valid_wav_bytes(),
        reference_transcript="The first exact reference.",
    )

    unrelated = adapter.invalidate(unrelated_owner)
    assert unrelated.matched is False
    assert unrelated.active_cancelled is False
    assert adapter.selected_voice_key == first_owner
    assert [chunk.chunk_index for chunk in adapter.stream(
        _request(), request_id="turn-first", voice_key=first_owner
    )] == [0, 1]

    matching = adapter.invalidate(first_owner)
    assert matching.matched is True
    assert matching.active_cancelled is False
    assert adapter.selected_voice_key is None
    assert process.prepared_prompt_key is None

    repeated = adapter.invalidate(first_owner)
    assert repeated.matched is False
    assert repeated.active_cancelled is False

    adapter.prewarm(
        voice_key=unrelated_owner,
        reference_audio=_valid_wav_bytes(amplitude=1024),
        reference_transcript="The second exact reference.",
    )
    assert [chunk.chunk_index for chunk in adapter.stream(
        _request(), request_id="turn-second", voice_key=unrelated_owner
    )] == [0, 1]


def test_qwen_adapter_invalidate_cancels_active_owner_before_prompt_eviction(
    qwen_runtime_available: None,
) -> None:
    qwen = _qwen_module()
    process = ScriptedQwenWorkerProcess(hang_generate=True)
    adapter = qwen.Qwen3TtsAdapter(process_factory=lambda *_args, **_kwargs: process)
    owner_key = "d" * 64
    adapter.load()
    adapter.prewarm(
        voice_key=owner_key,
        reference_audio=_valid_wav_bytes(),
        reference_transcript="The exact active reference.",
    )
    produced: list[object] = []
    producer = threading.Thread(
        target=lambda: produced.extend(
            adapter.stream(_request(), request_id="turn-delete", voice_key=owner_key)
        ),
        daemon=True,
    )
    producer.start()
    deadline = time.monotonic() + 1.0
    while not any(payload["op"] == "generate" for payload in process.ops):
        assert time.monotonic() < deadline
        time.sleep(0.001)

    result = adapter.invalidate(owner_key)
    producer.join(timeout=1.0)

    assert producer.is_alive() is False
    assert produced == []
    assert result.matched is True
    assert result.active_cancelled is True
    assert [payload["op"] for payload in process.ops][-2:] == ["cancel", "invalidate"]
    assert process.prepared_prompt_key is None


def test_qwen_prompt_invalidate_api_accepts_only_opaque_owner_key() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    class RecordingManager:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def startup(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

        async def invalidate_tts_prompt(self, engine_id: str, voice_key: str) -> dict[str, Any]:
            self.calls.append((engine_id, voice_key))
            return {
                "engine_id": engine_id,
                "voice_key": voice_key,
                "status": "invalidated",
                "matched": True,
                "active_cancelled": False,
            }

    app = create_app()
    manager = RecordingManager()
    app.state.model_manager = manager
    owner_key = "e" * 64

    with TestClient(app) as client:
        response = client.post(
            "/tts/qwen3/prompts/invalidate",
            json={"engine_id": "qwen3_1_7b", "voice_key": owner_key},
        )
        invalid = client.post(
            "/tts/qwen3/prompts/invalidate",
            json={"engine_id": "qwen3_1_7b", "voice_key": "private-path"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "engine_id": "qwen3_1_7b",
        "voice_key": owner_key,
        "status": "invalidated",
        "matched": True,
        "active_cancelled": False,
    }
    assert manager.calls == [("qwen3_1_7b", owner_key)]
    assert invalid.status_code == 422
    serialized = json.dumps(invalid.json())
    assert "private-path" not in serialized
    assert "Traceback" not in serialized


def test_qwen_adapter_spawn_imports_no_cuda_runtime_in_parent(
    monkeypatch: pytest.MonkeyPatch, qwen_runtime_available: None
) -> None:
    qwen = _qwen_module()
    captured: list[tuple[list[str], dict[str, Any]]] = []

    def process_factory(args: list[str], **kwargs: Any) -> ScriptedQwenWorkerProcess:
        captured.append((args, kwargs))
        return ScriptedQwenWorkerProcess()

    adapter = qwen.Qwen3TtsAdapter(process_factory=process_factory)
    adapter.load()

    assert captured[0][0][-2:] == ["-m", "app.models.tts_qwen3_worker"]
    source = Path(qwen.__file__).read_text(encoding="utf-8")
    assert "import torch" not in source
    assert "from faster_qwen3_tts" not in source


def test_qwen_adapter_uses_console_python_for_ipc_when_backend_runs_pythonw(
    monkeypatch: pytest.MonkeyPatch,
    qwen_runtime_available: None,
    tmp_path: Path,
) -> None:
    qwen = _qwen_module()
    pythonw = tmp_path / "pythonw.exe"
    console_python = tmp_path / "python.exe"
    pythonw.touch()
    console_python.touch()
    monkeypatch.setattr(qwen.sys, "executable", str(pythonw))
    captured: list[list[str]] = []

    def process_factory(args: list[str], **_kwargs: Any) -> ScriptedQwenWorkerProcess:
        captured.append(args)
        return ScriptedQwenWorkerProcess()

    adapter = qwen.Qwen3TtsAdapter(process_factory=process_factory)
    adapter.load()
    adapter.unload()

    assert captured[0][0] == str(console_python)


def test_qwen_adapter_rejects_wrong_request_worker_event_and_contains_process(
    qwen_runtime_available: None,
) -> None:
    qwen = _qwen_module()
    process = ScriptedQwenWorkerProcess(generate_mutation="wrong_request")
    adapter = qwen.Qwen3TtsAdapter(process_factory=lambda *_args, **_kwargs: process)
    adapter.load()
    adapter.prewarm(
        voice_key="voice_0123456789abcdef",
        reference_audio=b"RIFF-reference",
        reference_transcript="The exact spoken reference.",
    )

    with pytest.raises(qwen.Qwen3WorkerProtocolError):
        list(adapter.stream(_request(), request_id="turn-1"))

    assert process.terminated is True


@pytest.mark.parametrize("mutation", ["non_wav", "silent", "duration_mismatch"])
def test_qwen_adapter_rejects_malformed_or_silent_worker_audio_and_contains_process(
    mutation: str,
    qwen_runtime_available: None,
) -> None:
    qwen = _qwen_module()
    process = ScriptedQwenWorkerProcess(generate_mutation=mutation)
    adapter = qwen.Qwen3TtsAdapter(process_factory=lambda *_args, **_kwargs: process)
    adapter.load()
    adapter.prewarm(
        voice_key="voice_0123456789abcdef",
        reference_audio=b"RIFF-reference",
        reference_transcript="The exact spoken reference.",
    )

    with pytest.raises(qwen.Qwen3WorkerProtocolError) as raised:
        list(adapter.stream(_request(), request_id=f"turn-{mutation}"))

    assert raised.value.code == "qwen3_worker_protocol"
    assert process.terminated is True


def test_qwen_adapter_exposes_ceiling_as_request_failure_without_poisoning_worker(
    qwen_runtime_available: None,
) -> None:
    qwen = _qwen_module()
    process = ScriptedQwenWorkerProcess(generate_mutation="ceiling")
    adapter = qwen.Qwen3TtsAdapter(process_factory=lambda *_args, **_kwargs: process)
    adapter.load()
    adapter.prewarm(
        voice_key="voice_0123456789abcdef",
        reference_audio=_valid_wav_bytes(),
        reference_transcript="The exact spoken reference.",
    )

    with pytest.raises(qwen.Qwen3GenerationCeilingError) as raised:
        list(adapter.stream(_request(), request_id="turn-ceiling"))

    assert raised.value.code == "qwen3_generation_ceiling"
    assert raised.value.marks_engine_unavailable is False
    assert adapter.loaded is True
    assert process.terminated is False


def test_qwen_adapter_protocol_failure_drops_prompt_and_allows_clean_worker_reload(
    qwen_runtime_available: None,
) -> None:
    qwen = _qwen_module()
    failed_process = ScriptedQwenWorkerProcess(generate_mutation="wrong_request")
    recovered_process = ScriptedQwenWorkerProcess()
    processes = iter((failed_process, recovered_process))
    adapter = qwen.Qwen3TtsAdapter(
        process_factory=lambda *_args, **_kwargs: next(processes)
    )
    adapter.load()
    adapter.prewarm(
        voice_key="voice_0123456789abcdef",
        reference_audio=_valid_wav_bytes(),
        reference_transcript="The exact spoken reference.",
    )

    with pytest.raises(qwen.Qwen3WorkerProtocolError):
        list(adapter.stream(_request(), request_id="turn-failed"))

    assert adapter.loaded is False
    assert adapter.selected_voice_key is None
    adapter.load()
    adapter.prewarm(
        voice_key="voice_recovered",
        reference_audio=_valid_wav_bytes(amplitude=1024),
        reference_transcript="A new exact spoken reference.",
    )
    chunks = list(
        adapter.stream(_request(), request_id="turn-recovered", voice_key="voice_recovered")
    )

    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert recovered_process.terminated is False


def test_qwen_prompt_cache_key_is_content_bound_but_uses_comparison_normalization() -> None:
    qwen = _qwen_module()
    reference = _valid_wav_bytes()

    canonical = qwen.qwen_prompt_cache_key(reference, "Hello, MARIA!")

    assert canonical == qwen.qwen_prompt_cache_key(reference, "hello maria")
    assert canonical == qwen.qwen_prompt_cache_key(reference, "Héllo María.")
    assert canonical != qwen.qwen_prompt_cache_key(reference + b"changed", "hello maria")
    assert canonical.startswith("prompt_")
    assert len(canonical) == len("prompt_") + 64


def test_qwen_adapter_binds_worker_prompt_to_content_identity_but_preserves_exact_icl_text(
    qwen_runtime_available: None,
) -> None:
    qwen = _qwen_module()
    process = ScriptedQwenWorkerProcess()
    adapter = qwen.Qwen3TtsAdapter(process_factory=lambda *_args, **_kwargs: process)
    reference = _valid_wav_bytes()
    exact_transcript = "  The exact approved transcript.  "

    adapter.load()
    adapter.prewarm(
        voice_key="voice_0123456789abcdef",
        reference_audio=reference,
        reference_transcript=exact_transcript,
    )
    list(adapter.stream(_request(), request_id="turn-content-bound"))

    prompt_key = qwen.qwen_prompt_cache_key(reference, exact_transcript)
    prewarm = next(payload for payload in process.ops if payload["op"] == "prewarm")
    generate = next(payload for payload in process.ops if payload["op"] == "generate")
    assert adapter.selected_voice_key == "voice_0123456789abcdef"
    assert prewarm["voice_key"] == prompt_key
    assert prewarm["reference_transcript"] == exact_transcript
    assert generate["voice_key"] == prompt_key


def test_qwen_prompt_failure_is_correctable_and_does_not_retain_prompt_identity(
    qwen_runtime_available: None,
) -> None:
    qwen = _qwen_module()

    class PromptFailingProcess(ScriptedQwenWorkerProcess):
        class ScriptedStdin(ScriptedQwenWorkerProcess.ScriptedStdin):
            def write(self, line: str) -> int:
                qwen_module = _qwen_module()
                payload = json.loads(line[len(qwen_module.WORKER_EVENT_PREFIX) :])
                if payload["op"] != "prewarm":
                    return super().write(line)
                self.process.ops.append(payload)
                self.process.emit(
                    {
                        "schema_version": 1,
                        "event": "prompt_failed",
                        "request_id": payload["request_id"],
                        "voice_key": payload["voice_key"],
                        "error_code": "qwen3_prompt_failed",
                    }
                )
                return len(line)

    process = PromptFailingProcess()
    adapter = qwen.Qwen3TtsAdapter(process_factory=lambda *_args, **_kwargs: process)
    adapter.load()

    with pytest.raises(qwen.Qwen3PromptError) as raised:
        adapter.prewarm(
            voice_key="voice_0123456789abcdef",
            reference_audio=_valid_wav_bytes(),
            reference_transcript="The exact spoken reference.",
        )

    assert raised.value.code == "qwen3_prompt_failed"
    assert raised.value.marks_engine_unavailable is False
    assert adapter.loaded is True
    assert adapter.selected_voice_key is None


def test_qwen_adapter_cancel_is_request_scoped_and_stream_drains_cancelled_terminal(
    qwen_runtime_available: None,
) -> None:
    qwen = _qwen_module()
    process = ScriptedQwenWorkerProcess(hang_generate=True)
    adapter = qwen.Qwen3TtsAdapter(process_factory=lambda *_args, **_kwargs: process)
    adapter.load()
    adapter.prewarm(
        voice_key="voice_0123456789abcdef",
        reference_audio=b"RIFF-reference",
        reference_transcript="The exact spoken reference.",
    )
    result: list[object] = []

    producer = threading.Thread(
        target=lambda: result.extend(adapter.stream(_request(), request_id="turn-1")),
        daemon=True,
    )
    producer.start()
    deadline = time.monotonic() + 1.0
    while not any(payload["op"] == "generate" for payload in process.ops):
        assert time.monotonic() < deadline
        time.sleep(0.001)

    assert adapter.cancel("turn-1") is True
    producer.join(timeout=1.0)

    assert producer.is_alive() is False
    assert result == []
    assert process.ops[-1] == {
        "schema_version": 1,
        "op": "cancel",
        "request_id": "turn-1",
    }
    assert process.terminated is False


def test_qwen_adapter_cancel_timeout_terminates_stuck_worker(
    monkeypatch: pytest.MonkeyPatch, qwen_runtime_available: None
) -> None:
    qwen = _qwen_module()
    process = ScriptedQwenWorkerProcess(hang_generate=True, acknowledge_cancel=False)
    monkeypatch.setattr(qwen, "WORKER_CANCEL_TIMEOUT_SECONDS", 0.01)
    adapter = qwen.Qwen3TtsAdapter(process_factory=lambda *_args, **_kwargs: process)
    adapter.load()
    adapter.prewarm(
        voice_key="voice_0123456789abcdef",
        reference_audio=b"RIFF-reference",
        reference_transcript="The exact spoken reference.",
    )

    producer_errors: list[Exception] = []

    def consume_stuck_stream() -> None:
        try:
            list(adapter.stream(_request(), request_id="turn-1"))
        except Exception as exc:  # the forced process stop must unblock the reader
            producer_errors.append(exc)

    producer = threading.Thread(target=consume_stuck_stream, daemon=True)
    producer.start()
    deadline = time.monotonic() + 1.0
    while not any(payload["op"] == "generate" for payload in process.ops):
        assert time.monotonic() < deadline
        time.sleep(0.001)

    assert adapter.cancel("turn-1") is False

    assert process.terminated is True
    producer.join(timeout=1.0)
    assert producer.is_alive() is False
    assert len(producer_errors) == 1
    assert isinstance(producer_errors[0], qwen.Qwen3WorkerError)


class ScriptedNativeRuntime:
    def __init__(self) -> None:
        self.streaming_calls: list[dict[str, Any]] = []

    def generate_voice_clone_streaming(self, **kwargs: Any):
        self.streaming_calls.append(kwargs)
        yield ([0.1] * 7680, 24000, {"total_steps": 4})
        yield ([0.1] * 7680, 24000, {"total_steps": 8})


def test_qwen_worker_loads_only_exact_cuda_torch_runtime_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.models import gpu_runtime
    from app.models import tts_qwen3_worker as worker

    calls: list[tuple[str, dict[str, Any]]] = []
    warmups: list[int] = []

    class Parameter:
        device = type("Device", (), {"type": "cuda"})()

    class Runtime:
        def parameters(self):
            yield Parameter()

        def warmup(self, *, prefill_len: int) -> None:
            warmups.append(prefill_len)

    class RuntimeClass:
        @classmethod
        def from_pretrained(cls, model_path: str, **kwargs: Any) -> Runtime:
            calls.append((model_path, kwargs))
            return Runtime()

    fake_torch = type("FakeTorch", (), {"bfloat16": object()})()
    cuda_guards: list[str] = []
    monkeypatch.setattr(
        gpu_runtime,
        "require_torch_cuda_runtime",
        lambda component: cuda_guards.append(component),
    )
    monkeypatch.setattr(worker.importlib.metadata, "version", lambda _name: "0.3.2")

    runtime = worker.load_runtime(
        tmp_path,
        runtime_class=RuntimeClass,
        torch_module=fake_torch,
    )

    assert isinstance(runtime, Runtime)
    assert cuda_guards == ["Qwen3-TTS 1.7B"]
    assert calls == [
        (
            str(tmp_path),
            {
                "device": "cuda",
                "dtype": fake_torch.bfloat16,
                "attn_implementation": "sdpa",
                "max_seq_len": 2048,
                "backend": "torch",
            },
        )
    ]
    assert warmups == [100]


def test_qwen_worker_accepts_cuda_parameters_at_pinned_wrapper_model_depth() -> None:
    from app.models import tts_qwen3_worker as worker

    class Parameter:
        device = type("Device", (), {"type": "cuda"})()

    class NativeModel:
        def parameters(self):
            yield Parameter()

    runtime = type(
        "PinnedFasterQwenRuntime",
        (),
        {"model": type("QwenWrapper", (), {"model": NativeModel()})()},
    )()

    worker._assert_runtime_cuda(runtime)


def test_qwen_worker_rejects_non_cuda_parameter_at_pinned_wrapper_model_depth() -> None:
    from app.models import tts_qwen3_worker as worker

    class Parameter:
        device = type("Device", (), {"type": "cpu"})()

    class NativeModel:
        def parameters(self):
            yield Parameter()

    runtime = type(
        "PinnedFasterQwenRuntime",
        (),
        {"model": type("QwenWrapper", (), {"model": NativeModel()})()},
    )()

    with pytest.raises(RuntimeError, match="did not expose CUDA parameters"):
        worker._assert_runtime_cuda(runtime)


def test_qwen_worker_prewarm_builds_one_full_icl_prompt_from_exact_reference() -> None:
    from app.models import tts_qwen3_worker as worker

    reference = BytesIO()
    with wave.open(reference, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes((b"\x00\x01" * 2400))
    prompt_calls: list[dict[str, Any]] = []

    class PromptModel:
        def create_voice_clone_prompt(self, **kwargs: Any) -> list[str]:
            prompt_calls.append(kwargs)
            return ["gpu-prompt-stays-worker-local"]

    runtime = type("Runtime", (), {"model": PromptModel()})()
    command = _protocol_module().parse_command(
        {
            "schema_version": 1,
            "op": "prewarm",
            "request_id": "prewarm-1",
            "voice_key": "voice_0123456789abcdef",
            "reference_audio_b64": base64.b64encode(reference.getvalue()).decode("ascii"),
            "reference_transcript": "The exact spoken reference.",
        }
    )

    prompt = worker.prepare_voice_prompt(runtime, command)

    assert prompt.voice_key == command.voice_key
    assert prompt.reference_transcript == "The exact spoken reference."
    assert prompt.prompt_items == ["gpu-prompt-stays-worker-local"]
    assert prompt_calls[0]["ref_text"] == "The exact spoken reference."
    assert prompt_calls[0]["x_vector_only_mode"] is False
    audio, sample_rate = prompt_calls[0]["ref_audio"]
    assert sample_rate == 24000
    assert len(audio) == 2400 + 12000


def test_qwen_worker_passes_approved_transcript_to_icl_without_rewriting() -> None:
    from app.models import tts_qwen3_worker as worker

    reference = BytesIO()
    with wave.open(reference, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes((b"\x00\x01" * 2400))
    exact_transcript = "  The exact approved transcript.  "
    prompt_calls: list[dict[str, Any]] = []

    class PromptModel:
        def create_voice_clone_prompt(self, **kwargs: Any) -> list[str]:
            prompt_calls.append(kwargs)
            return ["gpu-prompt-stays-worker-local"]

    runtime = type("Runtime", (), {"model": PromptModel()})()
    command = _protocol_module().parse_command(
        {
            "schema_version": 1,
            "op": "prewarm",
            "request_id": "prewarm-exact",
            "voice_key": "prompt_" + "a" * 64,
            "reference_audio_b64": base64.b64encode(reference.getvalue()).decode("ascii"),
            "reference_transcript": exact_transcript,
        }
    )

    prompt = worker.prepare_voice_prompt(runtime, command)

    assert prompt.reference_transcript == exact_transcript
    assert prompt_calls[0]["ref_text"] == exact_transcript


def test_qwen_worker_pulls_only_native_full_icl_stream_with_locked_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import tts_qwen3_worker as worker

    runtime = ScriptedNativeRuntime()
    prompt = worker.PreparedVoicePrompt(
        voice_key="voice_0123456789abcdef",
        reference_transcript="The exact spoken reference.",
        prompt_items=[object()],
    )
    command = _protocol_module().parse_command(
        {
            "schema_version": 1,
            "op": "generate",
            "request_id": "turn-1",
            "voice_key": prompt.voice_key,
            "text": "The native stream stays live.",
            "max_new_tokens": 48,
            "hard_audio_seconds": 6.0,
        }
    )
    monkeypatch.setattr(
        worker,
        "_wav_bytes",
        lambda _audio, _sample_rate: b"RIFF-native-chunk",
    )

    events = list(worker.iter_generation_events(runtime, prompt, command, threading.Event()))

    assert [event.event for event in events] == ["chunk", "chunk", "done"]
    call = runtime.streaming_calls[0]
    assert call["voice_clone_prompt"] is prompt.prompt_items
    assert call["ref_text"] == prompt.reference_transcript
    assert call["chunk_size"] == 4
    assert call["xvec_only"] is False
    assert call["non_streaming_mode"] is True
    assert call["append_silence"] is True
    assert call["parity_mode"] is False
    assert call["max_new_tokens"] == 48
    assert not hasattr(runtime, "generate_voice_clone")
    assert not hasattr(runtime, "generate")


def test_qwen_worker_cancel_closes_native_generator_and_emits_one_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import tts_qwen3_worker as worker

    runtime = ScriptedNativeRuntime()
    prompt = worker.PreparedVoicePrompt(
        voice_key="voice_0123456789abcdef",
        reference_transcript="The exact spoken reference.",
        prompt_items=[object()],
    )
    command = _protocol_module().parse_command(
        {
            "schema_version": 1,
            "op": "generate",
            "request_id": "turn-1",
            "voice_key": prompt.voice_key,
            "text": "Cancel this stream.",
            "max_new_tokens": 48,
            "hard_audio_seconds": 6.0,
        }
    )
    cancelled = threading.Event()
    monkeypatch.setattr(
        worker,
        "_wav_bytes",
        lambda _audio, _sample_rate: b"RIFF-native-chunk",
    )
    iterator = worker.iter_generation_events(runtime, prompt, command, cancelled)

    assert next(iterator).event == "chunk"
    cancelled.set()
    remaining = list(iterator)

    assert [event.event for event in remaining] == ["cancelled"]


def test_qwen_worker_preserves_cancel_that_arrives_before_generate_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import tts_qwen3_worker as worker

    runtime = ScriptedNativeRuntime()
    prompt = worker.PreparedVoicePrompt(
        voice_key="voice_0123456789abcdef",
        reference_transcript="The exact spoken reference.",
        prompt_items=[object()],
    )
    command = _protocol_module().parse_command(
        {
            "schema_version": 1,
            "op": "generate",
            "request_id": "turn-before-first-audio",
            "voice_key": prompt.voice_key,
            "text": "This request is cancelled before dispatch.",
            "max_new_tokens": 48,
            "hard_audio_seconds": 6.0,
        }
    )
    cancel = _protocol_module().parse_command(
        {
            "schema_version": 1,
            "op": "cancel",
            "request_id": "turn-before-first-audio",
        }
    )
    monkeypatch.setattr(worker, "_RUNTIME", runtime)
    monkeypatch.setattr(worker, "_PREPARED_PROMPT", prompt)
    monkeypatch.setattr(worker, "_emit_event", lambda event: emitted.append(event))
    emitted: list[Any] = []

    worker._signal_cancel(cancel)
    worker._dispatch(command)

    assert [event.event for event in emitted] == ["cancelled"]
    assert runtime.streaming_calls[0]["text"] == command.text


def test_qwen_worker_loads_cuda_before_starting_cancellation_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import tts_qwen3_worker as worker

    command = _protocol_module().parse_command(
        {"schema_version": 1, "op": "load", "request_id": "initial-load"}
    )
    events: list[str] = []
    commands: queue.Queue[Any | None] = queue.Queue()
    monkeypatch.setattr(worker, "_COMMANDS", commands)
    monkeypatch.setattr(worker, "_read_initial_command", lambda: command)

    def dispatch(received: Any) -> bool:
        assert received is command
        events.append("cuda-loaded")
        return True

    class ReaderThread:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def start(self) -> None:
            assert events == ["cuda-loaded"]
            events.append("reader-started")
            commands.put(None)

    monkeypatch.setattr(worker, "_dispatch", dispatch)
    monkeypatch.setattr(worker.threading, "Thread", ReaderThread)

    assert worker.main() == 0
    assert events == ["cuda-loaded", "reader-started"]


def test_qwen_worker_runtime_failure_after_audio_emits_matching_single_error_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import tts_qwen3_worker as worker

    class FailingRuntime(ScriptedNativeRuntime):
        def generate_voice_clone_streaming(self, **kwargs: Any):
            self.streaming_calls.append(kwargs)
            yield ([0.1] * 7680, 24000, {"total_steps": 4})
            raise RuntimeError("private CUDA failure detail")

    runtime = FailingRuntime()
    prompt = worker.PreparedVoicePrompt(
        voice_key="voice_0123456789abcdef",
        reference_transcript="The exact spoken reference.",
        prompt_items=[object()],
    )
    command = _protocol_module().parse_command(
        {
            "schema_version": 1,
            "op": "generate",
            "request_id": "turn-runtime-failure",
            "voice_key": prompt.voice_key,
            "text": "The private error must remain inside the worker.",
            "max_new_tokens": 48,
            "hard_audio_seconds": 6.0,
        }
    )
    monkeypatch.setattr(
        worker,
        "_wav_bytes",
        lambda _audio, _sample_rate: b"RIFF-native-chunk",
    )

    events = list(
        worker.iter_generation_events(runtime, prompt, command, threading.Event())
    )

    assert [event.event for event in events] == ["chunk", "error"]
    assert events[-1].chunk_count == 1
    assert events[-1].error_code == "qwen3_generation_failed"
    assert "private" not in events[-1].model_dump_json()


def test_qwen_worker_non_ending_stream_stops_at_token_ceiling_without_yielding_ceiling_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import tts_qwen3_worker as worker

    class NonEndingRuntime(ScriptedNativeRuntime):
        def generate_voice_clone_streaming(self, **kwargs: Any):
            self.streaming_calls.append(kwargs)
            steps = 0
            while True:
                steps += 4
                yield ([0.1] * 7680, 24000, {"total_steps": steps})

    runtime = NonEndingRuntime()
    prompt = worker.PreparedVoicePrompt(
        voice_key="prompt_" + "a" * 64,
        reference_transcript="The exact spoken reference.",
        prompt_items=[object()],
    )
    command = _protocol_module().parse_command(
        {
            "schema_version": 1,
            "op": "generate",
            "request_id": "turn-token-ceiling",
            "voice_key": prompt.voice_key,
            "text": "A short bounded phrase.",
            "max_new_tokens": 8,
            "hard_audio_seconds": 6.0,
        }
    )
    monkeypatch.setattr(
        worker,
        "_wav_bytes",
        lambda _audio, _sample_rate: _valid_wav_bytes(),
    )

    events = list(
        worker.iter_generation_events(runtime, prompt, command, threading.Event())
    )

    assert [event.event for event in events] == ["chunk", "error"]
    assert events[-1].chunk_count == 1
    assert events[-1].error_code == "qwen3_generation_ceiling"
