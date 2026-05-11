---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
reviewed: 2026-05-11T11:48:10Z
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

**Reviewed:** 2026-05-11T11:48:10Z
**Depth:** standard
**Files Reviewed:** 27
**Status:** issues_found

## Summary

Reviewed the scoped VoxCPM2 backend adapter, TTS registry/API wiring, WebRTC call path, Voice Lab UI, web-server voice/call facades, deployment script, and related tests. The fixes closed several API-shape and sanitization paths, but three behavioral risks remain: Voice Lab still ignores per-engine transcript metadata, fallback engine normalization can expose VoxCPM2 as selectable when the backend did not report it, and VoxCPM2 CUDA fallback detection can pass when device probing returns no evidence.

## Warnings

### WR-01: Voice Lab Requires Transcripts For Engines That Declare They Do Not Need One

**File:** `web-ui/client/src/routes/voice-lab/+page.svelte:149`
**Issue:** `transcriptRequired` is hard-coded to `selectedEngine !== 'voxcpm2'`. That contradicts the engine metadata shown in the picker, where XTTS v2 and other engines can advertise `requires_transcript: false`. When those engines are available, preview and save remain disabled until the user enters a transcript even though the selected engine does not require one.
**Fix:**
```svelte
$: selectedEngineMetadata = engines.find((engine) => engine.id === selectedEngine);
$: transcriptRequired = selectedEngineMetadata?.requires_transcript === true;
$: hasRequiredTranscript = !transcriptRequired || Boolean(transcript.trim());
```

### WR-02: Missing Backend Engine Metadata Falls Back To Selectable VoxCPM2

**File:** `web-ui/client/src/routes/voice-lab/+page.svelte:212`
**Issue:** `normalizeEngines()` seeds the map with `DEFAULT_TTS_ENGINES` and returns every default entry even when `settings.ai_backend_status.available_engines` is a non-empty backend list that omits an engine. Because the default VoxCPM2 entry is `available: true` at lines 96-102, an older or degraded backend response that does not include VoxCPM2 still renders VoxCPM2 as selectable, leading users into guaranteed preview/save failures.
**Fix:**
```ts
const returnedIds = new Set<string>();
// add each backend-reported id to returnedIds while normalizing

return DEFAULT_TTS_ENGINES.map((engine) => {
  const normalized = byId.get(engine.id) ?? engine;
  if (!returnedIds.has(engine.id)) {
    return {
      ...normalized,
      availability: {
        available: false,
        state: 'unavailable',
        unavailable_reason: 'Engine was not reported by the AI backend.'
      }
    };
  }
  return normalized;
});
```

### WR-03: VoxCPM2 CUDA Guard Accepts Unknown Device Evidence

**File:** `ai-backend/app/models/tts_voxcpm2.py:96`
**Issue:** `_assert_runtime_uses_cuda()` only raises when it finds device types and none are CUDA. If runtime objects expose no parameters, or parameter probing fails, `device_types` remains empty and the adapter accepts the runtime despite having no proof that VoxCPM2 loaded on CUDA. The deployment smoke script has the same shape at `scripts/deploy-omen.sh:179`, where an empty `device_types` set also passes. That weakens the Phase 7 CPU-fallback gate.
**Fix:**
```python
if "cuda" not in device_types:
    raise RuntimeError("VoxCPM2 runtime did not expose CUDA-loaded parameters")
```

Apply the same fail-closed check in the deployment probe after collecting `device_types`, or add a documented runtime-specific CUDA probe that cannot pass on missing evidence.

---

_Reviewed: 2026-05-11T11:48:10Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
