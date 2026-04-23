"""Warm-model TTS scenario matrix for RayMe-style reply generation."""

from __future__ import annotations

import argparse
import json
import os
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

ENGINE_ORDER = ("f5", "xtts", "luxtts", "chatterbox_turbo", "tada_1b", "qwen3")
PROFILE_ORDER = ("baseline", "optimized")
PHASE_DIR = Path(".planning/phases/00-measurement-gate")
RESULT_PATH = PHASE_DIR / "results" / "tts_scenario_matrix_local.json"
OUTPUT_SAMPLE_DIR = PHASE_DIR / "results" / "tts_scenario_audio"
LONG_REPLY_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "target_text_1min.txt"
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


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scenarios = []
    for row in rows:
        scenario = row.get("scenario")
        if scenario and scenario not in scenarios:
            scenarios.append(scenario)

    best_request_ttfa: dict[str, Any] = {}
    best_request_total: dict[str, Any] = {}
    for scenario in scenarios:
        best_ttfa = _best_row(rows, scenario, "request_ttfa_ms")
        best_total = _best_row(rows, scenario, "request_total_ms")
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

    return {
        "best_request_ttfa": best_request_ttfa,
        "best_request_total": best_request_total,
    }


def _write_audio_sample(sample_out: Path, sample: Any, sample_rate: int) -> None:
    import numpy as np
    import soundfile as sf
    import torch

    if isinstance(sample, torch.Tensor):
        sample_np = sample.detach().cpu().numpy()
    else:
        sample_np = np.asarray(sample)
    sample_np = sample_np.astype("float32").flatten()
    sample_out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(sample_out, sample_np, int(sample_rate))


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

    from f5_production_chunking import _max_chars_for_batches
    from f5_tts.api import F5TTS
    from f5_tts.infer.utils_infer import chunk_text, infer_batch_process, preprocess_ref_audio_text

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

    def synthesize(prepared: tuple[Any, int, str], text: str, *, chunked: bool) -> tuple[float, float, float, float, int, np.ndarray]:
        ref_wave, ref_sample_rate, prepared_ref_text = prepared
        batch_text = [text]
        if chunked:
            max_chars = _max_chars_for_batches(ref_wave, ref_sample_rate, prepared_ref_text, 1.0)
            batch_text = chunk_text(text, max_chars=max_chars)

        chunks: list[np.ndarray] = []
        sample_rate = model.target_sample_rate
        first_chunk_s: float | None = None
        with Timer() as timer:
            started = time.perf_counter()
            for chunk, sample_rate in infer_batch_process(
                (ref_wave, ref_sample_rate),
                prepared_ref_text,
                batch_text,
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
        "Prepared reference cached once per session and long replies are chunked before F5 synthesis."
    )
    for scenario in scenarios:
        try:
            torch.cuda.reset_peak_memory_stats()
            ttfa_ms, total_ms, audio_duration_s, peak_vram_mb, sample_rate, wav = synthesize(
                prepared_cached,
                scenario.text,
                chunked=True,
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
                    mode="simulated_streaming",
                    streaming_support="simulated",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=warmup_ms,
                    cached_prompt_build_ms=cached_prompt_build_ms,
                    request_prompt_prep_ms=0.0,
                    generate_ttfa_ms=ttfa_ms,
                    generate_total_ms=total_ms,
                    audio_duration_s=audio_duration_s,
                    peak_vram_mb=peak_vram_mb,
                    sample_rate=sample_rate,
                    output_wav=sample_out,
                    optimizations_applied=["prepared_ref_cache", "text_chunking"],
                    optimization_notes=optimized_notes,
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
                    mode="simulated_streaming",
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
                    optimizations_applied=["prepared_ref_cache", "text_chunking"],
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
    optimized_notes = "Conditioning latents cached once per session and reused across replies."
    for scenario in scenarios:
        torch.cuda.reset_peak_memory_stats()
        ttfa_ms, total_ms, audio_duration_s, peak_vram_mb, rate, wav, streaming_ok, streaming_error = synthesize(
            cached_conditioning,
            scenario.text,
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
                mode="streaming" if streaming_ok else "non_streaming_fallback",
                streaming_support="native" if streaming_ok else "native_fallback",
                true_streaming=streaming_ok,
                model_load_ms=model_load_ms,
                warmup_ms=warmup_ms,
                cached_prompt_build_ms=cached_prompt_build_ms,
                request_prompt_prep_ms=0.0,
                generate_ttfa_ms=ttfa_ms,
                generate_total_ms=total_ms,
                audio_duration_s=audio_duration_s,
                peak_vram_mb=peak_vram_mb,
                sample_rate=rate,
                output_wav=sample_out,
                optimizations_applied=["conditioning_cache"],
                optimization_notes=optimized_notes,
                extra={"streaming_error": streaming_error},
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
        "Prompt cache reused across replies. Generation settings stay on the official 4-step efficient path."
    )
    for scenario in scenarios:
        torch.cuda.reset_peak_memory_stats()
        with Timer() as timer:
            wav, sample_rate = _generate_luxtts_audio(model, cached_prompt, scenario.text)
            _maybe_cuda_sync(torch)
        sample_out = _sample_path(sample_root, "luxtts", "optimized", scenario.name)
        _write_audio_sample(sample_out, wav, sample_rate)
        audio_duration_s = len(wav.detach().cpu().numpy().flatten()) / float(sample_rate)
        rows.append(
            build_result_row(
                engine="luxtts",
                runtime=runtime,
                host_account=host_account,
                profile="optimized",
                scenario=scenario,
                backend="zipvoice_pytorch",
                mode="non_streaming_clone",
                streaming_support="none",
                true_streaming=False,
                model_load_ms=model_load_ms,
                warmup_ms=warmup_ms,
                cached_prompt_build_ms=cached_prompt_build_ms,
                request_prompt_prep_ms=0.0,
                generate_ttfa_ms=timer.elapsed_ms,
                generate_total_ms=timer.elapsed_ms,
                audio_duration_s=audio_duration_s,
                peak_vram_mb=float(sample_vram_mb()["peak_allocated_mb"]),
                sample_rate=int(sample_rate),
                output_wav=sample_out,
                optimizations_applied=["prompt_cache"],
                optimization_notes=optimized_notes,
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
    import torch

    torch.cuda.empty_cache()
    with Timer() as load_timer:
        model = _load_chatterbox_turbo_model()
    warmup_cuda()

    def prepare_conditionals() -> float:
        with Timer() as prep_timer:
            model.prepare_conditionals(ref_audio, exaggeration=0.0, norm_loudness=True)
        return prep_timer.elapsed_ms

    with Timer() as warm_timer:
        _ = prepare_conditionals()
        _ = model.generate("Warm.", audio_prompt_path=None)
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
            wav = model.generate(scenario.text, audio_prompt_path=None)
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
    optimized_notes = "Prepared speaker conditionals cached once per session and reused across replies."
    for scenario in scenarios:
        torch.cuda.reset_peak_memory_stats()
        with Timer() as timer:
            wav = model.generate(scenario.text, audio_prompt_path=None)
            _maybe_cuda_sync(torch)
        sample_rate = int(getattr(model, "sr", None) or getattr(model, "sample_rate", 24000))
        sample_out = _sample_path(sample_root, "chatterbox_turbo", "optimized", scenario.name)
        _write_audio_sample(sample_out, wav, sample_rate)
        audio_duration_s = len(wav.squeeze().detach().cpu().numpy().flatten()) / float(sample_rate)
        rows.append(
            build_result_row(
                engine="chatterbox_turbo",
                runtime=runtime,
                host_account=host_account,
                profile="optimized",
                scenario=scenario,
                backend="turbo_native",
                mode="non_streaming_clone",
                streaming_support="none",
                true_streaming=False,
                model_load_ms=model_load_ms,
                warmup_ms=warmup_ms,
                cached_prompt_build_ms=cached_prompt_build_ms,
                request_prompt_prep_ms=0.0,
                generate_ttfa_ms=timer.elapsed_ms,
                generate_total_ms=timer.elapsed_ms,
                audio_duration_s=audio_duration_s,
                peak_vram_mb=float(sample_vram_mb()["peak_allocated_mb"]),
                sample_rate=sample_rate,
                output_wav=sample_out,
                optimizations_applied=["conditioning_cache"],
                optimization_notes=optimized_notes,
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
        "Prompt cache reused across replies." + compile_note
    ).strip()
    for scenario in scenarios:
        try:
            torch.cuda.reset_peak_memory_stats()
            with Timer() as timer:
                wav, sample_rate = _generate_tada_audio(model, cached_prompt, scenario.text)
                _maybe_cuda_sync(torch)
            sample_out = _sample_path(sample_root, "tada_1b", "optimized", scenario.name)
            _write_audio_sample(sample_out, wav, sample_rate)
            audio_duration_s = len(np.asarray(wav).flatten()) / float(sample_rate)
            rows.append(
                build_result_row(
                    engine="tada_1b",
                    runtime=runtime,
                    host_account=host_account,
                    profile="optimized",
                    scenario=scenario,
                    backend="native_bf16_compiled" if "model.compile" in optimized_applied else "native_bf16",
                    mode="non_streaming_clone",
                    streaming_support="none",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=(warmup_ms + (compile_ms or 0.0)),
                    cached_prompt_build_ms=cached_prompt_build_ms,
                    request_prompt_prep_ms=0.0,
                    generate_ttfa_ms=timer.elapsed_ms,
                    generate_total_ms=timer.elapsed_ms,
                    audio_duration_s=audio_duration_s,
                    peak_vram_mb=float(sample_vram_mb()["peak_allocated_mb"]),
                    sample_rate=int(sample_rate),
                    output_wav=sample_out,
                    optimizations_applied=optimized_applied,
                    optimization_notes=optimized_notes,
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
                    mode="non_streaming_clone",
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
                    optimizations_applied=optimized_applied,
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

            with Timer() as timer:
                wavs, sample_rate = model.generate_voice_clone(
                    text=scenario.text,
                    voice_clone_prompt=prompt,
                    language="English",
                    non_streaming_mode=False,
                )
                _maybe_cuda_sync(torch)

            wav = wavs[0] if hasattr(wavs, "__len__") and len(wavs) > 0 else wavs
            if hasattr(wav, "detach"):
                wav = wav.detach().cpu().numpy()
            sample_out = _sample_path(sample_root, "qwen3", profile, scenario.name)
            _write_audio_sample(sample_out, wav, int(sample_rate))
            audio_duration_s = len(wav.astype("float32").flatten()) / float(sample_rate)
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
                    mode="simulated_streaming_text",
                    streaming_support="simulated",
                    true_streaming=False,
                    model_load_ms=model_load_ms,
                    warmup_ms=warm_timer.elapsed_ms,
                    cached_prompt_build_ms=cached_prompt_build_ms,
                    request_prompt_prep_ms=request_prompt_ms,
                    generate_ttfa_ms=timer.elapsed_ms,
                    generate_total_ms=timer.elapsed_ms,
                    audio_duration_s=audio_duration_s,
                    peak_vram_mb=float(sample_vram_mb()["peak_allocated_mb"]),
                    sample_rate=int(sample_rate),
                    output_wav=sample_out,
                    optimizations_applied=applied,
                    optimization_notes=notes,
                    variant="0.6B-Base",
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
        cwd=Path(__file__).resolve().parent,
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
