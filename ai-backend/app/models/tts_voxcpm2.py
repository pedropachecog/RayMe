from __future__ import annotations

import base64
import json
import os
import queue as thread_queue
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterable
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from app.models.gpu_runtime import require_torch_cuda_runtime
from app.models.tts_registry import (
    ImportGatedTtsAdapter,
    TtsAudioChunk,
    TtsSynthesisInput,
    TtsSynthesisOutput,
)


REQUIRED_PACKAGE = "voxcpm==2.0.2"
MODEL_ID = "openbmb/VoxCPM2"
WORKER_REQUEST_PREFIX = "__RAYME_VOXCPM2_REQUEST__"
WORKER_READY_PREFIX = "__RAYME_VOXCPM2_READY__"
WORKER_RESULT_PREFIX = "__RAYME_VOXCPM2_RESULT__"
WORKER_CHUNK_PREFIX = "__RAYME_VOXCPM2_CHUNK__"
WORKER_DONE_PREFIX = "__RAYME_VOXCPM2_DONE__"
WORKER_ERROR_PREFIX = "__RAYME_VOXCPM2_ERROR__"
WORKER_LOAD_TIMEOUT_SECONDS = 180.0
WORKER_SYNTHESIS_TIMEOUT_SECONDS = 120.0
WORKER_STREAM_EVENT_TIMEOUT_SECONDS = 60.0

ProcessFactory = Callable[..., subprocess.Popen[str]]


class VoxCpm2TtsAdapter(ImportGatedTtsAdapter):
    engine_id = "voxcpm2"
    required_modules = ("voxcpm",)
    synthesis_enabled = True

    def __init__(
        self,
        runtime_factory: Callable[[], Any] | None = None,
        process_factory: ProcessFactory | None = None,
    ) -> None:
        super().__init__()
        self._runtime_factory = runtime_factory
        self._runtime: Any | None = None
        self._process_factory = process_factory or subprocess.Popen
        self._worker: subprocess.Popen[str] | None = None
        self._worker_lines: thread_queue.Queue[str | None] | None = None

    def startup_self_test(self) -> None:
        self._ensure_runtime_available()

    def load(self) -> None:
        if self._runtime_factory is None:
            self._ensure_runtime_available()
            require_torch_cuda_runtime("VoxCPM2")
            self._ensure_worker_loaded()
            self.loaded = True
            return
        if self._runtime is None:
            self._runtime = self._build_runtime()
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False
        self._runtime = None
        self._stop_worker()

    def synthesize(self, request: TtsSynthesisInput) -> TtsSynthesisOutput:
        if self._runtime_factory is None:
            if not self.loaded:
                self.load()
            return self._synthesize_in_worker(request)
        if not self.loaded:
            self.load()
        runtime = self._runtime or self._build_runtime()
        self._runtime = runtime
        reference_transcript = (request.reference_transcript or "").strip()
        warning_codes: list[str] = []

        with tempfile.TemporaryDirectory(prefix="rayme-voxcpm2-") as tmp_dir:
            reference_path = Path(tmp_dir) / f"reference{_audio_suffix(request.reference_audio_content_type)}"
            reference_path.write_bytes(request.reference_audio)
            generate_kwargs = _build_generate_kwargs(
                request=request,
                reference_path=reference_path,
                reference_transcript=reference_transcript,
                warning_codes=warning_codes,
            )
            _ensure_librosa_load()
            generated = runtime.generate(**generate_kwargs)

        wav, sample_rate = _split_generate_result(generated, runtime)
        wav_array = np.asarray(wav, dtype=np.float32).flatten()
        if wav_array.size == 0:
            raise ValueError("VoxCPM2 synthesis failed")
        sample_rate = int(sample_rate)
        buffer = BytesIO()
        sf.write(buffer, wav_array, sample_rate, format="WAV")
        return TtsSynthesisOutput(
            engine_id=self.engine_id,
            wav_bytes=buffer.getvalue(),
            sample_rate=sample_rate,
            duration_ms=round((wav_array.size / float(sample_rate)) * 1000, 1),
            warning_codes=warning_codes,
            warnings=warning_codes,
        )

    def stream(self, request: TtsSynthesisInput) -> Iterable[TtsAudioChunk]:
        if self._runtime_factory is None:
            if not self.loaded:
                self.load()
            yield from self._stream_in_worker(request)
            return
        if not self.loaded:
            self.load()
        runtime = self._runtime or self._build_runtime()
        self._runtime = runtime
        reference_transcript = (request.reference_transcript or "").strip()
        warning_codes: list[str] = []
        started_at = time.perf_counter()
        chunk_index = 0

        with tempfile.TemporaryDirectory(prefix="rayme-voxcpm2-") as tmp_dir:
            reference_path = Path(tmp_dir) / f"reference{_audio_suffix(request.reference_audio_content_type)}"
            reference_path.write_bytes(request.reference_audio)
            generate_kwargs = _build_generate_kwargs(
                request=request,
                reference_path=reference_path,
                reference_transcript=reference_transcript,
                warning_codes=warning_codes,
            )
            _ensure_librosa_load()
            generate_streaming = getattr(runtime, "generate_streaming", None)
            if not callable(generate_streaming):
                raise ValueError("VoxCPM2 streaming synthesis failed")

            for generated in generate_streaming(**generate_kwargs):
                split = _try_split_streaming_result(generated, runtime)
                if split is None:
                    continue
                wav_array, sample_rate = split
                if wav_array.size == 0 or sample_rate <= 0:
                    continue

                buffer = BytesIO()
                sf.write(buffer, wav_array, sample_rate, format="WAV")
                yield TtsAudioChunk(
                    engine_id=self.engine_id,
                    chunk_index=chunk_index,
                    wav_bytes=buffer.getvalue(),
                    sample_rate=sample_rate,
                    duration_ms=round((wav_array.size / float(sample_rate)) * 1000, 1),
                    generated_at_ms=round((time.perf_counter() - started_at) * 1000, 1),
                    warning_codes=list(warning_codes),
                    warnings=list(warning_codes),
                )
                chunk_index += 1

        if chunk_index == 0:
            raise ValueError("VoxCPM2 streaming synthesis failed")

    def _ensure_worker_loaded(self) -> None:
        worker = self._ensure_worker()
        self._send_worker_request({"op": "load"})
        for line in self._iter_worker_lines(worker, timeout_seconds=WORKER_LOAD_TIMEOUT_SECONDS):
            if line.startswith(WORKER_READY_PREFIX):
                return
            if line.startswith(WORKER_ERROR_PREFIX):
                self._stop_worker()
                raise ValueError("VoxCPM2 worker failed")
        self._stop_worker()
        raise ValueError("VoxCPM2 worker failed")

    def _synthesize_in_worker(self, request: TtsSynthesisInput) -> TtsSynthesisOutput:
        worker = self._ensure_worker()
        self._send_worker_request({"op": "synthesize", "request": _worker_request_payload(request)})
        for line in self._iter_worker_lines(
            worker,
            timeout_seconds=WORKER_SYNTHESIS_TIMEOUT_SECONDS,
        ):
            if line.startswith(WORKER_RESULT_PREFIX):
                payload = json.loads(line[len(WORKER_RESULT_PREFIX) :])
                wav_bytes = base64.b64decode(payload.get("wav_b64") or b"", validate=True)
                return TtsSynthesisOutput(
                    engine_id=self.engine_id,
                    wav_bytes=wav_bytes,
                    sample_rate=int(payload["sample_rate"]),
                    duration_ms=float(payload["duration_ms"]),
                    warning_codes=list(payload.get("warning_codes") or []),
                    warnings=list(payload.get("warnings") or []),
                )
            if line.startswith(WORKER_ERROR_PREFIX):
                self._stop_worker()
                raise ValueError("VoxCPM2 synthesis failed")
        self._stop_worker()
        raise ValueError("VoxCPM2 synthesis failed")

    def _stream_in_worker(self, request: TtsSynthesisInput) -> Iterable[TtsAudioChunk]:
        worker = self._ensure_worker()
        yielded = 0
        self._send_worker_request({"op": "stream", "request": _worker_request_payload(request)})
        for line in self._iter_worker_lines(
            worker,
            timeout_seconds=WORKER_STREAM_EVENT_TIMEOUT_SECONDS,
        ):
            if line.startswith(WORKER_CHUNK_PREFIX):
                payload = json.loads(line[len(WORKER_CHUNK_PREFIX) :])
                yielded += 1
                yield TtsAudioChunk(
                    engine_id=self.engine_id,
                    chunk_index=int(payload["chunk_index"]),
                    wav_bytes=base64.b64decode(payload.get("wav_b64") or b"", validate=True),
                    sample_rate=int(payload["sample_rate"]),
                    duration_ms=float(payload["duration_ms"]),
                    generated_at_ms=float(payload["generated_at_ms"]),
                    warning_codes=list(payload.get("warning_codes") or []),
                    warnings=list(payload.get("warnings") or []),
                )
                continue
            if line.startswith(WORKER_DONE_PREFIX):
                if yielded == 0:
                    raise ValueError("VoxCPM2 streaming synthesis failed")
                return
            if line.startswith(WORKER_ERROR_PREFIX):
                self._stop_worker()
                raise ValueError("VoxCPM2 streaming synthesis failed")
        self._stop_worker()
        raise ValueError("VoxCPM2 streaming synthesis failed")

    def _ensure_worker(self) -> subprocess.Popen[str]:
        if self._worker is not None and self._worker.poll() is None:
            return self._worker

        ai_backend_root = Path(__file__).resolve().parents[2]
        env = dict(os.environ)
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(ai_backend_root)
            if not existing_pythonpath
            else f"{ai_backend_root}{os.pathsep}{existing_pythonpath}"
        )
        self._worker = self._process_factory(
            [sys.executable, "-m", "app.models.tts_voxcpm2_worker"],
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
            name="rayme-voxcpm2-worker-stdout",
            daemon=True,
        ).start()

    def _send_worker_request(self, payload: dict[str, Any]) -> None:
        worker = self._ensure_worker()
        if worker.stdin is None:
            self._stop_worker()
            raise ValueError("VoxCPM2 worker failed")
        try:
            worker.stdin.write(WORKER_REQUEST_PREFIX + json.dumps(payload, separators=(",", ":")) + "\n")
            worker.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            self._stop_worker()
            raise ValueError("VoxCPM2 worker failed") from exc

    def _iter_worker_lines(
        self,
        worker: subprocess.Popen[str],
        *,
        timeout_seconds: float,
    ) -> Iterable[str]:
        lines = self._worker_lines
        if lines is None:
            return
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = max(deadline - time.monotonic(), 0.0)
            if remaining <= 0:
                self._stop_worker()
                raise ValueError("VoxCPM2 worker timed out")
            try:
                line = lines.get(timeout=remaining)
            except thread_queue.Empty as exc:
                self._stop_worker()
                raise ValueError("VoxCPM2 worker timed out") from exc
            if line is None:
                if worker.poll() is not None:
                    return
                continue
            if not line.startswith("__RAYME_VOXCPM2_"):
                continue
            deadline = time.monotonic() + timeout_seconds
            yield line

    def _stop_worker(self) -> None:
        worker = self._worker
        self._worker = None
        self._worker_lines = None
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

    def _build_runtime(self) -> Any:
        if self._runtime_factory is not None:
            return self._runtime_factory()
        require_torch_cuda_runtime("VoxCPM2")
        from voxcpm import VoxCPM

        runtime = VoxCPM.from_pretrained(MODEL_ID, load_denoiser=False)
        _assert_runtime_uses_cuda(runtime)
        return runtime


def _assert_runtime_uses_cuda(runtime: Any) -> None:
    device_types: set[str] = set()
    for candidate in (runtime, getattr(runtime, "tts_model", None), getattr(runtime, "model", None)):
        if candidate is None or not hasattr(candidate, "parameters"):
            continue
        try:
            for parameter in candidate.parameters():
                device = getattr(parameter, "device", None)
                if device is not None:
                    device_types.add(str(getattr(device, "type", device)))
                break
        except Exception:
            continue
    if "cuda" not in device_types:
        raise RuntimeError("VoxCPM2 runtime did not expose CUDA-loaded parameters")


def _build_generate_kwargs(
    *,
    request: TtsSynthesisInput,
    reference_path: Path,
    reference_transcript: str,
    warning_codes: list[str],
) -> dict[str, Any]:
    style_prompt = (request.voxcpm2_style_prompt or "").strip()
    text = request.text
    if style_prompt and request.voxcpm2_cloning_mode != "transcript_guided":
        text = f"({style_prompt}){text}"

    kwargs: dict[str, Any] = {
        "text": text,
        "cfg_value": request.voxcpm2_cfg_value,
        "inference_timesteps": request.voxcpm2_inference_timesteps,
        "normalize": request.voxcpm2_normalize,
        "denoise": request.voxcpm2_denoise,
    }

    if request.voxcpm2_cloning_mode == "transcript_guided" and reference_transcript:
        kwargs["prompt_wav_path"] = str(reference_path)
        kwargs["prompt_text"] = reference_transcript
        kwargs["reference_wav_path"] = str(reference_path)
    else:
        kwargs["reference_wav_path"] = str(reference_path)
        if request.voxcpm2_cloning_mode != "reference_only" and not reference_transcript:
            warning_codes.append("voxcpm2_reference_only_without_transcript")
    return kwargs


def _split_generate_result(generated: Any, runtime: Any) -> tuple[Any, int]:
    if isinstance(generated, tuple) and len(generated) >= 2:
        return generated[0], int(generated[1])
    sample_rate = int(getattr(runtime, "sample_rate", 48_000))
    return generated, sample_rate


def _try_split_streaming_result(generated: Any, runtime: Any) -> tuple[np.ndarray, int] | None:
    try:
        wav, sample_rate = _split_generate_result(generated, runtime)
        sample_rate = int(sample_rate)
        wav_array = np.asarray(wav, dtype=np.float32).flatten()
    except (TypeError, ValueError):
        return None
    return wav_array, sample_rate


def _worker_request_payload(request: TtsSynthesisInput) -> dict[str, Any]:
    return {
        "text": request.text,
        "reference_audio_b64": base64.b64encode(request.reference_audio).decode("ascii"),
        "reference_audio_content_type": request.reference_audio_content_type,
        "reference_transcript": request.reference_transcript,
        "speech_speed": request.speech_speed,
        "voxcpm2_cloning_mode": request.voxcpm2_cloning_mode,
        "voxcpm2_style_prompt": request.voxcpm2_style_prompt,
        "voxcpm2_cfg_value": request.voxcpm2_cfg_value,
        "voxcpm2_inference_timesteps": request.voxcpm2_inference_timesteps,
        "voxcpm2_normalize": request.voxcpm2_normalize,
        "voxcpm2_denoise": request.voxcpm2_denoise,
    }


def _ensure_librosa_load() -> None:
    try:
        import librosa  # type: ignore[import]
    except Exception:
        return
    if callable(getattr(librosa, "load", None)):
        return

    def _soundfile_load(
        path: str,
        *,
        sr: int | None = 22050,
        mono: bool = True,
        dtype: str = "float32",
        **_: Any,
    ) -> tuple[np.ndarray, int]:
        audio, source_sr = sf.read(path, dtype=dtype, always_2d=False)
        audio_array = np.asarray(audio, dtype=np.float32)
        if mono and audio_array.ndim > 1:
            audio_array = audio_array.mean(axis=1)
        elif not mono and audio_array.ndim == 1:
            audio_array = audio_array.reshape(-1, 1)
        target_sr = int(sr) if sr else int(source_sr)
        if target_sr != int(source_sr):
            audio_array = _resample_linear(audio_array, int(source_sr), target_sr)
        return audio_array, target_sr

    librosa.load = _soundfile_load  # type: ignore[attr-defined]


def _resample_linear(audio: np.ndarray, source_sr: int, target_sr: int) -> np.ndarray:
    if source_sr <= 0 or target_sr <= 0 or audio.size == 0:
        return audio.astype(np.float32, copy=False)
    if audio.ndim == 1:
        sample_count = max(int(round(audio.shape[0] * target_sr / source_sr)), 1)
        source_x = np.linspace(0.0, 1.0, num=audio.shape[0], endpoint=False)
        target_x = np.linspace(0.0, 1.0, num=sample_count, endpoint=False)
        return np.interp(target_x, source_x, audio).astype(np.float32)
    channels = [
        _resample_linear(audio[:, channel], source_sr, target_sr)
        for channel in range(audio.shape[1])
    ]
    return np.stack(channels, axis=1).astype(np.float32)


def _audio_suffix(content_type: str | None) -> str:
    return {
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/flac": ".flac",
        "audio/x-flac": ".flac",
    }.get((content_type or "").lower(), ".wav")
