---
status: resolved
created: 2026-07-31T23:10:38Z
updated: 2026-07-31T23:25:48Z
trigger: "Phase 09 Plan 14 exact-commit OMEN core evidence stopped after the real CUDA tracer passed because the release runner could not measure Qwen GPU process memory."
---

# Debug Session: Qwen GPU Memory Measurement

## Current Focus

user_goal_preservation: "RayMe must remain honestly within the RTX 3060 VRAM release budget while running Qwen3-TTS 1.7B, and the final evidence must use a supported measured value rather than a guessed or waived number."
hypothesis: "Confirmed: OMEN runs Windows WDDM, whose compute-app rows report [N/A] for per-process used memory; a truthful release measurement must originate from torch.cuda.memory_reserved() inside the isolated Qwen worker and remain independently bounded from system GPU usage."
test: "Commit the worker-origin allocator telemetry and run the canonical exact-commit OMEN deployment/evidence flow, requiring a positive <= 5,888 MiB worker value and fresh per-turn values through the 50-turn soak."
expecting: "The hardware tracer and core evidence pass without nvidia-smi compute-app parsing; qwen3-runtime and every soak row contain positive worker-origin Torch reserved memory while system GPU memory remains a separate health measurement."
next_action: "Resolved; continue the independently tracked core-evidence runner failure without weakening the allocator or system-memory gates."

## Symptoms

expected: "After the exact-commit CUDA hardware tracer passes, canonical deployment measures Qwen GPU memory, enforces <= 5,888 MiB, and begins the 20-scenario/50-turn/STT evidence run."
actual: "The tracer passed but the core runner stopped with Qwen GPU process memory could not be measured; no core bundle was produced or claimed."
errors:
  - "Qwen GPU process memory could not be measured"
timeline: "Observed on 2026-07-31 after canonical deployment of exact commit a1b203220e9cc5396dcc96774d2c08772c233080 to OMEN."
reproduction: "Run RAYME_OMEN_VERIFY_QWEN3=1 scripts/deploy-omen.sh on Windows/OMEN after Qwen becomes resident; the compute-app memory parsing block yields no positive numeric row."

## Evidence

- timestamp: 2026-07-31T23:10:38Z
  checked: "Plan 14 executor's exact-commit deploy and hardware tracer result."
  found: "All local gates passed; OMEN exact commit matched; real RTX 3060 CUDA/Torch/model/prompt/stream/cancel/recovery tracer gates passed; the release stopped only at GPU process memory measurement; no downstream evidence was claimed."
  implication: "Keep the limit mandatory and repair the Windows measurement source before rerunning canonical evidence."

- timestamp: 2026-07-31T23:13:00Z
  checked: "Read-only OMEN nvidia-smi queries for driver model, GPU memory, and compute-app pid/process/used_memory."
  found: "The RTX 3060 is in WDDM mode with 8,130 MiB system GPU memory used; 23 compute-app rows were returned and every per-process used_memory value was [N/A], with zero numeric rows."
  implication: "The failed parser is behaving correctly against unsupported WDDM data; substituting the total GPU value would falsely label system usage as Torch allocator reservation."

- timestamp: 2026-07-31T23:20:27Z
  checked: "Worker protocol/adapter/status/evidence repair and local regression suite."
  found: "Qwen loaded and chunk events now require positive bounded worker-origin torch_reserved_mib; the adapter exposes it through non-blocking status, the soak refreshes worker and system metrics independently each turn, and canonical deploy rejects missing or >5,888 MiB worker values. Focused tests passed 117/117, evidence tests passed 39/39, full backend passed 240/240, syntax and diff checks passed."
  implication: "The code path is locally fail-closed and preserves streaming; exact CUDA deployment is the remaining verification."

- timestamp: 2026-07-31T23:25:48Z
  checked: "Canonical scripts/deploy-omen.sh deployment of exact commit 03125f177e0659d34cfae397a6c61d31754d4753 with RAYME_OMEN_VERIFY_QWEN3=1."
  found: "The real CUDA hardware tracer passed and the release advanced beyond the worker allocator ceiling into core evidence. A read-only status check reported qwen3_1_7b resident with torch_reserved_mib=5764.0, below the mandatory 5,888 MiB ceiling. The subsequent core runner stopped on a separate missing-target contract before soak completion."
  implication: "The WDDM measurement failure is resolved with a truthful worker-origin value; long-soak growth remains a downstream evidence gate and is not claimed here."

## Eliminated

- hypothesis: "Use total nvidia-smi memory.used as the Torch reserved value."
  evidence: "That value is available under WDDM but includes every GPU consumer and already has its own system_gpu_mib evidence field, so relabeling it would be false evidence."

- hypothesis: "Treat missing WDDM per-process memory as zero or waive the 5,888 MiB gate."
  evidence: "The release contract requires a measured positive worker allocation and reserved-growth ceiling; a zero/default would self-certify an unmeasured runtime."

## Resolution

root_cause:
  "Windows WDDM returned [N/A] for every nvidia-smi compute-app used_memory row, while the canonical deployment required a numeric per-process value. The script could neither measure nor truthfully relabel system-wide GPU usage as Torch allocator reservation."
fix:
  "Measure torch.cuda.memory_reserved() inside the isolated Qwen CUDA worker, require positive bounded values in loaded/chunk IPC events, expose the latest value through non-blocking model/WebRTC status, collect fresh worker and system metrics independently per soak turn, and make canonical deployment enforce the unchanged 5,888 MiB worker ceiling."
verification:
  "117 focused backend tests passed; 39 Phase 09 evidence tests passed; all 240 backend tests passed; bash syntax, Python compile, and diff checks passed. Canonical exact-commit OMEN deployment reported a resident Qwen worker value of 5,764 MiB and advanced past the memory gate into core evidence."
files_changed:
  - "ai-backend/app/models/tts_qwen3_protocol.py"
  - "ai-backend/app/models/tts_qwen3_worker.py"
  - "ai-backend/app/models/tts_qwen3.py"
  - "ai-backend/app/models/model_manager.py"
  - "ai-backend/app/api/webrtc.py"
  - "ai-backend/tests/test_tts_qwen3.py"
  - "ai-backend/tests/test_model_manager.py"
  - "ai-backend/tests/test_webrtc_signaling.py"
  - ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py"
  - ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/test_phase09_evidence.py"
  - "scripts/deploy-omen.sh"
