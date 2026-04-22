"""Production-shaped F5 probe: short ack first, then chunked remainder."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torchaudio

from bench_utils import Timer, sample_vram_mb, warmup_cuda, write_results
from tts_ttfa import (
    _install_f5_runtime_shims,
    _maybe_cuda_sync,
    _read_reference_text,
    _read_target_text,
    compute_rtf,
)

_install_f5_runtime_shims()

from f5_tts.api import F5TTS
from f5_tts.infer.utils_infer import chunk_text, infer_batch_process, preprocess_ref_audio_text


def _max_chars_for_batches(
    ref_wave: torch.Tensor,
    ref_sample_rate: int,
    ref_text: str,
    speed: float,
) -> int:
    audio = ref_wave
    if audio.shape[0] > 1:
        audio = torch.mean(audio, dim=0, keepdim=True)
    return int(
        len(ref_text.encode("utf-8"))
        / (audio.shape[-1] / ref_sample_rate)
        * (22 - audio.shape[-1] / ref_sample_rate)
        * speed
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref-audio", required=True)
    parser.add_argument("--ref-text", required=True)
    parser.add_argument("--target-text-file", required=True)
    parser.add_argument("--ack-text", default="Yeah, I hear you.")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--output", required=True)
    parser.add_argument("--combined-out", required=True)
    parser.add_argument("--ack-out")
    parser.add_argument("--remainder-out")
    args = parser.parse_args()

    ref_audio = Path(args.ref_audio)
    ref_text_path = Path(args.ref_text)
    target_text_path = Path(args.target_text_file)
    if not ref_audio.exists():
        raise FileNotFoundError(f"Missing ref audio: {ref_audio}")
    if not ref_text_path.exists():
        raise FileNotFoundError(f"Missing ref text: {ref_text_path}")
    if not target_text_path.exists():
        raise FileNotFoundError(f"Missing target text file: {target_text_path}")

    ref_text = _read_reference_text(ref_text_path)
    remainder_text = _read_target_text(target_text_path)

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    model = F5TTS()
    warmup_cuda()
    _ = model.infer(str(ref_audio), ref_text, "Warm.", nfe_step=7)
    _maybe_cuda_sync(torch)

    with Timer() as ack_timer:
        ack_wav, sample_rate, _ = model.infer(
            str(ref_audio),
            ref_text,
            args.ack_text,
            nfe_step=7,
            speed=args.speed,
        )
        _maybe_cuda_sync(torch)

    ack = np.asarray(ack_wav, dtype=np.float32).flatten()
    ack_audio_duration_s = len(ack) / float(sample_rate)

    prepared_ref_audio, prepared_ref_text = preprocess_ref_audio_text(
        str(ref_audio),
        ref_text,
        show_info=lambda *_args, **_kwargs: None,
    )
    ref_wave, ref_sample_rate = torchaudio.load(prepared_ref_audio)
    max_chars = _max_chars_for_batches(ref_wave, ref_sample_rate, prepared_ref_text, args.speed)
    batches = chunk_text(remainder_text, max_chars=max_chars)

    remainder_chunks: list[np.ndarray] = []
    remainder_first_chunk_s: float | None = None
    with Timer() as remainder_timer:
        started = time.perf_counter()
        for chunk, sample_rate in infer_batch_process(
            (ref_wave, ref_sample_rate),
            prepared_ref_text,
            batches,
            model.ema_model,
            model.vocoder,
            mel_spec_type=model.mel_spec_type,
            progress=None,
            nfe_step=7,
            cfg_strength=2.0,
            sway_sampling_coef=-1.0,
            speed=args.speed,
            device=model.device,
            streaming=True,
        ):
            if remainder_first_chunk_s is None:
                remainder_first_chunk_s = time.perf_counter() - started
            remainder_chunks.append(np.asarray(chunk, dtype=np.float32).flatten())
        _maybe_cuda_sync(torch)

    remainder = np.concatenate(remainder_chunks) if remainder_chunks else np.zeros(1, dtype=np.float32)
    remainder_audio_duration_s = len(remainder) / float(sample_rate)

    # One short pause between ack and substantive reply keeps the render intelligible.
    pause = np.zeros(int(sample_rate * 0.08), dtype=np.float32)
    combined = np.concatenate([ack, pause, remainder])

    combined_out = Path(args.combined_out)
    combined_out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(combined_out, combined, sample_rate)

    if args.ack_out:
        ack_out = Path(args.ack_out)
        ack_out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(ack_out, ack, sample_rate)
    if args.remainder_out:
        remainder_out = Path(args.remainder_out)
        remainder_out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(remainder_out, remainder, sample_rate)

    ack_ready_s = ack_timer.elapsed_s
    remainder_ready_after_start_s = (remainder_first_chunk_s or remainder_timer.elapsed_s)
    dead_air_after_ack_ms = max(0.0, (remainder_ready_after_start_s - ack_audio_duration_s) * 1000.0)
    hidden_by_ack_playback_ms = max(0.0, (ack_audio_duration_s - remainder_ready_after_start_s) * 1000.0)
    peak_vram_mb = sample_vram_mb()["peak_allocated_mb"]

    payload = {
        "engine": "f5",
        "mode": "production_ack_then_chunked_remainder",
        "true_streaming": False,
        "speed": args.speed,
        "ack_text": args.ack_text,
        "ack_ttfa_ms": round(ack_ready_s * 1000, 1),
        "ack_audio_duration_s": round(ack_audio_duration_s, 3),
        "remainder_first_chunk_after_ack_start_ms": round(remainder_ready_after_start_s * 1000, 1),
        "remainder_audio_duration_s": round(remainder_audio_duration_s, 3),
        "remainder_synthesis_time_s": round(remainder_timer.elapsed_s, 3),
        "remainder_rtf": round(compute_rtf(remainder_audio_duration_s, remainder_timer.elapsed_s), 3),
        "dead_air_after_ack_ms": round(dead_air_after_ack_ms, 1),
        "hidden_by_ack_playback_ms": round(hidden_by_ack_playback_ms, 1),
        "num_batches": len(batches),
        "max_chars": max_chars,
        "batch_char_lengths": [len(batch) for batch in batches],
        "peak_vram_mb": round(peak_vram_mb, 1),
        "combined_audio_duration_s": round(len(combined) / float(sample_rate), 3),
        "combined_output_wav": str(combined_out),
    }
    write_results(args.output, payload)
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
