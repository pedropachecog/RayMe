from __future__ import annotations

import base64
import json
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from app.models.gpu_runtime import require_torch_cuda_runtime
from app.models.tts_registry import TtsSynthesisInput
from app.models.tts_voxcpm2 import (
    MODEL_ID,
    WORKER_CHUNK_PREFIX,
    WORKER_DONE_PREFIX,
    WORKER_ERROR_PREFIX,
    WORKER_READY_PREFIX,
    WORKER_REQUEST_PREFIX,
    WORKER_RESULT_PREFIX,
    _assert_runtime_uses_cuda,
    _audio_suffix,
    _build_generate_kwargs,
    _ensure_librosa_load,
    _split_generate_result,
    _try_split_streaming_result,
)


_RUNTIME: Any | None = None


def main() -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line.startswith(WORKER_REQUEST_PREFIX):
            continue
        try:
            payload = json.loads(line[len(WORKER_REQUEST_PREFIX) :])
            op = payload.get("op")
            if op == "load":
                _runtime()
                _emit(WORKER_READY_PREFIX, {"ok": True})
            elif op == "synthesize":
                _handle_synthesize(payload["request"])
            elif op == "stream":
                _handle_stream(payload["request"])
            else:
                raise ValueError("unknown VoxCPM2 worker operation")
        except Exception:
            _emit(WORKER_ERROR_PREFIX, {"code": "voxcpm2_worker_failed"})
    return 0


def _runtime() -> Any:
    global _RUNTIME
    if _RUNTIME is None:
        require_torch_cuda_runtime("VoxCPM2")
        from voxcpm import VoxCPM

        runtime = VoxCPM.from_pretrained(MODEL_ID, load_denoiser=False)
        _assert_runtime_uses_cuda(runtime)
        _RUNTIME = runtime
    return _RUNTIME


def _handle_synthesize(raw_request: dict[str, Any]) -> None:
    runtime = _runtime()
    request = _request_from_payload(raw_request)
    wav, sample_rate, warning_codes = _generate(request, runtime)
    wav_array = np.asarray(wav, dtype=np.float32).flatten()
    if wav_array.size == 0:
        raise ValueError("VoxCPM2 synthesis failed")
    buffer = BytesIO()
    sf.write(buffer, wav_array, int(sample_rate), format="WAV")
    _emit(
        WORKER_RESULT_PREFIX,
        {
            "engine_id": "voxcpm2",
            "wav_b64": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "sample_rate": int(sample_rate),
            "duration_ms": round((wav_array.size / float(sample_rate)) * 1000, 1),
            "warning_codes": warning_codes,
            "warnings": warning_codes,
        },
    )


def _handle_stream(raw_request: dict[str, Any]) -> None:
    runtime = _runtime()
    request = _request_from_payload(raw_request)
    warning_codes: list[str] = []
    started_at = time.perf_counter()
    chunk_index = 0

    with tempfile.TemporaryDirectory(prefix="rayme-voxcpm2-worker-") as tmp_dir:
        reference_path = _write_reference_audio(request, tmp_dir)
        generate_kwargs = _build_generate_kwargs(
            request=request,
            reference_path=reference_path,
            reference_transcript=(request.reference_transcript or "").strip(),
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
            _emit(
                WORKER_CHUNK_PREFIX,
                {
                    "engine_id": "voxcpm2",
                    "chunk_index": chunk_index,
                    "wav_b64": base64.b64encode(buffer.getvalue()).decode("ascii"),
                    "sample_rate": int(sample_rate),
                    "duration_ms": round((wav_array.size / float(sample_rate)) * 1000, 1),
                    "generated_at_ms": round((time.perf_counter() - started_at) * 1000, 1),
                    "warning_codes": list(warning_codes),
                    "warnings": list(warning_codes),
                },
            )
            chunk_index += 1

    if chunk_index == 0:
        raise ValueError("VoxCPM2 streaming synthesis failed")
    _emit(WORKER_DONE_PREFIX, {"chunk_count": chunk_index})


def _generate(request: TtsSynthesisInput, runtime: Any) -> tuple[Any, int, list[str]]:
    warning_codes: list[str] = []
    with tempfile.TemporaryDirectory(prefix="rayme-voxcpm2-worker-") as tmp_dir:
        reference_path = _write_reference_audio(request, tmp_dir)
        generate_kwargs = _build_generate_kwargs(
            request=request,
            reference_path=reference_path,
            reference_transcript=(request.reference_transcript or "").strip(),
            warning_codes=warning_codes,
        )
        _ensure_librosa_load()
        generated = runtime.generate(**generate_kwargs)
    wav, sample_rate = _split_generate_result(generated, runtime)
    return wav, int(sample_rate), warning_codes


def _request_from_payload(payload: dict[str, Any]) -> TtsSynthesisInput:
    return TtsSynthesisInput(
        text=payload["text"],
        reference_audio=base64.b64decode(payload["reference_audio_b64"], validate=True),
        reference_audio_content_type=payload.get("reference_audio_content_type"),
        reference_transcript=payload.get("reference_transcript"),
        speech_speed=float(payload.get("speech_speed", 1.0)),
        voxcpm2_cloning_mode=payload.get("voxcpm2_cloning_mode", "auto"),
        voxcpm2_style_prompt=payload.get("voxcpm2_style_prompt"),
        voxcpm2_cfg_value=float(payload.get("voxcpm2_cfg_value", 2.0)),
        voxcpm2_inference_timesteps=int(payload.get("voxcpm2_inference_timesteps", 10)),
        voxcpm2_normalize=bool(payload.get("voxcpm2_normalize", True)),
        voxcpm2_denoise=bool(payload.get("voxcpm2_denoise", True)),
    )


def _write_reference_audio(request: TtsSynthesisInput, tmp_dir: str) -> Path:
    reference_path = Path(tmp_dir) / f"reference{_audio_suffix(request.reference_audio_content_type)}"
    reference_path.write_bytes(request.reference_audio)
    return reference_path


def _emit(prefix: str, payload: dict[str, Any]) -> None:
    print(prefix + json.dumps(payload, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
