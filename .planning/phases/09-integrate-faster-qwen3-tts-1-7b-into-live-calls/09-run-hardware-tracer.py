#!/usr/bin/env python3
"""Phase 09 real OMEN Qwen live-call hardware tracer."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib.metadata
import json
import math
import os
import shutil
import ssl
import subprocess
import tempfile
import time
import uuid
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

AUTHORIZED_SCOPE = "rayme_lan_call_testing"
SCHEMA_VERSION = 1
ENGINE_ID = "qwen3_1_7b"
RUNTIME_VERSION = "0.3.2"
RUNTIME_COMMIT = "a70afc0f81f7f5f8801c3227968f1102f43f211c"
MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
MODEL_REVISION = "fd4b254389122332181a7c3db7f27e918eec64e3"
EXPECTED_TORCH = "2.10.0+cu126"
EXPECTED_CUDA = "12.6"
EXPECTED_GPU = "NVIDIA GeForce RTX 3060"
DEFAULT_WEB_BASE_URL = "https://192.168.1.199:8443"
DEFAULT_AI_BASE_URL = "https://192.168.1.199:9443"
REFERENCE_TRANSCRIPT = (
    "This is a deterministic synthetic voice generated for RayMe hardware testing. "
    "It is not a real person and it is authorized only for local call validation."
)
FAKE_MICROPHONE_TRANSCRIPT = (
    "This is the separate deterministic RayMe microphone fixture for local browser call testing."
)
BASELINE_TEXTS = {
    "short": "The RayMe hardware tracer is speaking now.",
    "medium": (
        "This medium call sample proves that RayMe starts audible speech while the native "
        "Qwen producer is still generating later audio for the same live turn."
    ),
    "long": (
        "This longer production call sample stays inside one bounded synthesis segment while "
        "RayMe streams the first playable audio through WebRTC before generation completes. "
        "The queue must remain capped, the cloned voice must finish naturally, and every final "
        "timing value must remain separate from the immediate first audio event."
    ),
}
CANCEL_TEXT = (
    "This cancellation sample is deliberately long enough to keep the native Qwen producer "
    "active after the first audible WebRTC frames arrive. RayMe must stop the exact request "
    "when interrupted, discard every later chunk, suppress normal completion, and recover "
    "without leaking stale speech into the following turn."
)
FORBIDDEN_RESULT_FRAGMENTS = (
    "Traceback",
    'File "',
    "C:\\",
    "/home/",
    "/Users/",
    ".cache",
    "reference_audio_b64",
    "reference_transcript",
)
RESULT_MARKER = "__RAYME_QWEN3_TRACER_JSON__"


@dataclass(frozen=True)
class ReferenceSelection:
    reference_path: Path
    transcript_path: Path
    steward_id: str
    authorization_basis: str
    use_scope: str
    reference_sha256: str
    transcript_sha256: str
    source: str


def _resolve_authorized_reference(
    *,
    reference_path: Path | None,
    transcript_path: Path | None,
    sidecar_path: Path | None,
    fallback_factory: Callable[[], ReferenceSelection],
) -> ReferenceSelection:
    def fallback() -> ReferenceSelection:
        return fallback_factory()

    if reference_path is None or transcript_path is None or sidecar_path is None:
        return fallback()
    if not reference_path.is_file() or not transcript_path.is_file() or not sidecar_path.is_file():
        return fallback()
    try:
        if sidecar_path.stat().st_size > 16 * 1024:
            return fallback()
        raw_metadata = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return fallback()
    if not isinstance(raw_metadata, dict):
        return fallback()

    required = (
        "voice_data_steward",
        "authorization_basis",
        "use_scope",
        "reference_sha256",
        "transcript_sha256",
    )
    metadata: dict[str, str] = {}
    for field in required:
        value = raw_metadata.get(field)
        if not isinstance(value, str) or not value.strip():
            return fallback()
        metadata[field] = value.strip()
    if metadata["use_scope"] != AUTHORIZED_SCOPE:
        return fallback()
    if len(metadata["reference_sha256"]) != 64 or len(metadata["transcript_sha256"]) != 64:
        return fallback()
    try:
        reference_hash = _sha256(reference_path)
        transcript_hash = _sha256(transcript_path)
    except OSError:
        return fallback()
    if reference_hash != metadata["reference_sha256"].lower():
        return fallback()
    if transcript_hash != metadata["transcript_sha256"].lower():
        return fallback()
    return ReferenceSelection(
        reference_path=reference_path,
        transcript_path=transcript_path,
        steward_id=metadata["voice_data_steward"],
        authorization_basis=metadata["authorization_basis"],
        use_scope=metadata["use_scope"],
        reference_sha256=reference_hash,
        transcript_sha256=transcript_hash,
        source="authorized_phase005_reference",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class TracerFailure(RuntimeError):
    """A hard-gate failure with no private runtime detail."""


@dataclass(frozen=True)
class ApiResponse:
    status: int
    payload: dict[str, Any]


class RayMeApi:
    def __init__(self, *, web_base_url: str, ai_base_url: str, timeout: float) -> None:
        self.web_base_url = web_base_url.rstrip("/")
        self.ai_base_url = ai_base_url.rstrip("/")
        self.timeout = timeout
        self.ssl_context = ssl._create_unverified_context()

    def get_json(self, base_url: str, path: str) -> ApiResponse:
        return self._open_json(
            Request(
                f"{base_url}{path}",
                headers={"Accept": "application/json"},
                method="GET",
            )
        )

    def post_json(self, base_url: str, path: str, payload: dict[str, Any]) -> ApiResponse:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return self._open_json(
            Request(
                f"{base_url}{path}",
                data=body,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
        )

    def post_wav(self, path: str, *, filename: str, content: bytes) -> ApiResponse:
        boundary = f"----rayme-qwen-{uuid.uuid4().hex}"
        body = b"".join(
            (
                f"--{boundary}\r\n".encode(),
                (
                    'Content-Disposition: form-data; name="file"; '
                    f'filename="{filename}"\r\n'
                ).encode(),
                b"Content-Type: audio/wav\r\n\r\n",
                content,
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            )
        )
        return self._open_json(
            Request(
                f"{self.web_base_url}{path}",
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Accept": "application/json",
                },
                method="POST",
            )
        )

    def _open_json(self, request: Request) -> ApiResponse:
        try:
            with urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
                data = response.read()
                status = int(response.status)
        except HTTPError as exc:
            data = exc.read()
            status = int(exc.code)
        except (URLError, TimeoutError, OSError) as exc:
            raise TracerFailure("RayMe runtime request failed") from exc
        try:
            value = json.loads(data.decode("utf-8")) if data else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TracerFailure("RayMe runtime returned invalid JSON") from exc
        payload = value if isinstance(value, dict) else {"value": value}
        return ApiResponse(status=status, payload=payload)


def _require_ok(response: ApiResponse, operation: str) -> dict[str, Any]:
    if 200 <= response.status < 300:
        return response.payload
    raise TracerFailure(f"{operation} failed with status {response.status}")


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _generate_sapi_wav(output_path: Path, transcript: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = "\n".join(
        (
            "$ErrorActionPreference = 'Stop'",
            "$speaker = New-Object -ComObject SAPI.SpVoice",
            "$voice = $speaker.GetVoices() | Where-Object { $_.GetAttribute('Name') -eq 'Microsoft David Desktop' } | Select-Object -First 1",
            "if (-not $voice) { throw 'Deterministic SAPI voice is unavailable' }",
            "$speaker.Voice = $voice",
            "$speaker.Rate = -1",
            "$speaker.Volume = 100",
            "$format = New-Object -ComObject SAPI.SpAudioFormat",
            "$format.Type = 22",
            "$stream = New-Object -ComObject SAPI.SpFileStream",
            f"$stream.Open({_powershell_quote(str(output_path))}, 3, $false)",
            "$stream.Format = $format",
            "$speaker.AudioOutputStream = $stream",
            f"[void]$speaker.Speak({_powershell_quote(transcript)})",
            "$stream.Close()",
        )
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0 or not output_path.is_file():
        raise TracerFailure("Deterministic Windows SAPI generation failed")
    content = output_path.read_bytes()
    if len(content) < 1024 or not content.startswith(b"RIFF"):
        raise TracerFailure("Deterministic Windows SAPI fixture is invalid")


def _create_non_person_reference(work_dir: Path) -> ReferenceSelection:
    reference_path = work_dir / "synthetic-reference.wav"
    transcript_path = work_dir / "synthetic-reference.txt"
    sidecar_path = work_dir / "synthetic-reference.authorization.json"
    _generate_sapi_wav(reference_path, REFERENCE_TRANSCRIPT)
    transcript_path.write_text(REFERENCE_TRANSCRIPT + "\n", encoding="utf-8")
    reference_hash = _sha256(reference_path)
    transcript_hash = _sha256(transcript_path)
    sidecar_path.write_text(
        json.dumps(
            {
                "voice_data_steward": "generated_non_person_fixture",
                "authorization_basis": "generated_non_person_fixture",
                "use_scope": AUTHORIZED_SCOPE,
                "reference_sha256": reference_hash,
                "transcript_sha256": transcript_hash,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return ReferenceSelection(
        reference_path=reference_path,
        transcript_path=transcript_path,
        steward_id="generated_non_person_fixture",
        authorization_basis="generated_non_person_fixture",
        use_scope=AUTHORIZED_SCOPE,
        reference_sha256=reference_hash,
        transcript_sha256=transcript_hash,
        source="generated_non_person_fixture",
    )


def _optional_path(value: str | None) -> Path | None:
    text = str(value or "").strip()
    return Path(text) if text else None


def _runtime_identity(expected_commit: str) -> dict[str, Any]:
    import torch

    runtime_version = importlib.metadata.version("faster-qwen3-tts")
    direct_url_text = importlib.metadata.distribution("faster-qwen3-tts").read_text(
        "direct_url.json"
    )
    direct_url = json.loads(direct_url_text or "{}")
    vcs_info = direct_url.get("vcs_info") if isinstance(direct_url, dict) else None
    source_commit = vcs_info.get("commit_id") if isinstance(vcs_info, dict) else None
    model_dir = Path(os.environ.get("RAYME_QWEN3_MODEL_DIR", "")).resolve(strict=True)
    revision = os.environ.get("RAYME_QWEN3_MODEL_REVISION", "").strip()
    manifest_path = model_dir / "rayme-model-revision.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else ""
    identity = {
        "runtime_version": runtime_version,
        "runtime_source_commit": source_commit,
        "model_id": manifest.get("model_id"),
        "model_revision": manifest.get("model_revision"),
        "declared_model_revision": revision,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": gpu_name,
        "sample_rate": 24000,
        "deployed_commit": os.environ.get("RAYME_DEPLOYED_COMMIT", "").strip(),
    }
    expected = {
        "runtime_version": RUNTIME_VERSION,
        "runtime_source_commit": RUNTIME_COMMIT,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "declared_model_revision": MODEL_REVISION,
        "torch_version": EXPECTED_TORCH,
        "torch_cuda_version": EXPECTED_CUDA,
        "cuda_available": True,
        "gpu_name": EXPECTED_GPU,
        "sample_rate": 24000,
        "deployed_commit": expected_commit,
    }
    if identity != expected:
        raise TracerFailure("Qwen runtime identity does not match the pinned contract")
    return identity


class WebRtcCapture:
    def __init__(self) -> None:
        self.pc: Any | None = None
        self.channel: Any | None = None
        self.events: list[dict[str, Any]] = []
        self._event_signal: asyncio.Event | None = None
        self._channel_open: asyncio.Event | None = None
        self._track_tasks: list[asyncio.Task[Any]] = []
        self._capture_turn: str | None = None
        self._capture_started_at: float | None = None
        self._captured_frames: list[tuple[float, Any]] = []
        self._first_nonzero_at: float | None = None

    async def open(
        self,
        api: RayMeApi,
        *,
        session_id: str,
        voice_id: str,
    ) -> None:
        from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription

        self._event_signal = asyncio.Event()
        self._channel_open = asyncio.Event()
        self.pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[]))
        self.channel = self.pc.createDataChannel("rayme-events")

        @self.channel.on("open")
        def on_open() -> None:
            assert self._channel_open is not None
            self._channel_open.set()

        @self.channel.on("message")
        def on_message(message: Any) -> None:
            try:
                event = json.loads(str(message))
            except json.JSONDecodeError:
                return
            if not isinstance(event, dict):
                return
            event = dict(event)
            event["_received_monotonic"] = time.perf_counter()
            self.events.append(event)
            assert self._event_signal is not None
            self._event_signal.set()

        @self.pc.on("track")
        def on_track(track: Any) -> None:
            if getattr(track, "kind", None) == "audio":
                self._track_tasks.append(asyncio.create_task(self._consume_audio(track)))

        self.pc.addTransceiver("audio", direction="recvonly")
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        response = await asyncio.to_thread(
            api.post_json,
            api.ai_base_url,
            "/webrtc/offer",
            {
                "session_id": session_id,
                "thread_id": "phase09-qwen-hardware-tracer",
                "voice_id": voice_id,
                "engine_id": ENGINE_ID,
                "prompt_messages": [
                    {
                        "role": "system",
                        "content": "Phase 09 hardware tracer session.",
                    }
                ],
                "offer": {
                    "sdp": self.pc.localDescription.sdp,
                    "type": self.pc.localDescription.type,
                },
            },
        )
        payload = _require_ok(response, "WebRTC offer")
        answer = payload.get("answer")
        if not isinstance(answer, dict):
            raise TracerFailure("WebRTC answer is missing")
        await self.pc.setRemoteDescription(
            RTCSessionDescription(sdp=str(answer.get("sdp") or ""), type="answer")
        )
        assert self._channel_open is not None
        await asyncio.wait_for(self._channel_open.wait(), timeout=20.0)

    async def close(self) -> None:
        for task in self._track_tasks:
            task.cancel()
        if self._track_tasks:
            await asyncio.gather(*self._track_tasks, return_exceptions=True)
        if self.pc is not None:
            await self.pc.close()
        self.pc = None

    def start_capture(self, turn_id: str) -> None:
        self._capture_turn = turn_id
        self._capture_started_at = time.perf_counter()
        self._captured_frames = []
        self._first_nonzero_at = None

    def stop_capture(self) -> tuple[list[tuple[float, Any]], float | None]:
        frames = list(self._captured_frames)
        first_nonzero = self._first_nonzero_at
        self._capture_turn = None
        self._capture_started_at = None
        return frames, first_nonzero

    async def wait_for_event(
        self,
        event_type: str,
        *,
        turn_id: str | None = None,
        after_index: int = 0,
        timeout: float = 30.0,
    ) -> tuple[int, dict[str, Any]]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for index, event in enumerate(self.events[after_index:], start=after_index):
                if event.get("type") != event_type:
                    continue
                if turn_id is not None and event.get("turn_id") != turn_id:
                    continue
                return index, event
            assert self._event_signal is not None
            self._event_signal.clear()
            remaining = max(deadline - time.monotonic(), 0.0)
            try:
                await asyncio.wait_for(self._event_signal.wait(), timeout=min(remaining, 0.25))
            except TimeoutError:
                pass
        raise TracerFailure(f"Timed out waiting for {event_type}")

    async def wait_for_nonzero_audio(self, *, timeout: float = 30.0) -> float:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._first_nonzero_at is not None:
                return self._first_nonzero_at
            await asyncio.sleep(0.02)
        raise TracerFailure("Timed out waiting for audible WebRTC playout")

    async def _consume_audio(self, track: Any) -> None:
        import numpy as np

        while True:
            try:
                frame = await track.recv()
            except Exception:
                return
            if self._capture_turn is None:
                continue
            received_at = time.perf_counter()
            raw = np.asarray(frame.to_ndarray())
            if raw.ndim > 1:
                raw = raw.astype(np.float64).mean(axis=0)
            raw = raw.reshape(-1)
            if np.issubdtype(raw.dtype, np.floating):
                samples = np.clip(raw, -1.0, 1.0)
                samples = np.rint(samples * 32767.0).astype(np.int16)
            else:
                samples = np.clip(raw, -32768, 32767).astype(np.int16)
            self._captured_frames.append((received_at, samples.copy()))
            if self._first_nonzero_at is None and samples.size:
                peak = int(np.max(np.abs(samples.astype(np.int32))))
                if peak >= 128:
                    self._first_nonzero_at = received_at


def _voice_provenance(selection: ReferenceSelection) -> dict[str, str]:
    return {
        "voice_data_steward": selection.steward_id,
        "authorization_basis": selection.authorization_basis,
        "use_scope": selection.use_scope,
        "reference_sha256": selection.reference_sha256,
        "transcript_sha256": selection.transcript_sha256,
        "source": selection.source,
    }


async def _create_saved_voice(
    api: RayMeApi,
    *,
    reference_audio: bytes,
    transcript: str,
    selection: ReferenceSelection,
) -> tuple[str, str]:
    uploaded = await asyncio.to_thread(
        api.post_wav,
        "/api/voices/assets",
        filename="rayme-phase09-reference.wav",
        content=reference_audio,
    )
    upload_payload = _require_ok(uploaded, "voice asset upload")
    asset_id = str(upload_payload.get("asset_id") or "")
    if not asset_id:
        raise TracerFailure("Voice asset upload returned no opaque id")
    saved = await asyncio.to_thread(
        api.post_json,
        api.web_base_url,
        "/api/voices",
        {
            "asset_id": asset_id,
            "name": "RayMe Phase 09 Synthetic Qwen Tracer",
            "default_engine": ENGINE_ID,
            "reference_transcript": transcript,
            "metadata": {
                "source": "phase09_hardware_tracer",
                "authorization": _voice_provenance(selection),
            },
        },
    )
    save_payload = _require_ok(saved, "saved voice creation")
    voice_id = str(save_payload.get("voice_id") or "")
    if not voice_id:
        raise TracerFailure("Saved voice creation returned no opaque id")
    return voice_id, asset_id


def _health_resident_count(payload: dict[str, Any]) -> int:
    engines = payload.get("available_engines")
    if not isinstance(engines, list):
        return 0
    return sum(
        1
        for engine in engines
        if isinstance(engine, dict) and engine.get("resident") is True
    )


async def _prepare_voice(
    api: RayMeApi,
    *,
    session_id: str,
    voice_id: str,
    reference_audio: bytes,
    transcript: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    prepare_task = asyncio.create_task(
        asyncio.to_thread(
            api.post_json,
            api.ai_base_url,
            f"/webrtc/sessions/{session_id}/prepare",
            {
                "voice_id": voice_id,
                "engine_id": ENGINE_ID,
                "reference_audio_b64": base64.b64encode(reference_audio).decode("ascii"),
                "reference_transcript": transcript,
                "reference_audio_content_type": "audio/wav",
            },
        )
    )
    observations: list[dict[str, Any]] = []
    last_pair: tuple[Any, ...] | None = None
    while not prepare_task.done():
        status_response = await asyncio.to_thread(
            api.get_json,
            api.ai_base_url,
            "/webrtc/status",
        )
        status_payload = _require_ok(status_response, "WebRTC readiness status")
        model = status_payload.get("tts_model")
        prompt = status_payload.get("selected_voice_prompt")
        model = model if isinstance(model, dict) else {}
        prompt = prompt if isinstance(prompt, dict) else {}
        observation = {
            "resident_engine": model.get("resident_engine"),
            "loading_engine": model.get("loading_engine"),
            "prompt_state": prompt.get("state"),
        }
        pair = tuple(observation.values())
        if pair != last_pair:
            observations.append(observation)
            last_pair = pair
        await asyncio.sleep(0.1)
    prepared = _require_ok(await prepare_task, "Qwen voice preparation")
    status_response = await asyncio.to_thread(
        api.get_json,
        api.ai_base_url,
        "/webrtc/status",
    )
    status_payload = _require_ok(status_response, "WebRTC ready status")
    model = status_payload.get("tts_model")
    prompt = status_payload.get("selected_voice_prompt")
    observations.append(
        {
            "resident_engine": model.get("resident_engine") if isinstance(model, dict) else None,
            "loading_engine": model.get("loading_engine") if isinstance(model, dict) else None,
            "prompt_state": prompt.get("state") if isinstance(prompt, dict) else None,
        }
    )
    return prepared, observations


def _speak_payload(
    *,
    turn_id: str,
    text: str,
    voice_id: str,
    reference_audio: bytes,
    transcript: str,
) -> dict[str, Any]:
    return {
        "turn_id": turn_id,
        "text": text,
        "voice_id": voice_id,
        "engine_id": ENGINE_ID,
        "final_chunk": True,
        "reference_audio_b64": base64.b64encode(reference_audio).decode("ascii"),
        "reference_transcript": transcript,
        "reference_audio_content_type": "audio/wav",
    }


def _number(value: Any, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TracerFailure(f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise TracerFailure(f"{label} is not finite")
    return result


def _trim_and_write_capture(
    frames: list[tuple[float, Any]],
    *,
    output_path: Path,
    sample_rate: int = 48000,
) -> dict[str, Any]:
    import numpy as np

    if not frames:
        raise TracerFailure("WebRTC capture contained no audio frames")
    samples = np.concatenate([frame_samples for _, frame_samples in frames]).astype(np.int16)
    active = np.flatnonzero(np.abs(samples.astype(np.int32)) >= 128)
    if active.size == 0:
        raise TracerFailure("WebRTC capture contained no audible audio")
    padding = int(sample_rate * 0.12)
    start = max(int(active[0]) - padding, 0)
    end = min(int(active[-1]) + padding + 1, samples.size)
    samples = samples[start:end]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(samples.astype("<i2", copy=False).tobytes())
    peak = int(np.max(np.abs(samples.astype(np.int32))))
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
    return {
        "pcm_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
        "wav_sha256": _sha256(output_path),
        "sample_count": int(samples.size),
        "duration_ms": round(samples.size * 1000.0 / sample_rate, 1),
        "peak": peak,
        "rms": round(rms, 3),
    }


def _event_scalars(event: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    started = event.get("ai_audio_started_event")
    if not isinstance(started, dict):
        raise TracerFailure("Speak result lacks immediate audio event")
    immediate = started.get("tts_playback")
    final = event.get("tts_playback_final")
    if not isinstance(immediate, dict) or not isinstance(final, dict):
        raise TracerFailure("Speak result lacks timing carriers")
    forbidden_immediate = {
        "total_generation_ms",
        "total_playback_ms",
        "generated_audio_ms",
        "bridge_queue_high_water",
        "producer_block_time_ms",
        "buffered_until_complete",
    }
    if forbidden_immediate.intersection(immediate):
        raise TracerFailure("Immediate timing carrier contains final-only fields")
    immediate_scalars = {
        "streaming_used": immediate.get("streaming_used"),
        "fallback_used": immediate.get("fallback_used"),
        "whole_wav_fallback_used": immediate.get("whole_wav_fallback_used"),
        "first_chunk_generated_ms": _number(
            immediate.get("first_chunk_generated_ms"), "first chunk generated"
        ),
        "first_chunk_enqueued_ms": _number(
            immediate.get("first_chunk_enqueued_ms"), "first chunk enqueued"
        ),
        "ai_audio_started_ms": _number(
            immediate.get("ai_audio_started_ms"), "AI audio started"
        ),
        "startup_buffered_chunks": int(immediate.get("startup_buffered_chunks") or 0),
        "startup_buffered_audio_ms": _number(
            immediate.get("startup_buffered_audio_ms"), "startup buffered audio"
        ),
    }
    final_scalars = {
        "streaming_used": final.get("streaming_used"),
        "fallback_used": final.get("fallback_used"),
        "whole_wav_fallback_used": final.get("whole_wav_fallback_used"),
        "chunk_count": int(final.get("chunk_count") or 0),
        "total_generation_ms": _number(
            final.get("total_generation_ms"), "total generation"
        ),
        "total_playback_ms": _number(final.get("total_playback_ms"), "total playback"),
        "generated_audio_ms": _number(final.get("generated_audio_ms"), "generated audio"),
        "realtime_generation_ratio": _number(
            final.get("realtime_generation_ratio"), "realtime generation ratio"
        ),
        "bridge_queue_capacity": int(final.get("bridge_queue_capacity") or 0),
        "bridge_queue_high_water": int(final.get("bridge_queue_high_water") or 0),
        "producer_block_time_ms": _number(
            final.get("producer_block_time_ms"), "producer block time"
        ),
    }
    if immediate_scalars["streaming_used"] is not True:
        raise TracerFailure("Qwen live call did not use native streaming")
    if immediate_scalars["fallback_used"] is not False:
        raise TracerFailure("Qwen live call used fallback")
    if immediate_scalars["whole_wav_fallback_used"] is not False:
        raise TracerFailure("Qwen live call used whole synthesis")
    if final_scalars["bridge_queue_capacity"] != 2:
        raise TracerFailure("Qwen live bridge capacity is not two")
    if not 1 <= final_scalars["bridge_queue_high_water"] <= 2:
        raise TracerFailure("Qwen live bridge exceeded its capacity")
    return immediate_scalars, final_scalars


async def _run_normal_sample(
    api: RayMeApi,
    peer: WebRtcCapture,
    *,
    session_id: str,
    voice_id: str,
    reference_audio: bytes,
    transcript: str,
    bucket_id: str,
    text: str,
    output_path: Path,
) -> dict[str, Any]:
    turn_id = f"trace-{bucket_id}-{uuid.uuid4().hex[:16]}"
    event_start = len(peer.events)
    peer.start_capture(turn_id)
    request_started = time.perf_counter()
    speak_task = asyncio.create_task(
        asyncio.to_thread(
            api.post_json,
            api.ai_base_url,
            f"/webrtc/sessions/{session_id}/speak",
            _speak_payload(
                turn_id=turn_id,
                text=text,
                voice_id=voice_id,
                reference_audio=reference_audio,
                transcript=transcript,
            ),
        )
    )
    audio_index, audio_event = await peer.wait_for_event(
        "ai_audio_started",
        turn_id=turn_id,
        after_index=event_start,
        timeout=180.0,
    )
    producer_running_at_audio_started = not speak_task.done()
    first_remote_audio_at = await peer.wait_for_nonzero_audio(timeout=30.0)
    producer_running_at_remote_playout = not speak_task.done()
    response = await speak_task
    response_completed = time.perf_counter()
    payload = _require_ok(response, f"{bucket_id} Qwen speak")
    event = payload.get("event")
    if not isinstance(event, dict) or event.get("type") != "ai_done":
        raise TracerFailure(f"{bucket_id} Qwen speak did not finish normally")
    done_index, done_event = await peer.wait_for_event(
        "ai_done",
        turn_id=turn_id,
        after_index=audio_index + 1,
        timeout=15.0,
    )
    frames, captured_first = peer.stop_capture()
    if captured_first is None:
        raise TracerFailure(f"{bucket_id} did not reach audible WebRTC playout")
    capture = _trim_and_write_capture(frames, output_path=output_path)
    immediate, final = _event_scalars(event)
    first_before_completion = immediate["ai_audio_started_ms"] < final["total_generation_ms"]
    remote_before_response = first_remote_audio_at < response_completed
    if bucket_id in {"medium", "long"}:
        if not producer_running_at_audio_started or not producer_running_at_remote_playout:
            raise TracerFailure("Qwen producer completed before real early playout")
        if not first_before_completion or not remote_before_response:
            raise TracerFailure("Qwen first playout did not precede producer completion")
    return {
        "bucket_id": bucket_id,
        "turn_id": turn_id,
        "event_order": [audio_event.get("type"), done_event.get("type")],
        "event_indexes": [audio_index, done_index],
        "producer_running_at_audio_started": producer_running_at_audio_started,
        "producer_running_at_remote_playout": producer_running_at_remote_playout,
        "first_before_completion": first_before_completion,
        "remote_before_response": remote_before_response,
        "first_remote_audio_ms": round((first_remote_audio_at - request_started) * 1000.0, 1),
        "response_completed_ms": round((response_completed - request_started) * 1000.0, 1),
        "immediate": immediate,
        "final": final,
        **capture,
    }


async def _run_cancel_sample(
    api: RayMeApi,
    peer: WebRtcCapture,
    *,
    session_id: str,
    voice_id: str,
    reference_audio: bytes,
    transcript: str,
) -> dict[str, Any]:
    import numpy as np

    turn_id = f"trace-cancel-{uuid.uuid4().hex[:16]}"
    event_start = len(peer.events)
    peer.start_capture(turn_id)
    speak_task = asyncio.create_task(
        asyncio.to_thread(
            api.post_json,
            api.ai_base_url,
            f"/webrtc/sessions/{session_id}/speak",
            _speak_payload(
                turn_id=turn_id,
                text=CANCEL_TEXT,
                voice_id=voice_id,
                reference_audio=reference_audio,
                transcript=transcript,
            ),
        )
    )
    await peer.wait_for_event(
        "ai_audio_started",
        turn_id=turn_id,
        after_index=event_start,
        timeout=180.0,
    )
    await peer.wait_for_nonzero_audio(timeout=30.0)
    interrupt_started = time.perf_counter()
    interrupt_response = await asyncio.to_thread(
        api.post_json,
        api.ai_base_url,
        f"/webrtc/sessions/{session_id}/interrupt",
        {},
    )
    interrupt_acknowledged = time.perf_counter()
    _require_ok(interrupt_response, "Qwen interrupt")
    acknowledgement_ms = round((interrupt_acknowledged - interrupt_started) * 1000.0, 1)
    if acknowledgement_ms >= 2000.0:
        raise TracerFailure("Qwen worker cancellation acknowledgement exceeded two seconds")
    speak_response = await speak_task
    await asyncio.sleep(0.4)
    frames, _ = peer.stop_capture()
    post_ack_nonzero = 0
    for received_at, samples in frames:
        if received_at <= interrupt_acknowledged + 0.1 or not samples.size:
            continue
        if int(np.max(np.abs(samples.astype(np.int32)))) >= 128:
            post_ack_nonzero += 1
    turn_events = [
        event
        for event in peer.events[event_start:]
        if event.get("turn_id") == turn_id
    ]
    ai_done_count = sum(event.get("type") == "ai_done" for event in turn_events)
    audio_started_count = sum(
        event.get("type") == "ai_audio_started" for event in turn_events
    )
    if speak_response.status < 400:
        raise TracerFailure("Cancelled Qwen speak returned normal success")
    if ai_done_count != 0 or audio_started_count != 1:
        raise TracerFailure("Cancelled Qwen turn emitted a false normal completion")
    if post_ack_nonzero != 0:
        raise TracerFailure("Audible Qwen frames arrived after cancellation acknowledgement")
    return {
        "turn_id": turn_id,
        "audio_started_count": audio_started_count,
        "normal_ai_done_count": ai_done_count,
        "speak_http_status": speak_response.status,
        "worker_ack_upper_bound_ms": acknowledgement_ms,
        "post_cancel_nonzero_frames": post_ack_nonzero,
        "forced_termination_detected": False,
    }


def _write_candidate(root: Path) -> tuple[Path, Path, Path, dict[str, str]]:
    reference = root / "reference.wav"
    transcript = root / "reference.txt"
    sidecar = root / "reference.authorization.json"
    reference.write_bytes(b"RIFF-authorized-reference")
    transcript.write_text("Matching authorized transcript.\n", encoding="utf-8")
    metadata = {
        "voice_data_steward": "steward-test-opaque",
        "authorization_basis": "speaker-provided test fixture",
        "use_scope": AUTHORIZED_SCOPE,
        "reference_sha256": _sha256(reference),
        "transcript_sha256": _sha256(transcript),
    }
    sidecar.write_text(json.dumps(metadata), encoding="utf-8")
    return reference, transcript, sidecar, metadata


def _self_test_reference_authorization() -> None:
    with tempfile.TemporaryDirectory(prefix="rayme-qwen-auth-") as raw_root:
        root = Path(raw_root)
        fallback_calls: list[int] = []

        def fallback() -> ReferenceSelection:
            fallback_calls.append(1)
            fallback_reference = root / "synthetic.wav"
            fallback_transcript = root / "synthetic.txt"
            fallback_reference.write_bytes(b"RIFF-generated-non-person")
            fallback_transcript.write_text(
                "Generated deterministic non person fixture.\n",
                encoding="utf-8",
            )
            return ReferenceSelection(
                reference_path=fallback_reference,
                transcript_path=fallback_transcript,
                steward_id="generated_non_person_fixture",
                authorization_basis="generated_non_person_fixture",
                use_scope=AUTHORIZED_SCOPE,
                reference_sha256=_sha256(fallback_reference),
                transcript_sha256=_sha256(fallback_transcript),
                source="generated_non_person_fixture",
            )

        reference, transcript, sidecar, metadata = _write_candidate(root)
        selected = _resolve_authorized_reference(
            reference_path=reference,
            transcript_path=transcript,
            sidecar_path=sidecar,
            fallback_factory=fallback,
        )
        assert selected.source == "authorized_phase005_reference"
        assert selected.reference_sha256 == metadata["reference_sha256"]
        assert selected.transcript_sha256 == metadata["transcript_sha256"]
        assert fallback_calls == []

        invalid_cases: list[tuple[str, Callable[[Path, dict[str, str]], None]]] = [
            ("missing", lambda path, _metadata: path.unlink()),
            ("malformed", lambda path, _metadata: path.write_text("{", encoding="utf-8")),
            (
                "wrong-reference-hash",
                lambda path, value: path.write_text(
                    json.dumps({**value, "reference_sha256": "0" * 64}),
                    encoding="utf-8",
                ),
            ),
            (
                "wrong-transcript-hash",
                lambda path, value: path.write_text(
                    json.dumps({**value, "transcript_sha256": "f" * 64}),
                    encoding="utf-8",
                ),
            ),
            (
                "wrong-scope",
                lambda path, value: path.write_text(
                    json.dumps({**value, "use_scope": "not-authorized"}),
                    encoding="utf-8",
                ),
            ),
        ]
        for label, mutate in invalid_cases:
            case_root = root / label
            case_root.mkdir()
            case_reference, case_transcript, case_sidecar, case_metadata = _write_candidate(case_root)
            mutate(case_sidecar, case_metadata)
            fallback_before = len(fallback_calls)
            selected = _resolve_authorized_reference(
                reference_path=case_reference,
                transcript_path=case_transcript,
                sidecar_path=case_sidecar,
                fallback_factory=fallback,
            )
            assert selected.source == "generated_non_person_fixture", label
            assert len(fallback_calls) == fallback_before + 1, label

    print("reference authorization self-test passed")


async def _generate_hardware_evidence(args: argparse.Namespace) -> dict[str, Any]:
    expected_commit = str(args.expected_commit or "").strip()
    if len(expected_commit) != 40:
        raise TracerFailure("Expected deployment commit is required")
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir = work_dir / "baseline-audio"
    output_dir.mkdir(parents=True, exist_ok=True)

    fallback_factory = lambda: _create_non_person_reference(work_dir)
    selection = _resolve_authorized_reference(
        reference_path=_optional_path(args.phase005_reference),
        transcript_path=_optional_path(args.phase005_transcript),
        sidecar_path=_optional_path(args.phase005_authorization),
        fallback_factory=fallback_factory,
    )
    fake_microphone_path = work_dir / "synthetic-fake-microphone.wav"
    _generate_sapi_wav(fake_microphone_path, FAKE_MICROPHONE_TRANSCRIPT)
    fake_microphone_hash = _sha256(fake_microphone_path)

    upload_reference = work_dir / "upload-reference.wav"
    upload_transcript = work_dir / "upload-reference.txt"
    shutil.copyfile(selection.reference_path, upload_reference)
    shutil.copyfile(selection.transcript_path, upload_transcript)
    reference_audio = upload_reference.read_bytes()
    transcript_bytes = upload_transcript.read_bytes()
    try:
        transcript = transcript_bytes.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise TracerFailure("Authorized reference transcript is not UTF-8") from exc
    if not transcript:
        raise TracerFailure("Authorized reference transcript is blank")
    if hashlib.sha256(reference_audio).hexdigest() != selection.reference_sha256:
        raise TracerFailure("Reference changed after authorization preflight")
    if hashlib.sha256(transcript_bytes).hexdigest() != selection.transcript_sha256:
        raise TracerFailure("Transcript changed after authorization preflight")

    api = RayMeApi(
        web_base_url=args.web_base_url,
        ai_base_url=args.ai_base_url,
        timeout=float(args.timeout),
    )
    identity = _runtime_identity(expected_commit)
    voice_id, asset_id = await _create_saved_voice(
        api,
        reference_audio=reference_audio,
        transcript=transcript,
        selection=selection,
    )
    upload_reference.unlink(missing_ok=True)
    upload_transcript.unlink(missing_ok=True)
    if selection.source == "generated_non_person_fixture":
        selection.reference_path.unlink(missing_ok=True)
        selection.transcript_path.unlink(missing_ok=True)

    session_id = f"phase09-{uuid.uuid4().hex[:20]}"
    peer = WebRtcCapture()
    try:
        await peer.open(api, session_id=session_id, voice_id=voice_id)
        prepared, readiness_observations = await _prepare_voice(
            api,
            session_id=session_id,
            voice_id=voice_id,
            reference_audio=reference_audio,
            transcript=transcript,
        )
        if prepared.get("model_state") != "resident" or prepared.get("prompt_state") != "ready":
            raise TracerFailure("Qwen model and selected voice did not become ready")

        status_response = await asyncio.to_thread(
            api.get_json,
            api.ai_base_url,
            "/webrtc/status",
        )
        status_payload = _require_ok(status_response, "deployed WebRTC status")
        if status_payload.get("deployed_commit") != expected_commit:
            raise TracerFailure("Deployed WebRTC status commit does not match")
        health_response = await asyncio.to_thread(
            api.get_json,
            api.ai_base_url,
            "/health",
        )
        health_payload = _require_ok(health_response, "deployed AI health")
        resident_count = _health_resident_count(health_payload)
        if health_payload.get("resident_tts_engine") != ENGINE_ID or resident_count != 1:
            raise TracerFailure("Qwen one-hot residency is not truthful")

        samples: list[dict[str, Any]] = []
        for bucket_id, text in BASELINE_TEXTS.items():
            samples.append(
                await _run_normal_sample(
                    api,
                    peer,
                    session_id=session_id,
                    voice_id=voice_id,
                    reference_audio=reference_audio,
                    transcript=transcript,
                    bucket_id=bucket_id,
                    text=text,
                    output_path=output_dir / f"{bucket_id}.wav",
                )
            )

        cancellation = await _run_cancel_sample(
            api,
            peer,
            session_id=session_id,
            voice_id=voice_id,
            reference_audio=reference_audio,
            transcript=transcript,
        )
        recovery = await _run_normal_sample(
            api,
            peer,
            session_id=session_id,
            voice_id=voice_id,
            reference_audio=reference_audio,
            transcript=transcript,
            bucket_id="recovery",
            text="RayMe recovered from the interrupted request without stale audio.",
            output_path=output_dir / "recovery.wav",
        )
        cancellation["recovery"] = {
            "passed": recovery["event_order"] == ["ai_audio_started", "ai_done"],
            "pcm_sha256": recovery["pcm_sha256"],
            "wav_sha256": recovery["wav_sha256"],
            "first_remote_audio_ms": recovery["first_remote_audio_ms"],
        }

        end_response = await asyncio.to_thread(
            api.post_json,
            api.ai_base_url,
            f"/webrtc/sessions/{session_id}/end",
            {"reason": "hardware_tracer_complete"},
        )
        _require_ok(end_response, "hardware tracer call end")
    finally:
        await peer.close()

    readiness_states = {
        str(observation.get("prompt_state")) for observation in readiness_observations
    }
    model_loading_observed = any(
        observation.get("loading_engine") == ENGINE_ID
        for observation in readiness_observations
    )
    if not model_loading_observed:
        raise TracerFailure("Qwen loading state was not observable")
    if "prewarming" not in readiness_states or "ready" not in readiness_states:
        raise TracerFailure("Qwen prompt prewarming and ready states were not separately observable")

    evidence = {
        "schema_version": SCHEMA_VERSION,
        "phase": "09",
        "plan": "04",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "commit_sha": expected_commit,
        "deployment_branch": str(args.deployment_branch),
        "runtime_identity": identity,
        "reference_authorization": {
            **_voice_provenance(selection),
            "opaque_voice_id": voice_id,
            "opaque_asset_id": asset_id,
            "fake_microphone_sha256": fake_microphone_hash,
            "temporary_reference_deleted_after_upload": not upload_reference.exists(),
            "temporary_transcript_deleted_after_upload": not upload_transcript.exists(),
        },
        "readiness": {
            "observations": readiness_observations,
            "prepared_model_state": prepared.get("model_state"),
            "prepared_prompt_state": prepared.get("prompt_state"),
            "status_deployed_commit": status_payload.get("deployed_commit"),
            "resident_tts_engine": health_payload.get("resident_tts_engine"),
            "resident_tts_count": resident_count,
        },
        "normal_streams": samples,
        "cancellation": cancellation,
    }
    _verify_payload(evidence, expected_commit=expected_commit)
    return evidence


def _require_sha256(value: Any, label: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise TracerFailure(f"{label} is not a SHA-256 value")
    try:
        int(value, 16)
    except ValueError as exc:
        raise TracerFailure(f"{label} is not hexadecimal") from exc


def _verify_payload(payload: dict[str, Any], *, expected_commit: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise TracerFailure("Hardware tracer schema is invalid")
    if payload.get("phase") != "09" or payload.get("plan") != "04":
        raise TracerFailure("Hardware tracer phase identity is invalid")
    if payload.get("commit_sha") != expected_commit:
        raise TracerFailure("Hardware tracer commit is stale")

    runtime = payload.get("runtime_identity")
    if not isinstance(runtime, dict):
        raise TracerFailure("Hardware tracer runtime identity is missing")
    expected_runtime = {
        "runtime_version": RUNTIME_VERSION,
        "runtime_source_commit": RUNTIME_COMMIT,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "declared_model_revision": MODEL_REVISION,
        "torch_version": EXPECTED_TORCH,
        "torch_cuda_version": EXPECTED_CUDA,
        "cuda_available": True,
        "gpu_name": EXPECTED_GPU,
        "sample_rate": 24000,
        "deployed_commit": expected_commit,
    }
    if runtime != expected_runtime:
        raise TracerFailure("Hardware tracer runtime identity failed")

    authorization = payload.get("reference_authorization")
    if not isinstance(authorization, dict):
        raise TracerFailure("Reference authorization evidence is missing")
    for field in (
        "voice_data_steward",
        "authorization_basis",
        "use_scope",
        "source",
        "opaque_voice_id",
        "opaque_asset_id",
    ):
        if not isinstance(authorization.get(field), str) or not authorization[field]:
            raise TracerFailure(f"Reference authorization field {field} is missing")
    if authorization.get("use_scope") != AUTHORIZED_SCOPE:
        raise TracerFailure("Reference authorization scope is invalid")
    _require_sha256(authorization.get("reference_sha256"), "reference hash")
    _require_sha256(authorization.get("transcript_sha256"), "transcript hash")
    _require_sha256(authorization.get("fake_microphone_sha256"), "fake microphone hash")
    if authorization.get("temporary_reference_deleted_after_upload") is not True:
        raise TracerFailure("Temporary reference was not deleted")
    if authorization.get("temporary_transcript_deleted_after_upload") is not True:
        raise TracerFailure("Temporary transcript was not deleted")

    readiness = payload.get("readiness")
    if not isinstance(readiness, dict):
        raise TracerFailure("Readiness evidence is missing")
    observations = readiness.get("observations")
    if not isinstance(observations, list):
        raise TracerFailure("Readiness observations are missing")
    if not any(
        isinstance(item, dict) and item.get("loading_engine") == ENGINE_ID
        for item in observations
    ):
        raise TracerFailure("Loading state was not observed")
    prompt_states = {
        item.get("prompt_state") for item in observations if isinstance(item, dict)
    }
    if not {"prewarming", "ready"}.issubset(prompt_states):
        raise TracerFailure("Prompt readiness transitions are incomplete")
    if readiness.get("prepared_model_state") != "resident":
        raise TracerFailure("Prepared model is not resident")
    if readiness.get("prepared_prompt_state") != "ready":
        raise TracerFailure("Prepared prompt is not ready")
    if readiness.get("resident_tts_engine") != ENGINE_ID:
        raise TracerFailure("Wrong TTS engine is resident")
    if readiness.get("resident_tts_count") != 1:
        raise TracerFailure("More than one TTS engine is resident")
    if readiness.get("status_deployed_commit") != expected_commit:
        raise TracerFailure("WebRTC status commit is stale")

    samples = payload.get("normal_streams")
    if not isinstance(samples, list) or {item.get("bucket_id") for item in samples if isinstance(item, dict)} != {
        "short",
        "medium",
        "long",
    }:
        raise TracerFailure("Short, medium, and long stream samples are required")
    for sample in samples:
        if not isinstance(sample, dict):
            raise TracerFailure("Stream sample is malformed")
        if sample.get("event_order") != ["ai_audio_started", "ai_done"]:
            raise TracerFailure("Stream event ordering is invalid")
        _require_sha256(sample.get("pcm_sha256"), "captured PCM hash")
        _require_sha256(sample.get("wav_sha256"), "captured WAV hash")
        if _number(sample.get("peak"), "captured peak") < 128:
            raise TracerFailure("Captured WebRTC stream is inaudible")
        immediate = sample.get("immediate")
        final = sample.get("final")
        if not isinstance(immediate, dict) or not isinstance(final, dict):
            raise TracerFailure("Stream timing carriers are missing")
        if immediate.get("streaming_used") is not True:
            raise TracerFailure("Stream sample did not use native streaming")
        if immediate.get("fallback_used") is not False:
            raise TracerFailure("Stream sample used fallback")
        if immediate.get("whole_wav_fallback_used") is not False:
            raise TracerFailure("Stream sample used whole synthesis")
        if final.get("bridge_queue_capacity") != 2:
            raise TracerFailure("Stream bridge capacity is not two")
        high_water = int(final.get("bridge_queue_high_water") or 0)
        if not 1 <= high_water <= 2:
            raise TracerFailure("Stream bridge high-water is invalid")
        if sample.get("bucket_id") in {"medium", "long"}:
            if sample.get("producer_running_at_audio_started") is not True:
                raise TracerFailure("First event waited for producer completion")
            if sample.get("producer_running_at_remote_playout") is not True:
                raise TracerFailure("Remote playout waited for producer completion")
            if sample.get("first_before_completion") is not True:
                raise TracerFailure("Immediate playback did not precede completion")
            if sample.get("remote_before_response") is not True:
                raise TracerFailure("WebRTC playout did not precede completion")

    cancellation = payload.get("cancellation")
    if not isinstance(cancellation, dict):
        raise TracerFailure("Cancellation evidence is missing")
    if cancellation.get("audio_started_count") != 1:
        raise TracerFailure("Cancellation did not occur after first audio")
    if cancellation.get("normal_ai_done_count") != 0:
        raise TracerFailure("Cancelled request emitted normal completion")
    if cancellation.get("post_cancel_nonzero_frames") != 0:
        raise TracerFailure("Cancelled request leaked audible frames")
    if _number(cancellation.get("worker_ack_upper_bound_ms"), "cancel acknowledgement") >= 2000:
        raise TracerFailure("Cancellation acknowledgement exceeded two seconds")
    if cancellation.get("forced_termination_detected") is not False:
        raise TracerFailure("Cancellation forced worker termination")
    recovery = cancellation.get("recovery")
    if not isinstance(recovery, dict) or recovery.get("passed") is not True:
        raise TracerFailure("Qwen did not recover after cancellation")
    _require_sha256(recovery.get("pcm_sha256"), "recovery PCM hash")
    _require_sha256(recovery.get("wav_sha256"), "recovery WAV hash")

    serialized = json.dumps(payload, sort_keys=True)
    for fragment in FORBIDDEN_RESULT_FRAGMENTS:
        if fragment in serialized:
            raise TracerFailure("Hardware tracer evidence contains private runtime data")


def _write_results(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _verify_results(path: Path, expected_commit: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TracerFailure("Hardware tracer result is not an object")
    _verify_payload(payload, expected_commit=expected_commit)
    print("Qwen3 hardware tracer evidence verified")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test-reference-authorization", action="store_true")
    parser.add_argument("--run-hardware-tracer", action="store_true")
    parser.add_argument("--verify-results")
    parser.add_argument("--expected-commit", default="")
    parser.add_argument("--deployment-branch", default=os.environ.get("OMEN_BRANCH", "main"))
    parser.add_argument("--web-base-url", default=DEFAULT_WEB_BASE_URL)
    parser.add_argument("--ai-base-url", default=DEFAULT_AI_BASE_URL)
    parser.add_argument("--phase005-reference", default=os.environ.get("RAYME_QWEN3_PHASE005_REFERENCE", ""))
    parser.add_argument("--phase005-transcript", default=os.environ.get("RAYME_QWEN3_PHASE005_TRANSCRIPT", ""))
    parser.add_argument("--phase005-authorization", default=os.environ.get("RAYME_QWEN3_PHASE005_AUTHORIZATION", ""))
    parser.add_argument("--work-dir", default=str(Path.cwd() / ".local" / "phase09-qwen3-tracer"))
    parser.add_argument("--output", default=str(Path(__file__).resolve().parent / "results" / "qwen3-hardware-tracer.json"))
    parser.add_argument("--timeout", type=float, default=900.0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.self_test_reference_authorization:
            _self_test_reference_authorization()
            return 0
        if args.verify_results:
            _verify_results(Path(args.verify_results), str(args.expected_commit or "").strip())
            return 0
        if args.run_hardware_tracer:
            payload = asyncio.run(_generate_hardware_evidence(args))
            _write_results(payload, Path(args.output))
            print(RESULT_MARKER + json.dumps(payload, separators=(",", ":"), sort_keys=True))
            return 0
        raise TracerFailure("A tracer operation is required")
    except TracerFailure as exc:
        print(f"FAIL: {exc}")
        return 1
    except Exception as exc:
        print(f"FAIL: unexpected tracer error ({exc.__class__.__name__})")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
