# Qwen3-TTS — Candidate TTS Engine Assessment for RayMe

**Researched:** 2026-04-17
**Scope:** Evaluate Qwen3-TTS (0.6B and 1.7B variants) against RayMe's TTS constraints — REQ-02 (12 GB VRAM budget), REQ-20–24 (Voice Lab reference-audio cloning), REQ-45 (sentence-streaming TTS), REQ-46 (<800 ms end-to-end TTFA), Resolved Tensions #3/#7/#12/#13.
**Confidence:** HIGH on model fundamentals, license, architecture, voice-cloning support, and voicebox integration (all from primary sources). MEDIUM on RTX 3060 performance (no direct 3060 benchmark exists — closest published points are GTX 1080 RTF 2.11× on 0.6B from Hacker News, and RTX 3090 RTF 0.87-0.95 for 1.7B from a benchmark article; the 3060 is ~2× a 1080 and ~0.5× a 3090, so the interpolation is defensible but not measured).

---

## 1. Summary

- **Qwen3-TTS exists and is real** — released 2026-01-22 by Alibaba Cloud Qwen team as an official open-source family, Apache-2.0 licensed, [QwenLM/Qwen3-TTS on GitHub](https://github.com/QwenLM/Qwen3-TTS) (10.7k stars, active). Not to be confused with Qwen-Audio, Qwen2-Audio, or Qwen3-Omni — it is a distinct TTS-specific line.
- **It supports reference-audio voice cloning** natively via the `-Base` variants: 3-second minimum reference audio + transcript → `create_voice_clone_prompt` → `generate_voice_clone`. This maps directly onto RayMe's Voice Lab UX (REQ-20–24) with essentially the same contract as F5-TTS.
- **It will NOT fit RayMe's latency budget on a 3060**. Closest datapoint: GTX 1080 achieves RTF 2.11× on the 0.6B model without FlashAttention (Hacker News). RTX 3090 achieves RTF 0.87-0.95 on 1.7B (qwen3-tts.app benchmarks). A 3060 sits between these — extrapolation says 0.6B might hit RTF ~1.0-1.3 with FlashAttention, 1.7B won't reach real-time. Phase 4's <800 ms TTFA target is infeasible unless TTFA-specific streaming optimizations (like `andimarafioti/faster-qwen3-tts` CUDA graph capture) are layered on — and those are third-party, unmaintained, and untested on 3060.
- **The license is a genuine upgrade** over F5 (CC-BY-NC) and XTTS (CPML non-commercial): Apache-2.0 across all weights and the `qwen-tts` package. Closes Resolved Tension #13 for this specific engine.
- **FlashAttention 2 is effectively required** for viable VRAM and speed, and FlashAttention 2 has documented install friction on Windows (Hacker News). RayMe's backend is Python + torch — Windows-compatible but this adds a setup-time gotcha.
- **jamiepine/voicebox integrates it non-streamingly.** Voicebox calls `model.generate_voice_clone(...)` synchronously and returns full utterances. It does NOT use `stream_generate_voice_clone` despite that API existing in `qwen-tts`. Voicebox's own roadmap lists real-time streaming as "not implemented." So voicebox is a validation of the voice-cloning API shape, not a reference for streaming integration.

**Verdict:** **Backlog for v2+.** Do not replace F5-TTS/XTTS v2 in v1. Do not add as a third engine in v1. Revisit after v1 ships when TTFA on the 3060 can be measured empirically (Phase 0 rig) and if/when a better-maintained streaming wrapper than `faster-qwen3-tts` emerges. Detailed triggers that would flip this decision are in §7.

---

## 2. Model Fundamentals

### 2.1 What it is, who publishes it

Qwen3-TTS is an **official Alibaba Cloud / Qwen team release**, first announced 2026-01-22 as an open-source series. Repository: [QwenLM/Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS). The README states:

> "We release **Qwen3-TTS**, a series of powerful speech generation capabilities developed by Qwen, offering comprehensive support for voice clone, voice design, ultra-high-quality human-like speech generation, and natural language-based voice control."

Blog: https://qwen.ai/blog?id=qwen3tts-0115. Paper: https://arxiv.org/abs/2601.15621. Demo: https://huggingface.co/spaces/Qwen/Qwen3-TTS.

It is **distinct from**:
- Qwen3 (the LLM family)
- Qwen2-Audio / Qwen-Audio (audio understanding, not synthesis)
- Qwen3-Omni (multimodal LLM that can speak — a different model family, end-to-end speech-to-speech)

### 2.2 Variants and HuggingFace IDs (confirmed from repo README)

Six models across two parameter sizes plus a separate tokenizer:

| HF Model ID | Size | Purpose | Streaming | Instruct |
|---|---|---|---|---|
| `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` | 1.7 B | Synthesize a new voice from natural-language description | ✅ | ✅ |
| `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` | 1.7 B | 9 preset speakers with emotion/style control | ✅ | ✅ |
| `Qwen/Qwen3-TTS-12Hz-1.7B-Base` | 1.7 B | **3-second reference-audio voice clone** | ✅ | — |
| `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` | 0.6 B | 9 preset speakers (lightweight) | ✅ | — |
| `Qwen/Qwen3-TTS-12Hz-0.6B-Base` | 0.6 B | **3-second reference-audio voice clone (lightweight)** | ✅ | — |
| `Qwen/Qwen3-TTS-Tokenizer-12Hz` | — | Shared encoder/decoder tokenizer | — | — |

For RayMe's Voice Lab, **the `-Base` variants are the only ones that matter** — the CustomVoice models are fixed-speaker, and VoiceDesign is text-prompt-only (no reference audio). The builder wants to clone his girlfriend's voice, not pick "Ryan" from a preset list.

### 2.3 License

**Apache-2.0.** Confirmed by direct read of `LICENSE` at the root of [QwenLM/Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS), and the `qwen-tts` PyPI page lists "License: Apache-2.0" under classifiers. Commercial use permitted, weight redistribution permitted with notice, derivative works permitted.

This is a **meaningful upgrade** over:
- F5-TTS: [CC-BY-NC 4.0, commercial ambiguous](https://github.com/SWivid/F5-TTS/discussions/997)
- XTTS v2: [CPML, explicitly non-commercial](https://github.com/coqui-ai/TTS/discussions/4304)

RayMe itself is non-commercial (PROJECT.md Out of Scope rules out cloud / SaaS / beyond-LAN), so the license advantage is latent, not active, in v1. But if RayMe ever pivots (v2+) or if the builder wants to share voice packs, Apache-2.0 removes the legal blocker.

### 2.4 Architecture

From the official README under "Overview → Introduction":

> "Utilizing a **discrete multi-codebook LM architecture**, it realizes full-information end-to-end speech modeling. This completely bypasses the information bottlenecks and cascading errors inherent in traditional LM+DiT schemes..."
>
> "Based on the innovative **Dual-Track hybrid streaming generation architecture**, a single model supports both streaming and non-streaming generation."
>
> "...a **lightweight non-DiT architecture**..."

Plain English: it is a **transformer-based autoregressive language model that generates discrete speech codec tokens**, paired with a separate decoder (the 12 Hz tokenizer) that turns those tokens into a 24 kHz waveform. This is the same family as CosyVoice, Fish Speech, and Spark-TTS — and architecturally **very different from F5-TTS** (which is flow-matching with DiT). Autoregressive LM-style TTS has two implications for RayMe:

1. **TTFA is naturally low** (you can emit the first audio packet after the first few decoded tokens) — this is what enables the claimed 97 ms streaming latency.
2. **Long-text RTF degrades** because each token requires a forward pass; the speech-token rate at 12 Hz × N codebooks means sustaining real-time needs roughly constant-time per 83 ms of audio. On weak GPUs that constant exceeds 83 ms and RTF > 1.

### 2.5 Voice cloning from reference audio — **YES, supported**

Confirmed via the README voice-clone section and `qwen-tts` PyPI docs:

```python
from qwen_tts import Qwen3TTSModel
import torch

model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    device_map="cuda:0",
    dtype=torch.bfloat16,
    attn_implementation="flash_attention_2",
)

wavs, sr = model.generate_voice_clone(
    text="I am solving the equation...",
    language="English",
    ref_audio="path/to/6s-sample.wav",   # path, URL, base64, or (numpy, sr)
    ref_text="Okay. Yeah. I resent you. I love you. I respect you. But you know what? You blew it!",
)
```

And for prompt reuse (the same pattern RayMe's Voice Lab needs — create once, synthesize many times):

```python
prompt_items = model.create_voice_clone_prompt(
    ref_audio=ref_audio,
    ref_text=ref_text,
    x_vector_only_mode=False,
)
wavs, sr = model.generate_voice_clone(
    text="Sentence to synthesize",
    language="English",
    voice_clone_prompt=prompt_items,
)
```

This contract is **almost identical to F5-TTS's**: reference audio + transcript → reusable speaker embedding/prompt → synthesis. The `x_vector_only_mode=True` flag gives a "speaker embedding only, no transcript" mode analogous to XTTS v2 — but Qwen itself flags that cloning quality degrades in this mode.

**Reference-audio constraints** (from the [ocdevel voice cloning guide](https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning)):
- **Minimum**: 3 seconds
- **Ideal sweet spot**: 10–15 seconds (quality plateaus, then degrades)
- **Hard maximum**: `ref_audio_max_seconds=30` default; 60 s pushes ~750 prefill tokens and "dramatically increases compute cost and instability risk"
- **Required format**: WAV 16-bit / MP3 / M4A, ≥24 kHz, mono, <10 MB

This **overlaps perfectly with RayMe's REQ-20** (6–15 s mono, WAV/MP3/FLAC — FLAC support in the Python wrapper is unknown and would need verification).

### 2.6 Languages, and accented-English handling

Official language list: Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian (10 total).

For RayMe's REQ-A3 (Spanish-accented English speaker), the picture is **mixed and ambiguous**:
- Chinese and English are the two best-supported languages in the WER benchmarks. English test WER = 1.24 (1.7B-Base), English multilingual = 0.934. Training data appears English-rich for a Chinese-team-produced model.
- But the same [ocdevel guide](https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning) notes: "Accent is conspicuously absent from the official dimensions table" and quotes a community report that "most of the voices have too strong a Chinese accent when speaking English," plus a documented case of a cloned **British accent reverting to American** after an update.
- The recommended workaround is: *clone from an actual Spanish-accented reference audio* rather than trying to prompt for an accent — which is exactly what RayMe's Voice Lab would do anyway.

**Bottom line on accent:** untested on Spanish-accented English, with community-reported risk of accent drift. Would need to be measured in Phase 0 before adoption. This is the same kind of Phase-0 measurement already budgeted for STT (REQ-A3 / Resolved Tension #2) and F5 TTFA (Resolved Tension #3).

---

## 3. VRAM & Performance on RTX 3060 12 GB

### 3.1 VRAM footprint (published numbers)

Two sources with concrete numbers, reconciled:

**From [qwen3-tts.app benchmark article](https://qwen3-tts.app/blog/qwen3-tts-performance-benchmarks-hardware-guide-2026)** (fp16/bf16):

| GPU | 0.6B | 1.7B |
|---|---|---|
| RTX 3060 Ti (8 GB) | 2.5 GB | 6.2 GB (OOM risk reported) |
| RTX 4090 (24 GB) | 2.9 GB | 5.4 GB |
| A100 (40 GB) | 2.8 GB | 5.1 GB |

**From [DeepWiki mu-zi-lee/qwen3-tts-skill page](https://deepwiki.com/mu-zi-lee/qwen3-tts-skill/8.2-memory-and-hardware-requirements)** — these are peak weights + inference overhead:

| dtype + Attn | 0.6B | 1.7B |
|---|---|---|
| float32 | 5–6 GB | 14–16 GB |
| bfloat16 | 3–4 GB | 7–8 GB |
| bfloat16 + FlashAttention 2 | 2–3 GB | 5–6 GB |

**No int8 / int4 / AWQ / GPTQ** is documented in the official README. The community mentions "7 quantized variants" on HuggingFace but no official path; treat quantization as experimental until proven.

### 3.2 The RayMe VRAM math on a 3060 12 GB

Compare against the STACK.md budget for the F5/XTTS path:

| Component | Mode | VRAM | Notes |
|---|---|---:|---|
| faster-whisper `distil-large-v3` | int8_float16 | 1.5 GB | Already planned for RayMe |
| Silero VAD (CPU) | onnx | ~0 GB on GPU | Runs CPU-side |
| CUDA runtime + cuDNN + Opus + allocator slack | — | 1.5 GB | Always reserve |
| **Subtotal (shared)** | | **~3.0 GB** | |
| --- | --- | --- | --- |
| **Option A: Qwen3-TTS 0.6B + FA2** | bf16 | 2–3 GB | Combined ≈ 5–6 GB |
| **Option B: Qwen3-TTS 1.7B + FA2** | bf16 | 5–6 GB | Combined ≈ 8–9 GB |
| **Option C: Qwen3-TTS 1.7B no FA2** | bf16 | 7–8 GB | Combined ≈ 10–11 GB — tight |
| Current F5-TTS | fp16 | 4–6 GB | Combined ≈ 7–9 GB |
| Current XTTS v2 | fp16 | 2.1 GB | Combined ≈ 5 GB |

**Does it fit?** Yes for 0.6B, and yes for 1.7B *if FlashAttention 2 is installed and working*. The math says so; the installation friction says maybe. Community (Hacker News thread) reports Windows install problems with FA2 are recurring. Without FA2, 1.7B on Windows is right at the cliff and the 30-minute soak test in Phase 0 success criterion #4 would almost certainly fail.

### 3.3 Inference speed — the actual blocker

This is where the story falls apart for RayMe's Phase 4 latency targets. No direct RTX 3060 benchmark exists, so we triangulate:

| Source | GPU | Model | TTFA | RTF | Notes |
|---|---|---|---:|---:|---|
| [qwen3-tts.app benchmarks](https://qwen3-tts.app/blog/qwen3-tts-performance-benchmarks-hardware-guide-2026) | RTX 3060 Ti | 0.6B | — | 0.85–1.15 | Mid-range compute, realtime-borderline |
| | RTX 3060 Ti | 1.7B | — | **1.65 + OOM risk** | Below real-time |
| | RTX 4090 | 1.7B | 97 ms | 0.65–0.85 | The flagship number Qwen advertises |
| Hacker News [thread](https://news.ycombinator.com/item?id=46719229) | **GTX 1080** | 0.6B | — | **2.11** (no FA2) | ~2× slower than real-time |
| [rekuenkdr/Qwen3-TTS-streaming](https://github.com/rekuenkdr/Qwen3-TTS-streaming) wrapper + FA2 | RTX 3090 | 1.7B | — | **0.87** | Barely real-time on a 3090 |
| [andimarafioti/faster-qwen3-tts](https://github.com/andimarafioti/faster-qwen3-tts) (CUDA graphs) | RTX 4060 | 0.6B | **413 ms** | 2.26 (5.8× faster than baseline) | Closest comparable consumer card |
| | RTX 4090 | 0.6B | 156 ms | 4.78 | Flagship |
| | RTX 4090 | 1.7B | 174 ms | 4.22 | Flagship |

**Interpretation for RTX 3060 12 GB (base model, Ampere, ~12.7 TFLOPS FP32):**
- RTX 3060 Ti has similar compute to the 3060 (Ti is ~17% faster) but only 8 GB VRAM.
- A 3060 on **0.6B with FlashAttention 2** will plausibly hit **RTF ~1.0–1.3**. That's *not real-time*: you cannot sustain a streaming call because the TTS falls behind.
- A 3060 on **1.7B with FlashAttention 2** will plausibly hit **RTF ~1.8–2.2**. Strictly below real-time.
- The [faster-qwen3-tts](https://github.com/andimarafioti/faster-qwen3-tts) project's CUDA-graph-capture approach gets RTF 2.26 on RTX 4060 for 0.6B — that extrapolates to roughly **RTF 1.6–1.9 on a 3060**. Viable for real-time, but this wrapper is a 2-month-old third-party project with no community activity and no published 3060 number. Relying on it for v1 is a roll of the dice.

Compare to **F5-TTS** (7-step Sway sampling, per STACK.md): expected RTF ~0.06–0.10 on 3060. And **XTTS v2** natively streams with <200 ms first-chunk. Both comfortably clear the real-time bar on this GPU; Qwen3-TTS does not, at least without aggressive third-party optimization.

### 3.4 The 97 ms claim

The "end-to-end synthesis latency as low as 97 ms" figure appears throughout Qwen's marketing. It is **measured on H100/A100-class hardware** with FlashAttention 2 and the streaming API. It has not been independently verified on a 3060. Treat it as a best-case marketing number. For RayMe's Phase 4 <800 ms end-to-end budget (STT endpoint + LLM TTFT + TTS first audio + network), Qwen3-TTS's TTFA component would need to come in under ~300 ms on a 3060 — the faster-qwen3-tts numbers suggest that's achievable on 0.6B with CUDA graph capture, but again, this is unverified third-party work.

### 3.5 Quantization

No official quantization path. No int8/int4 support documented in the README. Community finetunes exist on HuggingFace ("7 quantized variants" mentioned in one source) but are unaudited and not published by Alibaba. Assume fp16/bf16 is the floor for v1 planning.

---

## 4. Streaming Behavior

### 4.1 Does the engine support intra-utterance streaming?

**Yes, natively — but only via specific APIs that RayMe would have to wire up itself.**

The `qwen-tts` Python package exposes:
- `stream_generate_voice_clone(...)` — streaming variant of the clone path
- `stream_generate_custom_voice(...)` — streaming variant of the preset-speaker path
- `stream_generate_pcm(...)` — raw PCM streaming

These were confirmed in WebSearch snippets showing "true token-by-token PCM chunks via `stream_generate_custom_voice` / `stream_generate_voice_clone` functions, not post-generation chunking." A third-party FastAPI wrapper ([groxaxo/Qwen3-TTS-Openai-Fastapi](https://github.com/groxaxo/Qwen3-TTS-Openai-Fastapi)) uses these exact methods.

So the capability exists. For RayMe, you would:
1. Split the LLM stream into sentence chunks (as already planned for F5 in REQ-45 / Pitfall #23).
2. Feed each sentence to `stream_generate_voice_clone(...)` which yields PCM chunks as tokens are decoded.
3. Push each PCM chunk to the browser via WebRTC / MediaStreamAudioDestinationNode.

This is architecturally the same as the XTTS v2 streaming integration already planned — just pointed at a different engine.

### 4.2 Can it be pushed intra-sentence, not just inter-sentence?

Yes — this is the whole point of the "Dual-Track hybrid streaming" architecture. The model is autoregressive over speech codec tokens at 12 Hz (one token = 83 ms of audio), so the engine can emit PCM **while still generating the text**. That's a theoretical TTFA advantage over F5 (which must synthesize a whole sentence before playback can start).

However: **this advantage is only realized if the decode-per-token cost on the 3060 is under 83 ms.** Given RTF ~1.0–1.3 for 0.6B (§3.3), it's close to the margin. For 1.7B it doesn't hit.

### 4.3 First-sentence TTFA on a 3–5 word acknowledgment — unknown on 3060

No published 3060 number. Extrapolating from the CUDA-graph-wrapper 4060 number (TTFA 413 ms for 0.6B) suggests a baseline 3060 TTFA of **~500–800 ms on 0.6B**, possibly worse without optimizations. That is at or outside the Phase 4 <800 ms end-to-end budget (which must also include STT endpoint + LLM TTFT + network). **This is a real risk flag**, and without a Phase-0 measurement on the actual hardware, it cannot be confidently estimated to fit.

### 4.4 voicebox does NOT stream it

See §5. Voicebox calls `generate_voice_clone(...)` (non-streaming, full-utterance) through `asyncio.to_thread`. Voicebox's roadmap explicitly lists "Real-time Streaming: Stream audio as it generates, word by word" as **not yet implemented**. So voicebox cannot be used as a reference implementation for streaming Qwen3-TTS.

---

## 5. voicebox Reference Implementation

### 5.1 Repo shape

[jamiepine/voicebox](https://github.com/jamiepine/voicebox) — MIT licensed, TypeScript + Rust (Tauri desktop) + Python (FastAPI backend). 19.7k stars, very active (last push 2026-04-17). Describes itself as "local-first voice cloning studio — free and open-source alternative to ElevenLabs."

Top-level structure:
- `backend/` — Python FastAPI (Qwen3-TTS + other engines)
- `tauri/` — Rust native app shell
- `web/` + `app/` — TypeScript/React frontend
- `landing/` — Next.js marketing site

### 5.2 How voicebox loads Qwen3-TTS

From [`backend/backends/pytorch_backend.py`](https://github.com/jamiepine/voicebox/blob/main/backend/backends/pytorch_backend.py):

```python
hf_model_map = {
    "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "0.6B": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
}
# ...
from qwen_tts import Qwen3TTSModel
self.model = Qwen3TTSModel.from_pretrained(
    model_path,
    cache_dir=tts_cache_dir,
    device_map=self.device,
    torch_dtype=torch.bfloat16,
)
```

CPU fallback uses `torch.float32` + `low_cpu_mem_usage=False`. No FlashAttention, no quantization, no `attn_implementation="flash_attention_2"` — which is **different from what the Qwen README recommends**. This likely leaves VRAM headroom on the table but is more portable across setups.

There's a dedicated Windows comment: models cache to a single `HF_HUB_CACHE` because "on Windows local setups, model assets can otherwise split between `.hf-cache/hub` and `.hf-cache/transformers`, causing `speech_tokenizer` and `preprocessor_config.json` to fail to resolve during load." **This is a reusable learning for RayMe's Windows-first backend**: force a single cache dir.

### 5.3 How voicebox invokes voice cloning

Same file — `create_voice_prompt` caches the computed prompt (avoiding re-computation), then `generate` synthesizes:

```python
def _create_prompt_sync():
    return self.model.create_voice_clone_prompt(
        ref_audio=str(audio_path),
        ref_text=reference_text,
        x_vector_only_mode=False,
    )
# ...
wavs, sample_rate = self.model.generate_voice_clone(
    text=text,
    voice_clone_prompt=voice_prompt,
    language=LANGUAGE_CODE_TO_NAME.get(language, "auto"),
    instruct=instruct,
)
return wavs[0], sample_rate
```

Both calls happen inside `asyncio.to_thread()` wrappers so the blocking inference doesn't block the event loop. This pattern is **directly reusable for RayMe** — FastAPI + asyncio backend, wrap blocking inference in `to_thread`, return complete audio.

Also reusable: the voice-prompt cache in `backend/utils/cache.py` that keys on `(audio_path, reference_text)` → cached tensor dict → reuse across multiple generations. This exactly matches what RayMe's Voice Library needs (build prompt once on Voice Lab save, use forever).

### 5.4 What voicebox does NOT do

- **No streaming.** No use of `stream_generate_voice_clone`. Roadmap lists streaming as pending.
- **No WebSocket/WebRTC media transport.** Voicebox is a desktop studio app (Tauri), not a real-time call app. The backend exposes a FastAPI REST API that returns complete audio files.
- **No sentence chunking or mid-utterance cancellation.** The closest thing is the multi-engine registry that lets the user pick a different engine for the next generation.
- **No VAD, no STT-in-the-loop, no LLM integration.** Voicebox is a studio tool for offline voice synthesis.

So **voicebox validates the Qwen3-TTS voice-cloning API contract works**, but it is structurally the wrong shape for RayMe's real-time call loop. Voicebox is closer in spirit to RayMe's Voice Lab *previewing* a voice than to the call runtime.

### 5.5 Reusable code

| Voicebox file | What's reusable for RayMe |
|---|---|
| `backend/backends/pytorch_backend.py` | `PyTorchTTSBackend` class shape — `load_model_async`, `unload_model`, `create_voice_prompt` with cache, `generate` wrapped in `to_thread`. Almost drop-in if RayMe adopts Qwen3-TTS. |
| `backend/backends/qwen_custom_voice_backend.py` | Shows the CustomVoice path — not needed for RayMe (we want clone-from-reference, not presets). |
| `backend/backends/base.py` + shared utils | `get_torch_device(allow_xpu, allow_directml, allow_mps)`, `empty_device_cache(device)`, `is_model_cached(hf_repo)`, `model_load_progress(...)`, `manual_seed(...)`, `combine_voice_prompts(...)` — generic TTS-backend plumbing that works for any engine. RayMe could import this pattern wholesale. |
| `backend/utils/hf_offline_patch.py` (`force_offline_if_cached`) | Avoids HuggingFace online check when weights are already cached — matters for boot time and offline use. |
| `backend/utils/cache.py` (voice-prompt cache) | Key `(audio_path, ref_text) → tensor dict` cache for pre-computed voice prompts. Directly reusable. |

### 5.6 Voicebox license

**MIT.** Means any code copied into RayMe needs an attribution and MIT notice in `LICENSES.md` (cheap), but no copyleft obligation.

---

## 6. Engine Comparison Matrix

Rows are engines; columns are the decision dimensions for RayMe v1.

| Criterion | **Qwen3-TTS 0.6B-Base** | **Qwen3-TTS 1.7B-Base** | **F5-TTS** (pinned) | **XTTS v2 idiap** (pinned) |
|---|---|---|---|---|
| **License** | Apache-2.0 ✅ commercial-OK | Apache-2.0 ✅ commercial-OK | CC-BY-NC 4.0 ⚠️ non-commercial | CPML ⚠️ explicitly non-commercial |
| **VRAM @ bf16 + FA2** | 2–3 GB | 5–6 GB | ~4–6 GB | ~2.1 GB |
| **VRAM + Whisper + VAD + slack (3060 12 GB)** | ~5–6 GB ✅ | ~8–9 GB ✅ (with FA2) / ~10–11 GB ⚠️ (without) | ~7–9 GB ✅ | ~4.5 GB ✅ |
| **Voice cloning from reference audio?** | ✅ 3-sec min, 10–15 s ideal, transcript + audio | ✅ same, stronger quality | ✅ 6–15 s, transcript required | ✅ 6–15 s, transcript NOT required |
| **Streaming TTFA class on 3060** | Unknown, extrapolated 500–800 ms w/ CUDA-graph wrapper; natively RTF ~1.0–1.3 (borderline) | Unknown, extrapolated RTF ~1.8–2.2 (**below real-time**) | Sentence-chunked: ~300 ms target on 3–5 words with 7-step Sway sampling; no native mid-sentence streaming | **Native streaming, <200 ms first-chunk on 3060-class** |
| **Languages** | 10 (ZH, EN, JA, KO, DE, FR, RU, PT, ES, IT) | 10 (same) | Primarily EN + ZH; multilingual variant exists | 17 including English + Spanish |
| **Accent handling (Sp-accented EN)** | Unverified; community reports Chinese-accent bleed and drift | Unverified (same) | Well-attested on English; accent from reference audio preserved | Well-attested; longest track record |
| **Maintenance activity** | High (official Alibaba team, 2026-01-22 release, 10.7k stars, actively pushed) | High (same) | High (upstream `SWivid/F5-TTS`, actively maintained) | Medium (Coqui defunct; idiap fork live but volunteer-paced) |
| **Python package stability** | `qwen-tts` v0.1.1 (2026-02-06) — young, only 2 months old at time of research | same | `f5-tts` 1.1.19 — 1.5 years, mature | `coqui-tts` 0.27.5 — mature |
| **Windows install friction** | ⚠️ FlashAttention 2 install problems reported on HN; cache-dir gotcha (voicebox patched it) | ⚠️ same | Low | Low |
| **Natively streamable via Python API** | ✅ `stream_generate_voice_clone` | ✅ same | ❌ not native; sentence-chunking wrapper needed | ✅ native streaming API |
| **3060 real-time (RTF <1)** | Borderline w/ FA2, likely viable w/ CUDA-graph wrapper | ❌ likely not viable | ✅ with 7-step Sway | ✅ native |
| **Integration effort for RayMe** | Medium–high (write new `TTSService`, wire streaming API, Windows install pitfalls) | Same | Already planned in STACK.md | Already planned, Pipecat ships service |
| **Known bugs** | Long-reference infinite-loop; random laughter/moans in long gen; 0.6B fails to capture emotion; timbre drift across repeated gens ([ocdevel guide](https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning)) | same, less pronounced | Transcript-mismatch failure mode (Pitfall #9); 20 s ref cap | Historically solid |
| **Abandonware risk** | Low — official Alibaba line, actively developed | Low | Low (upstream active) | **Medium** (Resolved Tension #12 — fork is volunteer) |

---

## 7. Recommendation

**Verdict: Backlog for v2+. Do not replace. Do not add as a third engine in v1.**

**Confidence: HIGH** that this is the right call for v1 given current data.

### Primary reasons

1. **Real-time performance on the 3060 is unverified and likely marginal.** All extrapolations from published numbers suggest Qwen3-TTS 0.6B is RTF-borderline on a 3060, and 1.7B is below real-time. Phase 4's core-value requirement (<800 ms end-to-end TTFA) depends on the TTS staying ahead of the sentence stream. F5 and XTTS both clear that bar with published headroom on this GPU class; Qwen3-TTS has no such evidence.

2. **Voice-cloning API is equivalent to F5's, not strictly better.** RayMe already has a 2-engine plan (F5 + XTTS) that covers the cloning-from-reference UX. Qwen3-TTS adds variety, not a fundamentally new capability. The one genuine advantage — Apache-2.0 license — is latent in v1 because RayMe is non-commercial by scope.

3. **Adding a third engine multiplies v1 scope against a product that is already "one load-bearing core-value phase away from validating its own premise."** ROADMAP.md Phase 4 is explicitly the make-or-break phase. Adding a third TTS engine to validate in Phase 5 would double the cold-swap UX surface (REQ-22 / Pitfall #7), add a third VRAM math case to Phase 0 soak-testing, and import a bundle of unknowns (FlashAttention install friction, tokenizer warnings, long-gen infinite loops) into a project that is already managing nine critical pitfalls.

4. **Python package is 2 months old.** `qwen-tts` 0.1.1 was released 2026-02-06 (about 2.5 months before this research). F5 and XTTS have 12–24 months of community shakedown. For v1, "maturity of the Python wrapper" matters as much as "maturity of the model."

5. **No independent verification of the 97 ms / streaming claims on consumer hardware.** Every published benchmark that hits sub-100 ms is on H100/A100 class GPUs with FlashAttention 2. The only 3060-adjacent number (3060 Ti, qwen3-tts.app article) shows 0.6B at RTF 0.85–1.15 and 1.7B at RTF 1.65 with OOM risk.

### Conditional triggers that would flip the decision

The verdict is **backlog**, not **permanent reject**. Any of the following would warrant re-evaluation for v1.x or v2+:

| Trigger | Action |
|---|---|
| Phase 0 VRAM + TTFA spike measures **Qwen3-TTS 0.6B on the 3060 at TTFA <400 ms, RTF <0.7, sustained 30-min soak <11 GB** | Promote to **augment** consideration as a third engine in v1.x Voice Lab (REQ-22 would grow to three engines) |
| A well-maintained, 3060-validated streaming wrapper (better than the current 2-month-old [faster-qwen3-tts](https://github.com/andimarafioti/faster-qwen3-tts)) emerges with published benchmarks | Same as above — adds a viable path |
| Either F5 OR XTTS becomes unusable in v1 (F5 Phase-0 TTFA fails; XTTS idiap fork abandonware risk materializes) | Promote to **replace the failed engine**, not both (keeps the 2-engine surface stable) |
| RayMe pivots past PROJECT.md's non-commercial scope in v2+ | License advantage activates; Qwen3-TTS becomes the **recommended primary**, F5/XTTS move to compatibility |
| A user requests non-English TTS (Spanish, Japanese, Korean) that F5/XTTS handle poorly | Qwen3-TTS 10-language coverage wins — augment candidate |

---

## 8. Phase-by-Phase Implications if Adopted

Even though the recommendation is backlog, here's what adoption would cost per phase — useful as a sanity check on the size of the "no" and for v2+ planning.

### Phase 0 (Measurement Gate)

Adding Qwen3-TTS to Phase 0 expands the spike from "3 days" to "4 days":
- Add RTX 3060 TTFA measurement on 0.6B and 1.7B, with and without FlashAttention 2 (FA2 install friction on Windows is itself a Phase-0 risk)
- Add Qwen3-TTS 0.6B + Whisper + Silero soak test (new line in Phase 0 success criterion #4)
- Add a Spanish-accented English reference-audio cloning quality test (analogous to the Whisper WER test) because community reports accent drift
- The acceptance gate would become: "Qwen3-TTS 0.6B TTFA on the actual 3060 ≤400 ms AND 30-min soak under 11 GB AND Spanish-accent clone is subjectively acceptable. If yes → augment candidate. If any fail → v2+ backlog."

### Phase 2 (AI Backend Skeleton & Voice Lab)

- **Hot-swap registry**: the "exactly one TTS engine resident" rule (REQ-02) still holds, but the swap table grows from 2 engines to 3. Implementation cost is minor (one more registry entry, one more cold-swap path) but the state-machine surface area ~1.5×.
- **Voice Lab save UX**: REQ-22 "Voice save captures: name, engine (F5-TTS or XTTS v2, user-selected per voice)" becomes three engines. The Voice Lab picker is a radio group today — adding a third radio is trivial.
- **Phase 0 engine default**: if Qwen3-TTS 0.6B passes Phase 0 measurement, it may become a *third default option* — but XTTS v2 should remain the conservative fallback for the Spanish-accented-English case unless Qwen3-TTS wins that specific test decisively.
- **Install friction**: the backend `requirements.txt` now pins `qwen-tts>=0.1.1` and optionally `flash-attn`. Windows install instructions need a FA2 section.

### Phase 5 (Voice Breadth & Unified Thread Polish)

- **Cold-swap UX (Pitfall #7)**: instead of two engines in the swap registry (F5 ↔ XTTS), three (F5 ↔ XTTS ↔ Qwen). The "Switching voice…" loading state UX is the same, but the possible paths grow from 2 to 6. Testing matrix scales O(N²) for swap-correctness.
- **Per-character voice default / per-chat override**: no change — these are engine-agnostic in schema.
- **Research risk to Phase 4** eliminated: by this phase, the core call loop with one engine is already proven. Adding engine #3 in Phase 5 instead of Phase 2 would be safer. **But** the integration cost (new `TTSService` subclass, streaming wrapper, install docs) is real — a day or two of engineering, at best.

### VRAM budget across all phases

With FA2 installed and only 0.6B resident:
- Whisper (1.5) + VAD (~0) + Qwen3-TTS 0.6B (2.5) + CUDA slack (1.5) = **~5.5 GB** ✅ comfortable

With FA2 and 1.7B resident:
- Whisper (1.5) + VAD + Qwen3-TTS 1.7B (6) + slack (1.5) = **~9 GB** ⚠️ tight but feasible

Without FA2 and 1.7B:
- Whisper (1.5) + VAD + Qwen3-TTS 1.7B (8) + slack (1.5) = **~11 GB** ⛔ at the cliff

---

## 9. Pitfalls & Risks

### 9.1 Abandonware / availability risks (analogous to Resolved Tension #12)

**Risk: LOW.** Qwen3-TTS is an official Alibaba Cloud product released through the Qwen team's primary GitHub org, the same team that ships Qwen3 LLMs (10M+ monthly downloads). Alibaba has commercial skin in the game (DashScope API) and a published fine-tuning path. This is the **opposite** of Coqui's situation, where the company actively shut down. However:

- **Forks may diverge** — already three major third-party optimizer forks exist ([faster-qwen3-tts](https://github.com/andimarafioti/faster-qwen3-tts), [rekuenkdr/Qwen3-TTS-streaming](https://github.com/rekuenkdr/Qwen3-TTS-streaming), [groxaxo/Qwen3-TTS-Openai-Fastapi](https://github.com/groxaxo/Qwen3-TTS-Openai-Fastapi)). RayMe should depend only on the official `qwen-tts` PyPI package and QwenLM/Qwen3-TTS repo, not the forks.
- **Weight hosting** is on HuggingFace + ModelScope. Alibaba's OSS-CN-Beijing mirror is listed too. Multi-source → robust.
- **The `qwen-tts` package is 2 months old** (v0.1.1, 2026-02-06). API-breaking changes in 0.2.x are possible. Pin tightly.

### 9.2 Known bugs & quirks (from community sources)

From [Hacker News discussion](https://news.ycombinator.com/item?id=46719229) and [ocdevel's voice-cloning guide](https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning):

1. **FlashAttention 2 install friction on Windows.** HN confirms: "Windows users encountered FlashAttention compatibility problems." RayMe's backend is Windows-primary (3060 box is a Windows machine per the builder's setup). FA2 is `recommended` per Qwen docs; likely achievable via prebuilt wheels, but the Phase 0 setup script should validate this and fall back gracefully to non-FA2 if the install fails.

2. **Tokenizer warning:** "`fix_mistral_regex=True` flag when loading this tokenizer" (HN). Cosmetic but flags that the tokenizer is borrowed from Mistral.

3. **Long-reference infinite loops.** If `ref_audio >30 s`, the model fails to emit EOS and loops. `qwen-tts` enforces `ref_audio_max_seconds=30` but the app layer should cap earlier (REQ-20 already caps at 15 s, so this is handled).

4. **Random emotional outbursts in long generations.** "Laughing, moaning, humming" injected into long outputs. Mitigation: keep generated chunks short (<15 s per chunk) via sentence-boundary splitting — which RayMe already plans per REQ-45.

5. **0.6B model consistently fails to capture emotion** (ocdevel). If RayMe needs expressive speech for character calls, 1.7B is the right tier — but that's the one that may not fit the 3060 real-time budget.

6. **Timbre drift across repeated generations** (zero-shot cloning instability). Calling the same sentence twice produces different timbres. For RayMe this is probably fine (conversations don't repeat sentences often), but the test-play button in Voice Lab (REQ-23) should generate with a fixed seed for reproducibility during voice auditioning.

7. **Phoneme bleed from reference ending.** "The model's first generated token conditions on whatever phoneme the reference audio ends on, causing bleed into the start of generated speech." Voice Lab should recommend users trim silence/breath from the end of their reference audio (already good hygiene).

8. **Chinese-accent bleed on English output.** [ocdevel](https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning) quotes user reports of English output with Chinese-accent flavor. For Spanish-accented-English reference audio, unknown whether the model preserves the Spanish accent or drifts toward a default American or Chinese-flavored English. **This is the single biggest unknown for REQ-A3 fit.**

9. **Sample rate mismatch gotchas.** Model outputs 24 kHz (or 48 kHz if the new 48 kHz tokenizer decoder is used). WebRTC / aiortc expects 48 kHz Opus. A resampler step is already in the RayMe pipeline for XTTS (24 kHz native); same code handles Qwen.

### 9.3 Failure modes if adopted despite the recommendation

If RayMe decides to add Qwen3-TTS anyway in v1:

| Failure | Detection | Recovery |
|---|---|---|
| Phase 4 TTFA misses <800 ms budget | Phase 0 measurement rig (as planned) | Fall back to F5 or XTTS for that voice; `engine` field in Voice Library lets user move the clone to another engine |
| Windows FlashAttention install fails | Phase 2 backend bringup script | Warn user, fall back to non-FA2 — but VRAM budget for 1.7B becomes untenable; restrict to 0.6B |
| Spanish-accented English drifts to American | Phase 0 qualitative listening test | Block adoption for this user; retain F5/XTTS as the Spanish-accent path |
| `qwen-tts` 0.2.x breaking change | Pinned dependency prevents auto-upgrade | Pin to `qwen-tts==0.1.1`; vendor the relevant `.py` modules if upstream breaks |
| Long-gen infinite loop | Inference timeout (e.g., 15 s hard timeout per sentence) | Timeout cancel + retry with shorter text; surface error to user |

---

## 10. Open Questions

Things I could not confidently answer from available sources; flagged for Phase 0 or later empirical work:

1. **Exact TTFA on RTX 3060 12 GB** for 0.6B-Base and 1.7B-Base, with and without FlashAttention 2, on 3–5 word acknowledgment text. Closest datapoints are GTX 1080 RTF 2.11 (0.6B, no FA2) and RTX 4060 TTFA 413 ms (0.6B, CUDA graphs). **Measurable only on the actual hardware.** [needs-measurement]

2. **Sustained VRAM under 30-minute soak with Qwen3-TTS 1.7B + Whisper + Silero cycling** — does fragmentation drift? Analogous to the existing Phase 0 success criterion #4 but for a different engine. [needs-measurement]

3. **Quality of Spanish-accented English voice clone** on the builder's actual voice. Every available community report is on non-accented English or Chinese. **Subjective listening test required** — no published WER on accented English cloning. [needs-measurement]

4. **Does `stream_generate_voice_clone` yield sub-100-ms chunks on 3060?** The API exists; chunk rate on a 3060 is unpublished. Would determine whether Qwen3-TTS can match or beat XTTS's native streaming on this hardware. [needs-measurement]

5. **Does FlashAttention 2 install cleanly on Python 3.12 + CUDA 12.1 + Windows 11 for RTX 3060 (Ampere sm_86)?** HN thread suggests problems; exact repro is unclear. A 10-minute install check would confirm. [needs-verification]

6. **Is the `coqui-tts[server]` Pipecat integration path functionally broader than a custom Qwen3-TTS `TTSService`?** Pipecat ships `XTTSTTSService` out of the box and has no Qwen3-TTS service — a custom service is ~50–150 lines but needs testing with Pipecat's frame-cancellation semantics for barge-in. Untested. [untested-claim]

7. **What happens on SillyTavern character persona prompts that include emoji, code, or math?** Qwen3-TTS's text handling at character-card boundaries is not tested; community examples use English prose. [untested-claim]

8. **Does voicebox's cache-dir-unification patch matter for RayMe?** Voicebox explicitly forces `HF_HUB_CACHE` to avoid Windows dual-cache issues. Whether RayMe's own setup hits this is unclear — depends on whether we co-install `transformers` separately. Worth noting for Phase 2 backend setup. [needs-verification]

---

## 11. Sources

### Primary — official Qwen3-TTS (HIGH confidence)

- [QwenLM/Qwen3-TTS GitHub repository](https://github.com/QwenLM/Qwen3-TTS) — official source, README, LICENSE (Apache-2.0)
- [QwenLM/Qwen3-TTS README (raw)](https://raw.githubusercontent.com/QwenLM/Qwen3-TTS/main/README.md) — model IDs, code samples, architecture description, release notes
- [Qwen3-TTS LICENSE](https://github.com/QwenLM/Qwen3-TTS/blob/main/LICENSE) — confirmed Apache-2.0
- [Qwen/Qwen3-TTS-12Hz-1.7B-Base on HuggingFace](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base) — model card, reference-audio usage
- [Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice on HuggingFace](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice) — preset-speaker variant
- [qwen-tts on PyPI](https://pypi.org/project/qwen-tts/) — 0.1.1, Apache-2.0, Python 3.9–3.13
- [Qwen3-TTS HuggingFace Space Demo](https://huggingface.co/spaces/Qwen/Qwen3-TTS)
- [QwenLM/Qwen3-TTS Discussion #255 — 48 kHz decoder](https://github.com/QwenLM/Qwen3-TTS/discussions/255) — sample rate clarification

### Primary — voicebox reference implementation (HIGH confidence)

- [jamiepine/voicebox GitHub repository](https://github.com/jamiepine/voicebox) — MIT, TypeScript + Python, active 2026-04-17
- [voicebox backend/backends/pytorch_backend.py](https://github.com/jamiepine/voicebox/blob/main/backend/backends/pytorch_backend.py) — Qwen3-TTS integration pattern
- [voicebox backend/backends/qwen_custom_voice_backend.py](https://github.com/jamiepine/voicebox/blob/main/backend/backends/qwen_custom_voice_backend.py) — CustomVoice variant
- [voicebox backend/requirements.txt](https://github.com/jamiepine/voicebox/blob/main/backend/requirements.txt) — `qwen-tts>=0.0.5`, transformers range, torch
- [voicebox README](https://github.com/jamiepine/voicebox/blob/main/README.md) — platform + engine list + architecture

### Secondary — performance / VRAM benchmarks (MEDIUM confidence — external sites)

- [qwen3-tts.app performance benchmarks article](https://qwen3-tts.app/blog/qwen3-tts-performance-benchmarks-hardware-guide-2026) — RTX 3060 Ti / 3090 / 4090 VRAM + RTF numbers
- [DeepWiki mu-zi-lee/qwen3-tts-skill memory requirements](https://deepwiki.com/mu-zi-lee/qwen3-tts-skill/8.2-memory-and-hardware-requirements) — dtype-by-size VRAM breakdown
- [andimarafioti/faster-qwen3-tts GitHub](https://github.com/andimarafioti/faster-qwen3-tts) — CUDA graph capture, RTX 4060/4090/H100 benchmarks, 5–10× speedup
- [rekuenkdr/Qwen3-TTS-streaming GitHub](https://github.com/rekuenkdr/Qwen3-TTS-streaming) — two-phase streaming wrapper, RTX 3090 RTF 0.87
- [groxaxo/Qwen3-TTS-Openai-Fastapi GitHub](https://github.com/groxaxo/Qwen3-TTS-Openai-Fastapi) — FastAPI wrapper that uses `stream_generate_voice_clone`
- [Hacker News: Qwen3-TTS family is now open sourced](https://news.ycombinator.com/item?id=46719229) — community reports, GTX 1080 RTF 2.11, FA2 Windows issues, tokenizer warning, Chinese-accent drift
- [Qwen3-TTS CustomVoice discussion #18 — generation speed](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice/discussions/18) — GPU utilization reports

### Secondary — voice-cloning quality and quirks (MEDIUM)

- [ocdevel: Qwen3-TTS Voice Cloning Guide 2026](https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning) — reference length optimum 10–15 s, infinite-loop failure, emotional outbursts in long gen, 0.6B emotion gap, phoneme bleed, accent drift
- [ComfyUI Wiki Alibaba Qwen3-TTS release](https://comfyui-wiki.com/en/news/2026-01-22-alibaba-qwen3-tts-release) — release summary
- [StableLearn Qwen3-TTS announcement](https://stable-learn.com/en/qwen3-tts-0115-opensource/) — feature summary
- [ComfyUI-Qwen-TTS integration](https://github.com/flybirdxx/ComfyUI-Qwen-TTS) — community ComfyUI node

### Context — already in RayMe research (HIGH)

- [RayMe STACK.md](D:/Pedro/Repos/Program/RayMe/.planning/research/STACK.md) — F5 + XTTS v2 baseline, VRAM budget math
- [RayMe PITFALLS.md](D:/Pedro/Repos/Program/RayMe/.planning/research/PITFALLS.md) — Pitfalls #4, #7, #9, #12, #13 directly relevant
- [RayMe REQUIREMENTS.md](D:/Pedro/Repos/Program/RayMe/.planning/REQUIREMENTS.md) — REQ-02, REQ-15, REQ-20, REQ-21, REQ-22, REQ-23, REQ-A3
- [RayMe ROADMAP.md](D:/Pedro/Repos/Program/RayMe/.planning/ROADMAP.md) — Phases 0, 2, 5; Resolved Tensions #3, #7, #12, #13

---

*Qwen3-TTS assessment for RayMe v1 — researched 2026-04-17.*
