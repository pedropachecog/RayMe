"""Warm-model TTS scenario matrix for RayMe-style reply generation."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bench_utils import Timer, sample_vram_mb, warmup_cuda, write_results
from tts_ttfa import (
    _create_tada_prompt,
    _encode_luxtts_prompt,
    _generate_luxtts_audio,
    _generate_tada_audio,
    _install_f5_runtime_shims,
    _load_chatterbox_turbo_model,
    _load_luxtts_model,
    _load_tada_1b,
    _maybe_cuda_sync,
    _read_reference_text,
    _read_target_text,
    compute_rtf,
)

ENGINE_ORDER = ("f5", "xtts", "luxtts", "chatterbox_turbo", "tada_1b", "qwen3", "voxcpm2")
PROFILE_ORDER = ("baseline", "optimized", "standard_python", "optimized_seed_1337", "streaming_collected")
PHASE_DIR = Path(".planning/phases/00-measurement-gate")
REPO_ROOT = Path(__file__).resolve().parents[4]
RESULT_PATH = PHASE_DIR / "results" / "tts_scenario_matrix_local.json"
OUTPUT_SAMPLE_DIR = PHASE_DIR / "results" / "tts_scenario_audio"
LONG_REPLY_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "target_text_1min.txt"
CHATTERBOX_ALT_SEED = 1337
MODEL_ID_VOXCPM2 = "openbmb/VoxCPM2"
ABBREVIATIONS = {
    "dr",
    "mr",
    "mrs",
    "ms",
    "jr",
    "sr",
    "st",
    "vs",
    "etc",
    "e.g",
    "i.e",
}
ENGINE_CHUNK_LIMITS = {
    "f5": {"max_estimated_tokens": 260, "max_chars": 520, "min_words": 8, "first_words": 28},
    "xtts": {"max_estimated_tokens": 300, "max_chars": 640, "min_words": 8, "first_words": 28},
    "luxtts": {"max_estimated_tokens": 300, "max_chars": 640, "min_words": 8, "first_words": 28},
    "chatterbox_turbo": {"max_estimated_tokens": 240, "max_chars": 480, "min_words": 8, "first_words": 24},
    "tada_1b": {"max_estimated_tokens": 240, "max_chars": 480, "min_words": 8, "first_words": 24},
    "qwen3": {"max_estimated_tokens": 220, "max_chars": 440, "min_words": 8, "first_words": 24},
    "voxcpm2": {"max_estimated_tokens": 240, "max_chars": 500, "min_words": 8, "first_words": 24},
}
SHORT_REPLY_TEXT = (
    "I can do that. The quickest fix is to keep the model warm and reuse the voice prompt."
)
MEDIUM_REPLY_TEXT = (
    "The main latency win comes from separating one-time setup from request work. "
    "Load the model once at startup, precompute the voice conditioning when the speaker is chosen, "
    "and only time the actual synthesis path when a reply is ready to speak."
)


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    text: str
    description: str

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass(frozen=True)
class ChunkPlan:
    engine: str
    chunks: list[str]
    max_estimated_tokens: int
    max_chars: int
    strategy: str

    def metadata(self) -> dict[str, Any]:
        return {
            "chunking_strategy": self.strategy,
            "chunk_count": len(self.chunks),
            "chunk_max_estimated_tokens": self.max_estimated_tokens,
            "chunk_max_chars": self.max_chars,
            "chunk_char_lengths": [len(chunk) for chunk in self.chunks],
            "chunk_word_counts": [_word_count(chunk) for chunk in self.chunks],
            "chunk_estimated_tokens": [_estimate_tts_tokens(chunk) for chunk in self.chunks],
            "chunk_text_preview": [chunk[:96] for chunk in self.chunks],
        }


def scenario_specs() -> list[ScenarioSpec]:
    return [
        ScenarioSpec(
            name="short_reply",
            text=SHORT_REPLY_TEXT,
            description="One concise assistant reply.",
        ),
        ScenarioSpec(
            name="medium_reply",
            text=MEDIUM_REPLY_TEXT,
            description="A practical multi-sentence assistant answer.",
        ),
        ScenarioSpec(
            name="long_reply",
            text=_read_target_text(LONG_REPLY_FIXTURE),
            description="Long-form assistant narration from the Phase 0 fixture.",
        ),
    ]


def _round_or_none(value: float | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text))


def _estimate_tts_tokens(text: str) -> int:
    """Conservative token estimate for planner caps without importing model tokenizers."""
    words = _word_count(text)
    punctuation = len(re.findall(r"[,.!?;:]", text))
    return max(1, int(round(words * 3.0 + punctuation * 0.5)))


def _last_word_fragment(text: str) -> str:
    match = re.search(r"([A-Za-z](?:[A-Za-z]|\.)*)[\"')\]]*$", text.strip())
    return match.group(1).lower().rstrip(".") if match else ""


def _is_sentence_boundary(text: str, index: int) -> bool:
    char = text[index]
    if char not in ".!?\n":
        return False
    if char == "\n":
        return True
    prefix = text[:index]
    token = _last_word_fragment(prefix)
    if token in ABBREVIATIONS:
        return False
    if char == ".":
        local = text[max(0, index - 3) : min(len(text), index + 4)].lower()
        if "e.g." in local or "i.e." in local:
            return False
    if char == "." and index > 0 and index + 1 < len(text) and text[index - 1].isdigit() and text[index + 1].isdigit():
        return False
    return True


def _split_sentence_units(text: str) -> list[str]:
    units: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        if _is_sentence_boundary(text, index):
            end = index + 1
            while end < len(text) and text[end] in "\"')]}":
                end += 1
            unit = " ".join(text[start:end].strip().split())
            if unit:
                units.append(unit)
            start = end
        index += 1
    tail = " ".join(text[start:].strip().split())
    if tail:
        units.append(tail)
    return units


def _fits_chunk(text: str, *, max_estimated_tokens: int, max_chars: int) -> bool:
    return len(text) <= max_chars and _estimate_tts_tokens(text) < max_estimated_tokens


def _split_oversize_unit(
    unit: str,
    *,
    max_estimated_tokens: int,
    max_chars: int,
) -> list[str]:
    phrase_parts = [
        part.strip()
        for part in re.split(r"(?<=[,;:])\s+|\s+-\s+|\s+--\s+", unit)
        if part.strip()
    ]
    if len(phrase_parts) <= 1:
        phrase_parts = unit.split()

    chunks: list[str] = []
    current = ""
    for part in phrase_parts:
        candidate = part if not current else f"{current} {part}"
        if current and not _fits_chunk(
            candidate,
            max_estimated_tokens=max_estimated_tokens,
            max_chars=max_chars,
        ):
            chunks.append(current.strip())
            current = part
        elif not current and not _fits_chunk(
            candidate,
            max_estimated_tokens=max_estimated_tokens,
            max_chars=max_chars,
        ):
            words = part.split()
            word_chunk = ""
            for word in words:
                word_candidate = word if not word_chunk else f"{word_chunk} {word}"
                if word_chunk and not _fits_chunk(
                    word_candidate,
                    max_estimated_tokens=max_estimated_tokens,
                    max_chars=max_chars,
                ):
                    chunks.append(word_chunk.strip())
                    word_chunk = word
                else:
                    word_chunk = word_candidate
            current = word_chunk
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())
    return chunks


def build_chunk_plan(engine: str, text: str) -> ChunkPlan:
    limits = ENGINE_CHUNK_LIMITS.get(engine, ENGINE_CHUNK_LIMITS["f5"])
    max_estimated_tokens = int(limits["max_estimated_tokens"])
    max_chars = int(limits["max_chars"])
    min_words = int(limits["min_words"])
    first_words = int(limits["first_words"])
    units = _split_sentence_units(text)
    chunks: list[str] = []
    current = ""

    for unit in units:
        oversized = not _fits_chunk(
            unit,
            max_estimated_tokens=max_estimated_tokens,
            max_chars=max_chars,
        )
        unit_parts = (
            _split_oversize_unit(
                unit,
                max_estimated_tokens=max_estimated_tokens,
                max_chars=max_chars,
            )
            if oversized
            else [unit]
        )
        for part in unit_parts:
            if not current:
                current = part
                if not chunks and _word_count(current) <= first_words:
                    chunks.append(current.strip())
                    current = ""
                continue

            candidate = f"{current} {part}".strip()
            if _fits_chunk(
                candidate,
                max_estimated_tokens=max_estimated_tokens,
                max_chars=max_chars,
            ):
                current = candidate
            else:
                chunks.append(current.strip())
                current = part

    if current.strip():
        chunks.append(current.strip())

    merged: list[str] = []
    for chunk in chunks:
        if (
            merged
            and _word_count(chunk) < min_words
            and _fits_chunk(
                f"{merged[-1]} {chunk}",
                max_estimated_tokens=max_estimated_tokens,
                max_chars=max_chars,
            )
        ):
            merged[-1] = f"{merged[-1]} {chunk}".strip()
        else:
            merged.append(chunk)

    return ChunkPlan(
        engine=engine,
        chunks=merged or [" ".join(text.strip().split())],
        max_estimated_tokens=max_estimated_tokens,
        max_chars=max_chars,
        strategy="sentence_boundary_token_cap_v1",
    )


def _to_float_np(sample: Any) -> Any:
    import numpy as np
    import torch

    if isinstance(sample, torch.Tensor):
        sample = sample.detach().cpu().numpy()
    return np.asarray(sample, dtype=np.float32).flatten()


def _chunk_playback_metadata(
    *,
    plan: ChunkPlan,
    chunk_ttfa_ms: list[float],
    chunk_total_ms: list[float],
    chunk_audio_duration_s: list[float],
) -> dict[str, Any]:
    ready_offsets: list[float] = []
    generated_ms = 0.0
    playback_end_ms = 0.0
    inter_chunk_gaps: list[float] = []

    for index, total_ms in enumerate(chunk_total_ms):
        ready_ms = generated_ms + chunk_ttfa_ms[index]
        ready_offsets.append(ready_ms)
        if index == 0:
            start_ms = ready_ms
        else:
            gap_ms = max(0.0, ready_ms - playback_end_ms)
            inter_chunk_gaps.append(gap_ms)
            start_ms = max(ready_ms, playback_end_ms)
        playback_end_ms = start_ms + chunk_audio_duration_s[index] * 1000.0
        generated_ms += total_ms

    metadata = plan.metadata()
    metadata.update(
        {
            "chunk_generate_ttfa_ms": [_round_or_none(value) for value in chunk_ttfa_ms],
            "chunk_generate_total_ms": [_round_or_none(value) for value in chunk_total_ms],
            "chunk_audio_duration_s": [_round_or_none(value, 3) for value in chunk_audio_duration_s],
            "chunk_audio_ready_offsets_ms": [_round_or_none(value) for value in ready_offsets],
            "inter_chunk_gap_ms": [_round_or_none(value) for value in inter_chunk_gaps],
            "max_inter_chunk_gap_ms": _round_or_none(max(inter_chunk_gaps) if inter_chunk_gaps else 0.0),
            "total_generation_ms": _round_or_none(sum(chunk_total_ms)),
            "stitched_audio_duration_s": _round_or_none(sum(chunk_audio_duration_s), 3),
            "stitched_playback_ms": _round_or_none(playback_end_ms),
        }
    )
    return metadata


def _set_generation_seed(seed: int | None) -> None:
    if seed is None:
        return
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except Exception:
        pass
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


def _configure_user_cache_env(env: dict[str, str] | None = None) -> dict[str, str]:
    target = dict(os.environ if env is None else env)
    target.setdefault("COQUI_TOS_AGREED", "1")
    home = Path.home()
    local_appdata = Path(target.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
    roaming_appdata = Path(target.get("APPDATA", str(home / "AppData" / "Roaming")))
    tts_home = Path(target.get("TTS_HOME", str(local_appdata / "rayme-tts-home")))
    local_appdata.mkdir(parents=True, exist_ok=True)
    roaming_appdata.mkdir(parents=True, exist_ok=True)
    tts_home.mkdir(parents=True, exist_ok=True)
    target.setdefault("LOCALAPPDATA", str(local_appdata))
    target.setdefault("APPDATA", str(roaming_appdata))
    target.setdefault("XDG_DATA_HOME", str(local_appdata))
    target.setdefault("TTS_HOME", str(tts_home))
    return target


def _sample_path(sample_root: Path, engine: str, profile: str, scenario: str) -> Path:
    return sample_root / f"{engine}__{profile}__{scenario}.wav"


def build_result_row(
    *,
    engine: str,
    runtime: str,
    host_account: str,
    profile: str,
    scenario: ScenarioSpec,
    backend: str,
    mode: str,
    streaming_support: str,
    true_streaming: bool,
    model_load_ms: float | None,
    warmup_ms: float | None,
    cached_prompt_build_ms: float | None,
    request_prompt_prep_ms: float | None,
    generate_ttfa_ms: float | None,
    generate_total_ms: float | None,
    audio_duration_s: float | None,
    peak_vram_mb: float | None,
    sample_rate: int | None,
    output_wav: Path | None,
    optimizations_applied: list[str],
    optimization_notes: str,
    variant: str | None = None,
    status: str = "measured",
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_ttfa_ms = None
    request_total_ms = None
    request_rtf = None
    generation_rtf = None

    if request_prompt_prep_ms is not None and generate_ttfa_ms is not None:
        request_ttfa_ms = request_prompt_prep_ms + generate_ttfa_ms
    if request_prompt_prep_ms is not None and generate_total_ms is not None:
        request_total_ms = request_prompt_prep_ms + generate_total_ms
    if audio_duration_s and audio_duration_s > 0 and generate_total_ms is not None:
        generation_rtf = compute_rtf(audio_duration_s, generate_total_ms / 1000.0)
    if audio_duration_s and audio_duration_s > 0 and request_total_ms is not None:
        request_rtf = compute_rtf(audio_duration_s, request_total_ms / 1000.0)

    row = {
        "engine": engine,
        "runtime": runtime,
        "host_account": host_account,
        "profile": profile,
        "scenario": scenario.name,
        "scenario_description": scenario.description,
        "scenario_word_count": scenario.word_count,
        "backend": backend,
        "mode": mode,
        "streaming_support": streaming_support,
        "true_streaming": true_streaming,
        "status": status,
        "model_load_ms": _round_or_none(model_load_ms),
        "warmup_ms": _round_or_none(warmup_ms),
        "cached_prompt_build_ms": _round_or_none(cached_prompt_build_ms),
        "request_prompt_prep_ms": _round_or_none(request_prompt_prep_ms),
        "generate_ttfa_ms": _round_or_none(generate_ttfa_ms),
        "generate_total_ms": _round_or_none(generate_total_ms),
        "request_ttfa_ms": _round_or_none(request_ttfa_ms),
        "request_total_ms": _round_or_none(request_total_ms),
        "audio_duration_s": _round_or_none(audio_duration_s, 3),
        "generation_rtf": _round_or_none(generation_rtf, 3),
        "request_rtf": _round_or_none(request_rtf, 3),
        "peak_vram_mb": _round_or_none(peak_vram_mb),
        "sample_rate": sample_rate,
        "output_wav": str(output_wav) if output_wav else None,
        "sample_path": str(output_wav) if output_wav else None,
        "stitched_playback_ms": None,
        "max_inter_chunk_gap_ms": None,
        "optimizations_applied": optimizations_applied,
        "optimization_notes": optimization_notes,
    }
    if variant:
        row["variant"] = variant
    if reason:
        row["reason"] = reason
    if extra:
        row.update(extra)
    return row


def _failed_rows(
    *,
    engine: str,
    runtime: str,
    host_account: str,
    scenarios: list[ScenarioSpec],
    profile: str,
    backend: str,
    mode: str,
    streaming_support: str,
    true_streaming: bool,
    model_load_ms: float | None,
    warmup_ms: float | None,
    cached_prompt_build_ms: float | None,
    optimizations_applied: list[str],
    optimization_notes: str,
    reason: str,
    variant: str | None = None,
) -> list[dict[str, Any]]:
    return [
        build_result_row(
            engine=engine,
            runtime=runtime,
            host_account=host_account,
            profile=profile,
            scenario=scenario,
            backend=backend,
            mode=mode,
            streaming_support=streaming_support,
            true_streaming=true_streaming,
            model_load_ms=model_load_ms,
            warmup_ms=warmup_ms,
            cached_prompt_build_ms=cached_prompt_build_ms,
            request_prompt_prep_ms=None,
            generate_ttfa_ms=None,
            generate_total_ms=None,
            audio_duration_s=None,
            peak_vram_mb=None,
            sample_rate=None,
            output_wav=None,
            optimizations_applied=optimizations_applied,
            optimization_notes=optimization_notes,
            variant=variant,
            status="failed",
            reason=reason,
        )
        for scenario in scenarios
    ]


def _best_row(rows: list[dict[str, Any]], scenario: str, metric: str) -> dict[str, Any] | None:
    candidates = [
        row
        for row in rows
        if row.get("scenario") == scenario
        and row.get("status") == "measured"
        and row.get(metric) is not None
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda row: (
            float(row[metric]),
            float(row.get("request_rtf") or float("inf")),
            ENGINE_ORDER.index(row["engine"]) if row["engine"] in ENGINE_ORDER else len(ENGINE_ORDER),
        ),
    )


def _promotion_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scenarios: list[str] = []
    for row in rows:
        scenario = row.get("scenario")
        if scenario and scenario not in scenarios:
            scenarios.append(str(scenario))

    comparisons: dict[str, Any] = {}
    for scenario in scenarios:
        f5_row = _best_row(
            [row for row in rows if row.get("engine") == "f5"],
            scenario,
            "request_ttfa_ms",
        )
        voxcpm2_row = _best_row(
            [row for row in rows if row.get("engine") == "voxcpm2"],
            scenario,
            "request_ttfa_ms",
        )
        comparisons[scenario] = {
            "f5_request_ttfa_ms": f5_row.get("request_ttfa_ms") if f5_row else None,
            "f5_request_total_ms": f5_row.get("request_total_ms") if f5_row else None,
            "f5_sample_path": f5_row.get("sample_path") if f5_row else None,
            "voxcpm2_request_ttfa_ms": voxcpm2_row.get("request_ttfa_ms") if voxcpm2_row else None,
            "voxcpm2_request_total_ms": voxcpm2_row.get("request_total_ms") if voxcpm2_row else None,
            "voxcpm2_sample_path": voxcpm2_row.get("sample_path") if voxcpm2_row else None,
            "voxcpm2_beats_f5_ttfa": (
                bool(voxcpm2_row and f5_row)
                and float(voxcpm2_row["request_ttfa_ms"]) < float(f5_row["request_ttfa_ms"])
            ),
        }
    return {
        "baseline_engine": "f5",
        "candidate_engine": "voxcpm2",
        "metric": "request_ttfa_ms",
        "requires_manual_quality": True,
        "by_scenario": comparisons,
    }


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scenarios = []
    for row in rows:
        scenario = row.get("scenario")
        if scenario and scenario not in scenarios:
            scenarios.append(scenario)

    best_request_ttfa: dict[str, Any] = {}
    best_request_total: dict[str, Any] = {}
    best_stitched_playback: dict[str, Any] = {}
    for scenario in scenarios:
        best_ttfa = _best_row(rows, scenario, "request_ttfa_ms")
        best_total = _best_row(rows, scenario, "request_total_ms")
        best_stitched = _best_row(rows, scenario, "stitched_playback_ms")
        if best_ttfa:
            best_request_ttfa[scenario] = {
                "engine": best_ttfa["engine"],
                "runtime": best_ttfa["runtime"],
                "profile": best_ttfa["profile"],
                "request_ttfa_ms": best_ttfa["request_ttfa_ms"],
                "output_wav": best_ttfa["output_wav"],
            }
        if best_total:
            best_request_total[scenario] = {
                "engine": best_total["engine"],
                "runtime": best_total["runtime"],
                "profile": best_total["profile"],
                "request_total_ms": best_total["request_total_ms"],
                "output_wav": best_total["output_wav"],
            }
        if best_stitched:
            best_stitched_playback[scenario] = {
                "engine": best_stitched["engine"],
                "runtime": best_stitched["runtime"],
                "profile": best_stitched["profile"],
                "stitched_playback_ms": best_stitched["stitched_playback_ms"],
                "output_wav": best_stitched["output_wav"],
            }

    return {
        "best_request_ttfa": best_request_ttfa,
        "best_request_total": best_request_total,
        "best_stitched_playback": best_stitched_playback,
        "promotion_comparison": _promotion_comparison(rows),
    }


def _write_audio_sample(sample_out: Path, sample: Any, sample_rate: int) -> None:
    import soundfile as sf

    sample_out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(sample_out, _to_float_np(sample), int(sample_rate))


def _run_f5_engine(
    *,
    runtime: str,
    host_account: str,
    ref_audio: str,
    ref_text: str,
    scenarios: list[ScenarioSpec],
    sample_root: Path,
) -> list[dict[str, Any]]:
    import numpy as np
    import torch
    import torchaudio

    _install_f5_runtime_shims()

    from f5_tts.api import F5TTS
    from f5_tts.infer.utils_infer import infer_batch_process, preprocess_ref_audio_text

    torch.cuda.empty_cache()
    with Timer() as load_timer:
        model = F5TTS()
    warmup_cuda()
    with Timer() as warm_timer:
        _ = model.infer(ref_audio, ref_text, "Warm.", nfe_step=7)
        _maybe_cuda_sync(torch)

    def prepare_reference() -> tuple[float, tuple[Any, int, str]]:
        with Timer() as prep_timer:
            prepared_ref_audio, prepared_ref_text = preprocess_ref_audio_text(
                ref_audio,
                ref_text,
                show_info=lambda *_args, **_kwargs: None,
            )
            ref_wave, ref_sample_rate = torchaudio.load(prepared_ref_audio)
        return prep_timer.elapsed_ms, (ref_wave, ref_sample_rate, prepared_ref_text)

    def synthesize(prepared: tuple[Any, int, str], text: str) -> tuple[float, float, float, float, int, np.ndarray]:
        ref_wave, ref_sample_rate, prepared_ref_text = prepared
        chunks: list[np.ndarray] = []
        sample_rate = model.target_sample_rate
        first_chunk_s: float | None = None
        with Timer() as timer:
            started = time.perf_counter()
            for chunk, sample_rate in infer_batch_process(
                (ref_wave, ref_sample_rate),
                prepared_ref_text,
                [text],
                model.ema_model,
                model.vocoder,
                mel_spec_type=model.mel_spec_type,
                progress=None,
                nfe_step=7,
                cfg_strength=2.0,
                sway_sampling_coef=-1.0,
                speed=1.0,
                device=model.device,
                streaming=True,
            ):
                if first_chunk_s is None:
                    first_chunk_s = time.perf_counter() - started
                chunks.append(np.asarray(chunk, dtype=np.float32).flatten())
            _maybe_cuda_sync(torch)

        wav = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
        audio_duration_s = len(wav) / float(sample_rate)
        return (
            (first_chunk_s or timer.elapsed_s) * 1000.0,
            timer.elapsed_ms,
            audio_duration_s,
            float(sample_vram_mb()["peak_allocated_mb"]),
            int(sample_rate),
            wav,
        )

    rows: list[dict[str, Any]] = []
    model_load_ms = load_timer.elapsed_ms
    warmup_ms = warm_timer.elapsed_ms

    baseline_notes = (
        "Warm model only. Baseline F5 uses the whole-request infer path, so prompt prep remains folded into the measured request time."
    )
    for scenario in scenarios:
        try:
            torch.cuda.reset_peak_memory_stats()
            with Timer() as timer:
                wav, sample_rate, _ = model.infer(
                    ref_audio,
                    ref_text,
                    scenario.text,
                    nfe_step=7,
                    speed=1.0,
                )
                _maybe_cuda_sync(torch)
            sample_out = _sample_path(sample_root, "f5", "baseline", scenario.name)
            _write_audio_sample(sample_out, wav, sample_rate)
            audio_duration_s = len(np.asarray(wav, dtype=np.float32).flatten()) / float(sample_rate)
            rows.append(
                build_result_row(
                    engine="f5",
                    runtime=runtime,
                    host_account=host_account,
                    profile="baseline",
                    scenario=scenario,
                    backend="native_infer_whole_request",
                    mode="non_streaming_clone",
                    streaming_support="none",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=warmup_ms,
                    cached_prompt_build_ms=None,
                    request_prompt_prep_ms=0.0,
                    generate_ttfa_ms=timer.elapsed_ms,
                    generate_total_ms=timer.elapsed_ms,
                    audio_duration_s=audio_duration_s,
                    peak_vram_mb=float(sample_vram_mb()["peak_allocated_mb"]),
                    sample_rate=int(sample_rate),
                    output_wav=sample_out,
                    optimizations_applied=[],
                    optimization_notes=baseline_notes,
                )
            )
        except Exception:
            rows.append(
                build_result_row(
                    engine="f5",
                    runtime=runtime,
                    host_account=host_account,
                    profile="baseline",
                    scenario=scenario,
                    backend="native_infer_whole_request",
                    mode="non_streaming_clone",
                    streaming_support="none",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=warmup_ms,
                    cached_prompt_build_ms=None,
                    request_prompt_prep_ms=None,
                    generate_ttfa_ms=None,
                    generate_total_ms=None,
                    audio_duration_s=None,
                    peak_vram_mb=None,
                    sample_rate=None,
                    output_wav=None,
                    optimizations_applied=[],
                    optimization_notes=baseline_notes,
                    status="failed",
                    reason=traceback.format_exc(limit=12),
                )
            )

    try:
        cached_prompt_build_ms, prepared_cached = prepare_reference()
    except Exception:
        return rows + _failed_rows(
            engine="f5",
            runtime=runtime,
            host_account=host_account,
            scenarios=scenarios,
            profile="optimized",
            backend="native_pytorch_chunked",
            mode="simulated_streaming",
            streaming_support="simulated",
            true_streaming=False,
            model_load_ms=model_load_ms,
            warmup_ms=warmup_ms,
            cached_prompt_build_ms=None,
            optimizations_applied=["prepared_ref_cache", "text_chunking"],
            optimization_notes="Optimized F5 prep failed before synthesis.",
            reason=traceback.format_exc(limit=12),
        )

    optimized_notes = (
        "Prepared reference cached once per session and replies use the shared sentence-aware chunk planner."
    )
    for scenario in scenarios:
        try:
            torch.cuda.reset_peak_memory_stats()
            plan = build_chunk_plan("f5", scenario.text)
            chunk_ttfa_ms: list[float] = []
            chunk_total_ms: list[float] = []
            chunk_audio_duration_s: list[float] = []
            chunk_peak_vram_mb: list[float] = []
            chunk_wavs: list[np.ndarray] = []
            sample_rate = model.target_sample_rate
            for chunk_text in plan.chunks:
                ttfa_ms, total_ms, audio_duration_s, peak_vram_mb, sample_rate, wav = synthesize(
                    prepared_cached,
                    chunk_text,
                )
                chunk_ttfa_ms.append(ttfa_ms)
                chunk_total_ms.append(total_ms)
                chunk_audio_duration_s.append(audio_duration_s)
                chunk_peak_vram_mb.append(peak_vram_mb)
                chunk_wavs.append(wav)
            wav = np.concatenate(chunk_wavs) if chunk_wavs else np.zeros(1, dtype=np.float32)
            audio_duration_s = len(wav) / float(sample_rate)
            peak_vram_mb = max(chunk_peak_vram_mb) if chunk_peak_vram_mb else 0.0
            chunk_extra = _chunk_playback_metadata(
                plan=plan,
                chunk_ttfa_ms=chunk_ttfa_ms,
                chunk_total_ms=chunk_total_ms,
                chunk_audio_duration_s=chunk_audio_duration_s,
            )
            sample_out = _sample_path(sample_root, "f5", "optimized", scenario.name)
            _write_audio_sample(sample_out, wav, sample_rate)
            rows.append(
                build_result_row(
                    engine="f5",
                    runtime=runtime,
                    host_account=host_account,
                    profile="optimized",
                    scenario=scenario,
                    backend="native_pytorch_chunked",
                    mode="non_streaming_clone",
                    streaming_support="simulated",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=warmup_ms,
                    cached_prompt_build_ms=cached_prompt_build_ms,
                    request_prompt_prep_ms=0.0,
                    generate_ttfa_ms=chunk_ttfa_ms[0] if chunk_ttfa_ms else None,
                    generate_total_ms=sum(chunk_total_ms),
                    audio_duration_s=audio_duration_s,
                    peak_vram_mb=peak_vram_mb,
                    sample_rate=sample_rate,
                    output_wav=sample_out,
                    optimizations_applied=["prepared_ref_cache", "shared_chunk_planner"],
                    optimization_notes=optimized_notes,
                    extra=chunk_extra,
                )
            )
        except Exception:
            rows.append(
                build_result_row(
                    engine="f5",
                    runtime=runtime,
                    host_account=host_account,
                    profile="optimized",
                    scenario=scenario,
                    backend="native_pytorch_chunked",
                    mode="shared_chunked_playback",
                    streaming_support="simulated",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=warmup_ms,
                    cached_prompt_build_ms=cached_prompt_build_ms,
                    request_prompt_prep_ms=None,
                    generate_ttfa_ms=None,
                    generate_total_ms=None,
                    audio_duration_s=None,
                    peak_vram_mb=None,
                    sample_rate=None,
                    output_wav=None,
                    optimizations_applied=["prepared_ref_cache", "shared_chunk_planner"],
                    optimization_notes=optimized_notes,
                    status="failed",
                    reason=traceback.format_exc(limit=12),
                )
            )

    del model
    torch.cuda.empty_cache()
    return rows


def _run_xtts_engine(
    *,
    runtime: str,
    host_account: str,
    ref_audio: str,
    scenarios: list[ScenarioSpec],
    sample_root: Path,
) -> list[dict[str, Any]]:
    import numpy as np
    import torch

    from TTS.api import TTS

    torch.cuda.empty_cache()
    with Timer() as load_timer:
        model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
    xtts_model = model.synthesizer.tts_model
    warmup_cuda()
    with Timer() as warm_timer:
        _ = model.tts(text="Warm.", speaker_wav=ref_audio, language="en")
        _maybe_cuda_sync(torch)

    sample_rate = int(getattr(model.synthesizer, "output_sample_rate", 24000))
    rows: list[dict[str, Any]] = []
    model_load_ms = load_timer.elapsed_ms
    warmup_ms = warm_timer.elapsed_ms

    def prepare_conditioning() -> tuple[float, tuple[Any, Any]]:
        with Timer() as prep_timer:
            latents = xtts_model.get_conditioning_latents(audio_path=ref_audio)
        return prep_timer.elapsed_ms, latents

    def synthesize(conditioning: tuple[Any, Any], text: str) -> tuple[float, float, float, float, int, np.ndarray, bool, str | None]:
        gpt_cond_latent, speaker_embedding = conditioning
        chunks: list[np.ndarray] = []
        streaming_ok = False
        streaming_error: str | None = None

        try:
            if hasattr(xtts_model, "inference_stream"):
                first_chunk_s: float | None = None
                with Timer() as timer:
                    started = time.perf_counter()
                    for chunk in xtts_model.inference_stream(
                        text=text,
                        language="en",
                        gpt_cond_latent=gpt_cond_latent,
                        speaker_embedding=speaker_embedding,
                    ):
                        if first_chunk_s is None:
                            first_chunk_s = time.perf_counter() - started
                        if isinstance(chunk, torch.Tensor):
                            chunk = chunk.detach().cpu().numpy()
                        chunks.append(np.asarray(chunk, dtype=np.float32).flatten())
                    _maybe_cuda_sync(torch)
                streaming_ok = True
                wav = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
                audio_duration_s = len(wav) / float(sample_rate)
                return (
                    (first_chunk_s or timer.elapsed_s) * 1000.0,
                    timer.elapsed_ms,
                    audio_duration_s,
                    float(sample_vram_mb()["peak_allocated_mb"]),
                    sample_rate,
                    wav,
                    streaming_ok,
                    streaming_error,
                )
        except Exception:
            streaming_error = traceback.format_exc(limit=8)

        with Timer() as timer:
            wav = model.tts(text=text, speaker_wav=ref_audio, language="en")
            _maybe_cuda_sync(torch)
        wav_np = np.asarray(wav, dtype=np.float32).flatten()
        audio_duration_s = len(wav_np) / float(sample_rate)
        return (
            timer.elapsed_ms,
            timer.elapsed_ms,
            audio_duration_s,
            float(sample_vram_mb()["peak_allocated_mb"]),
            sample_rate,
            wav_np,
            streaming_ok,
            streaming_error,
        )

    baseline_notes = (
        "Warm model only. Each request recomputes XTTS conditioning latents from the reference clip."
    )
    for scenario in scenarios:
        torch.cuda.reset_peak_memory_stats()
        prompt_ms, conditioning = prepare_conditioning()
        ttfa_ms, total_ms, audio_duration_s, peak_vram_mb, rate, wav, streaming_ok, streaming_error = synthesize(
            conditioning,
            scenario.text,
        )
        sample_out = _sample_path(sample_root, "xtts", "baseline", scenario.name)
        _write_audio_sample(sample_out, wav, rate)
        rows.append(
            build_result_row(
                engine="xtts",
                runtime=runtime,
                host_account=host_account,
                profile="baseline",
                scenario=scenario,
                backend="native_stream",
                mode="streaming" if streaming_ok else "non_streaming_fallback",
                streaming_support="native" if streaming_ok else "native_fallback",
                true_streaming=streaming_ok,
                model_load_ms=model_load_ms,
                warmup_ms=warmup_ms,
                cached_prompt_build_ms=None,
                request_prompt_prep_ms=prompt_ms,
                generate_ttfa_ms=ttfa_ms,
                generate_total_ms=total_ms,
                audio_duration_s=audio_duration_s,
                peak_vram_mb=peak_vram_mb,
                sample_rate=rate,
                output_wav=sample_out,
                optimizations_applied=[],
                optimization_notes=baseline_notes,
                extra={"streaming_error": streaming_error},
            )
        )

    cached_prompt_build_ms, cached_conditioning = prepare_conditioning()
    optimized_notes = (
        "Conditioning latents cached once per session; text is split by the shared planner before XTTS streaming."
    )
    for scenario in scenarios:
        torch.cuda.reset_peak_memory_stats()
        plan = build_chunk_plan("xtts", scenario.text)
        chunk_ttfa_ms: list[float] = []
        chunk_total_ms: list[float] = []
        chunk_audio_duration_s: list[float] = []
        chunk_peak_vram_mb: list[float] = []
        chunk_wavs: list[np.ndarray] = []
        chunk_streaming_ok: list[bool] = []
        streaming_errors: list[str] = []
        rate = sample_rate
        for chunk_text in plan.chunks:
            ttfa_ms, total_ms, audio_duration_s, peak_vram_mb, rate, wav, streaming_ok, streaming_error = synthesize(
                cached_conditioning,
                chunk_text,
            )
            chunk_ttfa_ms.append(ttfa_ms)
            chunk_total_ms.append(total_ms)
            chunk_audio_duration_s.append(audio_duration_s)
            chunk_peak_vram_mb.append(peak_vram_mb)
            chunk_wavs.append(wav)
            chunk_streaming_ok.append(streaming_ok)
            if streaming_error:
                streaming_errors.append(streaming_error)
        wav = np.concatenate(chunk_wavs) if chunk_wavs else np.zeros(1, dtype=np.float32)
        audio_duration_s = len(wav) / float(rate)
        peak_vram_mb = max(chunk_peak_vram_mb) if chunk_peak_vram_mb else 0.0
        all_streaming_ok = all(chunk_streaming_ok) if chunk_streaming_ok else False
        chunk_extra = _chunk_playback_metadata(
            plan=plan,
            chunk_ttfa_ms=chunk_ttfa_ms,
            chunk_total_ms=chunk_total_ms,
            chunk_audio_duration_s=chunk_audio_duration_s,
        )
        chunk_extra.update(
            {
                "chunk_streaming_ok": chunk_streaming_ok,
                "streaming_error": "\n--- chunk fallback ---\n".join(streaming_errors) if streaming_errors else None,
            }
        )
        sample_out = _sample_path(sample_root, "xtts", "optimized", scenario.name)
        _write_audio_sample(sample_out, wav, rate)
        rows.append(
            build_result_row(
                engine="xtts",
                runtime=runtime,
                host_account=host_account,
                profile="optimized",
                scenario=scenario,
                backend="native_stream",
                mode="shared_chunked_streaming" if all_streaming_ok else "shared_chunked_native_fallback",
                streaming_support="native" if all_streaming_ok else "native_partial_fallback",
                true_streaming=all_streaming_ok,
                model_load_ms=model_load_ms,
                warmup_ms=warmup_ms,
                cached_prompt_build_ms=cached_prompt_build_ms,
                request_prompt_prep_ms=0.0,
                generate_ttfa_ms=chunk_ttfa_ms[0] if chunk_ttfa_ms else None,
                generate_total_ms=sum(chunk_total_ms),
                audio_duration_s=audio_duration_s,
                peak_vram_mb=peak_vram_mb,
                sample_rate=rate,
                output_wav=sample_out,
                optimizations_applied=["conditioning_cache", "shared_chunk_planner"],
                optimization_notes=optimized_notes,
                extra=chunk_extra,
            )
        )

    del model
    torch.cuda.empty_cache()
    return rows


def _run_luxtts_engine(
    *,
    runtime: str,
    host_account: str,
    ref_audio: str,
    ref_text: str,
    scenarios: list[ScenarioSpec],
    sample_root: Path,
) -> list[dict[str, Any]]:
    import numpy as np
    import torch

    torch.cuda.empty_cache()
    with Timer() as load_timer:
        model = _load_luxtts_model()
    warmup_cuda()

    def prepare_prompt() -> tuple[float, dict[str, Any]]:
        with Timer() as prep_timer:
            prompt = _encode_luxtts_prompt(model, ref_audio, ref_text)
        return prep_timer.elapsed_ms, prompt

    with Timer() as warm_timer:
        _, warm_prompt = prepare_prompt()
        _ = _generate_luxtts_audio(model, warm_prompt, "Warm.")
        _maybe_cuda_sync(torch)

    rows: list[dict[str, Any]] = []
    model_load_ms = load_timer.elapsed_ms
    warmup_ms = warm_timer.elapsed_ms
    baseline_notes = (
        "Warm model only. Each request re-encodes the reference prompt before generation."
    )

    for scenario in scenarios:
        torch.cuda.reset_peak_memory_stats()
        prompt_ms, prompt = prepare_prompt()
        with Timer() as timer:
            wav, sample_rate = _generate_luxtts_audio(model, prompt, scenario.text)
            _maybe_cuda_sync(torch)
        sample_out = _sample_path(sample_root, "luxtts", "baseline", scenario.name)
        _write_audio_sample(sample_out, wav, sample_rate)
        audio_duration_s = len(wav.detach().cpu().numpy().flatten()) / float(sample_rate)
        rows.append(
            build_result_row(
                engine="luxtts",
                runtime=runtime,
                host_account=host_account,
                profile="baseline",
                scenario=scenario,
                backend="zipvoice_pytorch",
                mode="non_streaming_clone",
                streaming_support="none",
                true_streaming=False,
                model_load_ms=model_load_ms,
                warmup_ms=warmup_ms,
                cached_prompt_build_ms=None,
                request_prompt_prep_ms=prompt_ms,
                generate_ttfa_ms=timer.elapsed_ms,
                generate_total_ms=timer.elapsed_ms,
                audio_duration_s=audio_duration_s,
                peak_vram_mb=float(sample_vram_mb()["peak_allocated_mb"]),
                sample_rate=int(sample_rate),
                output_wav=sample_out,
                optimizations_applied=[],
                optimization_notes=baseline_notes,
            )
        )

    cached_prompt_build_ms, cached_prompt = prepare_prompt()
    optimized_notes = (
        "Prompt cache reused across replies and long text is split by the shared chunk planner."
    )
    for scenario in scenarios:
        torch.cuda.reset_peak_memory_stats()
        plan = build_chunk_plan("luxtts", scenario.text)
        chunk_ttfa_ms: list[float] = []
        chunk_total_ms: list[float] = []
        chunk_audio_duration_s: list[float] = []
        chunk_peak_vram_mb: list[float] = []
        chunk_wavs: list[np.ndarray] = []
        sample_rate = 48000
        for chunk_text in plan.chunks:
            with Timer() as timer:
                wav, sample_rate = _generate_luxtts_audio(model, cached_prompt, chunk_text)
                _maybe_cuda_sync(torch)
            wav_np = _to_float_np(wav)
            chunk_ttfa_ms.append(timer.elapsed_ms)
            chunk_total_ms.append(timer.elapsed_ms)
            chunk_audio_duration_s.append(len(wav_np) / float(sample_rate))
            chunk_peak_vram_mb.append(float(sample_vram_mb()["peak_allocated_mb"]))
            chunk_wavs.append(wav_np)
        wav = np.concatenate(chunk_wavs) if chunk_wavs else np.zeros(1, dtype=np.float32)
        sample_out = _sample_path(sample_root, "luxtts", "optimized", scenario.name)
        _write_audio_sample(sample_out, wav, sample_rate)
        audio_duration_s = len(wav) / float(sample_rate)
        chunk_extra = _chunk_playback_metadata(
            plan=plan,
            chunk_ttfa_ms=chunk_ttfa_ms,
            chunk_total_ms=chunk_total_ms,
            chunk_audio_duration_s=chunk_audio_duration_s,
        )
        rows.append(
            build_result_row(
                engine="luxtts",
                runtime=runtime,
                host_account=host_account,
                profile="optimized",
                scenario=scenario,
                backend="zipvoice_pytorch",
                mode="shared_chunked_playback",
                streaming_support="none",
                true_streaming=False,
                model_load_ms=model_load_ms,
                warmup_ms=warmup_ms,
                cached_prompt_build_ms=cached_prompt_build_ms,
                request_prompt_prep_ms=0.0,
                generate_ttfa_ms=chunk_ttfa_ms[0] if chunk_ttfa_ms else None,
                generate_total_ms=sum(chunk_total_ms),
                audio_duration_s=audio_duration_s,
                peak_vram_mb=max(chunk_peak_vram_mb) if chunk_peak_vram_mb else 0.0,
                sample_rate=int(sample_rate),
                output_wav=sample_out,
                optimizations_applied=["prompt_cache", "shared_chunk_planner"],
                optimization_notes=optimized_notes,
                extra=chunk_extra,
            )
        )

    del model
    torch.cuda.empty_cache()
    return rows


def _run_chatterbox_turbo_engine(
    *,
    runtime: str,
    host_account: str,
    ref_audio: str,
    scenarios: list[ScenarioSpec],
    sample_root: Path,
) -> list[dict[str, Any]]:
    import inspect
    import numpy as np
    import torch

    torch.cuda.empty_cache()
    with Timer() as load_timer:
        model = _load_chatterbox_turbo_model()
    warmup_cuda()

    def prepare_conditionals() -> float:
        with Timer() as prep_timer:
            model.prepare_conditionals(ref_audio, exaggeration=0.0, norm_loudness=True)
        return prep_timer.elapsed_ms

    def generate_text(text: str, seed: int | None = None) -> Any:
        _set_generation_seed(seed)
        kwargs: dict[str, Any] = {"audio_prompt_path": None}
        try:
            if seed is not None and "seed" in inspect.signature(model.generate).parameters:
                kwargs["seed"] = seed
        except Exception:
            pass
        return model.generate(text, **kwargs)

    with Timer() as warm_timer:
        _ = prepare_conditionals()
        _ = generate_text("Warm.")
        _maybe_cuda_sync(torch)

    rows: list[dict[str, Any]] = []
    model_load_ms = load_timer.elapsed_ms
    warmup_ms = warm_timer.elapsed_ms
    baseline_notes = (
        "Warm model only. Each request recomputes Chatterbox Turbo conditionals from the reference clip."
    )

    for scenario in scenarios:
        torch.cuda.reset_peak_memory_stats()
        prompt_ms = prepare_conditionals()
        with Timer() as timer:
            wav = generate_text(scenario.text)
            _maybe_cuda_sync(torch)
        sample_rate = int(getattr(model, "sr", None) or getattr(model, "sample_rate", 24000))
        sample_out = _sample_path(sample_root, "chatterbox_turbo", "baseline", scenario.name)
        _write_audio_sample(sample_out, wav, sample_rate)
        audio_duration_s = len(wav.squeeze().detach().cpu().numpy().flatten()) / float(sample_rate)
        rows.append(
            build_result_row(
                engine="chatterbox_turbo",
                runtime=runtime,
                host_account=host_account,
                profile="baseline",
                scenario=scenario,
                backend="turbo_native",
                mode="non_streaming_clone",
                streaming_support="none",
                true_streaming=False,
                model_load_ms=model_load_ms,
                warmup_ms=warmup_ms,
                cached_prompt_build_ms=None,
                request_prompt_prep_ms=prompt_ms,
                generate_ttfa_ms=timer.elapsed_ms,
                generate_total_ms=timer.elapsed_ms,
                audio_duration_s=audio_duration_s,
                peak_vram_mb=float(sample_vram_mb()["peak_allocated_mb"]),
                sample_rate=sample_rate,
                output_wav=sample_out,
                optimizations_applied=[],
                optimization_notes=baseline_notes,
            )
        )

    cached_prompt_build_ms = prepare_conditionals()
    for profile, seed in (("optimized", None), ("optimized_seed_1337", CHATTERBOX_ALT_SEED)):
        seed_note = (
            f" Alternate deterministic seed {seed} applied via model seed parameter when available, otherwise via Python/NumPy/Torch RNGs."
            if seed is not None
            else ""
        )
        optimized_notes = (
            "Prepared speaker conditionals cached once per session and text is split by the shared chunk planner."
            + seed_note
        ).strip()
        for scenario in scenarios:
            torch.cuda.reset_peak_memory_stats()
            plan = build_chunk_plan("chatterbox_turbo", scenario.text)
            chunk_ttfa_ms: list[float] = []
            chunk_total_ms: list[float] = []
            chunk_audio_duration_s: list[float] = []
            chunk_peak_vram_mb: list[float] = []
            chunk_wavs: list[np.ndarray] = []
            sample_rate = int(getattr(model, "sr", None) or getattr(model, "sample_rate", 24000))
            for index, chunk_text in enumerate(plan.chunks):
                with Timer() as timer:
                    wav = generate_text(chunk_text, None if seed is None else seed + index)
                    _maybe_cuda_sync(torch)
                wav_np = _to_float_np(wav.squeeze() if hasattr(wav, "squeeze") else wav)
                chunk_ttfa_ms.append(timer.elapsed_ms)
                chunk_total_ms.append(timer.elapsed_ms)
                chunk_audio_duration_s.append(len(wav_np) / float(sample_rate))
                chunk_peak_vram_mb.append(float(sample_vram_mb()["peak_allocated_mb"]))
                chunk_wavs.append(wav_np)
            stitched_wav = np.concatenate(chunk_wavs) if chunk_wavs else np.zeros(1, dtype=np.float32)
            sample_out = _sample_path(sample_root, "chatterbox_turbo", profile, scenario.name)
            _write_audio_sample(sample_out, stitched_wav, sample_rate)
            audio_duration_s = len(stitched_wav) / float(sample_rate)
            chunk_extra = _chunk_playback_metadata(
                plan=plan,
                chunk_ttfa_ms=chunk_ttfa_ms,
                chunk_total_ms=chunk_total_ms,
                chunk_audio_duration_s=chunk_audio_duration_s,
            )
            chunk_extra["seed"] = seed
            rows.append(
                build_result_row(
                    engine="chatterbox_turbo",
                    runtime=runtime,
                    host_account=host_account,
                    profile=profile,
                    scenario=scenario,
                    backend="turbo_native",
                    mode="shared_chunked_playback",
                    streaming_support="none",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=warmup_ms,
                    cached_prompt_build_ms=cached_prompt_build_ms,
                    request_prompt_prep_ms=0.0,
                    generate_ttfa_ms=chunk_ttfa_ms[0] if chunk_ttfa_ms else None,
                    generate_total_ms=sum(chunk_total_ms),
                    audio_duration_s=audio_duration_s,
                    peak_vram_mb=max(chunk_peak_vram_mb) if chunk_peak_vram_mb else 0.0,
                    sample_rate=sample_rate,
                    output_wav=sample_out,
                    optimizations_applied=["conditioning_cache", "shared_chunk_planner"]
                    + (["alternate_seed"] if seed is not None else []),
                    optimization_notes=optimized_notes,
                    extra=chunk_extra,
                )
            )

    del model
    torch.cuda.empty_cache()
    return rows


def _run_tada_engine(
    *,
    runtime: str,
    host_account: str,
    ref_audio: str,
    ref_text: str,
    scenarios: list[ScenarioSpec],
    sample_root: Path,
) -> list[dict[str, Any]]:
    import importlib.util
    import numpy as np
    import torch

    torch.cuda.empty_cache()
    with Timer() as load_timer:
        encoder, model = _load_tada_1b()
    warmup_cuda()

    def prepare_prompt() -> tuple[float, dict[str, Any]]:
        with Timer() as prep_timer:
            prompt = _create_tada_prompt(encoder, ref_audio, ref_text)
        return prep_timer.elapsed_ms, prompt

    with Timer() as warm_timer:
        _, warm_prompt = prepare_prompt()
        _ = _generate_tada_audio(model, warm_prompt, "Warm.")
        _maybe_cuda_sync(torch)

    rows: list[dict[str, Any]] = []
    model_load_ms = load_timer.elapsed_ms
    warmup_ms = warm_timer.elapsed_ms
    baseline_notes = (
        "Warm model only. Each request rebuilds the TADA voice prompt from the encoder."
    )

    for scenario in scenarios:
        try:
            torch.cuda.reset_peak_memory_stats()
            prompt_ms, prompt = prepare_prompt()
            with Timer() as timer:
                wav, sample_rate = _generate_tada_audio(model, prompt, scenario.text)
                _maybe_cuda_sync(torch)
            sample_out = _sample_path(sample_root, "tada_1b", "baseline", scenario.name)
            _write_audio_sample(sample_out, wav, sample_rate)
            audio_duration_s = len(np.asarray(wav).flatten()) / float(sample_rate)
            rows.append(
                build_result_row(
                    engine="tada_1b",
                    runtime=runtime,
                    host_account=host_account,
                    profile="baseline",
                    scenario=scenario,
                    backend="native_bf16",
                    mode="non_streaming_clone",
                    streaming_support="none",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=warmup_ms,
                    cached_prompt_build_ms=None,
                    request_prompt_prep_ms=prompt_ms,
                    generate_ttfa_ms=timer.elapsed_ms,
                    generate_total_ms=timer.elapsed_ms,
                    audio_duration_s=audio_duration_s,
                    peak_vram_mb=float(sample_vram_mb()["peak_allocated_mb"]),
                    sample_rate=int(sample_rate),
                    output_wav=sample_out,
                    optimizations_applied=[],
                    optimization_notes=baseline_notes,
                    variant="1B",
                )
            )
        except Exception:
            rows.append(
                build_result_row(
                    engine="tada_1b",
                    runtime=runtime,
                    host_account=host_account,
                    profile="baseline",
                    scenario=scenario,
                    backend="native_bf16",
                    mode="non_streaming_clone",
                    streaming_support="none",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=warmup_ms,
                    cached_prompt_build_ms=None,
                    request_prompt_prep_ms=None,
                    generate_ttfa_ms=None,
                    generate_total_ms=None,
                    audio_duration_s=None,
                    peak_vram_mb=None,
                    sample_rate=None,
                    output_wav=None,
                    optimizations_applied=[],
                    optimization_notes=baseline_notes,
                    status="failed",
                    reason=traceback.format_exc(limit=12),
                    variant="1B",
                )
            )

    optimized_applied = ["prompt_cache"]
    compile_ms: float | None = None
    compile_note = ""
    triton_available = importlib.util.find_spec("triton") is not None
    can_compile = runtime != "windows_native" and hasattr(model, "compile") and triton_available
    if can_compile:
        try:
            with Timer() as compile_timer:
                model.compile()
                _maybe_cuda_sync(torch)
            compile_ms = compile_timer.elapsed_ms
            optimized_applied.append("model.compile")
            compile_note = " Upstream model.compile() applied before the optimized run."
        except Exception as exc:
            compile_note = f" model.compile() was unavailable in this runtime ({type(exc).__name__}: {exc})."
    elif runtime == "windows_native":
        compile_note = " model.compile() skipped on Windows because Triton/inductor is not available in this runtime."

    cached_prompt_build_ms, cached_prompt = prepare_prompt()
    optimized_notes = (
        "Prompt cache reused across replies and text is split by the shared chunk planner." + compile_note
    ).strip()
    for scenario in scenarios:
        try:
            torch.cuda.reset_peak_memory_stats()
            plan = build_chunk_plan("tada_1b", scenario.text)
            chunk_ttfa_ms: list[float] = []
            chunk_total_ms: list[float] = []
            chunk_audio_duration_s: list[float] = []
            chunk_peak_vram_mb: list[float] = []
            chunk_wavs: list[np.ndarray] = []
            sample_rate = 24000
            for chunk_text in plan.chunks:
                with Timer() as timer:
                    wav, sample_rate = _generate_tada_audio(model, cached_prompt, chunk_text)
                    _maybe_cuda_sync(torch)
                wav_np = _to_float_np(wav)
                chunk_ttfa_ms.append(timer.elapsed_ms)
                chunk_total_ms.append(timer.elapsed_ms)
                chunk_audio_duration_s.append(len(wav_np) / float(sample_rate))
                chunk_peak_vram_mb.append(float(sample_vram_mb()["peak_allocated_mb"]))
                chunk_wavs.append(wav_np)
            wav = np.concatenate(chunk_wavs) if chunk_wavs else np.zeros(1, dtype=np.float32)
            sample_out = _sample_path(sample_root, "tada_1b", "optimized", scenario.name)
            _write_audio_sample(sample_out, wav, sample_rate)
            audio_duration_s = len(wav) / float(sample_rate)
            chunk_extra = _chunk_playback_metadata(
                plan=plan,
                chunk_ttfa_ms=chunk_ttfa_ms,
                chunk_total_ms=chunk_total_ms,
                chunk_audio_duration_s=chunk_audio_duration_s,
            )
            rows.append(
                build_result_row(
                    engine="tada_1b",
                    runtime=runtime,
                    host_account=host_account,
                    profile="optimized",
                    scenario=scenario,
                    backend="native_bf16_compiled" if "model.compile" in optimized_applied else "native_bf16",
                    mode="shared_chunked_playback",
                    streaming_support="none",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=(warmup_ms + (compile_ms or 0.0)),
                    cached_prompt_build_ms=cached_prompt_build_ms,
                    request_prompt_prep_ms=0.0,
                    generate_ttfa_ms=chunk_ttfa_ms[0] if chunk_ttfa_ms else None,
                    generate_total_ms=sum(chunk_total_ms),
                    audio_duration_s=audio_duration_s,
                    peak_vram_mb=max(chunk_peak_vram_mb) if chunk_peak_vram_mb else 0.0,
                    sample_rate=int(sample_rate),
                    output_wav=sample_out,
                    optimizations_applied=optimized_applied + ["shared_chunk_planner"],
                    optimization_notes=optimized_notes,
                    extra=chunk_extra,
                    variant="1B",
                )
            )
        except Exception:
            rows.append(
                build_result_row(
                    engine="tada_1b",
                    runtime=runtime,
                    host_account=host_account,
                    profile="optimized",
                    scenario=scenario,
                    backend="native_bf16_compiled" if "model.compile" in optimized_applied else "native_bf16",
                    mode="shared_chunked_playback",
                    streaming_support="none",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=(warmup_ms + (compile_ms or 0.0)),
                    cached_prompt_build_ms=cached_prompt_build_ms,
                    request_prompt_prep_ms=None,
                    generate_ttfa_ms=None,
                    generate_total_ms=None,
                    audio_duration_s=None,
                    peak_vram_mb=None,
                    sample_rate=None,
                    output_wav=None,
                    optimizations_applied=optimized_applied + ["shared_chunk_planner"],
                    optimization_notes=optimized_notes,
                    status="failed",
                    reason=traceback.format_exc(limit=12),
                    variant="1B",
                )
            )

    del encoder
    del model
    torch.cuda.empty_cache()
    return rows


def _run_qwen3_engine(
    *,
    runtime: str,
    host_account: str,
    ref_audio: str,
    ref_text: str,
    scenarios: list[ScenarioSpec],
    sample_root: Path,
) -> list[dict[str, Any]]:
    import numpy as np
    import torch
    from qwen_tts import Qwen3TTSModel

    def load_model(attn_implementation: str) -> tuple[Any, float, str, str]:
        backend = attn_implementation
        note = ""
        with Timer() as load_timer:
            try:
                model = Qwen3TTSModel.from_pretrained(
                    "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                    device_map="cuda:0",
                    torch_dtype=torch.bfloat16,
                    attn_implementation=attn_implementation,
                )
            except Exception:
                if attn_implementation != "eager":
                    note = (
                        f"Requested {attn_implementation} but fell back to eager "
                        f"({traceback.format_exc(limit=4).strip()[:400]})."
                    )
                    backend = "eager"
                    model = Qwen3TTSModel.from_pretrained(
                        "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                        device_map="cuda:0",
                        torch_dtype=torch.bfloat16,
                        attn_implementation="eager",
                    )
                else:
                    raise
        return model, load_timer.elapsed_ms, backend, note

    def prepare_prompt(model: Any) -> tuple[float, Any]:
        with Timer() as prep_timer:
            prompt = model.create_voice_clone_prompt(
                ref_audio=ref_audio,
                ref_text=ref_text,
                x_vector_only_mode=False,
            )
        return prep_timer.elapsed_ms, prompt

    rows: list[dict[str, Any]] = []
    run_specs = [
        ("baseline", "eager"),
        ("optimized", "flash_attention_2"),
    ]

    for profile, backend_requested in run_specs:
        torch.cuda.empty_cache()
        model, model_load_ms, backend_used, backend_note = load_model(backend_requested)
        warmup_cuda()

        with Timer() as warm_timer:
            _, warm_prompt = prepare_prompt(model)
            _ = model.generate_voice_clone(
                text="Warm.",
                voice_clone_prompt=warm_prompt,
                language="English",
                non_streaming_mode=False,
            )
            _maybe_cuda_sync(torch)

        cached_prompt_build_ms = None
        cached_prompt = None
        request_prep_mode = "Each request rebuilds the Qwen voice clone prompt."
        applied: list[str] = []
        if profile == "optimized":
            cached_prompt_build_ms, cached_prompt = prepare_prompt(model)
            request_prep_mode = "Voice clone prompt cached once per session."
            applied.append("prompt_cache")
            if backend_used == "flash_attention_2":
                applied.append("flash_attention_2")

        for scenario in scenarios:
            torch.cuda.reset_peak_memory_stats()
            request_prompt_ms = 0.0
            prompt = cached_prompt
            if prompt is None:
                request_prompt_ms, prompt = prepare_prompt(model)

            extra: dict[str, Any] | None = None
            if profile == "optimized":
                plan = build_chunk_plan("qwen3", scenario.text)
                chunk_ttfa_ms: list[float] = []
                chunk_total_ms: list[float] = []
                chunk_audio_duration_s: list[float] = []
                chunk_peak_vram_mb: list[float] = []
                chunk_wavs: list[np.ndarray] = []
                sample_rate = 24000
                for chunk_text in plan.chunks:
                    with Timer() as timer:
                        wavs, sample_rate = model.generate_voice_clone(
                            text=chunk_text,
                            voice_clone_prompt=prompt,
                            language="English",
                            non_streaming_mode=False,
                        )
                        _maybe_cuda_sync(torch)
                    wav = wavs[0] if hasattr(wavs, "__len__") and len(wavs) > 0 else wavs
                    wav_np = _to_float_np(wav)
                    chunk_ttfa_ms.append(timer.elapsed_ms)
                    chunk_total_ms.append(timer.elapsed_ms)
                    chunk_audio_duration_s.append(len(wav_np) / float(sample_rate))
                    chunk_peak_vram_mb.append(float(sample_vram_mb()["peak_allocated_mb"]))
                    chunk_wavs.append(wav_np)
                sample = np.concatenate(chunk_wavs) if chunk_wavs else np.zeros(1, dtype=np.float32)
                audio_duration_s = len(sample) / float(sample_rate)
                generate_ttfa_ms = chunk_ttfa_ms[0] if chunk_ttfa_ms else None
                generate_total_ms = sum(chunk_total_ms)
                peak_vram_mb = max(chunk_peak_vram_mb) if chunk_peak_vram_mb else 0.0
                extra = _chunk_playback_metadata(
                    plan=plan,
                    chunk_ttfa_ms=chunk_ttfa_ms,
                    chunk_total_ms=chunk_total_ms,
                    chunk_audio_duration_s=chunk_audio_duration_s,
                )
                applied_for_row = applied + ["shared_chunk_planner"]
                mode = "shared_chunked_playback"
            else:
                with Timer() as timer:
                    wavs, sample_rate = model.generate_voice_clone(
                        text=scenario.text,
                        voice_clone_prompt=prompt,
                        language="English",
                        non_streaming_mode=False,
                    )
                    _maybe_cuda_sync(torch)

                wav = wavs[0] if hasattr(wavs, "__len__") and len(wavs) > 0 else wavs
                sample = _to_float_np(wav)
                audio_duration_s = len(sample) / float(sample_rate)
                generate_ttfa_ms = timer.elapsed_ms
                generate_total_ms = timer.elapsed_ms
                peak_vram_mb = float(sample_vram_mb()["peak_allocated_mb"])
                applied_for_row = applied
                mode = "simulated_streaming_text"
            sample_out = _sample_path(sample_root, "qwen3", profile, scenario.name)
            _write_audio_sample(sample_out, sample, int(sample_rate))
            notes = request_prep_mode
            if backend_note:
                notes = f"{notes} {backend_note}".strip()
            rows.append(
                build_result_row(
                    engine="qwen3",
                    runtime=runtime,
                    host_account=host_account,
                    profile=profile,
                    scenario=scenario,
                    backend=backend_used,
                    mode=mode,
                    streaming_support="simulated",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=warm_timer.elapsed_ms,
                    cached_prompt_build_ms=cached_prompt_build_ms,
                    request_prompt_prep_ms=request_prompt_ms,
                    generate_ttfa_ms=generate_ttfa_ms,
                    generate_total_ms=generate_total_ms,
                    audio_duration_s=audio_duration_s,
                    peak_vram_mb=peak_vram_mb,
                    sample_rate=int(sample_rate),
                    output_wav=sample_out,
                    optimizations_applied=applied_for_row,
                    optimization_notes=notes,
                    extra=extra,
                    variant="0.6B-Base",
                )
            )

        del model
        torch.cuda.empty_cache()

    return rows


def _voxcpm2_model_sample_rate(model: Any) -> int:
    tts_model = getattr(model, "tts_model", None)
    sample_rate = getattr(tts_model, "sample_rate", None)
    if sample_rate is None:
        sample_rate = getattr(model, "sample_rate", None)
    if sample_rate is None:
        raise ValueError("VoxCPM2 runtime did not report an output sample rate")
    return int(sample_rate)


def _voxcpm2_generate_kwargs(*, text: str, ref_audio: str, ref_text: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "text": text,
        "cfg_value": 2.0,
        "inference_timesteps": 10,
    }
    reference_text = ref_text.strip()
    if reference_text:
        kwargs["prompt_wav_path"] = ref_audio
        kwargs["prompt_text"] = reference_text
    else:
        kwargs["reference_wav_path"] = ref_audio
    return kwargs


def _ensure_voxcpm2_cuda_residency(model: Any) -> None:
    device_types: set[str] = set()
    for candidate in (model, getattr(model, "tts_model", None), getattr(model, "model", None)):
        if candidate is None or not hasattr(candidate, "parameters"):
            continue
        try:
            for parameter in candidate.parameters():
                device_types.add(parameter.device.type)
                break
        except Exception:
            continue
    if device_types == {"cpu"}:
        raise RuntimeError("VoxCPM2 model parameters loaded on CPU")


def _run_voxcpm2_engine(
    *,
    runtime: str,
    host_account: str,
    ref_audio: str,
    ref_text: str,
    scenarios: list[ScenarioSpec],
    sample_root: Path,
) -> list[dict[str, Any]]:
    import numpy as np
    import torch
    from voxcpm import VoxCPM

    torch.cuda.empty_cache()
    with Timer() as load_timer:
        # voxcpm==2.0.2 rejects the documented device kwarg; CUDA residency is
        # verified after load to keep the runtime contract truthful.
        model = VoxCPM.from_pretrained(MODEL_ID_VOXCPM2, load_denoiser=False)
    _ensure_voxcpm2_cuda_residency(model)
    sample_rate = _voxcpm2_model_sample_rate(model)
    warmup_cuda()
    with Timer() as warm_timer:
        _ = model.generate(**_voxcpm2_generate_kwargs(text="Warm.", ref_audio=ref_audio, ref_text=ref_text))
        _maybe_cuda_sync(torch)

    rows: list[dict[str, Any]] = []
    model_load_ms = load_timer.elapsed_ms
    warmup_ms = warm_timer.elapsed_ms

    def synthesize(text: str) -> tuple[float, float, float, float, int, np.ndarray]:
        with Timer() as timer:
            sample = model.generate(**_voxcpm2_generate_kwargs(text=text, ref_audio=ref_audio, ref_text=ref_text))
            _maybe_cuda_sync(torch)
        rate = _voxcpm2_model_sample_rate(model)
        wav = _to_float_np(sample)
        return (
            timer.elapsed_ms,
            timer.elapsed_ms,
            len(wav) / float(rate),
            float(sample_vram_mb()["peak_allocated_mb"]),
            rate,
            wav,
        )

    baseline_notes = (
        "Warm model only. VoxCPM2 standard Python generate path uses the official openbmb/VoxCPM2 runtime."
    )
    for scenario in scenarios:
        try:
            torch.cuda.reset_peak_memory_stats()
            ttfa_ms, total_ms, audio_duration_s, peak_vram_mb, rate, wav = synthesize(scenario.text)
            sample_out = _sample_path(sample_root, "voxcpm2", "baseline", scenario.name)
            _write_audio_sample(sample_out, wav, rate)
            rows.append(
                build_result_row(
                    engine="voxcpm2",
                    runtime=runtime,
                    host_account=host_account,
                    profile="baseline",
                    scenario=scenario,
                    backend="standard_python_api",
                    mode="standard_python_generate",
                    streaming_support="available_benchmark_only",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=warmup_ms,
                    cached_prompt_build_ms=None,
                    request_prompt_prep_ms=0.0,
                    generate_ttfa_ms=ttfa_ms,
                    generate_total_ms=total_ms,
                    audio_duration_s=audio_duration_s,
                    peak_vram_mb=peak_vram_mb,
                    sample_rate=rate,
                    output_wav=sample_out,
                    optimizations_applied=[],
                    optimization_notes=baseline_notes,
                )
            )
        except Exception:
            rows.append(
                build_result_row(
                    engine="voxcpm2",
                    runtime=runtime,
                    host_account=host_account,
                    profile="baseline",
                    scenario=scenario,
                    backend="standard_python_api",
                    mode="standard_python_generate",
                    streaming_support="available_benchmark_only",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=warmup_ms,
                    cached_prompt_build_ms=None,
                    request_prompt_prep_ms=None,
                    generate_ttfa_ms=None,
                    generate_total_ms=None,
                    audio_duration_s=None,
                    peak_vram_mb=None,
                    sample_rate=None,
                    output_wav=None,
                    optimizations_applied=[],
                    optimization_notes=baseline_notes,
                    status="failed",
                    reason=traceback.format_exc(limit=12),
                )
            )

    optimized_notes = (
        "VoxCPM2 standard Python generate path measured through the shared RayMe chunk planner; "
        "streaming API remains benchmark-only unless call code consumes chunks live."
    )
    for scenario in scenarios:
        try:
            torch.cuda.reset_peak_memory_stats()
            plan = build_chunk_plan("voxcpm2", scenario.text)
            chunk_ttfa_ms: list[float] = []
            chunk_total_ms: list[float] = []
            chunk_audio_duration_s: list[float] = []
            chunk_peak_vram_mb: list[float] = []
            chunk_wavs: list[np.ndarray] = []
            rate = sample_rate
            for chunk_text in plan.chunks:
                ttfa_ms, total_ms, audio_duration_s, peak_vram_mb, rate, wav = synthesize(chunk_text)
                chunk_ttfa_ms.append(ttfa_ms)
                chunk_total_ms.append(total_ms)
                chunk_audio_duration_s.append(audio_duration_s)
                chunk_peak_vram_mb.append(peak_vram_mb)
                chunk_wavs.append(wav)
            stitched_wav = np.concatenate(chunk_wavs) if chunk_wavs else np.zeros(1, dtype=np.float32)
            sample_out = _sample_path(sample_root, "voxcpm2", "optimized", scenario.name)
            _write_audio_sample(sample_out, stitched_wav, rate)
            audio_duration_s = len(stitched_wav) / float(rate)
            chunk_extra = _chunk_playback_metadata(
                plan=plan,
                chunk_ttfa_ms=chunk_ttfa_ms,
                chunk_total_ms=chunk_total_ms,
                chunk_audio_duration_s=chunk_audio_duration_s,
            )
            rows.append(
                build_result_row(
                    engine="voxcpm2",
                    runtime=runtime,
                    host_account=host_account,
                    profile="standard_python",
                    scenario=scenario,
                    backend="standard_python_api",
                    mode="shared_chunked_playback",
                    streaming_support="available_benchmark_only",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=warmup_ms,
                    cached_prompt_build_ms=None,
                    request_prompt_prep_ms=0.0,
                    generate_ttfa_ms=chunk_ttfa_ms[0] if chunk_ttfa_ms else None,
                    generate_total_ms=sum(chunk_total_ms),
                    audio_duration_s=audio_duration_s,
                    peak_vram_mb=max(chunk_peak_vram_mb) if chunk_peak_vram_mb else 0.0,
                    sample_rate=rate,
                    output_wav=sample_out,
                    optimizations_applied=["shared_chunk_planner"],
                    optimization_notes=optimized_notes,
                    extra=chunk_extra,
                )
            )
        except Exception:
            rows.append(
                build_result_row(
                    engine="voxcpm2",
                    runtime=runtime,
                    host_account=host_account,
                    profile="optimized",
                    scenario=scenario,
                    backend="standard_python_api",
                    mode="shared_chunked_playback",
                    streaming_support="available_benchmark_only",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=warmup_ms,
                    cached_prompt_build_ms=None,
                    request_prompt_prep_ms=None,
                    generate_ttfa_ms=None,
                    generate_total_ms=None,
                    audio_duration_s=None,
                    peak_vram_mb=None,
                    sample_rate=None,
                    output_wav=None,
                    optimizations_applied=["shared_chunk_planner"],
                    optimization_notes=optimized_notes,
                    status="failed",
                    reason=traceback.format_exc(limit=12),
                )
            )

    if hasattr(model, "generate_streaming"):
        streaming_notes = (
            "VoxCPM2 generate_streaming chunks are collected into one WAV for benchmark-only metrics; "
            "this row does not claim RayMe call-flow streaming."
        )
        for scenario in scenarios:
            try:
                torch.cuda.reset_peak_memory_stats()
                chunks: list[np.ndarray] = []
                first_chunk_s: float | None = None
                with Timer() as timer:
                    started = time.perf_counter()
                    for chunk in model.generate_streaming(
                        **_voxcpm2_generate_kwargs(text=scenario.text, ref_audio=ref_audio, ref_text=ref_text)
                    ):
                        if first_chunk_s is None:
                            first_chunk_s = time.perf_counter() - started
                        chunks.append(_to_float_np(chunk))
                    _maybe_cuda_sync(torch)
                rate = _voxcpm2_model_sample_rate(model)
                wav = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
                sample_out = _sample_path(sample_root, "voxcpm2", "streaming_collected", scenario.name)
                _write_audio_sample(sample_out, wav, rate)
                audio_duration_s = len(wav) / float(rate)
                rows.append(
                    build_result_row(
                        engine="voxcpm2",
                        runtime=runtime,
                        host_account=host_account,
                        profile="streaming_collected",
                        scenario=scenario,
                        backend="standard_python_api",
                        mode="standard_python_streaming_collected",
                        streaming_support="native_benchmark_only",
                        true_streaming=False,
                        model_load_ms=model_load_ms,
                        warmup_ms=warmup_ms,
                        cached_prompt_build_ms=None,
                        request_prompt_prep_ms=0.0,
                        generate_ttfa_ms=(first_chunk_s or timer.elapsed_s) * 1000.0,
                        generate_total_ms=timer.elapsed_ms,
                        audio_duration_s=audio_duration_s,
                        peak_vram_mb=float(sample_vram_mb()["peak_allocated_mb"]),
                        sample_rate=rate,
                        output_wav=sample_out,
                        optimizations_applied=["generate_streaming_collected"],
                        optimization_notes=streaming_notes,
                        extra={"streaming_benchmark_only": True},
                    )
                )
            except Exception:
                rows.append(
                    build_result_row(
                        engine="voxcpm2",
                        runtime=runtime,
                        host_account=host_account,
                        profile="streaming_collected",
                        scenario=scenario,
                        backend="standard_python_api",
                        mode="standard_python_streaming_collected",
                        streaming_support="native_benchmark_only",
                        true_streaming=False,
                        model_load_ms=model_load_ms,
                        warmup_ms=warmup_ms,
                        cached_prompt_build_ms=None,
                        request_prompt_prep_ms=None,
                        generate_ttfa_ms=None,
                        generate_total_ms=None,
                        audio_duration_s=None,
                        peak_vram_mb=None,
                        sample_rate=None,
                        output_wav=None,
                        optimizations_applied=["generate_streaming_collected"],
                        optimization_notes=streaming_notes,
                        status="failed",
                        reason=traceback.format_exc(limit=12),
                        extra={"streaming_benchmark_only": True},
                    )
                )

    del model
    torch.cuda.empty_cache()
    return rows


def run_engine_locally(
    *,
    engine: str,
    runtime: str,
    host_account: str,
    ref_audio: str,
    ref_text: str,
    sample_root: Path,
) -> dict[str, Any]:
    scenarios = scenario_specs()
    try:
        if engine == "f5":
            rows = _run_f5_engine(
                runtime=runtime,
                host_account=host_account,
                ref_audio=ref_audio,
                ref_text=ref_text,
                scenarios=scenarios,
                sample_root=sample_root,
            )
        elif engine == "xtts":
            rows = _run_xtts_engine(
                runtime=runtime,
                host_account=host_account,
                ref_audio=ref_audio,
                scenarios=scenarios,
                sample_root=sample_root,
            )
        elif engine == "luxtts":
            rows = _run_luxtts_engine(
                runtime=runtime,
                host_account=host_account,
                ref_audio=ref_audio,
                ref_text=ref_text,
                scenarios=scenarios,
                sample_root=sample_root,
            )
        elif engine == "chatterbox_turbo":
            rows = _run_chatterbox_turbo_engine(
                runtime=runtime,
                host_account=host_account,
                ref_audio=ref_audio,
                scenarios=scenarios,
                sample_root=sample_root,
            )
        elif engine == "tada_1b":
            rows = _run_tada_engine(
                runtime=runtime,
                host_account=host_account,
                ref_audio=ref_audio,
                ref_text=ref_text,
                scenarios=scenarios,
                sample_root=sample_root,
            )
        elif engine == "qwen3":
            rows = _run_qwen3_engine(
                runtime=runtime,
                host_account=host_account,
                ref_audio=ref_audio,
                ref_text=ref_text,
                scenarios=scenarios,
                sample_root=sample_root,
            )
        elif engine == "voxcpm2":
            rows = _run_voxcpm2_engine(
                runtime=runtime,
                host_account=host_account,
                ref_audio=ref_audio,
                ref_text=ref_text,
                scenarios=scenarios,
                sample_root=sample_root,
            )
        else:
            raise ValueError(f"Unknown engine: {engine}")
    except BaseException as exc:
        rows = _failed_rows(
            engine=engine,
            runtime=runtime,
            host_account=host_account,
            scenarios=scenarios,
            profile="baseline",
            backend="unknown",
            mode="unknown",
            streaming_support="unknown",
            true_streaming=False,
            model_load_ms=None,
            warmup_ms=None,
            cached_prompt_build_ms=None,
            optimizations_applied=[],
            optimization_notes="Engine run failed before producing measurements.",
            reason=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=12)}",
        ) + _failed_rows(
            engine=engine,
            runtime=runtime,
            host_account=host_account,
            scenarios=scenarios,
            profile="optimized",
            backend="unknown",
            mode="unknown",
            streaming_support="unknown",
            true_streaming=False,
            model_load_ms=None,
            warmup_ms=None,
            cached_prompt_build_ms=None,
            optimizations_applied=[],
            optimization_notes="Engine run failed before producing measurements.",
            reason=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=12)}",
        )
    return {
        "engine": engine,
        "runtime": runtime,
        "host_account": host_account,
        "rows": rows,
    }


def run_engine_subprocess(
    *,
    engine: str,
    runtime: str,
    host_account: str,
    ref_audio: Path,
    ref_text_path: Path,
    sample_root: Path,
) -> dict[str, Any]:
    temp_output = sample_root / f"{engine}.rows.json"
    if temp_output.exists():
        temp_output.unlink()

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--run-engine",
        engine,
        "--runtime-label",
        runtime,
        "--host-account",
        host_account,
        "--ref-audio",
        str(ref_audio),
        "--ref-text",
        str(ref_text_path),
        "--engine-output",
        str(temp_output),
        "--sample-root",
        str(sample_root),
    ]
    env = _configure_user_cache_env()
    proc = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )

    if proc.returncode == 0 and temp_output.exists():
        return json.loads(temp_output.read_text(encoding="utf-8"))

    error = "\n".join(part for part in (proc.stdout, proc.stderr) if part).strip()
    scenarios = scenario_specs()
    rows = _failed_rows(
        engine=engine,
        runtime=runtime,
        host_account=host_account,
        scenarios=scenarios,
        profile="baseline",
        backend="subprocess",
        mode="unknown",
        streaming_support="unknown",
        true_streaming=False,
        model_load_ms=None,
        warmup_ms=None,
        cached_prompt_build_ms=None,
        optimizations_applied=[],
        optimization_notes="Engine subprocess failed.",
        reason=f"subprocess_exit_{proc.returncode}: {error[:4000]}",
    ) + _failed_rows(
        engine=engine,
        runtime=runtime,
        host_account=host_account,
        scenarios=scenarios,
        profile="optimized",
        backend="subprocess",
        mode="unknown",
        streaming_support="unknown",
        true_streaming=False,
        model_load_ms=None,
        warmup_ms=None,
        cached_prompt_build_ms=None,
        optimizations_applied=[],
        optimization_notes="Engine subprocess failed.",
        reason=f"subprocess_exit_{proc.returncode}: {error[:4000]}",
    )
    return {
        "engine": engine,
        "runtime": runtime,
        "host_account": host_account,
        "rows": rows,
        "subprocess_error": error[:4000],
    }


def run_matrix(
    *,
    runtime: str,
    host_account: str,
    ref_audio: Path,
    ref_text_path: Path,
    output: Path,
    sample_root: Path,
    engines: list[str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    engine_payloads: list[dict[str, Any]] = []
    for engine in engines:
        payload = run_engine_subprocess(
            engine=engine,
            runtime=runtime,
            host_account=host_account,
            ref_audio=ref_audio,
            ref_text_path=ref_text_path,
            sample_root=sample_root,
        )
        engine_payloads.append(payload)
        rows.extend(payload["rows"])

    document = {
        "probe": "tts_scenario_matrix",
        "runtime": runtime,
        "host_account": host_account,
        "ref_audio": str(ref_audio),
        "ref_text": str(ref_text_path),
        "engines": engines,
        "profiles": list(PROFILE_ORDER),
        "scenarios": [
            {
                "name": scenario.name,
                "description": scenario.description,
                "word_count": scenario.word_count,
            }
            for scenario in scenario_specs()
        ],
        "rows": rows,
        "summary": build_summary(rows),
        "engine_payloads": engine_payloads,
    }
    write_results(output, document)
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref-audio", required=True)
    parser.add_argument("--ref-text", required=True)
    parser.add_argument("--output", default=str(RESULT_PATH))
    parser.add_argument("--sample-root", default=str(OUTPUT_SAMPLE_DIR))
    parser.add_argument("--runtime-label", default="local")
    parser.add_argument("--host-account", default="local")
    parser.add_argument("--engines", nargs="*", choices=ENGINE_ORDER, default=list(ENGINE_ORDER))
    parser.add_argument("--run-engine", choices=ENGINE_ORDER)
    parser.add_argument("--engine-output")
    args = parser.parse_args()

    ref_audio = Path(args.ref_audio)
    ref_text_path = Path(args.ref_text)
    if not ref_audio.exists():
        print(f"ERROR: ref-audio missing: {ref_audio}", file=sys.stderr)
        return 2
    if not ref_text_path.exists():
        print(f"ERROR: ref-text missing: {ref_text_path}", file=sys.stderr)
        return 2
    if not LONG_REPLY_FIXTURE.exists():
        print(f"ERROR: long-reply fixture missing: {LONG_REPLY_FIXTURE}", file=sys.stderr)
        return 2

    env = _configure_user_cache_env()
    os.environ.update(env)
    ref_text = _read_reference_text(ref_text_path)
    sample_root = Path(args.sample_root)
    sample_root.mkdir(parents=True, exist_ok=True)

    if args.run_engine:
        if not args.engine_output:
            print("ERROR: --run-engine requires --engine-output", file=sys.stderr)
            return 2
        payload = run_engine_locally(
            engine=args.run_engine,
            runtime=args.runtime_label,
            host_account=args.host_account,
            ref_audio=str(ref_audio),
            ref_text=ref_text,
            sample_root=sample_root,
        )
        Path(args.engine_output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return 0

    payload = run_matrix(
        runtime=args.runtime_label,
        host_account=args.host_account,
        ref_audio=ref_audio,
        ref_text_path=ref_text_path,
        output=Path(args.output),
        sample_root=sample_root,
        engines=list(args.engines),
    )
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
