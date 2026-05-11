---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
reviewed: 2026-05-11T11:58:14Z
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
  warning: 2
  info: 0
  total: 2
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-05-11T11:58:14Z
**Depth:** standard
**Files Reviewed:** 27
**Status:** issues_found

## Summary

Final standard-depth re-review covered the VoxCPM2 adapter, engine registry metadata, transient TTS APIs, call-session forwarding, Voice Lab UI, Web UI voice/call facades, deployment script changes, and associated tests. The main VoxCPM2 control path is coherent and the earlier call/preview forwarding fixes appear covered by tests. Two remaining validation gaps allow oversized base64 reference audio to enter the AI backend before any size limit is enforced.

## Warnings

### WR-01: `/tts/synthesize` accepts unbounded reference audio

**File:** `ai-backend/app/api/tts.py:24`
**Issue:** `reference_audio_b64` has a minimum length but no maximum length, and `_decode_reference_audio()` decodes it into memory. A caller can send a very large JSON body to the AI backend and force memory/disk work before the request is rejected by any audio-size policy. The Web UI upload path caps samples at 25 MiB, but this direct transient synthesis endpoint does not.
**Fix:**
```python
MAX_REFERENCE_AUDIO_BYTES = 25 * 1024 * 1024
MAX_REFERENCE_AUDIO_B64_LENGTH = 36 * 1024 * 1024

reference_audio_b64: str = Field(
    min_length=1,
    max_length=MAX_REFERENCE_AUDIO_B64_LENGTH,
    validation_alias=AliasChoices("reference_audio_b64", "reference_audio_base64"),
)

def _decode_reference_audio(reference_audio_b64: str) -> bytes:
    ...
    if len(decoded) > MAX_REFERENCE_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "invalid_tts_request",
                "message": "reference audio is too large",
            },
        )
```

### WR-02: WebRTC speak also accepts unbounded reference audio

**File:** `ai-backend/app/api/webrtc.py:77`
**Issue:** `SpeakRequest.reference_audio_b64` is optional but unbounded. Call speech normally uses saved voice samples, but this route also accepts inline reference audio and passes it into synthesis, where it is decoded for generic adapters. A malformed or hostile caller can submit an oversized payload and bypass the Web UI voice-sample cap.
**Fix:** Reuse the same limit constants as `/tts/synthesize` and bound the Pydantic field.
```python
reference_audio_b64: str | None = Field(
    default=None,
    max_length=MAX_REFERENCE_AUDIO_B64_LENGTH,
    validation_alias=AliasChoices("reference_audio_b64", "reference_audio_base64"),
)
```
If synthesis code decodes this field outside the route model, also reject decoded payloads above `MAX_REFERENCE_AUDIO_BYTES` before constructing `TtsSynthesisInput`.

---

_Reviewed: 2026-05-11T11:58:14Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
