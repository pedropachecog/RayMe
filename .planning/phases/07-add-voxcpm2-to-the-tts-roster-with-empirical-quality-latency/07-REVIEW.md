---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
reviewed: 2026-05-11T11:35:56Z
depth: standard
files_reviewed: 27
files_reviewed_list:
  - ai-backend/app/api/tts.py
  - ai-backend/app/api/webrtc.py
  - ai-backend/app/call/session.py
  - ai-backend/app/main.py
  - ai-backend/app/models/engine_metadata.py
  - ai-backend/app/models/tts_registry.py
  - ai-backend/app/models/tts_voxcpm2.py
  - ai-backend/pyproject.toml
  - ai-backend/tests/test_call_session.py
  - ai-backend/tests/test_model_manager.py
  - ai-backend/tests/test_tts_registry.py
  - ai-backend/tests/test_tts_voxcpm2.py
  - ai-backend/tests/test_webrtc_signaling.py
  - scripts/deploy-omen.sh
  - web-ui/client/src/lib/api/types.ts
  - web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte
  - web-ui/client/src/lib/components/voice/VoiceAssignmentSelect.svelte
  - web-ui/client/src/lib/components/voice/VoxCpm2Controls.svelte
  - web-ui/client/src/routes/voice-lab/+page.svelte
  - web-ui/client/tests/e2e/voice-lab.spec.ts
  - web-ui/client/tests/unit/voice-lab.test.ts
  - web-ui/server/app/api/calls.py
  - web-ui/server/app/api/voices.py
  - web-ui/server/app/domain/call_service.py
  - web-ui/server/app/domain/voice_service.py
  - web-ui/server/tests/test_calls.py
  - web-ui/server/tests/test_voices.py
findings:
  critical: 0
  warning: 3
  info: 0
  total: 3
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-05-11T11:35:56Z
**Depth:** standard
**Files Reviewed:** 27
**Status:** issues_found

## Summary

Reviewed the VoxCPM2 adapter, TTS API routing, call-flow propagation, Voice Lab UI/server metadata handling, tests, and OMEN deployment changes. The integration is mostly bounded and sanitizes public failures, but the new VoxCPM2 adapter sends parameters that do not match the upstream runtime contract, and the transient TTS endpoint can mask invalid engine requests with an internal server error. `ai-backend/uv.lock` was excluded as a lock file per review-scope filtering.

## Warnings

### WR-01: VoxCPM2 Style Prompt Is Sent as an Unsupported Runtime Keyword

**File:** `ai-backend/app/models/tts_voxcpm2.py:127`
**Issue:** `_build_generate_kwargs` adds `style_prompt` directly to `runtime.generate(**generate_kwargs)`. The VoxCPM2 `generate()` API supports style/control instructions by prepending parenthesized control text to `text`; it does not expose a `style_prompt` keyword. Any non-empty style prompt from Voice Lab will therefore raise a runtime `TypeError` and make VoxCPM2 preview/call synthesis fail.
**Fix:**
```python
style_prompt = (request.voxcpm2_style_prompt or "").strip()
text = request.text
if style_prompt and request.voxcpm2_cloning_mode != "transcript_guided":
    text = f"({style_prompt}){text}"

kwargs: dict[str, Any] = {
    "text": text,
    "cfg_value": request.voxcpm2_cfg_value,
    "inference_timesteps": request.voxcpm2_inference_timesteps,
    "normalize": request.voxcpm2_normalize,
    "denoise": request.voxcpm2_denoise,
}
```
Also update `ai-backend/tests/test_tts_voxcpm2.py` so the fake runtime rejects unknown kwargs and asserts the style prompt is folded into `text`.

### WR-02: Transcript-Guided VoxCPM2 Mode Drops the Reference Cloning Input

**File:** `ai-backend/app/models/tts_voxcpm2.py:131`
**Issue:** Transcript-guided mode sends only `prompt_wav_path` and `prompt_text`. VoxCPM2's Hi-Fi cloning path combines those with `reference_wav_path` for the same clip, so the current implementation switches to continuation-style prompting instead of the intended high-fidelity voice cloning path. This can reduce cloning quality exactly in the mode users choose for better fidelity.
**Fix:**
```python
if request.voxcpm2_cloning_mode == "transcript_guided" and reference_transcript:
    kwargs["prompt_wav_path"] = str(reference_path)
    kwargs["prompt_text"] = reference_transcript
    kwargs["reference_wav_path"] = str(reference_path)
else:
    kwargs["reference_wav_path"] = str(reference_path)
    if request.voxcpm2_cloning_mode != "reference_only" and not reference_transcript:
        warning_codes.append("voxcpm2_reference_only_without_transcript")
```
Add a test assertion that transcript-guided synthesis includes both `prompt_wav_path` and `reference_wav_path`.

### WR-03: Invalid TTS Engine Requests Can Mask the Intended Public Error

**File:** `ai-backend/app/api/tts.py:74`
**Issue:** `synthesize()` catches any switch/synthesis failure and calls `_mark_engine_unavailable(manager, target_engine)`. With an unknown `engine_id`, `ModelManager.switch_tts_engine()` raises `ValueError`, then `_mark_engine_unavailable()` calls `ModelManager._mark_unavailable()` with that same unknown id, which raises `KeyError`. That secondary failure can turn a sanitized 502 response into an unhandled 500.
**Fix:**
```python
def _mark_engine_unavailable(manager: Any, engine_id: str) -> None:
    statuses = getattr(manager, "_statuses", {})
    if isinstance(statuses, dict) and engine_id not in statuses:
        return
    marker = getattr(manager, "_mark_unavailable", None)
    if callable(marker):
        try:
            marker(engine_id, "engine synthesis failed")
        except Exception:
            logger.warning(
                "[rayme-tts] mark_unavailable.failed engine=%s",
                engine_id,
                exc_info=True,
            )
```
Cover this with a `/tts/synthesize` test that posts an unknown `engine_id` and asserts the public error remains sanitized.

---

_Reviewed: 2026-05-11T11:35:56Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
