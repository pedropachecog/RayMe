#!/usr/bin/env python3
"""Generate Phase 8 live VoxCPM2-vs-F5 streaming call-flow evidence.

Run with the AI backend environment so aiortc is available, for example:

    uv run --project ai-backend python .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-run-call-flow-evidence.py
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import ssl
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PHASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PHASE_DIR.parents[2]
RESULTS_DIR = PHASE_DIR / "results"
CALL_FLOW_JSON = RESULTS_DIR / "voxcpm2-live-streaming-call-flow.json"
DEFAULT_WARM_SAMPLES = 3
DEFAULT_REFERENCE_AUDIO = (
    REPO_ROOT
    / ".planning"
    / "phases"
    / "00-measurement-gate"
    / "probes"
    / "fixtures"
    / "short_ref_audio.wav"
)
DEFAULT_REFERENCE_TRANSCRIPT = (
    "I passed up a job at the Vulcan Science Academy a few months ago, "
    "or maybe I will just live on a station for a while."
)
DEFAULT_CALL_TEXT = "Phase 8 live streaming call-flow evidence is now queued."
DEFAULT_WEB_BASE_URL = "https://192.168.1.199:8443"
DEFAULT_AI_BASE_URL = "https://192.168.1.199:9443"
ENGINE_ORDER = ["f5", "voxcpm2"]
VOXCPM2_SETTINGS = {
    "voxcpm2_cloning_mode": "transcript_guided",
    "voxcpm2_style_prompt": "",
    "voxcpm2_cfg_value": 2.0,
    "voxcpm2_inference_timesteps": 10,
    "voxcpm2_normalize": False,
    "voxcpm2_denoise": False,
}
FORBIDDEN_LEAK_PATTERNS = (
    "Traceback",
    'File "',
    "C:\\",
    "/home/",
    ".cache",
    "huggingface",
    "openbmb/VoxCPM2",
)


@dataclass(frozen=True)
class ApiResponse:
    status: int
    payload: dict[str, Any]


class EvidenceFailure(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


class RayMeApi:
    def __init__(self, *, web_base_url: str, ai_base_url: str, timeout: float) -> None:
        self.web_base_url = web_base_url.rstrip("/")
        self.ai_base_url = ai_base_url.rstrip("/")
        self.timeout = timeout
        self.ssl_context = ssl._create_unverified_context()

    def post_json(self, base_url: str, path: str, payload: dict[str, Any]) -> ApiResponse:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = Request(
            f"{base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        return self._open_json(request)

    def _open_json(self, request: Request) -> ApiResponse:
        try:
            with urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
                data = response.read()
                status = int(response.status)
        except HTTPError as exc:
            data = exc.read()
            status = int(exc.code)
        except URLError as exc:
            raise EvidenceFailure("runtime_unavailable", _sanitize_error(exc)) from exc
        try:
            payload = json.loads(data.decode("utf-8")) if data else {}
        except json.JSONDecodeError as exc:
            raise EvidenceFailure("runtime_unavailable", f"non-json response status={status}") from exc
        return ApiResponse(status=status, payload=payload if isinstance(payload, dict) else {"value": payload})


async def _create_audio_offer() -> tuple[Any, dict[str, str]]:
    from aiortc import RTCConfiguration, RTCPeerConnection

    pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[]))
    pc.createDataChannel("rayme-events")
    pc.addTransceiver("audio", direction="recvonly")
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    return pc, {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


def _require_ok(response: ApiResponse, *, operation: str) -> dict[str, Any]:
    if 200 <= response.status < 300:
        return response.payload
    raise EvidenceFailure(_failure_category(response.payload), f"{operation} failed with status {response.status}")


def _failure_category(payload: dict[str, Any]) -> str:
    detail = payload.get("detail")
    if isinstance(detail, dict):
        code = detail.get("code")
    elif isinstance(payload.get("error"), dict):
        code = payload["error"].get("code")
    else:
        code = None
    if code in {"tts_failed", "call_tts_failed", "voxcpm2_unavailable", "runtime_unavailable", "validation_failed"}:
        return str(code)
    if code in {"invalid_tts_request", "invalid_voice_metadata"}:
        return "validation_failed"
    return "runtime_unavailable"


def _sanitize_error(exc: BaseException) -> str:
    text = f"{exc.__class__.__name__}: {exc}"
    for pattern in FORBIDDEN_LEAK_PATTERNS:
        text = text.replace(pattern, "[redacted]")
    return text[:240]


def _contains_raw_error_leak(value: Any) -> bool:
    text = json.dumps(value, sort_keys=True)
    return any(pattern in text for pattern in FORBIDDEN_LEAK_PATTERNS)


def _require_number(value: Any, *, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise EvidenceFailure("validation_failed", f"{label} must be a number")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise EvidenceFailure("validation_failed", f"{label} must be finite")
    return number


def _median(values: list[float]) -> float:
    if not values:
        raise EvidenceFailure("validation_failed", "median requires at least one value")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return round(float(ordered[middle]), 1)
    return round((ordered[middle - 1] + ordered[middle]) / 2.0, 1)


def _read_reference_audio(path: str) -> bytes:
    reference_audio = Path(path)
    if not reference_audio.is_file():
        raise EvidenceFailure("validation_failed", "reference audio fixture is missing")
    content = reference_audio.read_bytes()
    if not content:
        raise EvidenceFailure("validation_failed", "reference audio fixture is empty")
    return content


def _offer_payload(*, session_id: str, engine: str, voice_id: str, offer: dict[str, str]) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "thread_id": "phase08-live-streaming-call-flow",
        "voice_id": voice_id,
        "engine_id": engine,
        "prompt_messages": [
            {
                "role": "system",
                "content": "Phase 8 live streaming evidence session.",
            }
        ],
        "offer": offer,
    }


def _speak_payload(
    *,
    turn_id: str,
    text: str,
    voice_id: str,
    engine: str,
    reference_audio_b64: str,
    reference_transcript: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "turn_id": turn_id,
        "text": text,
        "voice_id": voice_id,
        "engine_id": engine,
        "final_chunk": True,
        "reference_audio_b64": reference_audio_b64,
        "reference_transcript": reference_transcript,
        "reference_audio_content_type": "audio/wav",
    }
    if engine == "voxcpm2":
        payload.update(VOXCPM2_SETTINGS)
    return payload


async def _run_speak_call(
    api: RayMeApi,
    *,
    engine: str,
    sample_index: int,
    measured: bool,
    reference_audio_b64: str,
    reference_transcript: str,
    call_text: str,
) -> dict[str, Any] | None:
    session_id = f"phase08-{engine}-{uuid.uuid4().hex[:20]}"
    turn_id = f"turn-{uuid.uuid4().hex[:16]}"
    voice_id = f"phase08-{engine}-voice"
    pc = None
    try:
        pc, offer = await _create_audio_offer()
        _require_ok(
            api.post_json(
                api.ai_base_url,
                "/webrtc/offer",
                _offer_payload(session_id=session_id, engine=engine, voice_id=voice_id, offer=offer),
            ),
            operation=f"{engine} webrtc offer",
        )
        speak_request = _speak_payload(
            turn_id=turn_id,
            text=call_text,
            voice_id=voice_id,
            engine=engine,
            reference_audio_b64=reference_audio_b64,
            reference_transcript=reference_transcript,
        )
        request_started = time.perf_counter()
        speak_payload = _require_ok(
            api.post_json(api.ai_base_url, f"/webrtc/sessions/{session_id}/speak", speak_request),
            operation=f"{engine} call speak",
        )
        http_elapsed_ms = round((time.perf_counter() - request_started) * 1000.0, 1)
    finally:
        if pc is not None:
            close = getattr(pc, "close", None)
            if callable(close):
                result = close()
                if asyncio.iscoroutine(result):
                    await result

    if not measured:
        return None

    event = speak_payload["event"]
    first_audio_metrics = event["ai_audio_started_event"]["tts_playback"]
    final_metrics = event["tts_playback_final"]
    warm_call_ttfa_ms = round(
        _require_number(first_audio_metrics["ai_audio_started_ms"], label=f"{engine} ai_audio_started_ms"),
        1,
    )
    return {
        "engine": engine,
        "sample_index": sample_index,
        "session_id": session_id,
        "turn_id": turn_id,
        "warm_call_ttfa_ms": warm_call_ttfa_ms,
        "http_elapsed_ms": http_elapsed_ms,
        "ai_audio_started_event": event["ai_audio_started_event"],
        "tts_playback_final": final_metrics,
    }


def _summary(samples: list[dict[str, Any]], *, warm_samples: int) -> dict[str, Any]:
    by_engine: dict[str, list[float]] = {engine: [] for engine in ENGINE_ORDER}
    for sample in samples:
        engine = str(sample.get("engine") or "")
        if engine in by_engine:
            by_engine[engine].append(_require_number(sample.get("warm_call_ttfa_ms"), label=f"{engine} warm_call_ttfa_ms"))
    for engine, values in by_engine.items():
        if len(values) != warm_samples:
            raise EvidenceFailure("validation_failed", f"{engine} measured sample count mismatch")

    f5_median = _median(by_engine["f5"])
    voxcpm2_median = _median(by_engine["voxcpm2"])
    return {
        "warm_sample_count": warm_samples,
        "voxcpm2_warm_call_ttfa_ms": voxcpm2_median,
        "f5_warm_call_ttfa_ms": f5_median,
        "voxcpm2_beats_f5": voxcpm2_median < f5_median,
    }


async def generate_evidence(args: argparse.Namespace) -> dict[str, Any]:
    warm_samples = int(args.warm_samples)
    if warm_samples < 1:
        raise EvidenceFailure("validation_failed", "--warm-samples must be >= 1")
    api = RayMeApi(web_base_url=args.web_base_url, ai_base_url=args.ai_base_url, timeout=args.timeout)
    reference_audio_b64 = base64.b64encode(_read_reference_audio(args.reference_audio)).decode("ascii")
    reference_transcript = str(args.reference_transcript or "").strip()
    if not reference_transcript:
        raise EvidenceFailure("validation_failed", "reference transcript is required")

    samples: list[dict[str, Any]] = []
    for engine in ENGINE_ORDER:
        await _run_speak_call(
            api,
            engine=engine,
            sample_index=0,
            measured=False,
            reference_audio_b64=reference_audio_b64,
            reference_transcript=reference_transcript,
            call_text=args.call_text,
        )
        for sample_index in range(1, warm_samples + 1):
            sample = await _run_speak_call(
                api,
                engine=engine,
                sample_index=sample_index,
                measured=True,
                reference_audio_b64=reference_audio_b64,
                reference_transcript=reference_transcript,
                call_text=args.call_text,
            )
            if sample is not None:
                samples.append(sample)

    payload = {
        "schema_version": 1,
        "phase": "08",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "web_base_url": "configured-web-ui",
        "ai_base_url": "configured-ai-backend",
        "runtime": {
            "engine_order": list(ENGINE_ORDER),
            "warmup_samples_per_engine": 1,
            "measured_warm_samples_per_engine": warm_samples,
            "reference_audio_source": str(args.reference_audio),
        },
        "samples": samples,
        "summary": _summary(samples, warm_samples=warm_samples),
    }
    if _contains_raw_error_leak(payload):
        raise EvidenceFailure("validation_failed", "call-flow payload contains unsanitized runtime detail")
    return payload


def write_evidence(payload: dict[str, Any], output: str | Path) -> None:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warm-samples", type=int, default=DEFAULT_WARM_SAMPLES)
    parser.add_argument("--web-base-url", default=DEFAULT_WEB_BASE_URL)
    parser.add_argument("--ai-base-url", default=DEFAULT_AI_BASE_URL)
    parser.add_argument("--reference-audio", default=str(DEFAULT_REFERENCE_AUDIO))
    parser.add_argument("--reference-transcript", default=DEFAULT_REFERENCE_TRANSCRIPT)
    parser.add_argument("--call-text", default=DEFAULT_CALL_TEXT)
    parser.add_argument("--output", default=str(CALL_FLOW_JSON))
    parser.add_argument("--timeout", type=float, default=300.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = asyncio.run(generate_evidence(args))
    except EvidenceFailure as exc:
        print(f"FAIL: {exc.category}: {_sanitize_error(exc)}")
        return 1
    write_evidence(payload, args.output)
    output_path = Path(args.output)
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
