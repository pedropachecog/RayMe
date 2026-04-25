# RayMe License Notices

This file tracks third-party package, code, model, and weights notices that
affect RayMe runtime choices. It is not legal advice and does not replace the
upstream license text. Before enabling an engine for distribution or commercial
use, verify the current upstream license for the exact package and model
artifact being shipped.

## TTS Engine Notices

License metadata is separate from RayMe's default engine selection. An engine
can be selectable or resident for runtime reasons without being commercially
permissive, and a permissive license does not make an engine the default.

| Engine | Code/package license | Model/weights license | Commercial-use caveat | Quality/runtime caveat |
| --- | --- | --- | --- | --- |
| F5-TTS | MIT for the package/code path used by the F5 runtime. | CC-BY-NC for the pretrained F5 model weights used by RayMe. | Treat pretrained F5-TTS weights as non-commercial unless replacement weights with a different license are explicitly documented. F5 being the RayMe default is a quality/runtime decision, not a commercial-use clearance. | Phase 0 selected F5 as the default TTS path: TTFA 517.3 ms, RTF 0.388, and 30-minute soak peak 1990.2 MB on the RTX 3060. Long-form stretch/duration still needs tuning before call-feel finalization. |
| XTTS v2 | MPL-2.0 for the Coqui/idiap code package path used by RayMe. | CPML for the XTTS v2 model weights. | Do not present XTTS v2 model weights as commercially permissive. Review CPML terms before any paid, hosted, or redistributable use. | Native streaming is available, but long text must respect the XTTS `inference_stream` 400-token cap and use RayMe's shared chunking path. Phase 0 measured WSL short TTFA 489.9 ms and 30-minute soak peak 2104.0 MB. |
| Qwen3-TTS 0.6B-Base | Apache-2.0 for the Qwen3-TTS package/code path. | Apache-2.0 for the 0.6B-Base model weights. | Commercial-use posture is permissive under Apache-2.0, subject to upstream notices and any generated-voice policy outside this repository. This does not change default selection. | Qwen3-TTS remains opt-in and non-default because Phase 0 failed its acceptance gate on latency, RTF, and accent quality. Only the measured 0.6B-Base path is in scope; Qwen 1.7B remains ineligible without FlashAttention 2/runtime evidence. |
| LuxTTS | Apache-2.0 based on the currently referenced public LuxTTS code/model pages; verify before release. | Apache-2.0 based on the currently referenced public LuxTTS weights; verify before release. | Treat as permissive only after the exact artifact is pinned and rechecked. Do not infer license from third-party mirrors. | Phase 0 scenario matrix showed very fast optimized rows, but current user-sample quality failures are recorded in project state. Do not promote by latency alone; retest references first. |
| Chatterbox Turbo | MIT based on the currently referenced public Chatterbox Turbo package/model pages; verify before release. | MIT based on the currently referenced public Chatterbox Turbo weights; verify before release. | Treat as permissive only after the exact artifact is pinned and rechecked. | Experimental. Baseline long-form output is documented as unusable; optimized long-form normal and seed 1337 samples were acceptable in listening checks. |
| TADA 1B | Llama 3.2 license family based on the currently referenced public TADA 1B model page; verify before release. | Llama 3.2 license family based on the currently referenced public TADA 1B weights; verify before release. | Do not treat as Apache/MIT. Review the Llama 3.2 license terms before any redistribution or commercial use. | Highest-VRAM measured roster path, around 7.5 GB peak in Phase 0 scenario evidence. Keep one-hot TTS residency mandatory; Windows optimized long-form was acceptable, while WSL remains caution. |

## Runtime Evidence Links

- Phase 0 summary: `.planning/phases/00-measurement-gate/results/phase0_summary.json`
- Warm-model scenario matrix: `.planning/phases/00-measurement-gate/results/tts_runtime_matrix_v2.json`
- Human-readable decisions: `.planning/phases/00-measurement-gate/KEY_DECISIONS.md`
- AI backend registry metadata: `ai-backend/app/models/tts_registry.py`

## Default Selection Notice

RayMe's Phase 2 default engine is F5-TTS because Phase 0 selected it for local
latency, VRAM fit, and current quality tradeoffs on the target RTX 3060. That
default does not grant commercial rights to F5 pretrained model weights. The
full measured roster remains available for evidence-gated runtime work:
F5-TTS, XTTS v2, Qwen3-TTS 0.6B-Base, LuxTTS, Chatterbox Turbo, and TADA 1B.
