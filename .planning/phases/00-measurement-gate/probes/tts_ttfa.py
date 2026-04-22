"""TTS TTFA + RTF benchmark for Phase 0 success criterion #3."""

from __future__ import annotations

import argparse
import importlib.machinery
import json
import os
import subprocess
import sys
import traceback
import types
from pathlib import Path
from typing import Any

from bench_utils import Timer, sample_vram_mb, warmup_cuda, write_results

TTFA_TARGET_MS = 400
RTF_TARGET = 1.0
OUTPUT_SAMPLE_DIR = Path(__file__).resolve().parent / "fixtures" / "tts_samples"


def compute_rtf(audio_duration_s: float, synthesis_time_s: float) -> float:
    """Compute real-time factor; values below 1 are faster than real time."""
    if audio_duration_s <= 0:
        return float("inf")
    return synthesis_time_s / audio_duration_s


def pick_v1_default(engines: dict[str, dict[str, Any]]) -> str | None:
    """Pick the v1 default using the priority order from Resolved Tension #3."""

    def clears_budget(engine: dict[str, Any]) -> bool:
        ttfa_ms = engine.get("ttfa_ms")
        rtf = engine.get("rtf")
        return (
            ttfa_ms is not None
            and rtf is not None
            and ttfa_ms <= TTFA_TARGET_MS
            and rtf < RTF_TARGET
        )

    for name in ("f5", "xtts", "qwen3"):
        engine = engines.get(name)
        if engine and clears_budget(engine):
            return name

    measured = {
        name: engine
        for name, engine in engines.items()
        if engine.get("ttfa_ms") is not None
    }
    if not measured:
        return None
    return min(measured, key=lambda name: measured[name]["ttfa_ms"])


def qwen_gate_disposition(
    qwen_metrics: dict[str, Any], accent_ok: bool
) -> dict[str, Any]:
    """Evaluate the separate Qwen acceptance gate."""
    failures: list[str] = []
    ttfa_ms = qwen_metrics.get("ttfa_ms")
    rtf = qwen_metrics.get("rtf")

    if ttfa_ms is None or ttfa_ms > TTFA_TARGET_MS:
        failures.append("ttfa_too_high")
    if rtf is None or rtf >= RTF_TARGET:
        failures.append("rtf_too_high")
    if not accent_ok:
        failures.append("accent_drift_or_untested")

    if failures:
        return {"accepted": False, "reasons": failures}
    return {"accepted": True, "reasons": ["ttfa_ok", "rtf_ok", "accent_ok"]}


def _maybe_cuda_sync(torch_module: Any) -> None:
    if torch_module.cuda.is_available():
        torch_module.cuda.synchronize()


def _install_f5_runtime_shims() -> None:
    """Avoid Windows-only F5 import crashes from training deps and librosa/numba."""
    import numpy as np
    import torchaudio.functional as audio_functional

    def mel_filter(
        *, sr: int, n_fft: int, n_mels: int, fmin: float = 0, fmax: float | None = None, **_: Any
    ) -> np.ndarray:
        filter_bank = audio_functional.melscale_fbanks(
            n_freqs=(int(n_fft) // 2) + 1,
            f_min=float(fmin or 0),
            f_max=float((sr / 2) if fmax is None else fmax),
            n_mels=int(n_mels),
            sample_rate=int(sr),
            norm="slaney",
            mel_scale="slaney",
        )
        return filter_bank.transpose(0, 1).cpu().numpy().astype(np.float32)

    librosa_mod = types.ModuleType("librosa")
    librosa_mod.__path__ = []
    librosa_mod.__spec__ = importlib.machinery.ModuleSpec(
        "librosa",
        loader=None,
        is_package=True,
    )
    filters_mod = types.ModuleType("librosa.filters")
    filters_mod.__spec__ = importlib.machinery.ModuleSpec(
        "librosa.filters",
        loader=None,
        is_package=False,
    )
    filters_mod.mel = mel_filter
    librosa_mod.filters = filters_mod
    sys.modules["librosa"] = librosa_mod
    sys.modules["librosa.filters"] = filters_mod

    trainer_mod = types.ModuleType("f5_tts.model.trainer")
    trainer_mod.__spec__ = importlib.machinery.ModuleSpec(
        "f5_tts.model.trainer",
        loader=None,
        is_package=False,
    )

    class Trainer:  # pragma: no cover - runtime shim only
        pass

    trainer_mod.Trainer = Trainer
    sys.modules["f5_tts.model.trainer"] = trainer_mod


def measure_f5(ref_audio: str, ref_text: str, target_text: str, sample_out: Path) -> dict[str, Any]:
    import time

    import numpy as np
    import torch
    import soundfile as sf
    import torchaudio

    _install_f5_runtime_shims()

    from f5_tts.api import F5TTS
    from f5_tts.infer.utils_infer import infer_batch_process, preprocess_ref_audio_text

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    print("[tts] Loading F5-TTS...", flush=True)
    model = F5TTS()
    warmup_cuda()
    _ = model.infer(ref_audio, ref_text, "Warm.", nfe_step=7)
    _maybe_cuda_sync(torch)

    prepared_ref_audio, prepared_ref_text = preprocess_ref_audio_text(
        ref_audio,
        ref_text,
        show_info=lambda *_args, **_kwargs: None,
    )
    ref_wave, ref_sample_rate = torchaudio.load(prepared_ref_audio)
    chunks: list[np.ndarray] = []
    sample_rate = model.target_sample_rate
    first_chunk_s: float | None = None

    with Timer() as timer:
        started = time.perf_counter()
        for chunk, sample_rate in infer_batch_process(
            (ref_wave, ref_sample_rate),
            prepared_ref_text,
            [target_text],
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
    synthesis_s = timer.elapsed_s
    audio_duration_s = len(wav) / float(sample_rate)
    sample_out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(sample_out, wav, sample_rate)
    peak_vram_mb = sample_vram_mb()["peak_allocated_mb"]

    del model
    torch.cuda.empty_cache()

    return {
        "engine": "f5",
        "mode": "simulated_streaming",
        "streaming_support": "simulated",
        "true_streaming": False,
        "ttfa_ms": round((first_chunk_s or synthesis_s) * 1000, 1),
        "rtf": round(compute_rtf(audio_duration_s, synthesis_s), 3),
        "audio_duration_s": round(audio_duration_s, 3),
        "synthesis_time_s": round(synthesis_s, 3),
        "peak_vram_mb": round(peak_vram_mb, 1),
        "sample_rate": int(sample_rate),
        "output_wav": str(sample_out),
        "streaming_notes": "F5-TTS slices generated audio into chunks after synthesis; no true incremental decode.",
    }


def measure_xtts(ref_audio: str, target_text: str, sample_out: Path) -> dict[str, Any]:
    import time

    import numpy as np
    import soundfile as sf
    import torch

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

    from TTS.api import TTS

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    print("[tts] Loading XTTS v2...", flush=True)
    model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
    xtts_model = model.synthesizer.tts_model
    warmup_cuda()

    chunks: list[np.ndarray] = []
    sample_rate = int(getattr(model.synthesizer, "output_sample_rate", 24000))
    ttfa_ms: float
    synthesis_s: float
    streaming_ok = False
    streaming_error: str | None = None

    try:
        _ = model.tts(text="Warm.", speaker_wav=ref_audio, language="en")
        _maybe_cuda_sync(torch)

        if hasattr(xtts_model, "inference_stream"):
            first_chunk_s: float | None = None
            with Timer() as timer:
                started = time.perf_counter()
                gpt_cond_latent, speaker_embedding = xtts_model.get_conditioning_latents(
                    audio_path=ref_audio,
                )
                for chunk in xtts_model.inference_stream(
                    text=target_text,
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
            ttfa_ms = round((first_chunk_s or timer.elapsed_s) * 1000, 1)
            synthesis_s = timer.elapsed_s
            streaming_ok = True
        else:
            with Timer() as timer:
                wav = model.tts(text=target_text, speaker_wav=ref_audio, language="en")
                _maybe_cuda_sync(torch)
            ttfa_ms = round(timer.elapsed_s * 1000, 1)
            synthesis_s = timer.elapsed_s
            chunks = [np.asarray(wav, dtype=np.float32).flatten()]
    except Exception:
        streaming_error = traceback.format_exc(limit=8)
        traceback.print_exc()
        with Timer() as timer:
            wav = model.tts(text=target_text, speaker_wav=ref_audio, language="en")
            _maybe_cuda_sync(torch)
        ttfa_ms = round(timer.elapsed_s * 1000, 1)
        synthesis_s = timer.elapsed_s
        chunks = [np.asarray(wav, dtype=np.float32).flatten()]

    full_wav = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    audio_duration_s = len(full_wav) / float(sample_rate)
    sample_out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(sample_out, full_wav, sample_rate)
    peak_vram_mb = sample_vram_mb()["peak_allocated_mb"]

    del model
    torch.cuda.empty_cache()

    return {
        "engine": "xtts",
        "mode": "streaming" if streaming_ok else "non_streaming_fallback",
        "streaming_support": "native" if streaming_ok else "native_fallback",
        "true_streaming": streaming_ok,
        "fallback_to_non_streaming": not streaming_ok,
        "ttfa_ms": ttfa_ms,
        "rtf": round(compute_rtf(audio_duration_s, synthesis_s), 3),
        "audio_duration_s": round(audio_duration_s, 3),
        "synthesis_time_s": round(synthesis_s, 3),
        "peak_vram_mb": round(peak_vram_mb, 1),
        "sample_rate": sample_rate,
        "output_wav": str(sample_out),
        "streaming_error": streaming_error,
    }


def measure_qwen3(
    ref_audio: str, ref_text: str, target_text: str, sample_out: Path
) -> dict[str, Any]:
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    print("[tts] Loading Qwen3-TTS 0.6B-Base...", flush=True)
    model = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        device_map="cuda:0",
        torch_dtype=torch.bfloat16,
    )
    warmup_cuda()

    prompt = model.create_voice_clone_prompt(
        ref_audio=ref_audio,
        ref_text=ref_text,
        x_vector_only_mode=False,
    )
    _ = model.generate_voice_clone(
        text="Warm.",
        voice_clone_prompt=prompt,
        language="English",
        non_streaming_mode=False,
    )
    _maybe_cuda_sync(torch)

    with Timer() as timer:
        wavs, sample_rate = model.generate_voice_clone(
            text=target_text,
            voice_clone_prompt=prompt,
            language="English",
            non_streaming_mode=False,
        )
        _maybe_cuda_sync(torch)

    synthesis_s = timer.elapsed_s
    wav = wavs[0] if hasattr(wavs, "__len__") and len(wavs) > 0 else wavs
    if hasattr(wav, "detach"):
        wav = wav.detach().cpu().numpy()
    sample = wav.astype("float32").flatten()
    audio_duration_s = len(sample) / float(sample_rate)
    sample_out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(sample_out, sample, int(sample_rate))
    peak_vram_mb = sample_vram_mb()["peak_allocated_mb"]

    del model
    torch.cuda.empty_cache()

    return {
        "engine": "qwen3",
        "mode": "simulated_streaming_text",
        "streaming_support": "simulated",
        "true_streaming": False,
        "variant": "0.6B-Base",
        "flash_attention": "eager",
        "ttfa_ms": round(synthesis_s * 1000, 1),
        "rtf": round(compute_rtf(audio_duration_s, synthesis_s), 3),
        "audio_duration_s": round(audio_duration_s, 3),
        "synthesis_time_s": round(synthesis_s, 3),
        "peak_vram_mb": round(peak_vram_mb, 1),
        "sample_rate": int(sample_rate),
        "output_wav": str(sample_out),
        "streaming_notes": "Qwen3-TTS non_streaming_mode=False simulates streaming text input but still returns audio after full generation.",
    }


def run_engine_locally(
    engine: str,
    ref_audio: str,
    ref_text: str,
    target_text: str,
    sample_out: Path,
) -> dict[str, Any]:
    if engine == "f5":
        return measure_f5(ref_audio, ref_text, target_text, sample_out)
    if engine == "xtts":
        return measure_xtts(ref_audio, target_text, sample_out)
    if engine == "qwen3":
        return measure_qwen3(ref_audio, ref_text, target_text, sample_out)
    raise ValueError(f"Unknown engine: {engine}")


def run_engine_subprocess(
    engine: str,
    ref_audio: Path,
    ref_text_path: Path,
    target_text: str,
    sample_out: Path,
) -> dict[str, Any]:
    """Run one engine in a child process so a fatal import does not kill the driver."""
    temp_output = OUTPUT_SAMPLE_DIR / f"{engine}.metrics.json"
    if temp_output.exists():
        temp_output.unlink()

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--run-engine",
        engine,
        "--ref-audio",
        str(ref_audio),
        "--ref-text",
        str(ref_text_path),
        "--target-text",
        target_text,
        "--sample-out",
        str(sample_out),
        "--engine-output",
        str(temp_output),
    ]
    env = os.environ.copy()
    home = Path.home()
    local_appdata = home / "AppData" / "Local"
    roaming_appdata = home / "AppData" / "Roaming"
    tts_home = local_appdata / "rayme-tts-home"
    local_appdata.mkdir(parents=True, exist_ok=True)
    roaming_appdata.mkdir(parents=True, exist_ok=True)
    tts_home.mkdir(parents=True, exist_ok=True)
    env.setdefault("LOCALAPPDATA", str(local_appdata))
    env.setdefault("APPDATA", str(roaming_appdata))
    env.setdefault("TTS_HOME", str(tts_home))

    proc = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parent,
        capture_output=True,
        text=True,
        env=env,
    )

    if proc.returncode == 0 and temp_output.exists():
        return json.loads(temp_output.read_text(encoding="utf-8"))

    combined_log = "\n".join(part for part in (proc.stdout, proc.stderr) if part).strip()
    return {
        "engine": engine,
        "ttfa_ms": None,
        "rtf": None,
        "error": f"subprocess_exit_{proc.returncode}",
        "stderr": combined_log[:4000] if combined_log else "",
    }


def _read_reference_text(path: Path) -> str:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _read_target_text(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _default_reason(default: str | None, engines: dict[str, dict[str, Any]]) -> str:
    if default is None:
        return "All engines failed"

    engine = engines.get(default, {})
    ttfa_ms = engine.get("ttfa_ms")
    rtf = engine.get("rtf")
    if ttfa_ms is not None and rtf is not None and ttfa_ms <= TTFA_TARGET_MS and rtf < RTF_TARGET:
        return f"{default} cleared TTFA<={TTFA_TARGET_MS}ms and RTF<{RTF_TARGET}"
    return f"No engine hit the budget; {default} has best TTFA"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref-audio", required=True, help="Short reference audio WAV")
    parser.add_argument("--ref-text", required=True, help="Reference transcript text file")
    parser.add_argument(
        "--target-text",
        default="Hey, got it.",
        help="Short target utterance to synthesize",
    )
    parser.add_argument(
        "--target-text-file",
        help="Optional path to a UTF-8 text file whose contents override --target-text",
    )
    parser.add_argument("--output", help="Results JSON path")
    parser.add_argument(
        "--accent-ok",
        action="store_true",
        help="Only set after the builder confirms the Qwen accent test passes",
    )
    parser.add_argument(
        "--run-engine",
        choices=("f5", "xtts", "qwen3"),
        help="Internal: run a single engine in an isolated subprocess",
    )
    parser.add_argument(
        "--sample-out",
        help="Internal: output WAV path for isolated engine runs",
    )
    parser.add_argument(
        "--engine-output",
        help="Internal: JSON path for isolated engine runs",
    )
    args = parser.parse_args()

    ref_audio = Path(args.ref_audio)
    ref_text_path = Path(args.ref_text)
    if not ref_audio.exists():
        print(f"ERROR: ref-audio missing: {ref_audio}", file=sys.stderr)
        print("Builder must record probes/fixtures/short_ref_audio.wav first.", file=sys.stderr)
        return 2
    if not ref_text_path.exists():
        print(f"ERROR: ref-text missing: {ref_text_path}", file=sys.stderr)
        return 2

    ref_text = _read_reference_text(ref_text_path)
    target_text = args.target_text
    if args.target_text_file:
        target_text_path = Path(args.target_text_file)
        if not target_text_path.exists():
            print(f"ERROR: target-text-file missing: {target_text_path}", file=sys.stderr)
            return 2
        target_text = _read_target_text(target_text_path)
    OUTPUT_SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    if args.run_engine:
        if not args.sample_out or not args.engine_output:
            print("ERROR: --run-engine requires --sample-out and --engine-output", file=sys.stderr)
            return 2
        metrics = run_engine_locally(
            args.run_engine,
            str(ref_audio),
            ref_text,
            target_text,
            Path(args.sample_out),
        )
        Path(args.engine_output).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        return 0

    if not args.output:
        print("ERROR: --output is required unless --run-engine is set", file=sys.stderr)
        return 2

    engines: dict[str, dict[str, Any]] = {}
    for name in ("f5", "xtts", "qwen3"):
        sample_out = OUTPUT_SAMPLE_DIR / f"{name}.wav"
        try:
            engines[name] = run_engine_subprocess(
                name,
                ref_audio,
                ref_text_path,
                target_text,
                sample_out,
            )
            if engines[name].get("ttfa_ms") is not None:
                print(
                    f"[tts] {name}: TTFA={engines[name]['ttfa_ms']} ms, "
                    f"RTF={engines[name]['rtf']}, "
                    f"VRAM={engines[name]['peak_vram_mb']} MB",
                    flush=True,
                )
            else:
                print(f"[tts] {name}: FAILED {engines[name].get('error')}", file=sys.stderr)
                if engines[name].get("stderr"):
                    print(engines[name]["stderr"], file=sys.stderr)
        except BaseException as exc:
            print(f"[tts] {name}: FAILED {exc!r}", file=sys.stderr)
            traceback.print_exc()
            engines[name] = {
                "engine": name,
                "ttfa_ms": None,
                "rtf": None,
                "error": repr(exc),
            }

    default = pick_v1_default(engines)
    qwen_gate = qwen_gate_disposition(engines.get("qwen3", {}), args.accent_ok)
    payload = {
        "probe": "tts_ttfa",
        "target_text": target_text,
        "ref_audio": str(ref_audio),
        "engines": engines,
        "v1_default": default,
        "v1_default_reason": _default_reason(default, engines),
        "qwen_gate": qwen_gate,
        "accent_ok_passed_to_probe": args.accent_ok,
    }
    write_results(args.output, payload)
    print(f"[tts] v1_default = {default}", flush=True)
    print(f"[tts] qwen_gate  = {qwen_gate}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
