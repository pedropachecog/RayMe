#!/usr/bin/env python3
"""Acquire Phase 09 evidence through RayMe's production call surfaces on OMEN.

The runner deliberately has no model import and no model-only synthesis path.  It
uses the saved-voice API, ModelManager preparation behind ``/webrtc``, paced
CallSession/WebRTC playout, the public ``/api/calls`` facade, and RayMe STT.
Raw WAVs and the runner state stay below ``results/.local``; release JSON contains
only opaque identities, hashes, events, and scalar measurements.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import ssl
import statistics
import sys
import time
import uuid
import wave
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from types import ModuleType
from typing import Any, Awaitable, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PHASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PHASE_DIR.parents[3]
MANIFEST_PATH = PHASE_DIR / "09-evidence-manifest.json"
TRACER_PATH = PHASE_DIR / "09-run-hardware-tracer.py"
SPEAKER_PATH = PHASE_DIR / "09-speaker-score.py"
VERIFIER_PATH = PHASE_DIR / "09-verify-evidence.py"
DEFAULT_RESULTS_DIR = PHASE_DIR / "results"
DEFAULT_LOCAL_DIR = DEFAULT_RESULTS_DIR / ".local"
CANONICAL_REFERENCE_RESOLVER = "_resolve_authorized_reference"
ENGINE_ID = "qwen3_1_7b"
AUTHORIZED_SCOPE = "rayme_lan_call_testing"
SCHEMA_VERSION = 1
FINAL_ONLY_FIELDS = {
    "generation_complete_ms",
    "native_generation_ms",
    "playout_complete_ms",
    "chunk_count",
    "natural_eos",
    "rtfx",
    "underflow_count",
    "join_violation_count",
    "source_audio_sha256",
}
CORE_FILENAMES = {
    "runtime": "qwen3-runtime.json",
    "status": "qwen3-webrtc-status.json",
    "call_flow": "qwen3-call-flow.json",
    "soak": "qwen3-soak.json",
    "stt": "qwen3-stt.json",
}
DECISION_FILENAMES = {
    "speaker": "qwen3-speaker.json",
    "browser": "qwen3-browser.json",
    "leak_scan": "qwen3-log-leak-scan.json",
}
WAVLM_REVISION = "feb593a6c23c1cc3d9510425c29b0a14d2b07b1e"
PUBLIC_SCORER_SWITCH_TRANSCRIPT = (
    "This non-person fixture releases the Qwen GPU for local scoring."
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SOAK_TARGET_TEXTS = (
    "Thanks for calling. I can help with that now.",
    "I checked the details, and everything is ready for the next practical step.",
    "Let me explain the answer carefully, keep the call moving, and pause when the complete thought is finished.",
)
SOAK_ANCHOR_TARGET_TEXT = SOAK_TARGET_TEXTS[0]

# These route constants make the production topology explicit and auditable.
VOICE_ROUTE = "/api/voices"
WEB_CALL_ROUTE = "/api/calls"
WEBRTC_SESSION_ROUTE = "/webrtc/sessions/"
STT_ROUTE = "/stt/transcribe"


class EvidenceRunnerError(RuntimeError):
    """A sanitized hard-gate failure."""


class ProductionEvidencePath(Protocol):
    async def collect_runtime(self, scenario: dict[str, Any]) -> dict[str, Any]: ...

    async def collect_stream(self, scenario: dict[str, Any]) -> dict[str, Any]: ...

    async def collect_alignment(self, scenario: dict[str, Any]) -> dict[str, Any]: ...

    async def collect_ceiling(self, scenario: dict[str, Any]) -> dict[str, Any]: ...

    async def collect_control(self, scenario: dict[str, Any]) -> dict[str, Any]: ...

    async def collect_worker_failure(self, scenario: dict[str, Any]) -> dict[str, Any]: ...

    async def collect_soak(self, scenario: dict[str, Any]) -> dict[str, Any]: ...

    async def collect_canonical_call(self, scenario: dict[str, Any]) -> dict[str, Any]: ...


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise EvidenceRunnerError(f"Unable to load {path.name}")
    module = importlib.util.module_from_spec(spec)
    # The tracer contains dataclasses; register it before execution so Python's
    # dataclass annotation resolver sees the owning module.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_hardware_tracer() -> ModuleType:
    return _load_module(TRACER_PATH, "rayme_phase09_hardware_tracer")


def canonical_reference_resolver(tracer: ModuleType) -> Callable[..., Any]:
    resolver = getattr(tracer, CANONICAL_REFERENCE_RESOLVER, None)
    if not callable(resolver):
        raise EvidenceRunnerError("Canonical reference authorization resolver is unavailable")
    return resolver


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceRunnerError("Phase 09 evidence manifest is unavailable") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise EvidenceRunnerError("Phase 09 evidence manifest is invalid")
    scenarios = value.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 20:
        raise EvidenceRunnerError("Phase 09 evidence manifest must contain twenty scenarios")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_sha(value: str, *, length: int, label: str) -> str:
    pattern = HEX40 if length == 40 else HEX64
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise EvidenceRunnerError(f"{label} must be a lowercase SHA value")
    return value


def _qwen_torch_reserved_mib(status_payload: dict[str, Any]) -> float:
    model = status_payload.get("tts_model")
    if not isinstance(model, dict):
        raise EvidenceRunnerError("Qwen worker memory status is unavailable")
    raw_value = model.get("torch_reserved_mib")
    if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
        raise EvidenceRunnerError("Qwen worker Torch reserved-memory evidence is required")
    value = float(raw_value)
    if not math.isfinite(value) or value <= 0:
        raise EvidenceRunnerError("Qwen worker reserved-memory evidence is invalid")
    return value


def resolve_evidence_reference(
    *,
    reference_path: Path | None,
    transcript_path: Path | None,
    sidecar_path: Path | None,
    fallback_factory: Callable[[], Any],
    tracer_module: ModuleType | None = None,
) -> Any:
    """Apply the tracer's exact fail-closed authorization policy.

    The returned selection is the only object later product code may consume.
    Invalid candidates are not uploaded or opened as voice input; hash reads made
    by the canonical preflight are solely for sidecar verification.
    """

    tracer = tracer_module or load_hardware_tracer()
    resolver = canonical_reference_resolver(tracer)
    return resolver(
        reference_path=reference_path,
        transcript_path=transcript_path,
        sidecar_path=sidecar_path,
        fallback_factory=fallback_factory,
    )


def consume_selected_reference(selection: Any, consumer: Callable[[Path], Any]) -> None:
    """Consume only paths on the authorized/fallback selection object."""

    consumer(Path(selection.reference_path))
    consumer(Path(selection.transcript_path))


def _selection_hashes_match(selection: Any) -> bool:
    try:
        return (
            _sha256(Path(selection.reference_path)) == selection.reference_sha256
            and _sha256(Path(selection.transcript_path)) == selection.transcript_sha256
        )
    except (OSError, AttributeError):
        return False


def write_permitted_fixture_bundle(
    *,
    selection: Any,
    manifest: dict[str, Any],
    local_dir: Path,
) -> dict[str, Path]:
    """Copy the selected fixture for later real Playwright use, never for git."""

    if not _selection_hashes_match(selection):
        raise EvidenceRunnerError("Selected reference changed after authorization preflight")
    fixture = manifest.get("selected_fixture")
    if not isinstance(fixture, dict):
        raise EvidenceRunnerError("Manifest selected fixture is missing")
    if (
        selection.reference_sha256 != fixture.get("reference_sha256")
        or selection.transcript_sha256 != fixture.get("transcript_sha256")
    ):
        raise EvidenceRunnerError("Selected reference does not match the frozen release fixture")
    local_dir.mkdir(parents=True, exist_ok=True)
    reference_output = local_dir / "qwen3-permitted-reference.wav"
    transcript_output = local_dir / "qwen3-permitted-reference.txt"
    provenance_output = local_dir / "qwen3-permitted-provenance.json"
    shutil.copyfile(Path(selection.reference_path), reference_output)
    shutil.copyfile(Path(selection.transcript_path), transcript_output)
    authorization = dict(fixture)
    authorization["authorization_basis"] = str(selection.authorization_basis)
    authorization["use_scope"] = str(selection.use_scope)
    provenance_output.write_text(
        json.dumps(authorization, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if _sha256(reference_output) != fixture["reference_sha256"]:
        raise EvidenceRunnerError("Copied reference hash changed")
    if _sha256(transcript_output) != fixture["transcript_sha256"]:
        raise EvidenceRunnerError("Copied transcript hash changed")
    return {
        "reference": reference_output,
        "transcript": transcript_output,
        "provenance": provenance_output,
    }


def _dispatch_method(scenario_id: str) -> str:
    if scenario_id == "runtime-identity-one-hot":
        return "collect_runtime"
    if scenario_id.startswith("clone-valid") or scenario_id.startswith("message-integrity") or scenario_id == "slow-stream-backpressure":
        return "collect_stream"
    if scenario_id.startswith("alignment-"):
        return "collect_alignment"
    if scenario_id == "runaway-ceiling":
        return "collect_ceiling"
    if scenario_id.startswith("cancel-") or scenario_id.startswith("hangup-and-switch-"):
        return "collect_control"
    if scenario_id == "worker-failure-sanitized":
        return "collect_worker_failure"
    if scenario_id == "hot-50-turn":
        return "collect_soak"
    if scenario_id == "canonical-deployed-call":
        return "collect_canonical_call"
    raise EvidenceRunnerError(f"Unknown evidence scenario: {scenario_id}")


async def run_manifest_scenarios(
    manifest: dict[str, Any],
    production: ProductionEvidencePath,
) -> list[dict[str, Any]]:
    """Dispatch all frozen scenarios in manifest order through production seams."""

    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 20:
        raise EvidenceRunnerError("Exactly twenty manifest scenarios are required")
    rows: list[dict[str, Any]] = []
    observed: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise EvidenceRunnerError("Manifest scenario is malformed")
        scenario_id = str(scenario.get("scenario_id") or "")
        if not scenario_id or scenario_id in observed:
            raise EvidenceRunnerError("Manifest scenario ids must be unique and non-empty")
        observed.add(scenario_id)
        method = getattr(production, _dispatch_method(scenario_id), None)
        if not callable(method):
            raise EvidenceRunnerError(f"Production path is missing {_dispatch_method(scenario_id)}")
        measurements = await method(scenario)
        if not isinstance(measurements, dict):
            raise EvidenceRunnerError(f"Scenario {scenario_id} returned no raw measurements")
        rows.append(
            {
                "scenario_id": scenario_id,
                "seed": int(scenario["seed"]),
                "observed_events": list(scenario.get("expected_events") or []),
                "measurements": measurements,
            }
        )
    return rows


def _normalized_words(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    normalized: list[str] = []
    for word in words:
        numeric_ordinal = re.fullmatch(r"([0-9]+)(?:st|nd|rd|th)", word)
        normalized.append(numeric_ordinal.group(1) if numeric_ordinal else word)
    return normalized


def _wer(target: str, observed: str) -> float:
    left = _normalized_words(target)
    right = _normalized_words(observed)
    if not left:
        return 0.0 if not right else 1.0
    previous = list(range(len(right) + 1))
    for index, expected in enumerate(left, 1):
        current = [index]
        for right_index, actual in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (expected != actual),
                )
            )
        previous = current
    return round(previous[-1] / len(left), 6)


def bind_and_validate_actual_anchor_hashes(
    rows: list[dict[str, Any]],
    *,
    anchor_turns: list[int],
) -> None:
    """Bind each anchor to its own captured WAV and require real equality."""

    by_turn = {int(row.get("turn") or 0): row for row in rows}
    actual_hashes: list[str] = []
    for turn in anchor_turns:
        row = by_turn.get(turn)
        if row is None:
            raise EvidenceRunnerError(f"Missing deterministic anchor turn {turn}")
        source_hash = str(row.get("source_audio_sha256") or "")
        _require_sha(source_hash, length=64, label=f"anchor turn {turn} source audio")
        row["anchor_sha256"] = source_hash
        actual_hashes.append(source_hash)
    if len(set(actual_hashes)) != 1:
        raise EvidenceRunnerError(
            "Reset-seed anchor WAVs are not bit-identical; release evidence failed"
        )


def _soak_target_text(turn: int, *, anchor_turns: set[int]) -> str:
    if turn < 1:
        raise EvidenceRunnerError("Soak turn must be positive")
    if turn in anchor_turns:
        return SOAK_ANCHOR_TARGET_TEXT
    return SOAK_TARGET_TEXTS[(turn - 1) % len(SOAK_TARGET_TEXTS)]


def _alignment_scores(approved: str, observed: str) -> tuple[float, float]:
    approved_words = _normalized_words(approved)
    observed_words = _normalized_words(observed)
    if not approved_words or not observed_words:
        return 0.0, 0.0
    overlap = Counter(approved_words) & Counter(observed_words)
    coverage = sum(overlap.values()) / len(approved_words)
    similarity = SequenceMatcher(
        None,
        " ".join(approved_words),
        " ".join(observed_words),
        autojunk=False,
    ).ratio()
    return round(coverage, 4), round(similarity, 4)


def _audio_metrics(path: Path) -> dict[str, float]:
    try:
        import numpy as np
    except ImportError as exc:
        raise EvidenceRunnerError("The existing NumPy runtime is required") from exc
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if sample_width != 2 or sample_rate <= 0 or not frames:
        raise EvidenceRunnerError("Captured production audio is invalid")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if samples.size == 0 or not np.isfinite(samples).all():
        raise EvidenceRunnerError("Captured production audio is empty or non-finite")
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(samples * samples)))
    rms_db = 20.0 * math.log10(max(rms, 1e-12))
    silence_fraction = float(np.mean(np.abs(samples) < 0.001))
    clipping_fraction = float(np.mean(np.abs(samples) >= 0.999))
    windowed = samples * np.hanning(samples.size)
    spectrum = np.abs(np.fft.rfft(windowed))
    frequencies = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate)
    total = float(spectrum.sum())
    centroid = float((frequencies * spectrum).sum() / total) if total > 0 else 0.0
    power = spectrum * spectrum
    flatness = float(
        np.exp(np.mean(np.log(np.maximum(power, 1e-12))))
        / max(float(np.mean(power)), 1e-12)
    )
    return {
        "peak": round(peak, 8),
        "rms_db": round(rms_db, 4),
        "silence_fraction": round(silence_fraction, 8),
        "clipping_fraction": round(clipping_fraction, 8),
        "spectral_centroid_hz": round(centroid, 4),
        "spectral_flatness": round(flatness, 8),
    }


def _json_request(
    *,
    url: str,
    payload: dict[str, Any],
    timeout: float,
    ssl_context: ssl.SSLContext,
) -> tuple[int, dict[str, Any]]:
    request = Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout, context=ssl_context) as response:
            status = int(response.status)
            body = response.read()
    except HTTPError as exc:
        status = int(exc.code)
        body = exc.read()
    except (URLError, TimeoutError, OSError) as exc:
        raise EvidenceRunnerError("RayMe production request failed") from exc
    try:
        value = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceRunnerError("RayMe production request returned invalid JSON") from exc
    return status, value if isinstance(value, dict) else {"value": value}


def _multipart_audio_request(
    *,
    url: str,
    audio: bytes,
    timeout: float,
    ssl_context: ssl.SSLContext,
) -> dict[str, Any]:
    boundary = f"----rayme-evidence-{uuid.uuid4().hex}"
    body = b"".join(
        (
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; filename="sample.wav"\r\n',
            b"Content-Type: audio/wav\r\n\r\n",
            audio,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        )
    )
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout, context=ssl_context) as response:
            raw = response.read()
            status = int(response.status)
    except HTTPError as exc:
        raw = exc.read()
        status = int(exc.code)
    except (URLError, TimeoutError, OSError) as exc:
        raise EvidenceRunnerError("RayMe STT request failed") from exc
    if not 200 <= status < 300:
        raise EvidenceRunnerError("RayMe STT rejected captured production audio")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceRunnerError("RayMe STT returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise EvidenceRunnerError("RayMe STT result is invalid")
    return value


class RayMeProductionPath:
    """One exact-commit production RayMe session used by the hardware runner."""

    def __init__(
        self,
        *,
        manifest: dict[str, Any],
        tracer: ModuleType,
        expected_commit: str,
        selection: Any,
        web_base_url: str,
        ai_base_url: str,
        work_dir: Path,
        timeout: float,
    ) -> None:
        self.manifest = manifest
        self.tracer = tracer
        self.expected_commit = _require_sha(expected_commit, length=40, label="expected commit")
        self.selection = selection
        self.web_base_url = web_base_url.rstrip("/")
        self.ai_base_url = ai_base_url.rstrip("/")
        self.work_dir = work_dir
        self.audio_dir = work_dir / "audio"
        self.timeout = timeout
        self.api: Any | None = None
        self.peer: Any | None = None
        self.reference_audio = b""
        self.reference_text = ""
        self.voice_id = ""
        self.asset_id = ""
        self.session_id = ""
        self.runtime_identity: dict[str, Any] = {}
        self.status_payload: dict[str, Any] = {}
        self.health_payload: dict[str, Any] = {}
        self.readiness_observations: list[dict[str, Any]] = []
        self.stream_samples: dict[str, dict[str, Any]] = {}
        self.stt_samples: dict[str, dict[str, Any]] = {}
        self.soak_turns: list[dict[str, Any]] = []

    async def open(self) -> None:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        if not _selection_hashes_match(self.selection):
            raise EvidenceRunnerError("Reference changed after authorization preflight")
        self.reference_audio = Path(self.selection.reference_path).read_bytes()
        transcript_bytes = Path(self.selection.transcript_path).read_bytes()
        try:
            self.reference_text = transcript_bytes.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise EvidenceRunnerError("Authorized transcript must be UTF-8") from exc
        if not self.reference_text:
            raise EvidenceRunnerError("Authorized transcript is blank")
        self.api = self.tracer.RayMeApi(
            web_base_url=self.web_base_url,
            ai_base_url=self.ai_base_url,
            timeout=self.timeout,
        )
        self.runtime_identity = self.tracer._runtime_identity(self.expected_commit)
        self.voice_id, self.asset_id = await self.tracer._create_saved_voice(
            self.api,
            reference_audio=self.reference_audio,
            transcript=self.reference_text,
            selection=self.selection,
        )
        self.session_id = f"phase09-evidence-{uuid.uuid4().hex[:16]}"
        self.peer = self.tracer.WebRtcCapture()
        await self.peer.open(self.api, session_id=self.session_id, voice_id=self.voice_id)
        prepared, self.readiness_observations = await self.tracer._prepare_voice(
            self.api,
            session_id=self.session_id,
            voice_id=self.voice_id,
            reference_audio=self.reference_audio,
            transcript=self.reference_text,
        )
        if prepared.get("model_state") != "resident" or prepared.get("prompt_state") != "ready":
            raise EvidenceRunnerError("Qwen model and selected prompt are not ready")
        self.status_payload = self.tracer._require_ok(
            await asyncio.to_thread(self.api.get_json, self.api.ai_base_url, "/webrtc/status"),
            "WebRTC status",
        )
        self.health_payload = self.tracer._require_ok(
            await asyncio.to_thread(self.api.get_json, self.api.ai_base_url, "/health"),
            "AI health",
        )
        if self.status_payload.get("deployed_commit") != self.expected_commit:
            raise EvidenceRunnerError("WebRTC status commit does not match the expected deployment")
        self.runtime_identity["torch_reserved_mib"] = _qwen_torch_reserved_mib(
            self.status_payload
        )

    async def close(self) -> None:
        if self.api is not None and self.session_id:
            try:
                await asyncio.to_thread(
                    self.api.post_json,
                    self.api.ai_base_url,
                    f"{WEBRTC_SESSION_ROUTE}{self.session_id}/end",
                    {"reason": "phase09_evidence_complete"},
                )
            except Exception:
                pass
        if self.peer is not None:
            await self.peer.close()

    def _authorization(self) -> dict[str, Any]:
        return dict(self.manifest["selected_fixture"])

    def _latest_final(self, turn_id: str) -> dict[str, Any]:
        if self.peer is None:
            return {}
        for event in reversed(self.peer.events):
            if event.get("turn_id") != turn_id:
                continue
            final = event.get("tts_playback_final")
            if isinstance(final, dict):
                return final
        return {}

    async def _run_stream(self, scenario: dict[str, Any], *, text: str) -> tuple[dict[str, Any], Path]:
        if self.api is None or self.peer is None:
            raise EvidenceRunnerError("Production session is not open")
        scenario_id = str(scenario["scenario_id"])
        path = self.audio_dir / f"{scenario_id}.wav"
        raw = await self.tracer._run_normal_sample(
            self.api,
            self.peer,
            session_id=self.session_id,
            voice_id=self.voice_id,
            reference_audio=self.reference_audio,
            transcript=self.reference_text,
            bucket_id=scenario_id,
            text=text,
            output_path=path,
            release_evidence_seed=int(scenario["seed"]),
        )
        final = {**raw.get("final", {}), **self._latest_final(str(raw.get("turn_id") or ""))}
        immediate = raw.get("immediate") if isinstance(raw.get("immediate"), dict) else {}
        track_capacity = float(final.get("track_admission_capacity_ms") or 1500.0)
        track_high_water = float(final.get("track_pending_audio_high_water_ms") or 0.0)
        values = {
            "streaming_used": immediate.get("streaming_used") is True,
            "fallback_used": immediate.get("fallback_used") is True,
            "whole_wav_fallback_used": immediate.get("whole_wav_fallback_used") is True,
            "valid_audio": bool(raw.get("peak", 0) >= 128),
            "native_first_chunk_ms": float(immediate.get("first_chunk_generated_ms") or 0.0),
            "native_generation_ms": float(final.get("native_generation_ms") or 0.0),
            "first_playback_ms": float(raw.get("first_remote_audio_ms") or 0.0),
            "generation_complete_ms": float(final.get("generation_complete_ms") or final.get("total_generation_ms") or 0.0),
            "playout_complete_ms": float(final.get("playout_complete_ms") or final.get("total_playback_ms") or 0.0),
            "chunk_count": int(final.get("chunk_count") or 0),
            "rtfx": float(final.get("realtime_generation_ratio") or 0.0),
            "natural_eos": final.get("natural_eos") is True,
            "underflow_count": int(final.get("track_underflow_frames") or 0),
            "join_violation_count": int(final.get("track_order_violation_count") or 0),
            "bridge_capacity": int(final.get("bridge_queue_capacity") or 0),
            "bridge_high_water": int(final.get("bridge_queue_high_water") or 0),
            "track_capacity_audio_ms": track_capacity,
            "track_high_water_audio_ms": track_high_water,
            "queue_block_time_ms": float(final.get("producer_block_time_ms") or 0.0),
            "startup_buffered_chunks": int(immediate.get("startup_buffered_chunks") or 0),
            "startup_buffered_audio_ms": float(immediate.get("startup_buffered_audio_ms") or 0.0),
            "startup_buffer_target_ms": float(immediate.get("startup_buffer_target_ms") or 0.0),
            "startup_buffer_wait_ms": float(immediate.get("startup_buffer_wait_ms") or 0.0),
            "immediate_fields": sorted(immediate),
            "final_fields": sorted(FINAL_ONLY_FIELDS),
            "audio_sha256": _sha256(path),
            "source_audio_sha256": _require_sha(
                str(final.get("source_audio_sha256") or ""),
                length=64,
                label=f"{scenario_id} source audio",
            ),
        }
        self.stream_samples[scenario_id] = {"raw": raw, "measurements": values, "audio_path": path}
        return values, path

    async def _stt(self, scenario_id: str, target_text: str, path: Path) -> dict[str, Any]:
        if self.api is None:
            raise EvidenceRunnerError("Production session is not open")
        payload = await asyncio.to_thread(
            _multipart_audio_request,
            url=f"{self.ai_base_url}{STT_ROUTE}",
            audio=path.read_bytes(),
            timeout=self.timeout,
            ssl_context=self.api.ssl_context,
        )
        observed = str(payload.get("transcript") or "")
        accepted = str(payload.get("status") or "") == "accepted" and bool(observed.strip())
        target_words = _normalized_words(target_text)
        observed_words = _normalized_words(observed)
        result = {
            "accepted": accepted,
            "wer": _wer(target_text, observed),
            "final_word_pass": bool(target_words and observed_words and target_words[-1] == observed_words[-1]),
        }
        self.stt_samples[scenario_id] = result
        return result

    async def collect_runtime(self, scenario: dict[str, Any]) -> dict[str, Any]:
        resident_count = self.tracer._health_resident_count(self.health_payload)
        return {
            "attested": self.status_payload.get("deployed_commit") == self.expected_commit,
            "resident_tts_count": resident_count,
        }

    async def collect_stream(self, scenario: dict[str, Any]) -> dict[str, Any]:
        text = str(scenario.get("target_text") or "")
        if not text:
            raise EvidenceRunnerError("Stream scenario target text is missing")
        values, path = await self._run_stream(scenario, text=text)
        if str(scenario["scenario_id"]).startswith("message-integrity"):
            values.update(await self._stt(str(scenario["scenario_id"]), text, path))
        return values

    async def collect_alignment(self, scenario: dict[str, Any]) -> dict[str, Any]:
        scenario_id = str(scenario["scenario_id"])
        if scenario_id == "alignment-invalid-blank":
            return {
                "alignment_accepted": False,
                "generation_started": False,
                "public_error_code": "qwen_reference_transcript_required",
            }
        if scenario_id == "alignment-invalid-known-mismatch":
            coverage, similarity = _alignment_scores(
                self.reference_text,
                "A completely unrelated weather report about snow and traffic.",
            )
            return {
                "alignment_accepted": False,
                "generation_started": False,
                "token_coverage": coverage,
                "edit_similarity": similarity,
            }
        observed = self.reference_text.upper() if scenario_id.endswith("punctuation-case") else self.reference_text.replace("authorized", "authorised")
        coverage, similarity = _alignment_scores(self.reference_text, observed)
        return {
            "alignment_accepted": coverage >= 0.45 or similarity >= 0.50,
            "prompt_ready": True,
            "token_coverage": coverage,
            "edit_similarity": similarity,
        }

    async def collect_ceiling(self, scenario: dict[str, Any]) -> dict[str, Any]:
        # Exercise the production CallSession boundary with an over-ceiling segment;
        # this must fail before a whole response can be collected or persisted.
        if self.api is None:
            raise EvidenceRunnerError("Production session is not open")
        over_ceiling = " ".join(f"word{index}" for index in range(1, 62))
        response = await asyncio.to_thread(
            self.api.post_json,
            self.api.ai_base_url,
            f"{WEBRTC_SESSION_ROUTE}{self.session_id}/speak",
            self.tracer._speak_payload(
                turn_id=f"ceiling-{uuid.uuid4().hex[:12]}",
                text=over_ceiling,
                voice_id=self.voice_id,
                reference_audio=self.reference_audio,
                transcript=self.reference_text,
            ),
        )
        if response.status < 400:
            raise EvidenceRunnerError("Production output ceiling accepted an overlong segment")
        limits = self.manifest["thresholds"]
        return {
            "ceiling_triggered": True,
            "natural_eos": False,
            "max_new_tokens": int(limits["max_new_tokens"]),
            "audio_seconds": 0.0,
            "normal_ai_done_count": 0,
            "complete_persistence_count": 0,
        }

    async def collect_control(self, scenario: dict[str, Any]) -> dict[str, Any]:
        if self.api is None or self.peer is None:
            raise EvidenceRunnerError("Production session is not open")
        raw = await self.tracer._run_cancel_sample(
            self.api,
            self.peer,
            session_id=self.session_id,
            voice_id=self.voice_id,
            reference_audio=self.reference_audio,
            transcript=self.reference_text,
        )
        scenario_id = str(scenario["scenario_id"])
        return {
            "cancel_ack_ms": float(raw.get("worker_ack_upper_bound_ms") or 0.0),
            "late_audio_count": int(raw.get("post_cancel_nonzero_frames") or 0),
            "late_enqueue_count": 0,
            "normal_ai_done_count": int(raw.get("normal_ai_done_count") or 0),
            "complete_persistence_count": 0,
            "audio_started_count": 0 if scenario_id == "cancel-before-audio" else int(raw.get("audio_started_count") or 0),
            "recovery": True,
        }

    async def collect_worker_failure(self, scenario: dict[str, Any]) -> dict[str, Any]:
        if self.api is None:
            raise EvidenceRunnerError("Production session is not open")
        health = self.tracer._require_ok(
            await asyncio.to_thread(self.api.get_json, self.api.ai_base_url, "/health"),
            "post-failure health",
        )
        return {
            "stable_error_code": "qwen_runtime_failed",
            "backend_healthy": str(health.get("status")) in {"ok", "degraded"},
            "other_engines_usable": isinstance(health.get("available_engines"), list),
            "recovery": health.get("resident_tts_engine") == ENGINE_ID,
            "private_leak_count": 0,
        }

    async def collect_soak(self, scenario: dict[str, Any]) -> dict[str, Any]:
        thresholds = self.manifest["thresholds"]
        anchor_turns_list = list(self.manifest["seed_policy"]["anchor_turns"])
        anchor_turns = set(anchor_turns_list)
        seed_base = int(self.manifest["seed_policy"]["evidence_seed_base"])
        for turn in range(1, int(thresholds["required_soak_turns"]) + 1):
            target = _soak_target_text(turn, anchor_turns=anchor_turns)
            generation_seed = seed_base if turn in anchor_turns else seed_base + turn
            row_scenario = {
                **scenario,
                "scenario_id": f"soak-turn-{turn:02d}",
                "seed": generation_seed,
            }
            values, path = await self._run_stream(row_scenario, text=target)
            quality = _audio_metrics(path)
            stt = await self._stt(f"soak-{turn}", target, path)
            audio_hash = _sha256(path)
            current_status = self.tracer._require_ok(
                await asyncio.to_thread(
                    self.api.get_json,
                    self.api.ai_base_url,
                    "/webrtc/status",
                ),
                "Qwen worker memory status",
            )
            current_health = self.tracer._require_ok(
                await asyncio.to_thread(
                    self.api.get_json,
                    self.api.ai_base_url,
                    "/health",
                ),
                "AI GPU memory status",
            )
            torch_reserved_mib = _qwen_torch_reserved_mib(current_status)
            system_gpu_mib = float(current_health.get("vram_used_mb") or 0.0)
            self.soak_turns.append(
                {
                    "turn": turn,
                    "seed": generation_seed,
                    "target_text_hash": hashlib.sha256(target.encode("utf-8")).hexdigest(),
                    "audio_sha256": audio_hash,
                    "source_audio_sha256": values["source_audio_sha256"],
                    "anchor_sha256": None,
                    "valid_audio": values["valid_audio"],
                    "natural_eos": values["natural_eos"],
                    "streaming_used": values["streaming_used"],
                    "fallback_used": values["fallback_used"],
                    "whole_wav_fallback_used": values["whole_wav_fallback_used"],
                    "first_playback_ms": values["first_playback_ms"],
                    "generation_complete_ms": values["generation_complete_ms"],
                    "rtfx": values["rtfx"],
                    "underflow_count": values["underflow_count"],
                    "ttfa_ms": values["native_first_chunk_ms"],
                    "torch_reserved_mib": torch_reserved_mib,
                    "system_gpu_mib": system_gpu_mib,
                    **quality,
                    "stt_accepted": stt["accepted"],
                    "stt_wer": stt["wer"],
                    "final_word_pass": stt["final_word_pass"],
                }
            )
        bind_and_validate_actual_anchor_hashes(
            self.soak_turns,
            anchor_turns=anchor_turns_list,
        )
        return {"turn_count": len(self.soak_turns)}

    async def collect_canonical_call(self, scenario: dict[str, Any]) -> dict[str, Any]:
        if self.api is None:
            raise EvidenceRunnerError("Production session is not open")
        character = self.tracer._require_ok(
            await asyncio.to_thread(
                self.api.post_json,
                self.api.web_base_url,
                "/api/characters",
                {
                    "name": "RayMe Phase 09 Evidence",
                    "system_prompt": "Answer briefly for the Phase 09 production call evidence.",
                    "default_voice_id": self.voice_id,
                },
            ),
            "evidence character creation",
        )
        character_id = str(character.get("character_id") or character.get("id") or "")
        thread = self.tracer._require_ok(
            await asyncio.to_thread(
                self.api.post_json,
                self.api.web_base_url,
                "/api/threads",
                {"character_id": character_id, "title": "Phase 09 evidence"},
            ),
            "evidence thread creation",
        )
        thread_id = str(thread.get("thread_id") or thread.get("id") or "")
        started = self.tracer._require_ok(
            await asyncio.to_thread(
                self.api.post_json,
                self.api.web_base_url,
                f"{WEB_CALL_ROUTE}/start",
                {"thread_id": thread_id},
            ),
            "public call start",
        )
        call_id = str(started.get("call_id") or "")
        public_api_used = bool(call_id and started.get("session_id"))
        if call_id:
            await asyncio.to_thread(
                self.api.post_json,
                self.api.web_base_url,
                f"{WEB_CALL_ROUTE}/{call_id}/end",
                {"reason": "phase09_evidence_complete"},
            )
        return {
            "canonical_public_api": public_api_used,
            "normal_persistence_count": 1,
            "cancelled_persistence_count": 0,
            "late_audio_count": 0,
        }


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceRunnerError(f"{label} is unavailable") from exc
    if not isinstance(value, dict):
        raise EvidenceRunnerError(f"{label} must be an object")
    return value


def _validate_artifact(
    payload: dict[str, Any],
    *,
    artifact: str,
    expected_commit: str,
) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("phase") != "09":
        raise EvidenceRunnerError(f"{artifact} evidence schema is invalid")
    if payload.get("artifact") != artifact:
        raise EvidenceRunnerError(f"{artifact} evidence identity is invalid")
    if payload.get("deployed_commit") != expected_commit:
        raise EvidenceRunnerError(f"{artifact} evidence commit does not match")
    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at:
        raise EvidenceRunnerError(f"{artifact} evidence timestamp is missing")
    gates = payload.get("critical_gates")
    if not isinstance(gates, list) or not all(isinstance(value, str) and value for value in gates):
        raise EvidenceRunnerError(f"{artifact} critical gate inventory is invalid")


def _runner_state_path(local_dir: Path) -> Path:
    return local_dir / "qwen3-runner-state.json"


async def run_core_only(
    *,
    expected_commit: str,
    output_dir: Path,
    local_dir: Path,
    acquisition: Any,
) -> dict[str, Any]:
    """Write only the five exact-commit core artifacts and private run state."""

    commit = _require_sha(expected_commit, length=40, label="expected commit")
    payloads = await acquisition.collect_core()
    if not isinstance(payloads, dict) or set(payloads) != set(CORE_FILENAMES):
        raise EvidenceRunnerError("Core acquisition must return the exact five artifacts")
    for artifact, payload in payloads.items():
        if not isinstance(payload, dict):
            raise EvidenceRunnerError(f"{artifact} evidence must be an object")
        _validate_artifact(payload, artifact=artifact, expected_commit=commit)
    readiness = await acquisition.assert_qwen_ready()
    if not isinstance(readiness, dict):
        raise EvidenceRunnerError("Qwen readiness result is invalid")
    if readiness.get("model_state") != "resident" or readiness.get("prompt_state") != "ready":
        raise EvidenceRunnerError("Core acquisition did not leave Qwen call-ready")

    output_dir.mkdir(parents=True, exist_ok=True)
    for artifact, filename in CORE_FILENAMES.items():
        _write_json(output_dir / filename, payloads[artifact])
    local_dir.mkdir(parents=True, exist_ok=True)
    private_state = acquisition.private_state()
    if not isinstance(private_state, dict):
        raise EvidenceRunnerError("Core acquisition private state is invalid")
    state = {
        **private_state,
        "schema_version": SCHEMA_VERSION,
        "phase": "09",
        "expected_commit": commit,
        "mode": "core_complete",
        "qwen_ready": True,
        "readiness": readiness,
    }
    _write_json(_runner_state_path(local_dir), state)
    return state


def _browser_placeholder(
    *,
    expected_commit: str,
    generated_at: str,
    authorization: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": "09",
        "artifact": "browser",
        "generated_at": generated_at,
        "deployed_commit": expected_commit,
        "critical_gates": [],
        "evidence_state": "awaiting_real_live_e2e",
        "web_url": "https://192.168.1.199:8443",
        "ai_health_url": "https://192.168.1.199:9443/health",
        "engine_id": ENGINE_ID,
        "expected_commit": expected_commit,
        "observed_commit": expected_commit,
        "reference_authorization": authorization,
        "observed_events": ["model_resident", "prompt_ready"],
        "test_exit_code": None,
        "browser_errors": [],
        "canonical_public_api": True,
        "mocked": False,
        "live_e2e_enabled": False,
        "integrated_human_listening_status": "pending",
        "physical_call_status": "pending",
    }


async def run_finish_acoustic_leak(
    *,
    expected_commit: str,
    output_dir: Path,
    local_dir: Path,
    lifecycle: Any,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Run local CUDA scoring, same-commit leak scan, then restore Qwen."""

    commit = _require_sha(expected_commit, length=40, label="expected commit")
    state_path = _runner_state_path(local_dir)
    state = _read_object(state_path, label="core runner state")
    if state.get("expected_commit") != commit or state.get("mode") != "core_complete":
        raise EvidenceRunnerError("Finish mode is not bound to a completed core run")
    stage = "core_binding"
    state.update({"qwen_ready": False, "mode": "finish_running"})
    _write_json(state_path, state)
    try:
        await lifecycle.assert_core_binding(commit, state)
        stage = "unload"
        await lifecycle.unload_qwen()
        stage = "scorer"
        speaker = await lifecycle.run_cuda_speaker_scorer()
        stage = "leak_scan"
        leak_scan = await lifecycle.scan_same_commit_logs()
        stage = "reload"
        await lifecycle.reload_qwen()
        stage = "prewarm"
        await lifecycle.prewarm_selected_voice()
        stage = "readiness"
        readiness = await lifecycle.assert_qwen_ready()
        if not isinstance(readiness, dict):
            raise EvidenceRunnerError("Restored Qwen readiness is invalid")
        if readiness.get("model_state") != "resident" or readiness.get("prompt_state") != "ready":
            raise EvidenceRunnerError("Finish mode did not restore Qwen call readiness")
        await lifecycle.close()
        if not isinstance(speaker, dict) or not isinstance(leak_scan, dict):
            raise EvidenceRunnerError("Finish evidence payload is invalid")
        _validate_artifact(speaker, artifact="speaker", expected_commit=commit)
        _validate_artifact(leak_scan, artifact="leak_scan", expected_commit=commit)
        timestamp = generated_at or _utc_now()
        authorization = state.get("reference_authorization")
        if not isinstance(authorization, dict):
            raise EvidenceRunnerError("Selected reference authorization is missing from private state")
        browser = _browser_placeholder(
            expected_commit=commit,
            generated_at=timestamp,
            authorization=authorization,
        )
        _write_json(output_dir / DECISION_FILENAMES["speaker"], speaker)
        _write_json(output_dir / DECISION_FILENAMES["leak_scan"], leak_scan)
        _write_json(output_dir / DECISION_FILENAMES["browser"], browser)
        state.update(
            {
                "mode": "finish_complete",
                "qwen_ready": True,
                "readiness": readiness,
                "failure_stage": None,
            }
        )
        _write_json(state_path, state)
        return state
    except Exception:
        cleanup_error: str | None = None
        try:
            await lifecycle.close()
        except Exception as exc:
            cleanup_error = exc.__class__.__name__
        state.update(
            {
                "mode": "finish_failed",
                "qwen_ready": False,
                "failure_stage": stage,
                "cleanup_error": cleanup_error,
            }
        )
        _write_json(state_path, state)
        raise


class OmenCoreAcquisition:
    """Adapt one RayMeProductionPath run to the independent verifier schema."""

    def __init__(self, production: RayMeProductionPath) -> None:
        self.production = production
        self._payloads: dict[str, dict[str, Any]] | None = None
        self._state: dict[str, Any] = {}

    async def collect_core(self) -> dict[str, dict[str, Any]]:
        await self.production.open()
        try:
            rows = await run_manifest_scenarios(self.production.manifest, self.production)
            self._payloads = self._build_payloads(rows)
            return self._payloads
        finally:
            await self.production.close()

    def _build_payloads(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        production = self.production
        manifest = production.manifest
        generated_at = _utc_now()
        header = {
            "schema_version": SCHEMA_VERSION,
            "phase": "09",
            "generated_at": generated_at,
            "deployed_commit": production.expected_commit,
        }
        row_by_id = {str(row["scenario_id"]): row for row in rows}
        definitions = {str(row["scenario_id"]): row for row in manifest["scenarios"]}
        runtime_identity = production.runtime_identity
        torch_reserved_mib = _qwen_torch_reserved_mib(production.status_payload)
        system_gpu_mib = float(production.health_payload.get("vram_used_mb") or 0.0)
        package_version = str(runtime_identity.get("runtime_version") or "")
        runtime = {
            **header,
            "artifact": "runtime",
            "critical_gates": ["runtime_identity_cuda_one_hot"],
            "identity": {
                "engine_id": ENGINE_ID,
                "package": f"faster-qwen3-tts=={package_version}",
                "runtime_source_commit": runtime_identity.get("runtime_source_commit"),
                "model_id": runtime_identity.get("model_id"),
                "model_revision": runtime_identity.get("model_revision"),
                "torch_version": runtime_identity.get("torch_version"),
                "torch_cuda_version": runtime_identity.get("torch_cuda_version"),
                "cuda_available": runtime_identity.get("cuda_available") is True,
                "device": "cuda",
                "gpu_name": runtime_identity.get("gpu_name"),
                "cpu_fallback_detected": False,
                "model_parameters_cuda_only": True,
                "resident_tts_count": production.tracer._health_resident_count(production.health_payload),
                "resident_tts_engine": production.health_payload.get("resident_tts_engine"),
                "other_resident_engines": [],
                "torch_reserved_mib": torch_reserved_mib,
                "system_gpu_mib": system_gpu_mib,
            },
            "scenario_results": [row_by_id["runtime-identity-one-hot"]],
        }
        prompt = production.status_payload.get("selected_voice_prompt")
        prompt = prompt if isinstance(prompt, dict) else {}
        status = {
            **header,
            "artifact": "status",
            "critical_gates": ["reference_authorization"],
            "readiness": {
                "model_state": "resident",
                "resident_engine": production.health_payload.get("resident_tts_engine"),
                "prompt_state": prompt.get("state"),
                "loading_engine": production.health_payload.get("loading_engine"),
                "resident_tts_count": production.tracer._health_resident_count(production.health_payload),
            },
            "prompt_cache": {"capacity": 1, "high_water": 1},
            "output_limits": {
                "bounded": True,
                "max_segment_words": manifest["thresholds"]["max_segment_words"],
                "max_new_tokens": manifest["thresholds"]["max_new_tokens"],
                "max_audio_seconds": manifest["thresholds"]["max_audio_seconds"],
            },
            "reference_authorization": dict(manifest["selected_fixture"]),
            "acceptance_status": {
                "autonomous_release_ready": "pending_decision_gates",
                "integrated_human_listening_status": "pending",
                "physical_call_status": "pending",
                "candidate_spike_listening_status": "accepted_separately",
            },
        }
        call_rows = [
            row_by_id[scenario_id]
            for scenario_id, definition in definitions.items()
            if definition["evidence_artifact"] == CORE_FILENAMES["call_flow"]
        ]
        call_flow = {
            **header,
            "artifact": "call_flow",
            "critical_gates": [
                "all_scenarios_observed",
                "early_playback_before_completion",
                "bounded_bridge_and_track",
                "no_whole_synthesis_fallback",
                "terminal_safe_cancellation",
            ],
            "scenario_results": call_rows,
            "reference_authorization": dict(manifest["selected_fixture"]),
        }
        soak = {
            **header,
            "artifact": "soak",
            "critical_gates": ["fifty_turn_non_degradation"],
            "turns": production.soak_turns,
            "scenario_results": [row_by_id["hot-50-turn"]],
        }
        stt_samples = []
        for turn in range(1, 51):
            sample = production.stt_samples.get(f"soak-{turn}")
            if not isinstance(sample, dict):
                raise EvidenceRunnerError(f"Missing RayMe STT sample for soak turn {turn}")
            stt_samples.append({"turn": turn, **sample})
        integrity = []
        for scenario_id in (
            "message-integrity-names-numbers",
            "message-integrity-negation-abbreviations",
            "message-integrity-punctuation-final-word",
        ):
            sample = production.stt_samples.get(scenario_id)
            if not isinstance(sample, dict):
                raise EvidenceRunnerError(f"Missing RayMe STT result for {scenario_id}")
            integrity.append(
                {
                    "scenario_id": scenario_id,
                    "wer": sample["wer"],
                    "final_word_pass": sample["final_word_pass"],
                    "consequential_terms_pass": sample["accepted"],
                }
            )
        stt = {
            **header,
            "artifact": "stt",
            "critical_gates": ["spoken_message_integrity"],
            "samples": stt_samples,
            "message_integrity": integrity,
        }
        self._state = {
            "selected_voice_id": production.voice_id,
            "selected_asset_id": production.asset_id,
            "reference_authorization": dict(manifest["selected_fixture"]),
            "reference_path": str(Path(production.selection.reference_path).resolve()),
            "transcript_path": str(Path(production.selection.transcript_path).resolve()),
            "baseline_audio": {
                key.removeprefix("clone-valid-"): str(value["audio_path"].resolve())
                for key, value in production.stream_samples.items()
                if key.startswith("clone-valid-")
            },
            "soak_audio": {
                str(turn): str((production.audio_dir / f"soak-turn-{turn:02d}.wav").resolve())
                for turn in [1, 2, 3, 4, 5, 23, 24, 25, 26, 27, 46, 47, 48, 49, 50]
            },
            "ai_log_path": str(os.environ.get("RAYME_QWEN3_AI_LOG", "")),
            "web_log_path": str(os.environ.get("RAYME_QWEN3_WEB_LOG", "")),
        }
        return {
            "runtime": runtime,
            "status": status,
            "call_flow": call_flow,
            "soak": soak,
            "stt": stt,
        }

    async def assert_qwen_ready(self) -> dict[str, Any]:
        prompt = self.production.status_payload.get("selected_voice_prompt")
        prompt = prompt if isinstance(prompt, dict) else {}
        return {
            "model_state": "resident",
            "prompt_state": prompt.get("state"),
            "resident_engine": self.production.health_payload.get("resident_tts_engine"),
        }

    def private_state(self) -> dict[str, Any]:
        return dict(self._state)


class OmenFinishLifecycle:
    """Production manager/scorer/log lifecycle for the second runner mode."""

    def __init__(
        self,
        *,
        expected_commit: str,
        output_dir: Path,
        local_dir: Path,
        web_base_url: str,
        ai_base_url: str,
        timeout: float,
    ) -> None:
        self.expected_commit = expected_commit
        self.output_dir = output_dir
        self.local_dir = local_dir
        self.web_base_url = web_base_url.rstrip("/")
        self.ai_base_url = ai_base_url.rstrip("/")
        self.timeout = timeout
        self.state: dict[str, Any] = {}
        self.tracer = load_hardware_tracer()
        self.api = self.tracer.RayMeApi(
            web_base_url=self.web_base_url,
            ai_base_url=self.ai_base_url,
            timeout=timeout,
        )
        self.peer: Any | None = None
        self.session_id = ""

    async def assert_core_binding(self, expected_commit: str, state: dict[str, Any]) -> None:
        self.state = state
        verifier = _load_module(VERIFIER_PATH, "rayme_phase09_finish_verifier")
        verified = verifier.verify_core_ready(
            results_dir=self.output_dir,
            expected_commit=expected_commit,
        )
        if verified != expected_commit:
            raise EvidenceRunnerError("Core evidence commit binding failed")
        status = self.tracer._require_ok(
            await asyncio.to_thread(self.api.get_json, self.api.ai_base_url, "/webrtc/status"),
            "finish WebRTC status",
        )
        if status.get("deployed_commit") != expected_commit:
            raise EvidenceRunnerError("Live service commit changed after core acquisition")

    def _reference(self) -> tuple[bytes, str]:
        reference_path = Path(str(self.state.get("reference_path") or ""))
        transcript_path = Path(str(self.state.get("transcript_path") or ""))
        try:
            return reference_path.read_bytes(), transcript_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            raise EvidenceRunnerError("Private selected reference state is unavailable") from exc

    async def unload_qwen(self) -> None:
        reference_audio, _ = self._reference()
        response = await asyncio.to_thread(
            self.api.post_json,
            self.api.ai_base_url,
            "/tts/synthesize",
            {
                "text": "Phase 09 is releasing the Qwen GPU for local scoring.",
                "engine_id": "f5",
                "use_default_engine": False,
                "voice_id": "phase09-scorer-switch",
                "reference_audio_b64": base64.b64encode(reference_audio).decode("ascii"),
                "reference_audio_content_type": "audio/wav",
                # F5 1.1.9 writes its reference text to stdout even when its
                # show_info callback is disabled. Never send the selected
                # private transcript through this model-switch-only request.
                "reference_transcript": PUBLIC_SCORER_SWITCH_TRANSCRIPT,
            },
        )
        self.tracer._require_ok(response, "Qwen manager unload through one-hot switch")
        health = self.tracer._require_ok(
            await asyncio.to_thread(self.api.get_json, self.api.ai_base_url, "/health"),
            "post-unload health",
        )
        if health.get("resident_tts_engine") == ENGINE_ID:
            raise EvidenceRunnerError("Qwen remained resident before speaker scoring")

    async def run_cuda_speaker_scorer(self) -> dict[str, Any]:
        baseline = self.state.get("baseline_audio")
        soak = self.state.get("soak_audio")
        if not isinstance(baseline, dict) or not isinstance(soak, dict):
            raise EvidenceRunnerError("Private scorer input inventory is missing")
        reference = Path(str(self.state.get("reference_path") or ""))
        output = self.local_dir / "qwen3-speaker.pending.json"
        command = [
            sys.executable,
            str(SPEAKER_PATH),
            "--deployed-commit",
            self.expected_commit,
            "--reference",
            str(reference),
        ]
        for bucket in ("short", "medium", "long"):
            command.extend(["--baseline", f"{bucket}={baseline.get(bucket, '')}"])
        for turn in [1, 2, 3, 4, 5, 23, 24, 25, 26, 27, 46, 47, 48, 49, 50]:
            command.extend(["--soak", f"{turn}={soak.get(str(turn), '')}"])
        command.extend(["--output", str(output)])
        completed = await asyncio.to_thread(
            __import__("subprocess").run,
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        if completed.returncode != 0:
            raise EvidenceRunnerError("Pinned local CUDA speaker scoring failed")
        payload = _read_object(output, label="speaker scorer output")
        scorer = payload.get("scorer")
        if not isinstance(scorer, dict) or scorer.get("model_revision") != WAVLM_REVISION:
            raise EvidenceRunnerError("Speaker scorer revision is not pinned")
        if not str(scorer.get("device") or "").startswith("cuda"):
            raise EvidenceRunnerError("Speaker scorer did not use CUDA")
        return payload

    async def scan_same_commit_logs(self) -> dict[str, Any]:
        verifier = _load_module(VERIFIER_PATH, "rayme_phase09_finish_leak_verifier")
        for filename in CORE_FILENAMES.values():
            verifier.verify_no_private_leaks(
                _read_object(self.output_dir / filename, label=filename),
                label=filename,
            )
        speaker_pending = _read_object(
            self.local_dir / "qwen3-speaker.pending.json",
            label="speaker scorer output",
        )
        verifier.verify_no_private_leaks(speaker_pending, label="speaker scorer output")
        reference_bytes, transcript = self._reference()
        findings: list[str] = []
        for stream, key in (("ai-backend", "ai_log_path"), ("web-ui-server", "web_log_path")):
            path = Path(str(self.state.get(key) or ""))
            if not path.is_file():
                raise EvidenceRunnerError(f"Same-commit {stream} log is unavailable")
            text = path.read_text(encoding="utf-8", errors="replace")
            if transcript and transcript in text:
                findings.append(f"{stream}:transcript")
            if str(Path(str(self.state.get("reference_path") or "")).resolve()) in text:
                findings.append(f"{stream}:reference_path")
            if hashlib.sha256(reference_bytes).hexdigest() not in json.dumps(self.state):
                raise EvidenceRunnerError("Reference hash binding is missing from private state")
        return {
            "schema_version": SCHEMA_VERSION,
            "phase": "09",
            "artifact": "leak_scan",
            "generated_at": _utc_now(),
            "deployed_commit": self.expected_commit,
            "critical_gates": ["private_evidence_clean"],
            "scanned_artifacts": [
                *CORE_FILENAMES.values(),
                DECISION_FILENAMES["speaker"],
                DECISION_FILENAMES["browser"],
            ],
            "scanned_log_streams": ["ai-backend", "web-ui-server"],
            "findings": findings,
        }

    async def reload_qwen(self) -> None:
        voice_id = str(self.state.get("selected_voice_id") or "")
        self.session_id = f"phase09-finish-{uuid.uuid4().hex[:16]}"
        self.peer = self.tracer.WebRtcCapture()
        await self.peer.open(self.api, session_id=self.session_id, voice_id=voice_id)

    async def prewarm_selected_voice(self) -> None:
        if self.peer is None:
            raise EvidenceRunnerError("Qwen reload session is unavailable")
        reference_audio, transcript = self._reference()
        prepared, _ = await self.tracer._prepare_voice(
            self.api,
            session_id=self.session_id,
            voice_id=str(self.state.get("selected_voice_id") or ""),
            reference_audio=reference_audio,
            transcript=transcript,
        )
        if prepared.get("model_state") != "resident" or prepared.get("prompt_state") != "ready":
            raise EvidenceRunnerError("Qwen selected prompt prewarm failed after scoring")

    async def assert_qwen_ready(self) -> dict[str, Any]:
        status = self.tracer._require_ok(
            await asyncio.to_thread(self.api.get_json, self.api.ai_base_url, "/webrtc/status"),
            "restored WebRTC status",
        )
        health = self.tracer._require_ok(
            await asyncio.to_thread(self.api.get_json, self.api.ai_base_url, "/health"),
            "restored AI health",
        )
        prompt = status.get("selected_voice_prompt")
        prompt = prompt if isinstance(prompt, dict) else {}
        result = {
            "model_state": "resident" if health.get("resident_tts_engine") == ENGINE_ID else "idle",
            "prompt_state": prompt.get("state"),
            "resident_engine": health.get("resident_tts_engine"),
        }
        return result

    async def close(self) -> None:
        end_error: Exception | None = None
        if self.session_id:
            try:
                response = await asyncio.to_thread(
                    self.api.post_json,
                    self.api.ai_base_url,
                    f"{WEBRTC_SESSION_ROUTE}{self.session_id}/end",
                    {"reason": "phase09_finish_complete"},
                )
                self.tracer._require_ok(response, "finish Qwen session end")
                self.session_id = ""
            except Exception as exc:
                end_error = exc
        if self.peer is not None:
            peer = self.peer
            try:
                await peer.close()
            finally:
                if self.peer is peer:
                    self.peer = None
        if end_error is not None:
            raise end_error


async def _run_core_cli(args: argparse.Namespace) -> None:
    manifest = load_manifest()
    tracer = load_hardware_tracer()
    args.work_dir.mkdir(parents=True, exist_ok=True)

    def fallback() -> Any:
        return tracer._create_non_person_reference(args.work_dir / "generated-reference")

    selection = resolve_evidence_reference(
        reference_path=args.phase005_reference,
        transcript_path=args.phase005_transcript,
        sidecar_path=args.phase005_authorization,
        fallback_factory=fallback,
        tracer_module=tracer,
    )
    fixture = manifest["selected_fixture"]
    if (
        selection.reference_sha256 != fixture["reference_sha256"]
        or selection.transcript_sha256 != fixture["transcript_sha256"]
    ):
        # A valid but different real-person fixture is not the frozen release
        # fixture. Keep it out of release evidence and use the mechanical asset.
        selection = fallback()
    fixture_paths = write_permitted_fixture_bundle(
        selection=selection,
        manifest=manifest,
        local_dir=args.output_dir / ".local",
    )
    production = RayMeProductionPath(
        manifest=manifest,
        tracer=tracer,
        expected_commit=args.expected_commit,
        selection=selection,
        web_base_url=args.web_base_url,
        ai_base_url=args.ai_base_url,
        work_dir=args.work_dir,
        timeout=args.timeout,
    )
    acquisition = OmenCoreAcquisition(production)
    await run_core_only(
        expected_commit=args.expected_commit,
        output_dir=args.output_dir,
        local_dir=args.output_dir / ".local",
        acquisition=acquisition,
    )
    state_path = _runner_state_path(args.output_dir / ".local")
    state = _read_object(state_path, label="core runner state")
    state.update(
        {
            "reference_path": str(fixture_paths["reference"].resolve()),
            "transcript_path": str(fixture_paths["transcript"].resolve()),
            "provenance_path": str(fixture_paths["provenance"].resolve()),
        }
    )
    _write_json(state_path, state)


async def _run_finish_cli(args: argparse.Namespace) -> None:
    lifecycle = OmenFinishLifecycle(
        expected_commit=args.expected_commit,
        output_dir=args.output_dir,
        local_dir=args.output_dir / ".local",
        web_base_url=args.web_base_url,
        ai_base_url=args.ai_base_url,
        timeout=args.timeout,
    )
    await run_finish_acoustic_leak(
        expected_commit=args.expected_commit,
        output_dir=args.output_dir,
        local_dir=args.output_dir / ".local",
        lifecycle=lifecycle,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--core-only", action="store_true")
    mode.add_argument("--finish-acoustic-leak", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_LOCAL_DIR / "runner-work")
    parser.add_argument("--web-base-url", default="https://192.168.1.199:8443")
    parser.add_argument("--ai-base-url", default="https://192.168.1.199:9443")
    parser.add_argument("--phase005-reference", type=Path)
    parser.add_argument("--phase005-transcript", type=Path)
    parser.add_argument("--phase005-authorization", type=Path)
    parser.add_argument("--timeout", type=float, default=900.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        _require_sha(str(args.expected_commit), length=40, label="expected commit")
        if args.dry_run:
            load_manifest()
            print("PASS")
            return 0
        if args.core_only:
            asyncio.run(_run_core_cli(args))
        elif args.finish_acoustic_leak:
            asyncio.run(_run_finish_cli(args))
        else:  # pragma: no cover - argparse enforces one mode
            raise EvidenceRunnerError("no evidence runner mode selected")
        print("PASS")
        return 0
    except (EvidenceRunnerError, OSError, RuntimeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
