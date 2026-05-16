---
status: fixing
created: 2026-05-16T13:00:00.000Z
updated: 2026-05-16T13:00:00.000Z
trigger: "User reports a terrible regression after the Phase 08.1 deploy: starting a repro got stuck in Rehearsing, then generation failed, the call failed, and afterward RayMe could not start another call."
---

# Debug Session: Live Call AI Backend Crash After Rehearsing

## Current Focus

user_goal_preservation: "RayMe must remain a live phone call: calls must start reliably, Rehearsing must not become a dead wait, TTS failures must not kill the AI backend process, and any fallback must preserve early playback, listening recovery, hangup, and barge-in."
hypothesis: "The deployed AI backend process crashed during VoxCPM2 model load or generation after a Rehearsing turn, leaving the web UI unable to start further calls because `/webrtc/status` became unreachable."
test: "Inspect OMEN logs and scheduled task status, reproduce or isolate backend process crash locally/deployed, add a regression that prevents call startup from depending on a crash-prone VoxCPM2 live path, run focused and full backend tests, deploy only through `scripts/deploy-omen.sh`, and verify deployed AI health plus call startup."
expecting: "The AI backend stays alive after VoxCPM2 TTS failure paths; subsequent calls can start; the live-call path never waits for whole TTS generation before first playback; failures are sanitized and recoverable."
next_action: "Gather crash evidence from OMEN backend logs, Windows task result, and relevant call/TTS code before choosing the smallest product-correct repair."

## Symptoms

expected: A VoxCPM2 live call should either speak with live playback or fail the turn recoverably while keeping the AI backend alive and allowing a new call.
actual: During a repro, the call got stuck in Rehearsing, generation failed, the call failed, and afterward RayMe could not start another call.
errors:
  - User-facing: generation failed, call failed, then "RayMe cannot start a call anymore."
  - OMEN scheduled task: `RayMePhase1AI` state `Ready`, not `Running`.
  - OMEN scheduled task result: `3221225477` (`0xC0000005`, native access violation).
timeline: Reported on 2026-05-16 after deploying commit `58544b2e17501d3dd460ed14ccaeff960c8ea99c`.
reproduction: Start a call with the newly created VoxCPM2 voice, reach Rehearsing, wait until generation fails/call fails, then attempt to start another call.

## Evidence

- timestamp: 2026-05-16T13:00:00Z
  checked: OMEN scheduled task state and backend/web log tails after user report.
  found: `RayMePhase1Web` is running, but `RayMePhase1AI` is `Ready`. `Get-ScheduledTaskInfo -TaskName RayMePhase1AI` reports `LastTaskResult: 3221225477`. Web logs show `/api/calls/start` returning 500 because the AI backend is unreachable. AI backend logs end while VoxCPM2 is loading model files (`Loading model from safetensors...`) after a call had entered `thinking`.
  implication: The call-start failure is downstream of the AI backend process being dead. The root fix must prevent a live-call VoxCPM2 failure from terminating the backend process and must restore deployed backend health.
- timestamp: 2026-05-16T13:40:00Z
  checked: `gsd-debugger` root-cause pass over the debug file, live-call invariants, and interrupted patch direction.
  found: Root cause confirmed: VoxCPM2 was loading/running in the AI backend process and hit native `0xC0000005`; Python exception handling cannot contain this, so the backend died. The debugger also confirmed `torch_cpu.dll` is not CPU fallback evidence because CUDA PyTorch uses that DLL and the deployed log says `Running on device: cuda, dtype: bfloat16`. Worker-process isolation is the correct direction, but the interrupted patch needs worker-crash regressions, bounded worker waits, explicit CUDA proof, and no whole-synthesis fallback.
  implication: Continue with a supervised CUDA-only worker process for VoxCPM2 production synthesis/streaming. A worker crash or hang must become sanitized `call_tts_failed`, not process death or endless Rehearsing.
- timestamp: 2026-05-16T14:20:00Z
  checked: Local implementation and backend verification for supervised VoxCPM2 worker isolation.
  found: Added `ai-backend/app/models/tts_voxcpm2_worker.py`; production `VoxCpm2TtsAdapter` now loads/synthesizes/streams through a child worker while preserving CUDA guard checks. Added tests for worker load, worker crash during stream, worker hang timeout, and no whole-synthesis fallback. Focused verification passed: `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q` -> 88 passed, 3 warnings. Full backend verification passed: `uv run --project ai-backend pytest ai-backend/tests -q` -> 139 passed, 3 warnings. `git diff --check` and `scripts/operational-check.sh start` passed.
  implication: Local repair is ready for commit/push/deploy. OMEN deployment and post-deploy health checks remain required before asking the user to retest.

## Eliminated

## Resolution

root_cause:
fix: "Production VoxCPM2 runtime is being moved into a supervised CUDA-only worker process so native worker crashes/hangs become sanitized recoverable TTS failures instead of killing the AI backend."
verification: "Local focused and full AI backend tests passed; OMEN deploy and live health verification pending."
files_changed: "ai-backend/app/models/tts_voxcpm2.py, ai-backend/app/models/tts_voxcpm2_worker.py, ai-backend/tests/test_tts_voxcpm2.py, .planning/phases/08.1-live-call-streaming-invariant-incident-repair-and-prevention/08.1-02-PLAN.md"
