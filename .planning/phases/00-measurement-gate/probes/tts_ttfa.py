"""TTS TTFA + RTF benchmark for Phase 0 success criterion #3."""

from __future__ import annotations

import argparse
import sys
import traceback
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


def measure_f5(ref_audio: str, ref_text: str, target_text: str, sample_out: Path) -> dict[str, Any]:
    import torch
    import soundfile as sf
    from f5_tts.api import F5TTS

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    print("[tts] Loading F5-TTS...", flush=True)
    model = F5TTS()
    warmup_cuda()
    _ = model.infer(ref_audio, ref_text, "Warm.", nfe_step=7)
    torch.cuda.synchronize()

    with Timer() as timer:
        wav, sample_rate, _ = model.infer(ref_audio, ref_text, target_text, nfe_step=7)
        torch.cuda.synchronize()

    synthesis_s = timer.elapsed_s
    audio_duration_s = len(wav) / float(sample_rate)
    sample_out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(sample_out, wav, sample_rate)
    peak_vram_mb = sample_vram_mb()["peak_allocated_mb"]

    del model
    torch.cuda.empty_cache()

    return {
        "engine": "f5",
        "mode": "non_streaming",
        "ttfa_ms": round(synthesis_s * 1000, 1),
        "rtf": round(compute_rtf(audio_duration_s, synthesis_s), 3),
        "audio_duration_s": round(audio_duration_s, 3),
        "synthesis_time_s": round(synthesis_s, 3),
        "peak_vram_mb": round(peak_vram_mb, 1),
        "sample_rate": int(sample_rate),
        "output_wav": str(sample_out),
    }


def measure_xtts(ref_audio: str, target_text: str, sample_out: Path) -> dict[str, Any]:
    import time

    import numpy as np
    import soundfile as sf
    import torch
    from TTS.api import TTS

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    print("[tts] Loading XTTS v2...", flush=True)
    model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
    warmup_cuda()

    chunks: list[np.ndarray] = []
    sample_rate = 24000
    ttfa_ms: float
    synthesis_s: float
    streaming_ok = False

    try:
        _ = model.tts(text="Warm.", speaker_wav=ref_audio, language="en")
        torch.cuda.synchronize()

        if hasattr(model, "tts_stream"):
            first_chunk_s: float | None = None
            with Timer() as timer:
                started = time.perf_counter()
                for chunk in model.tts_stream(
                    text=target_text,
                    speaker_wav=ref_audio,
                    language="en",
                ):
                    if first_chunk_s is None:
                        first_chunk_s = time.perf_counter() - started
                    if isinstance(chunk, torch.Tensor):
                        chunk = chunk.detach().cpu().numpy()
                    chunks.append(np.asarray(chunk, dtype=np.float32).flatten())
                torch.cuda.synchronize()
            ttfa_ms = round((first_chunk_s or timer.elapsed_s) * 1000, 1)
            synthesis_s = timer.elapsed_s
            streaming_ok = True
        else:
            with Timer() as timer:
                wav = model.tts(text=target_text, speaker_wav=ref_audio, language="en")
                torch.cuda.synchronize()
            ttfa_ms = round(timer.elapsed_s * 1000, 1)
            synthesis_s = timer.elapsed_s
            chunks = [np.asarray(wav, dtype=np.float32).flatten()]
    except Exception:
        traceback.print_exc()
        with Timer() as timer:
            wav = model.tts(text=target_text, speaker_wav=ref_audio, language="en")
            torch.cuda.synchronize()
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
        "fallback_to_non_streaming": not streaming_ok,
        "ttfa_ms": ttfa_ms,
        "rtf": round(compute_rtf(audio_duration_s, synthesis_s), 3),
        "audio_duration_s": round(audio_duration_s, 3),
        "synthesis_time_s": round(synthesis_s, 3),
        "peak_vram_mb": round(peak_vram_mb, 1),
        "sample_rate": sample_rate,
        "output_wav": str(sample_out),
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
    )
    torch.cuda.synchronize()

    with Timer() as timer:
        wavs, sample_rate = model.generate_voice_clone(
            text=target_text,
            voice_clone_prompt=prompt,
            language="English",
        )
        torch.cuda.synchronize()

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
        "mode": "non_streaming",
        "variant": "0.6B-Base",
        "flash_attention": "eager",
        "ttfa_ms": round(synthesis_s * 1000, 1),
        "rtf": round(compute_rtf(audio_duration_s, synthesis_s), 3),
        "audio_duration_s": round(audio_duration_s, 3),
        "synthesis_time_s": round(synthesis_s, 3),
        "peak_vram_mb": round(peak_vram_mb, 1),
        "sample_rate": int(sample_rate),
        "output_wav": str(sample_out),
    }


def _read_reference_text(path: Path) -> str:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


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
    parser.add_argument("--output", required=True, help="Results JSON path")
    parser.add_argument(
        "--accent-ok",
        action="store_true",
        help="Only set after the builder confirms the Qwen accent test passes",
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
    OUTPUT_SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    engines: dict[str, dict[str, Any]] = {}
    probe_runs = [
        ("f5", lambda: measure_f5(str(ref_audio), ref_text, args.target_text, OUTPUT_SAMPLE_DIR / "f5.wav")),
        ("xtts", lambda: measure_xtts(str(ref_audio), args.target_text, OUTPUT_SAMPLE_DIR / "xtts.wav")),
        ("qwen3", lambda: measure_qwen3(str(ref_audio), ref_text, args.target_text, OUTPUT_SAMPLE_DIR / "qwen3.wav")),
    ]

    for name, runner in probe_runs:
        try:
            engines[name] = runner()
            print(
                f"[tts] {name}: TTFA={engines[name]['ttfa_ms']} ms, "
                f"RTF={engines[name]['rtf']}, "
                f"VRAM={engines[name]['peak_vram_mb']} MB",
                flush=True,
            )
        except Exception as exc:
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
        "target_text": args.target_text,
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
