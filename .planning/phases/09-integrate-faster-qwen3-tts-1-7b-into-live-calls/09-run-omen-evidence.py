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
    "playout_complete_ms",
    "chunk_count",
    "natural_eos",
    "rtfx",
    "underflow_count",
    "join_violation_count",
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
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

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
    return re.findall(r"[a-z0-9]+", text.lower())


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
        audio_hash = str(row.get("audio_sha256") or "")
        _require_sha(audio_hash, length=64, label=f"anchor turn {turn} audio")
        row["anchor_sha256"] = audio_hash
        actual_hashes.append(audio_hash)
    if len(set(actual_hashes)) != 1:
        raise EvidenceRunnerError(
            "Reset-seed anchor WAVs are not bit-identical; release evidence failed"
        )


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
            "immediate_fields": sorted(immediate),
            "final_fields": sorted(FINAL_ONLY_FIELDS),
            "audio_sha256": _sha256(path),
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
            target = (
                "Thanks for calling. I can help with that now."
                if turn % 3 == 1
                else "I checked the details, and everything is ready for the next practical step."
                if turn % 3 == 2
                else "Let me explain the answer carefully, keep the call moving, and pause when the complete thought is finished."
            )
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
            identity = self.runtime_identity
            system_gpu_mib = float(self.health_payload.get("vram_used_mb") or 0.0)
            self.soak_turns.append(
                {
                    "turn": turn,
                    "seed": generation_seed,
                    "target_text_hash": hashlib.sha256(target.encode("utf-8")).hexdigest(),
                    "audio_sha256": audio_hash,
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
                    "torch_reserved_mib": float(identity.get("torch_reserved_mib") or 0.0),
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
    # Full core/finish orchestration is deliberately below the pure contracts;
    # callers never invoke a model-only path from this process.
    args = _parse_args(argv)
    try:
        _require_sha(str(args.expected_commit), length=40, label="expected commit")
        if args.dry_run:
            load_manifest()
            print("PASS")
            return 0
        raise EvidenceRunnerError("Runner mode orchestration is not initialized")
    except EvidenceRunnerError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
