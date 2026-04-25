# Learnings

This file records repeated execution mistakes and the durable guardrails added
after them. Read it with `.planning/OPERATING-NOTES.md` before handoff,
deployment, Android acceptance, or GPU-runtime work.

## 2026-04-25: User Was Asked To Validate Under-Tested Voice Lab Paths

### What Went Wrong

- The Voice Lab flow was handed off before the full upload -> transcribe ->
  manual edit -> preview -> play/save path had been proven end to end in the
  live browser.
- Playwright work existed too late and its evidence was not initially saved as
  a phase artifact.
- F5 preview appeared to work at the API layer but browser playback was blocked
  by CSP until a saved Playwright run exposed it.

### False Assumptions

- HTTP/API success was treated as enough for UI readiness.
- Manual user testing was treated too much like first-line QA instead of
  product-owner acceptance after agent verification.
- A transient browser script or terminal output was implicitly treated as
  evidence even when it was not persisted.

### Guards Added

- Saved Playwright test:
  `web-ui/client/tests/e2e/live-voice-lab-manual-preview.spec.ts`
- Saved results under:
  `.planning/phases/02-ai-backend-skeleton-voice-lab/playwright-results/`
- Operating rule: every Playwright/browser acceptance check must be persisted as
  a test file or saved phase artifact before handoff.

## 2026-04-25: OMEN Deployment Was Too Ad Hoc

### What Went Wrong

- Backend deployment used repeated manual SSH/build/restart sequences, which
  made stale runtime state and auth confusion more likely.
- SSH alias behavior had already been debugged, but command choices still risked
  bypassing the configured alias.

### False Assumptions

- Retyping the deployment sequence was acceptable because each individual step
  was familiar.
- Checking a health endpoint after restart was enough to prove the right commit
  and runtime were deployed.

### Guards Added

- `scripts/deploy-omen.sh` is the only normal OMEN deploy path.
- The deploy script verifies the expected Git commit, kills stale port owners,
  starts scheduled tasks, checks listeners, and verifies health.
- Operating rule: use exactly `ssh rayme-pmpg`; do not type
  `ssh rayme-pmpg@192.168.1.199`.

## 2026-04-25: CPU Runtime Was Accepted In A GPU-Mandatory Product

### What Went Wrong

- A CPU fallback was added for faster-whisper during STT troubleshooting.
- F5-TTS was later found running with CPU-only PyTorch/torchaudio in the OMEN AI
  venv, producing slow preview synthesis.
- The project requirement was real-time phone-call behavior, but the runtime
  check did not enforce GPU execution.

### False Assumptions

- A working model response was treated as progress even if the runtime device
  was wrong.
- CUDA availability was checked for one component but not every AI model path.
- Documentation saying "GPU required" was treated as enough without executable
  guards.

### Guards Added

- `ai-backend/app/models/gpu_runtime.py` fails fast for CPU device config,
  CPU-only PyTorch, missing `torch.version.cuda`, or unavailable CUDA.
- `WhisperSttAdapter` rejects non-CUDA or non-float16 compute config before
  loading a real faster-whisper model.
- `F5TtsAdapter` rejects CPU-only PyTorch before loading production F5 runtime.
- `scripts/deploy-omen.sh` refuses deployment when OMEN has CPU-only Torch or
  `torch.cuda.is_available()` is false.
- Tests in `ai-backend/tests/test_gpu_runtime.py` lock the guard behavior.

## Standing Handoff Rule

Before telling the user a workflow is ready, report the exact evidence:

- local test command and result,
- browser/Playwright test file and saved result path when UI is involved,
- live OMEN deploy commit and target when LAN/GPU behavior is involved,
- cold/warm timings for model-runtime paths,
- any remaining unverified path called out as not ready.

If that evidence does not exist yet, keep working instead of asking the user to
find the next failure.
