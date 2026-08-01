from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from io import BytesIO
import logging
import threading
from typing import Any

from app.config import AiBackendSettings
from app.models.engine_metadata import ENGINE_METADATA, EngineMetadata, EngineStatus
from app.models.tts_qwen3 import (
    Qwen3PromptError,
    Qwen3PromptLeaseError,
    Qwen3ValidationError,
    Qwen3WorkerError,
    normalize_qwen_comparison_text,
    qwen_prompt_cache_key,
)
from app.models.tts_registry import build_default_tts_adapters

logger = logging.getLogger(__name__)


VramProbe = Callable[[], Mapping[str, int | float]]
RETRIABLE_TTS_UNAVAILABLE_REASONS = {
    "engine load failed",
    "default engine load failed",
    "engine runtime failed",
}
QWEN_ALIGNMENT_MIN_TOKEN_COVERAGE = 0.45
QWEN_ALIGNMENT_MIN_EDIT_SIMILARITY = 0.50


@dataclass(frozen=True)
class QwenTranscriptAlignment:
    accepted: bool
    token_coverage: float
    edit_similarity: float


def evaluate_qwen_transcript_alignment(
    approved_transcript: str,
    observed_transcript: str,
) -> QwenTranscriptAlignment:
    approved_text = normalize_qwen_comparison_text(approved_transcript)
    observed_text = normalize_qwen_comparison_text(observed_transcript)
    approved_tokens = approved_text.split()
    observed_tokens = observed_text.split()
    if not approved_tokens or not observed_tokens:
        return QwenTranscriptAlignment(
            accepted=False,
            token_coverage=0.0,
            edit_similarity=0.0,
        )
    overlap = Counter(approved_tokens) & Counter(observed_tokens)
    token_coverage = sum(overlap.values()) / len(approved_tokens)
    edit_similarity = SequenceMatcher(
        None,
        approved_text,
        observed_text,
        autojunk=False,
    ).ratio()
    accepted = not (
        token_coverage < QWEN_ALIGNMENT_MIN_TOKEN_COVERAGE
        and edit_similarity < QWEN_ALIGNMENT_MIN_EDIT_SIMILARITY
    )
    return QwenTranscriptAlignment(
        accepted=accepted,
        token_coverage=round(token_coverage, 4),
        edit_similarity=round(edit_similarity, 4),
    )


class NullTtsAdapter:
    def __init__(self, engine_id: str) -> None:
        self.engine_id = engine_id
        self.loaded = False

    def startup_self_test(self) -> None:
        return None

    def load(self) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False


class ModelManager:
    def __init__(
        self,
        settings: AiBackendSettings | None = None,
        tts_adapters: Mapping[str, Any] | None = None,
        adapters: Mapping[str, Any] | None = None,
        vram_probe: VramProbe | None = None,
    ) -> None:
        self.settings = settings or AiBackendSettings()
        self.engine_metadata = {engine.id: engine for engine in ENGINE_METADATA}
        adapter_map = tts_adapters or adapters
        self.tts_adapters = dict(adapter_map or self._build_null_adapters())
        self.vram_probe: VramProbe = vram_probe or self._probe_vram
        self.loading_engine: str | None = None
        self.resident_tts_engine: str | None = None
        self._switch_lock = threading.RLock()
        self._prepare_lock: asyncio.Lock | None = None
        self._selected_voice_prompt: dict[str, str | None] = {
            "engine_id": None,
            "voice_key": None,
            "state": "none",
            "error_code": None,
        }
        self._selected_prompt_cache_key: str | None = None
        self._qwen_prompt_lease_owners: set[str] = set()
        self._qwen_prompt_lease_voice_key: str | None = None
        self._qwen_prompt_lease_cache_key: str | None = None
        self._qwen_alignment_cache: tuple[str, QwenTranscriptAlignment] | None = None
        self.stt_adapter: Any | None = None
        self.vad_adapter: Any | None = None
        self.stt_ready = False
        self._statuses = {
            engine.id: EngineStatus(id=engine.id, label=engine.label)
            for engine in ENGINE_METADATA
        }
        self._started = False
        if self.settings.default_tts_engine not in self._statuses:
            raise ValueError("default_tts_engine must match a registered engine")

    def startup(self) -> None:
        for engine_id, adapter in self.tts_adapters.items():
            if engine_id not in self._statuses:
                continue
            if getattr(adapter, "synthesis_enabled", True) is False:
                self._mark_unavailable(
                    engine_id,
                    "engine synthesis is not implemented in Phase 02",
                )
                continue
            try:
                self._run_self_test(adapter)
            except Exception:
                self._mark_unavailable(engine_id, "engine startup self-test failed")

        if self._statuses[self.settings.default_tts_engine].available:
            try:
                self.switch_tts_engine(self.settings.default_tts_engine)
            except Exception:
                self._mark_unavailable(
                    self.settings.default_tts_engine,
                    "default engine load failed",
                )
        if self.settings.load_models_on_startup:
            self._warm_speech_models()
        self._started = True

    def shutdown(self) -> None:
        if self.resident_tts_engine is not None:
            self._unload_engine(self.resident_tts_engine)
        self.resident_tts_engine = None
        self.loading_engine = None
        self._reset_selected_voice_prompt()
        self._clear_qwen_prompt_lease()
        for status in self._statuses.values():
            if status.available:
                status.resident = False
                status.state = "idle"
        self._started = False

    def switch_tts_engine(self, engine_id: str) -> EngineStatus:
        with self._switch_lock:
            return self._switch_tts_engine_locked(engine_id)

    def _switch_tts_engine_locked(self, engine_id: str) -> EngineStatus:
        if engine_id not in self._statuses:
            raise ValueError("unknown TTS engine")
        target = self._statuses[engine_id]
        if not target.available:
            if target.unavailable_reason not in RETRIABLE_TTS_UNAVAILABLE_REASONS:
                raise ValueError("TTS engine unavailable")
            logger.info(
                "[rayme-tts] retry_unavailable_engine engine=%s reason=%s",
                engine_id,
                target.unavailable_reason,
            )
            target.available = True
            target.state = "idle"
            target.unavailable_reason = None
        if self.resident_tts_engine == engine_id:
            target.resident = True
            target.state = "resident"
            return target

        if (
            self.resident_tts_engine == "qwen3_1_7b"
            and self._qwen_prompt_lease_owners
            and engine_id != "qwen3_1_7b"
        ):
            raise Qwen3PromptLeaseError(
                "Qwen3 prompt is leased to an active live call"
            )

        previous = self.resident_tts_engine
        self.loading_engine = engine_id
        target.state = "loading"
        if previous is not None:
            self._unload_engine(previous)
            self._statuses[previous].resident = False
            self._statuses[previous].state = "idle"
            self.resident_tts_engine = None
            if previous == "qwen3_1_7b" and engine_id != previous:
                self._reset_selected_voice_prompt()

        try:
            self._load_engine(engine_id)
        except Exception as exc:
            self.resident_tts_engine = None
            self.loading_engine = None
            self._mark_unavailable(engine_id, "engine load failed")
            logger.exception(
                "[rayme-tts] engine.load_failed engine=%s exc=%s",
                engine_id,
                exc.__class__.__name__,
            )
            raise

        target.resident = True
        target.state = "resident"
        self.resident_tts_engine = engine_id
        self.loading_engine = None
        return target

    async def prepare_tts_engine(
        self,
        engine_id: str,
        *,
        voice_key: str,
        reference_audio: bytes,
        reference_transcript: str,
        prompt_lease_owner: str | None = None,
    ) -> dict[str, str | None]:
        if engine_id not in self._statuses:
            raise ValueError("unknown TTS engine")
        if not voice_key or len(voice_key) > 128:
            raise ValueError("invalid voice key")
        prompt_cache_key: str | None = None
        if engine_id == "qwen3_1_7b":
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
            prompt_cache_key = qwen_prompt_cache_key(
                reference_audio,
                reference_transcript,
            )

        if self._prepare_lock is None:
            self._prepare_lock = asyncio.Lock()
        async with self._prepare_lock:
            if engine_id == "qwen3_1_7b":
                self._reject_competing_qwen_prompt(
                    voice_key=voice_key,
                    prompt_cache_key=prompt_cache_key or "",
                    prompt_lease_owner=prompt_lease_owner,
                )
            same_ready_prompt = (
                engine_id == "qwen3_1_7b"
                and self.resident_tts_engine == engine_id
                and self._selected_voice_prompt["voice_key"] == voice_key
                and self._selected_voice_prompt["state"] == "ready"
                and self._selected_prompt_cache_key == prompt_cache_key
            )
            if same_ready_prompt:
                if prompt_lease_owner is not None:
                    self._set_qwen_prompt_lease(
                        prompt_lease_owner,
                        voice_key,
                        prompt_cache_key or "",
                    )
                return self._prepare_result(engine_id)

            self._selected_voice_prompt = {
                "engine_id": engine_id,
                "voice_key": voice_key,
                "state": "none",
                "error_code": None,
            }
            self._selected_prompt_cache_key = None
            if engine_id == "qwen3_1_7b":
                try:
                    alignment = await asyncio.to_thread(
                        self._qwen_reference_alignment,
                        prompt_cache_key or "",
                        reference_audio,
                        reference_transcript,
                    )
                    if not alignment.accepted:
                        raise Qwen3ValidationError(
                            "Qwen3 reference audio and transcript do not match",
                            code="qwen3_transcript_mismatch",
                        )
                except Qwen3WorkerError as exc:
                    self._selected_voice_prompt["state"] = "failed"
                    self._selected_voice_prompt["error_code"] = exc.code
                    logger.warning(
                        "[rayme-tts] voice_prompt.alignment_failed "
                        "engine=%s voice=%s code=%s",
                        engine_id,
                        voice_key,
                        exc.code,
                    )
                    raise
            if self.resident_tts_engine != engine_id:
                self.loading_engine = engine_id
                self._statuses[engine_id].state = "loading"
                await asyncio.to_thread(self.switch_tts_engine, engine_id)

            if engine_id != "qwen3_1_7b":
                return self._prepare_result(engine_id)

            adapter = self.tts_adapters[engine_id]
            prewarm = getattr(adapter, "prewarm", None)
            if not callable(prewarm):
                self._selected_voice_prompt["state"] = "failed"
                self._selected_voice_prompt["error_code"] = (
                    "voice_prompt_preparation_failed"
                )
                raise ValueError("Qwen3 voice prompt preparation is unavailable")

            self._selected_voice_prompt["state"] = "prewarming"
            try:
                await asyncio.to_thread(
                    prewarm,
                    voice_key=voice_key,
                    reference_audio=reference_audio,
                    reference_transcript=reference_transcript,
                )
            except Exception as exc:
                self._selected_voice_prompt["state"] = "failed"
                error_code = getattr(
                    exc,
                    "code",
                    "voice_prompt_preparation_failed",
                )
                self._selected_voice_prompt["error_code"] = str(error_code)
                if bool(getattr(exc, "marks_engine_unavailable", False)):
                    self._contain_qwen_runtime_failure(engine_id)
                logger.warning(
                    "[rayme-tts] voice_prompt.prewarm_failed "
                    "engine=%s voice=%s code=%s exc=%s",
                    engine_id,
                    voice_key,
                    error_code,
                    exc.__class__.__name__,
                )
                raise

            self._selected_voice_prompt["state"] = "ready"
            self._selected_voice_prompt["error_code"] = None
            self._selected_prompt_cache_key = prompt_cache_key
            if prompt_lease_owner is not None:
                self._set_qwen_prompt_lease(
                    prompt_lease_owner,
                    voice_key,
                    prompt_cache_key or "",
                )
            return self._prepare_result(engine_id)

    async def release_tts_prompt_lease(self, prompt_lease_owner: str) -> bool:
        if self._prepare_lock is None:
            self._prepare_lock = asyncio.Lock()
        async with self._prepare_lock:
            if prompt_lease_owner not in self._qwen_prompt_lease_owners:
                return False
            self._qwen_prompt_lease_owners.remove(prompt_lease_owner)
            if not self._qwen_prompt_lease_owners:
                self._clear_qwen_prompt_lease()
            return True

    async def invalidate_tts_prompt(
        self,
        engine_id: str,
        voice_key: str,
    ) -> dict[str, object]:
        if engine_id != "qwen3_1_7b":
            raise ValueError("prompt invalidation is unavailable for this engine")
        if (
            not isinstance(voice_key, str)
            or not voice_key
            or len(voice_key) > 128
            or not all(
                character.isalnum() or character in "_.:-"
                for character in voice_key
            )
        ):
            raise ValueError("invalid voice key")
        if self._prepare_lock is None:
            self._prepare_lock = asyncio.Lock()
        async with self._prepare_lock:
            if (
                self._qwen_prompt_lease_owners
                and self._qwen_prompt_lease_voice_key == voice_key
            ):
                raise Qwen3PromptLeaseError(
                    "Qwen3 prompt is leased to an active live call"
                )
            manager_matched = (
                self._selected_voice_prompt["engine_id"] == engine_id
                and self._selected_voice_prompt["voice_key"] == voice_key
            )
            adapter = self.tts_adapters[engine_id]
            invalidate = getattr(adapter, "invalidate", None)
            if not callable(invalidate):
                raise Qwen3PromptError(
                    "Qwen3 voice prompt invalidation is unavailable",
                    code="qwen3_invalidate_failed",
                )
            try:
                adapter_result = await asyncio.to_thread(invalidate, voice_key)
            except Exception as exc:
                if bool(getattr(exc, "marks_engine_unavailable", False)):
                    self._contain_qwen_runtime_failure(engine_id)
                raise

            adapter_matched = bool(getattr(adapter_result, "matched", False))
            active_cancelled = bool(
                getattr(adapter_result, "active_cancelled", False)
            )
            matched = manager_matched or adapter_matched
            if manager_matched:
                self._reset_selected_voice_prompt()
                self._qwen_alignment_cache = None
            return {
                "engine_id": engine_id,
                "voice_key": voice_key,
                "status": "invalidated" if matched else "not_present",
                "matched": matched,
                "active_cancelled": active_cancelled,
            }

    def is_tts_prompt_ready(
        self,
        engine_id: str,
        voice_key: str,
        *,
        reference_audio: bytes | None = None,
        reference_transcript: str | None = None,
    ) -> bool:
        ready = (
            engine_id == "qwen3_1_7b"
            and self.resident_tts_engine == engine_id
            and self._selected_voice_prompt["engine_id"] == engine_id
            and self._selected_voice_prompt["voice_key"] == voice_key
            and self._selected_voice_prompt["state"] == "ready"
        )
        if not ready or reference_audio is None or reference_transcript is None:
            return ready
        try:
            return self._selected_prompt_cache_key == qwen_prompt_cache_key(
                reference_audio,
                reference_transcript,
            )
        except Qwen3WorkerError:
            return False

    def health(self) -> dict[str, object]:
        vram = self._safe_vram_probe()
        torch_reserved_mib: float | None = None
        if self.resident_tts_engine == "qwen3_1_7b":
            adapter = self.tts_adapters.get("qwen3_1_7b")
            raw_reserved = getattr(adapter, "torch_reserved_mib", None)
            if isinstance(raw_reserved, (int, float)) and raw_reserved > 0:
                torch_reserved_mib = float(raw_reserved)
        engine_statuses = list(self._statuses.values())
        degraded = any(not status.available for status in engine_statuses)
        status = "degraded" if degraded else "ok"
        if not self._started and self.resident_tts_engine is None:
            status = "starting"
        return {
            "service": "rayme-ai-backend",
            "status": status,
            "stt_model": self.settings.stt_model,
            "stt_compute_type": self.settings.stt_compute_type,
            "stt_language": self.settings.stt_language,
            "stt_ready": self.stt_ready,
            "vad_ready": True,
            "vad_threshold": self.settings.vad_threshold,
            "vad_end_silence_ms": self.settings.vad_end_silence_ms,
            "resident_tts_engine": self.resident_tts_engine,
            "available_engines": [status.model_dump() for status in engine_statuses],
            "loading_engine": self.loading_engine,
            "selected_voice_prompt": dict(self._selected_voice_prompt),
            "tts_torch_reserved_mib": torch_reserved_mib,
            "vram_used_mb": vram["used_mb"],
            "vram_headroom_mb": vram["headroom_mb"],
        }

    def _prepare_result(self, engine_id: str) -> dict[str, str | None]:
        return {
            "engine_id": engine_id,
            "model_state": self._statuses[engine_id].state,
            "prompt_state": self._selected_voice_prompt["state"],
            "voice_key": self._selected_voice_prompt["voice_key"],
            "error_code": self._selected_voice_prompt["error_code"],
        }

    def _reset_selected_voice_prompt(self) -> None:
        self._selected_voice_prompt = {
            "engine_id": None,
            "voice_key": None,
            "state": "none",
            "error_code": None,
        }
        self._selected_prompt_cache_key = None

    def _reject_competing_qwen_prompt(
        self,
        *,
        voice_key: str,
        prompt_cache_key: str,
        prompt_lease_owner: str | None,
    ) -> None:
        if not self._qwen_prompt_lease_owners:
            return
        same_identity = (
            self._qwen_prompt_lease_voice_key == voice_key
            and self._qwen_prompt_lease_cache_key == prompt_cache_key
        )
        if same_identity:
            return
        if (
            prompt_lease_owner is not None
            and self._qwen_prompt_lease_owners == {prompt_lease_owner}
        ):
            return
        raise Qwen3PromptLeaseError(
            "Qwen3 prompt is leased to an active live call"
        )

    def _set_qwen_prompt_lease(
        self,
        owner: str,
        voice_key: str,
        prompt_cache_key: str,
    ) -> None:
        if self._qwen_prompt_lease_owners and (
            self._qwen_prompt_lease_voice_key != voice_key
            or self._qwen_prompt_lease_cache_key != prompt_cache_key
        ):
            if self._qwen_prompt_lease_owners != {owner}:
                raise Qwen3PromptLeaseError(
                    "Qwen3 prompt is leased to an active live call"
                )
            self._qwen_prompt_lease_owners.clear()
        self._qwen_prompt_lease_owners.add(owner)
        self._qwen_prompt_lease_voice_key = voice_key
        self._qwen_prompt_lease_cache_key = prompt_cache_key

    def _clear_qwen_prompt_lease(self) -> None:
        self._qwen_prompt_lease_owners.clear()
        self._qwen_prompt_lease_voice_key = None
        self._qwen_prompt_lease_cache_key = None

    def _qwen_reference_alignment(
        self,
        prompt_cache_key: str,
        reference_audio: bytes,
        reference_transcript: str,
    ) -> QwenTranscriptAlignment:
        cached = self._qwen_alignment_cache
        if cached is not None and cached[0] == prompt_cache_key:
            return cached[1]

        try:
            import numpy as np
            import soundfile as sf

            audio, sample_rate = sf.read(
                BytesIO(reference_audio),
                dtype="float32",
                always_2d=False,
            )
            samples = np.asarray(audio, dtype=np.float32)
            if samples.ndim > 1:
                samples = samples.mean(axis=1)
            samples = samples.reshape(-1)
            if (
                samples.size == 0
                or int(sample_rate) <= 0
                or not np.isfinite(samples).all()
                or float(np.max(np.abs(samples))) <= 1e-5
            ):
                raise ValueError("invalid reference audio")
        except Exception as exc:
            raise Qwen3ValidationError(
                "Qwen3 reference audio is invalid",
                code="qwen3_reference_audio_invalid",
            ) from exc

        adapter = self.stt_adapter
        if adapter is None:
            from app.models.stt import WhisperSttAdapter

            adapter = WhisperSttAdapter(settings=self.settings)
            self.stt_adapter = adapter
        try:
            result = adapter.transcribe(
                audio=samples,
                vad_adapter=None,
                apply_vad_filter=False,
            )
            mapping = result.model_dump() if hasattr(result, "model_dump") else dict(result)
            observed = str(mapping.get("transcript") or "")
            if str(mapping.get("status") or "") != "accepted" or not observed.strip():
                raise ValueError("alignment transcript unavailable")
        except Qwen3WorkerError:
            raise
        except Exception as exc:
            raise Qwen3PromptError(
                "Qwen3 reference alignment could not be verified",
                code="qwen3_alignment_failed",
            ) from exc

        alignment = evaluate_qwen_transcript_alignment(
            reference_transcript,
            observed,
        )
        self._qwen_alignment_cache = (prompt_cache_key, alignment)
        return alignment

    def _contain_qwen_runtime_failure(self, engine_id: str) -> None:
        if engine_id != "qwen3_1_7b":
            return
        try:
            self._unload_engine(engine_id)
        except Exception:
            logger.warning(
                "[rayme-tts] engine.runtime_unload_failed engine=%s",
                engine_id,
            )
        if self.resident_tts_engine == engine_id:
            self.resident_tts_engine = None
        if self.loading_engine == engine_id:
            self.loading_engine = None
        self._mark_unavailable(engine_id, "engine runtime failed")

    def metadata(self) -> tuple[EngineMetadata, ...]:
        return ENGINE_METADATA

    def _build_null_adapters(self) -> dict[str, NullTtsAdapter]:
        try:
            return build_default_tts_adapters()
        except Exception:
            return {engine.id: NullTtsAdapter(engine.id) for engine in ENGINE_METADATA}

    def _run_self_test(self, adapter: Any) -> None:
        if hasattr(adapter, "startup_self_test"):
            adapter.startup_self_test()
        elif hasattr(adapter, "self_test"):
            adapter.self_test()

    def _load_engine(self, engine_id: str) -> None:
        adapter = self.tts_adapters[engine_id]
        if hasattr(adapter, "load"):
            adapter.load()

    def _unload_engine(self, engine_id: str) -> None:
        adapter = self.tts_adapters.get(engine_id)
        if adapter is not None and hasattr(adapter, "unload"):
            adapter.unload()

    def _mark_unavailable(self, engine_id: str, reason: str) -> None:
        status = self._statuses[engine_id]
        status.available = False
        status.resident = False
        status.state = "unavailable"
        status.unavailable_reason = reason

    def _warm_speech_models(self) -> None:
        try:
            from app.models.stt import WhisperSttAdapter
            from app.models.vad import SileroVadAdapter

            if self.stt_adapter is None:
                self.stt_adapter = WhisperSttAdapter(settings=self.settings)
            warmup = getattr(self.stt_adapter, "warmup", None)
            if callable(warmup):
                warmup()
            if self.vad_adapter is None:
                self.vad_adapter = SileroVadAdapter(
                    threshold=self.settings.vad_threshold,
                    end_silence_ms=self.settings.vad_end_silence_ms,
                    sampling_rate=16000,
                )
            self.stt_ready = True
            logger.info("[rayme-call] stt.warmup model=%s ready=True", self.settings.stt_model)
        except Exception as exc:
            self.stt_ready = False
            logger.exception(
                "[rayme-call] stt.warmup_failed model=%s exc=%s",
                self.settings.stt_model,
                exc.__class__.__name__,
            )

    def _safe_vram_probe(self) -> dict[str, int | float]:
        try:
            raw = dict(self.vram_probe())
        except Exception:
            raw = {}
        used_mb = raw.get("used_mb", 0)
        headroom_mb = raw.get("headroom_mb", self.settings.vram_budget_mb - used_mb)
        return {"used_mb": used_mb, "headroom_mb": headroom_mb}

    def _probe_vram(self) -> dict[str, int | float]:
        try:
            import pynvml

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            used_mb = round(info.used / 1024 / 1024, 1)
            return {
                "used_mb": used_mb,
                "headroom_mb": max(self.settings.vram_budget_mb - used_mb, 0),
            }
        except Exception:
            return {"used_mb": 0, "headroom_mb": self.settings.vram_budget_mb}
