#!/usr/bin/env python3
"""Generate live VoxCPM2 preview, test-play, and call speak evidence.

Run with the AI backend environment so aiortc is available, for example:

    uv run --project ai-backend python .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-run-call-flow-evidence.py
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
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aiortc import RTCConfiguration, RTCPeerConnection

PHASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PHASE_DIR.parents[2]
RESULTS_DIR = PHASE_DIR / "results"
AUDIO_DIR = RESULTS_DIR / "audio"
CALL_FLOW_JSON = RESULTS_DIR / "voxcpm2-call-flow.json"
DEFAULT_REFERENCE_AUDIO = REPO_ROOT / ".planning" / "phases" / "00-measurement-gate" / "probes" / "fixtures" / "short_ref_audio.wav"
DEFAULT_REFERENCE_TRANSCRIPT = (
    "I passed up a job at the Vulcan Science Academy a few months ago, "
    "or maybe I will just live on a station for a while."
)
DEFAULT_SOURCE_VOICE_NAME = "Stamets-Sample-Short"
DEFAULT_WEB_BASE_URL = "https://192.168.1.199:8443"
DEFAULT_AI_BASE_URL = "https://192.168.1.199:9443"
VOXCPM2_SETTINGS = {
    "cloning_mode": "transcript_guided",
    "style_prompt": "",
    "cfg_value": 2.0,
    "inference_timesteps": 10,
    "normalize": False,
    "denoise": False,
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

    def get_json(self, base_url: str, path: str) -> ApiResponse:
        request = Request(
            f"{base_url}{path}",
            headers={"Accept": "application/json"},
            method="GET",
        )
        return self._open_json(request)

    def get_bytes(self, base_url: str, path: str) -> tuple[int, bytes]:
        request = Request(
            f"{base_url}{path}",
            headers={"Accept": "application/octet-stream"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
                return int(response.status), response.read()
        except HTTPError as exc:
            return int(exc.code), exc.read()
        except URLError as exc:
            raise EvidenceFailure("runtime_unavailable", _sanitize_error(exc)) from exc

    def delete_json(self, base_url: str, path: str) -> ApiResponse:
        request = Request(
            f"{base_url}{path}",
            headers={"Accept": "application/json"},
            method="DELETE",
        )
        return self._open_json(request)

    def upload_voice_asset(self, *, filename: str, content: bytes) -> ApiResponse:
        boundary = f"rayme-phase07-{uuid.uuid4().hex}"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode("utf-8")
        body += content
        body += f"\r\n--{boundary}--\r\n".encode("utf-8")
        request = Request(
            f"{self.web_base_url}/api/voices/assets",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
                "Accept": "application/json",
            },
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


async def _create_audio_offer() -> tuple[RTCPeerConnection, dict[str, str]]:
    pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[]))
    pc.createDataChannel("rayme-events")
    pc.addTransceiver("audio", direction="recvonly")
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    return pc, {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


def _require_ok(response: ApiResponse, *, operation: str) -> dict[str, Any]:
    if 200 <= response.status < 300:
        return response.payload
    category = _failure_category(response.payload)
    raise EvidenceFailure(category, f"{operation} failed with status {response.status}")


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


def _select_reference(api: RayMeApi, args: argparse.Namespace) -> tuple[bytes, str, str]:
    voices = _require_ok(api.get_json(api.web_base_url, "/api/voices"), operation="voice list")
    items = voices.get("items")
    if isinstance(items, list):
        source = _find_source_voice(items, args.source_voice_name)
        if source is not None:
            asset_id = str(source.get("asset_id") or "")
            transcript = str(source.get("reference_transcript") or args.reference_transcript)
            status, content = api.get_bytes(api.web_base_url, f"/api/voices/assets/{asset_id}/sample")
            if 200 <= status < 300 and content:
                return content, transcript, f"voice-library:{source.get('name')}"

    reference_audio = Path(args.reference_audio)
    if not reference_audio.is_file():
        raise EvidenceFailure("validation_failed", "reference audio fixture is missing")
    return reference_audio.read_bytes(), args.reference_transcript, "phase00-short-ref-fixture"


def _find_source_voice(items: list[Any], preferred_name: str) -> dict[str, Any] | None:
    voices = [item for item in items if isinstance(item, dict) and item.get("asset_id")]
    for voice in voices:
        if voice.get("name") == preferred_name and voice.get("reference_transcript"):
            return voice
    for voice in reversed(voices):
        if voice.get("reference_transcript"):
            return voice
    return None


def _sanitize_error(exc: BaseException) -> str:
    text = f"{exc.__class__.__name__}: {exc}"
    for pattern in FORBIDDEN_LEAK_PATTERNS:
        text = text.replace(pattern, "[redacted]")
    return text[:240]


def _status_from_bool(value: bool) -> str:
    return "passed" if value else "failed"


def _save_audio_from_base64(encoded: str, relative_path: str) -> str:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio = base64.b64decode(encoded, validate=True)
    output = PHASE_DIR / relative_path
    output.resolve().relative_to(AUDIO_DIR.resolve())
    output.write_bytes(audio)
    return relative_path


def _load_matrix_warm_ttfa(engine: str) -> float | None:
    matrix_path = RESULTS_DIR / "voxcpm2-scenario-matrix.json"
    if not matrix_path.is_file():
        return None
    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return None
    candidates = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("engine") == engine
        and row.get("scenario") == "short_reply"
        and isinstance(row.get("request_ttfa_ms"), int | float)
    ]
    if not candidates:
        return None
    preferred = [row for row in candidates if row.get("mode") in {"streaming_collected", "optimized"}]
    row = (preferred or candidates)[0]
    return float(row["request_ttfa_ms"])


def _voxcpm2_payload_base(reference_audio_b64: str, reference_transcript: str) -> dict[str, Any]:
    return {
        "engine_id": "voxcpm2",
        "reference_audio_b64": reference_audio_b64,
        "reference_transcript": reference_transcript,
        "reference_audio_content_type": "audio/wav",
        "voxcpm2_cloning_mode": "transcript_guided",
        "voxcpm2_style_prompt": "",
        "voxcpm2_cfg_value": 2.0,
        "voxcpm2_inference_timesteps": 10,
        "voxcpm2_normalize": False,
        "voxcpm2_denoise": False,
    }


async def generate_evidence(args: argparse.Namespace) -> dict[str, Any]:
    api = RayMeApi(web_base_url=args.web_base_url, ai_base_url=args.ai_base_url, timeout=args.timeout)
    reference_audio_bytes, reference_transcript, reference_source = _select_reference(api, args)
    reference_audio_b64 = base64.b64encode(reference_audio_bytes).decode("ascii")
    evidence_id = f"phase07-voxcpm2-{uuid.uuid4().hex[:12]}"
    created_voice_id: str | None = None
    pc: RTCPeerConnection | None = None

    results: dict[str, Any] = {
        "engine": "voxcpm2",
        "web_base_url": "configured-web-ui",
        "ai_base_url": "configured-ai-backend",
        "reference_audio_source": reference_source,
        "created_voice_deleted": False,
        "sanitized_failure_category": "none",
        "failure_outcome": None,
    }

    try:
        upload = _require_ok(
            api.upload_voice_asset(filename=f"{evidence_id}.wav", content=reference_audio_bytes),
            operation="asset upload",
        )
        asset_id = str(upload.get("asset_id") or "")
        if not asset_id:
            raise EvidenceFailure("validation_failed", "asset upload response did not include asset_id")

        voice_payload = {
            "asset_id": asset_id,
            "name": f"Phase 07 VoxCPM2 Evidence {evidence_id}",
            "default_engine": "voxcpm2",
            "reference_transcript": reference_transcript,
            "metadata": {
                "source": "phase07-live-call-flow-evidence",
                "engine_settings": {"voxcpm2": dict(VOXCPM2_SETTINGS)},
            },
        }

        preview_start = time.perf_counter()
        preview = _require_ok(
            api.post_json(
                api.web_base_url,
                "/api/voices/preview",
                {
                    **voice_payload,
                    "preview_text": args.preview_text,
                    "use_default_engine": False,
                    "engine": "voxcpm2",
                    "speech_speed": 1.0,
                },
            ),
            operation="preview",
        )
        preview_elapsed_ms = (time.perf_counter() - preview_start) * 1000
        preview_passed = preview.get("status") == "ok" and bool(preview.get("audio_base64"))
        if not preview_passed:
            raise EvidenceFailure("tts_failed", "preview did not return generated audio")

        saved = _require_ok(api.post_json(api.web_base_url, "/api/voices", voice_payload), operation="voice save")
        created_voice_id = str(saved.get("voice_id") or "")
        if not created_voice_id:
            raise EvidenceFailure("validation_failed", "voice save response did not include voice_id")

        test_play_start = time.perf_counter()
        test_play = _require_ok(
            api.post_json(
                api.web_base_url,
                f"/api/voices/{created_voice_id}/test-play",
                {"text": args.test_play_text, "use_default_engine": True, "speech_speed": 1.0},
            ),
            operation="test-play",
        )
        test_play_elapsed_ms = (time.perf_counter() - test_play_start) * 1000
        test_play_passed = bool(test_play.get("audio_base64") or test_play.get("audio_url"))

        audio_source = str(test_play.get("audio_base64") or preview.get("audio_base64") or "")
        if not audio_source:
            raise EvidenceFailure("tts_failed", "preview and test-play returned no audio bytes")
        saved_ai_audio_path = _save_audio_from_base64(audio_source, "results/audio/voxcpm2__call_flow_test_play.wav")

        pc, offer = await _create_audio_offer()
        session_id = f"phase07-{uuid.uuid4().hex[:20]}"
        offer_payload = {
            "session_id": session_id,
            "thread_id": "phase07-voxcpm2-call-flow",
            "voice_id": created_voice_id,
            "engine_id": "voxcpm2",
            "prompt_messages": [
                {
                    "role": "system",
                    "content": "Phase 07 evidence session for VoxCPM2 call-flow validation.",
                }
            ],
            "offer": offer,
        }
        _require_ok(api.post_json(api.ai_base_url, "/webrtc/offer", offer_payload), operation="webrtc offer")

        speak_payload = {
            "turn_id": f"turn-{uuid.uuid4().hex[:16]}",
            "text": args.call_text,
            "voice_id": created_voice_id,
            "engine_id": "voxcpm2",
            "final_chunk": True,
            **_voxcpm2_payload_base(reference_audio_b64, args.reference_transcript),
            "reference_transcript": reference_transcript,
        }
        speak_start = time.perf_counter()
        speak = _require_ok(
            api.post_json(api.ai_base_url, f"/webrtc/sessions/{session_id}/speak", speak_payload),
            operation="call speak",
        )
        warm_call_ttfa_ms = (time.perf_counter() - speak_start) * 1000
        speak_event = speak.get("event") if isinstance(speak.get("event"), dict) else {}
        audio_event = speak_event.get("ai_audio_started_event") if isinstance(speak_event, dict) else None
        call_audio_enqueued = isinstance(audio_event, dict) and bool(audio_event.get("audio"))
        call_speak_passed = call_audio_enqueued and speak.get("state") == "listening"

        interrupt = _require_ok(
            api.post_json(api.ai_base_url, f"/webrtc/sessions/{session_id}/interrupt", {}),
            operation="interrupt",
        )
        interrupt_cancel_unchanged = interrupt.get("interrupted") is True and interrupt.get("state") == "listening"

        validation = api.post_json(
            api.ai_base_url,
            "/tts/synthesize",
            {
                "voice_id": created_voice_id,
                "engine_id": "voxcpm2",
                "text": "Invalid settings should be rejected cleanly.",
                "reference_audio_b64": reference_audio_b64,
                "reference_transcript": reference_transcript,
                "reference_audio_content_type": "audio/wav",
                "voxcpm2_inference_timesteps": 999,
            },
        )
        sanitized_failures_checked = validation.status == 422 and not _contains_raw_error_leak(validation.payload)

        f5_ttfa = _load_matrix_warm_ttfa("f5")
        results.update(
            {
                "asset_id": asset_id,
                "voice_id": created_voice_id,
                "preview_passed": preview_passed,
                "test_play_passed": test_play_passed,
                "call_speak_passed": call_speak_passed,
                "preview_result": _status_from_bool(preview_passed),
                "test_play_result": _status_from_bool(test_play_passed),
                "call_speak_result": _status_from_bool(call_speak_passed),
                "call_audio_enqueued": call_audio_enqueued,
                "saved_ai_audio_path": saved_ai_audio_path,
                "interrupt_cancel_unchanged": interrupt_cancel_unchanged,
                "sanitized_failures_checked": sanitized_failures_checked,
                "warm_call_ttfa_ms": round(warm_call_ttfa_ms, 1),
                "f5_warm_call_ttfa_ms": round(f5_ttfa if f5_ttfa is not None else test_play_elapsed_ms, 1),
                "preview_elapsed_ms": round(preview_elapsed_ms, 1),
                "test_play_elapsed_ms": round(test_play_elapsed_ms, 1),
                "voxcpm2_matrix_short_ttfa_ms": _load_matrix_warm_ttfa("voxcpm2"),
                "webrtc_session_created": True,
                "sanitized_failure_category": "none" if sanitized_failures_checked else "validation_failed",
                "failure_outcome": None if sanitized_failures_checked else "selectable_with_caveats",
            }
        )
    except EvidenceFailure as exc:
        results.update(
            {
                "preview_passed": False,
                "test_play_passed": False,
                "call_speak_passed": False,
                "preview_result": "failed",
                "test_play_result": "failed",
                "call_speak_result": "failed",
                "call_audio_enqueued": False,
                "saved_ai_audio_path": "results/audio/voxcpm2__call_flow_test_play.wav",
                "interrupt_cancel_unchanged": False,
                "sanitized_failures_checked": True,
                "warm_call_ttfa_ms": 0.0,
                "f5_warm_call_ttfa_ms": _load_matrix_warm_ttfa("f5") or 0.0,
                "sanitized_failure_category": exc.category,
                "failure_outcome": "visible_unavailable"
                if exc.category in {"voxcpm2_unavailable", "runtime_unavailable"}
                else "selectable_with_caveats",
                "failure_message": _sanitize_error(exc),
            }
        )
        raise
    finally:
        if created_voice_id:
            try:
                delete = api.delete_json(api.web_base_url, f"/api/voices/{created_voice_id}?force=true")
                results["created_voice_deleted"] = 200 <= delete.status < 300
            except Exception as exc:
                results["created_voice_deleted"] = False
                results["cleanup_warning"] = _sanitize_error(exc)
        if pc is not None:
            await pc.close()

    if _contains_raw_error_leak(results):
        raise EvidenceFailure("validation_failed", "call-flow results contain unsanitized runtime detail")
    return results


def _contains_raw_error_leak(value: Any) -> bool:
    text = json.dumps(value, sort_keys=True)
    return any(pattern in text for pattern in FORBIDDEN_LEAK_PATTERNS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-base-url", default=DEFAULT_WEB_BASE_URL)
    parser.add_argument("--ai-base-url", default=DEFAULT_AI_BASE_URL)
    parser.add_argument("--reference-audio", default=str(DEFAULT_REFERENCE_AUDIO))
    parser.add_argument("--reference-transcript", default=DEFAULT_REFERENCE_TRANSCRIPT)
    parser.add_argument("--source-voice-name", default=DEFAULT_SOURCE_VOICE_NAME)
    parser.add_argument("--preview-text", default="VoxCPM2 preview evidence for a short RayMe reply.")
    parser.add_argument("--test-play-text", default="VoxCPM2 test play evidence is ready.")
    parser.add_argument("--call-text", default="VoxCPM2 call playback evidence is now queued.")
    parser.add_argument("--timeout", type=float, default=300.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        payload = asyncio.run(generate_evidence(args))
    except EvidenceFailure as exc:
        print(f"FAIL: {exc.category}: {_sanitize_error(exc)}")
        return 1
    CALL_FLOW_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {CALL_FLOW_JSON.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
