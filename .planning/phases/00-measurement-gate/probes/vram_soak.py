"""30-minute VRAM soak for Whisper + Silero VAD + one TTS engine."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from bench_utils import sample_vram_mb, warmup_cuda, write_results

GROWTH_THRESHOLD_MB_PER_MIN = 50.0
GROWTH_WINDOW_MIN = 20
EMPTY_CACHE_EVERY_N_CYCLES = 10
SAMPLE_INTERVAL_S = 60
CYCLE_INTERVAL_S = 10
SHORT_PHRASES = [
    "Hey, got it.",
    "Right, okay, sounds good.",
    "Let me think about that.",
    "Yeah, I agree.",
    "Could you repeat that please?",
]


def _probe_root() -> Path:
    here = Path(__file__).resolve().parent
    if (here / "bench_utils.py").exists():
        return here
    if (here / "probes" / "bench_utils.py").exists():
        return here / "probes"
    raise FileNotFoundError("Could not resolve Phase 0 probe root from vram_soak.py")


PROBE_ROOT = _probe_root()
PHASE_ROOT = PROBE_ROOT.parent if (PROBE_ROOT.parent / "results").exists() else PROBE_ROOT
RESULTS_DIR = PHASE_ROOT / "results"
FIXTURES_DIR = PROBE_ROOT / "fixtures"
WHISPER_RESULTS = RESULTS_DIR / "whisper.json"


def detect_growth(samples: list[dict[str, float]], window_s: int) -> tuple[bool, float]:
    """Fit reserved-memory slope over the tail window and return MB/min growth."""
    if len(samples) < 2:
        return False, 0.0

    max_t = max(sample["t"] for sample in samples)
    window = [sample for sample in samples if sample["t"] >= max_t - window_s]
    if len(window) < 2:
        window = samples

    n = len(window)
    sum_t = sum(sample["t"] for sample in window)
    sum_v = sum(sample["v"] for sample in window)
    sum_tt = sum(sample["t"] ** 2 for sample in window)
    sum_tv = sum(sample["t"] * sample["v"] for sample in window)
    denom = n * sum_tt - sum_t * sum_t
    if denom == 0:
        return False, 0.0

    slope_mb_per_s = (n * sum_tv - sum_t * sum_v) / denom
    slope_mb_per_min = slope_mb_per_s * 60.0
    return slope_mb_per_min > GROWTH_THRESHOLD_MB_PER_MIN, slope_mb_per_min


def build_soak_result(engine: str, samples: list[dict[str, Any]], cycles_completed: int) -> dict[str, Any]:
    peak_reserved = max((float(sample.get("v", 0.0)) for sample in samples), default=0.0)
    peak_allocated = max((float(sample.get("allocated_mb", 0.0)) for sample in samples), default=0.0)
    peak_allocated_stat = max(
        (float(sample.get("peak_allocated_mb", 0.0)) for sample in samples),
        default=0.0,
    )
    nvml_values = [
        float(sample["used_mb_nvml"])
        for sample in samples
        if sample.get("used_mb_nvml") is not None
    ]
    peak_used_mb_nvml = max(nvml_values, default=0.0)
    baseline_used_mb_nvml = nvml_values[0] if nvml_values else None
    peak_used_mb_nvml_delta = (
        round(peak_used_mb_nvml - baseline_used_mb_nvml, 1)
        if baseline_used_mb_nvml is not None
        else None
    )

    growth_detected, slope_mb_per_min = detect_growth(
        samples,
        window_s=GROWTH_WINDOW_MIN * 60,
    )
    duration_s = samples[-1]["t"] - samples[0]["t"] if samples else 0.0
    peak_vram_mb = max(peak_reserved, peak_allocated_stat, peak_allocated)

    return {
        "probe": "vram_soak",
        "engine": engine,
        "peak_vram_mb": round(peak_vram_mb, 1),
        "peak_reserved_mb": round(peak_reserved, 1),
        "peak_allocated_mb": round(peak_allocated_stat, 1),
        "peak_used_mb_nvml": round(peak_used_mb_nvml, 1) if nvml_values else None,
        "baseline_used_mb_nvml": round(baseline_used_mb_nvml, 1)
        if baseline_used_mb_nvml is not None
        else None,
        "peak_used_mb_nvml_delta": peak_used_mb_nvml_delta,
        "growth_detected": growth_detected,
        "growth_slope_mb_per_min": round(slope_mb_per_min, 2),
        "cycles_completed": cycles_completed,
        "duration_s": round(duration_s, 1),
        "samples": samples,
        "fits_3060_budget": peak_vram_mb < 11000,
    }


def _read_reference_text(path: Path) -> str:
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    ).strip()


def _load_whisper_default() -> tuple[str, str]:
    """Return the default Whisper rung selected in plan 03."""
    if not WHISPER_RESULTS.exists():
        print(
            "ERROR: results/whisper.json missing; plan 03 must complete before 00-05.",
            file=sys.stderr,
        )
        sys.exit(2)

    document = json.loads(WHISPER_RESULTS.read_text(encoding="utf-8"))
    default_name = document.get("default_rung")
    for rung in document.get("rungs", []):
        if rung.get("default") or rung.get("model") == default_name:
            return rung["model"], rung["compute_type"]

    print(
        "ERROR: results/whisper.json has no default rung set.",
        file=sys.stderr,
    )
    sys.exit(2)


def _maybe_cuda_sync(torch_module: Any) -> None:
    if torch_module.cuda.is_available():
        torch_module.cuda.synchronize()


def _install_xtts_env() -> None:
    local_appdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    roaming_appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    tts_home = Path(os.environ.get("TTS_HOME", local_appdata / "rayme-tts-home"))
    local_appdata.mkdir(parents=True, exist_ok=True)
    roaming_appdata.mkdir(parents=True, exist_ok=True)
    tts_home.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("LOCALAPPDATA", str(local_appdata))
    os.environ.setdefault("APPDATA", str(roaming_appdata))
    os.environ.setdefault("XDG_DATA_HOME", str(local_appdata))
    os.environ.setdefault("TTS_HOME", str(tts_home))
    os.environ.setdefault("COQUI_TOS_AGREED", "1")


def _load_silero():
    model, _utils = __import__("torch").hub.load(
        "snakers4/silero-vad",
        "silero_vad",
        trust_repo=True,
        onnx=False,
    )
    return model


def _load_tts(engine: str, ref_audio: str, ref_text: str) -> tuple[str, Any, dict[str, Any]]:
    import torch

    if engine == "f5":
        from tts_ttfa import _install_f5_runtime_shims

        _install_f5_runtime_shims()
        from f5_tts.api import F5TTS

        model = F5TTS()
        return "f5", model, {"ref_audio": ref_audio, "ref_text": ref_text}

    if engine == "xtts":
        _install_xtts_env()
        from TTS.api import TTS

        model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
        return "xtts", model, {"ref_audio": ref_audio}

    if engine == "qwen3":
        from qwen_tts import Qwen3TTSModel

        model = Qwen3TTSModel.from_pretrained(
            "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
            device_map="cuda:0",
            torch_dtype=torch.bfloat16,
        )
        prompt = model.create_voice_clone_prompt(
            ref_audio=ref_audio,
            ref_text=ref_text,
            x_vector_only_mode=False,
        )
        return "qwen3", model, {"prompt": prompt}

    if engine == "luxtts":
        from tts_ttfa import _encode_luxtts_prompt, _load_luxtts_model

        model = _load_luxtts_model()
        prompt = _encode_luxtts_prompt(model, ref_audio, ref_text)
        return "luxtts", model, {"prompt": prompt}

    if engine == "chatterbox_turbo":
        from tts_ttfa import _load_chatterbox_turbo_model

        model = _load_chatterbox_turbo_model()
        return "chatterbox_turbo", model, {"ref_audio": ref_audio}

    if engine == "tada_1b":
        from tts_ttfa import _create_tada_prompt, _load_tada_1b

        encoder, model = _load_tada_1b()
        prompt = _create_tada_prompt(encoder, ref_audio, ref_text)
        return "tada_1b", (encoder, model), {"prompt": prompt}

    raise ValueError(f"Unknown engine: {engine}")


def _synthesize(engine: str, tts: Any, ctx: dict[str, Any], text: str) -> tuple[Any, int]:
    import numpy as np

    if engine == "f5":
        wav, sample_rate, _ = tts.infer(ctx["ref_audio"], ctx["ref_text"], text, nfe_step=7)
        return np.asarray(wav, dtype=np.float32), int(sample_rate)

    if engine == "xtts":
        wav = tts.tts(text=text, speaker_wav=ctx["ref_audio"], language="en")
        return np.asarray(wav, dtype=np.float32), 24000

    if engine == "qwen3":
        wavs, sample_rate = tts.generate_voice_clone(
            text=text,
            voice_clone_prompt=ctx["prompt"],
            language="English",
            non_streaming_mode=False,
        )
        wav = wavs[0] if hasattr(wavs, "__len__") and len(wavs) > 0 else wavs
        if hasattr(wav, "detach"):
            wav = wav.detach().cpu().numpy()
        return wav.astype("float32").flatten(), int(sample_rate)

    if engine == "luxtts":
        from tts_ttfa import _generate_luxtts_audio

        wav, sample_rate = _generate_luxtts_audio(tts, ctx["prompt"], text)
        if hasattr(wav, "detach"):
            wav = wav.detach().cpu().numpy()
        return wav.astype("float32").flatten(), int(sample_rate)

    if engine == "chatterbox_turbo":
        import torch
        from tts_ttfa import _generate_chatterbox_turbo_audio

        wav, sample_rate = _generate_chatterbox_turbo_audio(tts, ctx["ref_audio"], text)
        if isinstance(wav, torch.Tensor):
            wav = wav.squeeze().detach().cpu().numpy()
        return np.asarray(wav, dtype=np.float32).flatten(), int(sample_rate)

    if engine == "tada_1b":
        encoder, model = tts
        from tts_ttfa import _generate_tada_audio

        wav, sample_rate = _generate_tada_audio(model, ctx["prompt"], text)
        return np.asarray(wav, dtype=np.float32).flatten(), int(sample_rate)

    raise AssertionError(f"Unhandled engine: {engine}")


def _sample_record(t0: float, cycle: int) -> dict[str, Any]:
    vram = sample_vram_mb()
    return {
        "t": round(time.perf_counter() - t0, 1),
        "v": float(vram["reserved_mb"]),
        "allocated_mb": float(vram["allocated_mb"]),
        "peak_allocated_mb": float(vram["peak_allocated_mb"]),
        "used_mb_nvml": vram.get("used_mb_nvml"),
        "free_mb_nvml": vram.get("free_mb_nvml"),
        "cycle": cycle,
    }


def _vad_tensor(wav: Any, sample_rate: int):
    import numpy as np
    import torch
    import torchaudio.functional as audio_functional

    audio = torch.as_tensor(np.asarray(wav, dtype=np.float32)).flatten()
    if sample_rate != 16000:
        audio = audio_functional.resample(audio.unsqueeze(0), sample_rate, 16000).squeeze(0)
    if audio.numel() < 512:
        audio = torch.nn.functional.pad(audio, (0, 512 - audio.numel()))
    elif audio.numel() > 512:
        audio = audio[:512]
    return audio.cpu()


def soak(engine: str, ref_audio: str, ref_text: str, duration_min: int) -> dict[str, Any]:
    import soundfile as sf
    import torch
    from faster_whisper import WhisperModel

    whisper_name, whisper_compute_type = _load_whisper_default()
    print(f"[soak] Whisper: {whisper_name} ({whisper_compute_type})", flush=True)
    whisper = WhisperModel(whisper_name, device="cuda", compute_type=whisper_compute_type)
    silero = _load_silero()
    name, tts, ctx = _load_tts(engine, ref_audio, ref_text)
    print(f"[soak] TTS: {name}", flush=True)
    warmup_cuda()
    _maybe_cuda_sync(torch)

    errors: list[str] = []
    samples: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    deadline = t0 + duration_min * 60
    last_sample_t = 0.0
    cycle = 0

    samples.append(_sample_record(t0, cycle))

    while time.perf_counter() < deadline:
        cycle_started = time.perf_counter()
        phrase = SHORT_PHRASES[cycle % len(SHORT_PHRASES)]

        try:
            wav, sample_rate = _synthesize(engine, tts, ctx, phrase)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                tmp_path = Path(handle.name)
            try:
                sf.write(tmp_path, wav, sample_rate)
                segments, _info = whisper.transcribe(
                    str(tmp_path),
                    beam_size=5,
                    condition_on_previous_text=False,
                    language="en",
                )
                list(segments)
            finally:
                tmp_path.unlink(missing_ok=True)

            _ = silero(_vad_tensor(wav, sample_rate), 16000)
        except Exception as exc:  # pragma: no cover - runtime-only branch
            message = f"[soak] cycle {cycle} errored: {type(exc).__name__}: {exc}"
            print(message, file=sys.stderr, flush=True)
            if len(errors) < 10:
                errors.append(message)

        cycle += 1
        if cycle % EMPTY_CACHE_EVERY_N_CYCLES == 0:
            torch.cuda.empty_cache()
            _maybe_cuda_sync(torch)

        now = time.perf_counter()
        if (now - t0) - last_sample_t >= SAMPLE_INTERVAL_S:
            record = _sample_record(t0, cycle)
            samples.append(record)
            last_sample_t = record["t"]
            print(
                "[soak] "
                f"t={record['t']:.0f}s cycle={cycle} "
                f"reserved={record['v']}MB "
                f"peak={record['peak_allocated_mb']}MB "
                f"nvml={record['used_mb_nvml']}MB",
                flush=True,
            )

        elapsed = time.perf_counter() - cycle_started
        time.sleep(max(0.0, CYCLE_INTERVAL_S - elapsed))

    if not samples or samples[-1]["t"] < round(time.perf_counter() - t0, 1):
        samples.append(_sample_record(t0, cycle))

    result = build_soak_result(engine, samples, cycle)
    result["whisper_default"] = {
        "model": whisper_name,
        "compute_type": whisper_compute_type,
    }
    result["vad_backend"] = "silero_vad_cpu"
    result["sample_interval_s"] = SAMPLE_INTERVAL_S
    result["cycle_interval_s"] = CYCLE_INTERVAL_S
    if errors:
        result["errors"] = errors
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--engine",
        required=True,
        choices=["f5", "xtts", "luxtts", "chatterbox_turbo", "tada_1b", "qwen3"],
    )
    parser.add_argument(
        "--ref-audio",
        default=str(FIXTURES_DIR / "short_ref_audio.wav"),
        help="Reference WAV from the Phase 0 TTFA probe.",
    )
    parser.add_argument(
        "--ref-text",
        default=str(FIXTURES_DIR / "short_ref_transcript.txt"),
        help="Reference transcript from the Phase 0 TTFA probe.",
    )
    parser.add_argument("--duration-min", type=int, default=30)
    parser.add_argument(
        "--output",
        help="Defaults to results/vram_soak_{engine}.json",
    )
    args = parser.parse_args()

    ref_audio_path = Path(args.ref_audio)
    ref_text_path = Path(args.ref_text)
    if not ref_audio_path.exists():
        print(f"ERROR: ref-audio missing: {ref_audio_path}", file=sys.stderr)
        return 2
    if not ref_text_path.exists():
        print(f"ERROR: ref-text missing: {ref_text_path}", file=sys.stderr)
        return 2

    output_path = Path(args.output or f"results/vram_soak_{args.engine}.json")
    if not output_path.is_absolute():
        output_path = PHASE_ROOT / output_path

    result = soak(
        args.engine,
        str(ref_audio_path),
        _read_reference_text(ref_text_path),
        args.duration_min,
    )
    write_results(output_path, result)
    print(
        f"[soak] {args.engine}: peak={result['peak_vram_mb']}MB "
        f"grew={result['growth_detected']} "
        f"slope={result['growth_slope_mb_per_min']}MB/min "
        f"fits_3060={result['fits_3060_budget']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
