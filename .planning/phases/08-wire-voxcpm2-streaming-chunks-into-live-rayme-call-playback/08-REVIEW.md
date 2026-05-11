---
phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
reviewed: 2026-05-11T19:24:37Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - ai-backend/app/call/session.py
  - ai-backend/app/models/tts_registry.py
  - ai-backend/app/models/tts_voxcpm2.py
  - ai-backend/tests/test_call_session.py
  - ai-backend/tests/test_tts_voxcpm2.py
  - ai-backend/tests/test_webrtc_signaling.py
  - web-ui/server/tests/test_calls.py
findings:
  critical: 0
  warning: 1
  info: 0
  total: 1
status: issues_found
---

# Phase 08: Code Review Report

**Reviewed:** 2026-05-11T19:24:37Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Reviewed the VoxCPM2 streaming adapter contract, live call playback integration, route-level tests, and Web UI SSE/persistence tests. The streaming flow largely preserves the intended first-audio and final metric carrier separation, with one correctness issue in the final streaming metrics: `total_generation_ms` currently includes playback wait time.

## Warnings

### WR-01: Streaming final generation time includes playback wait

**File:** `ai-backend/app/call/session.py:977`
**Issue:** `_speak_streaming_speech()` computes `final_metrics()["total_generation_ms"]` from `elapsed_ms()`, but `final_metrics()` is called after `await self._wait_for_outbound_audio_playback(playback_seconds)` at line 1089. In real calls, `_wait_for_outbound_audio_playback()` waits for queued audio and adds the remote playout hold, so the streamed final `total_generation_ms` is inflated by playback time. The whole-WAV path records `total_generation_ms` before queue/playback, so streamed and non-streamed metrics are not comparable and Phase 8 evidence can misread playback latency as model generation latency.
**Fix:** Capture stream generation completion immediately after the producer finishes and before waiting for playback, then pass that fixed value into final metrics.

```python
generation_complete_ms: float | None = None

def final_metrics(total_generation_ms: float) -> dict[str, Any]:
    return {
        "streaming_used": True,
        "fallback_used": False,
        "whole_wav_fallback_used": False,
        "chunk_count": chunk_count,
        "total_generation_ms": round(total_generation_ms, 1),
        "total_playback_ms": round(playback_seconds * 1000, 1),
        "inter_chunk_gaps_ms": list(inter_chunk_gaps_ms),
    }

# after producer_task completes and before playback wait:
generation_complete_ms = elapsed_ms()
if generated_at_values:
    generation_complete_ms = max(generation_complete_ms, generated_at_values[-1])

await self._wait_for_outbound_audio_playback(playback_seconds)
playback_final = final_metrics(generation_complete_ms)
```

Add a regression test where `wait_until_idle()` or the playout hold advances time, and assert streamed `tts_playback_final.total_generation_ms` remains tied to the last chunk generation time rather than the playback wait.

---

_Reviewed: 2026-05-11T19:24:37Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
