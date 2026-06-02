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

## 2026-06-02: Invisible RayMe Launcher Was Not Debuggable UX

### What Went Wrong

- The OMEN Desktop launcher was changed from a suspicious-looking startup flow
  into a quiet background flow.
- That removed blank command prompts and browser auto-open, but it also removed
  visible running state, visible logs, and an obvious stop mechanism.
- The user could not tell whether RayMe was running or inspect startup failures.

### False Assumptions

- Quiet/minimized background execution was treated as better UX for a local
  development app.
- Log files and scheduled-task state were treated as sufficient debugging
  affordances even though the user needed console-visible output.
- Technical neatness was prioritized over the user's actual control loop:
  start it, watch logs, use it, close the window to stop it.

### Guards Added

- `scripts/start-rayme-omen.ps1` is now a foreground RayMe console launcher.
- The Desktop shortcut created by `scripts/deploy-omen.sh` opens that console
  normally, does not auto-open the browser, and does not use `-Quiet`.
- The console starts AI and Web as child processes, prefixes logs as `[AI]` and
  `[WEB]`, prints the URL, and stops children when the console closes.
- Local/dev RayMe launchers must show visible running state, logs, and a visible
  stop mechanism unless the user explicitly asks for daemon/background mode.

## 2026-05-15: VoxCPM2 First-Audio Evidence Hid Choppy Live Playback, Then Full-Stream Buffering Violated The Phone-Call Invariant

### What Went Wrong

- Phase 8 evidence proved VoxCPM2 produced earlier first audio than F5, but it
  did not prove that streamed chunks arrived fast enough for continuous
  realtime WebRTC playout.
- In the live call, VoxCPM2 generated repeated ~160 ms chunks roughly every
  ~280 ms, so the outbound track drained each chunk and inserted silence before
  the next chunk arrived.
- Voice Lab preview sounded fine because it used whole-result synthesis, while
  the call path played slow streamed chunks immediately.
- The first attempted fix, commit `1806eb0`, buffered slow streams until
  completion before playback. That avoided underrun but turned RayMe's live call
  into generate-then-play and left the UI stuck in `Rehearsing` for long
  messages.

### False Assumptions

- Lower first-audio latency was treated as sufficient for live-call playback
  quality.
- A streaming API was assumed to be realtime-capable without checking
  inter-chunk gap versus playable chunk duration.
- Browser RMS diagnostics were available, but there was no regression that
  rejected backend stream underflow before user testing.
- Smoothness was treated as allowed to override live phone-call behavior.
- Passing tests for "buffer until complete" were treated as valid even though
  they encoded the wrong product invariant.

### Guards Added

- `CallSession` uses bounded live startup buffering only. It must not wait for
  full TTS stream completion before first playback in a live call.
- Regression added:
  `ai-backend/tests/test_call_session.py::test_voxcpm2_slow_stream_starts_playback_before_stream_completion`
- WebRTC playback metrics tests reject the old `buffered_until_complete` live
  call metric and preserve the separation between immediate first-audio metrics
  and final playback metrics.
- Repository invariant added:
  `.planning/LIVE-CALL-INVARIANTS.md`
- Startup guard added:
  `scripts/operational-check.sh start` now fails if the live-call/GSD invariant
  documents are missing or weakened.
- Operating rule: non-trivial product regressions, incident repairs, and
  deployments use GSD artifacts before implementation. No unplanned quick fixes
  for call, AI runtime, deployment, or user-visible workflows.

## 2026-05-13: Post-End Call Suppression Was Mistaken For A Call-Liveness Fix

### What Went Wrong

- The Android call failure after `2d00461` was that a recovered long user turn
  produced a full transcript and AI response only after the live call had
  already failed.
- The deployed `6faf893` patch cancelled Web UI generation on `/end` and
  rejected AI backend `/speak` after an ended/failed session.
- That suppressed the misleading post-end response artifact, but it did not
  address the user's required behavior: the call should not fail before RayMe
  shows and plays the generated response.
- The patch was reverted by `3800391` and deployed through
  `scripts/deploy-omen.sh`.

### False Assumptions

- "Generated after `call_end`" was treated as the defect instead of evidence of
  an earlier premature terminal-cleanup defect.
- Tests that prove cancellation/rejection after `/end` were treated as
  sufficient even though they could never prove the call stays alive.
- A cleanup consistency fix was presented as ready for product-owner acceptance
  without explicitly checking whether it preserved the original success path.

### Guards Added

- Forensic report:
  `.planning/forensics/report-20260513-163852.md`
- Operating rule: before deploying a user-visible debug fix, write the
  user-goal preservation sentence and reject any patch that only cancels,
  rejects, hides, drops, or suppresses work after the failure.
- Test rule: the first RED regression must assert the earliest wrong state
  transition or control-flow edge. For this call issue, that means proving
  terminal cleanup does not post `/end` or enter failed UI while a recovered
  `user_final` turn stream is active.
- Negative cleanup tests such as "do not generate after end" can be secondary
  guardrails only; they cannot satisfy acceptance for "the call should not
  end."

## 2026-05-01: Post-Snapshot Reconnect Patch Stack Regressed Phone Calls

### What Went Wrong

- After selected snapshot `6607214`, the post-snapshot runtime fixes
  `6f63de0` and `a0d5d17` tried to patch reconnect final markers, held-frame
  release, data-channel replay, and hangup-time reconnect backfill.
- Those changes passed unit tests and mocked Playwright reconnect tests, but
  real phone-call verification still froze or dropped user turns longer than
  roughly 5 to 10 seconds.
- The fixes were too incremental over an unstable reconnect lifecycle. They
  moved turn finalization and event delivery into reconnect cleanup paths
  without proving the real phone/WebRTC transport was stable.

### False Assumptions

- Isolated reconnect unit tests were treated as enough confidence for live call
  behavior.
- Mocked browser reconnect ordering was treated as equivalent to Android/phone
  WebRTC behavior on OMEN.
- A patch over final markers and data-channel replay was treated as safer than
  returning to the last user-selected recovery snapshot.

### Guards Added

- `.planning/debug/phone-calls-post-snapshot-audit.md` records the post-
  `6607214` commit ledger, hypotheses, failed fixes, and explicit do-not-retry
  guard.
- Do not re-apply the exact `6f63de0` plus `a0d5d17` fix combination as a small
  patch stack. Reconnect architecture can only be revisited under a new plan
  with live OMEN/phone verification evidence.
- Rollbacks for this incident restore only call runtime files. Keep `AGENTS.md`
  and the debug-agent sequencing rules.

## 2026-04-25: Phase 3 Call Startup Did Not Request Microphone Or Create Backend Session

### What Went Wrong

- The call UI entered the active call surface without calling
  `navigator.mediaDevices.getUserMedia`, so Chrome did not ask for microphone
  permission and no real mic track was captured.
- The browser also skipped the `/api/calls/{call_id}/offer` negotiation step,
  so the Web UI had a durable call row but the AI backend had no matching
  `/webrtc/sessions/{session_id}` entry.
- Mute and End Call then proxied to the AI backend with a non-existent session
  and returned `404`, which the UI surfaced as a generic failed call.

### False Assumptions

- Passing mocked browser call specs was treated as enough proof of call startup,
  even though they did not verify a real mic permission request or backend
  session negotiation.
- A Web UI call row was treated as equivalent to an AI backend live call
  session.

### Guards Added

- Call startup now requests microphone access before creating the call.
- The browser creates a WebRTC offer with the mic track and posts it through
  `/api/calls/{call_id}/offer` before enabling call controls.
- Focused Playwright call specs now mock browser media deliberately and verify
  the same-origin offer route used by production call startup.

## 2026-04-25: Interactive GSD Discussion Was Replaced By Inferred Defaults

### What Went Wrong

- `$gsd-next` routed into `$gsd-discuss-phase 3`, but the session did not ask
  the user any Phase 3 discussion questions.
- The agent treated unavailable structured prompt UI as permission to infer
  defaults and wrote canonical Phase 3 context from those defaults.
- This violated an already-recorded Phase 1 decision: `workflow.text_mode: true`
  means use plain numbered prompts and wait; it does not mean skip discussion.

### False Assumptions

- "Execute mode fallback" was interpreted as "pick defaults" even for
  workflows whose purpose is to gather user decisions.
- Prior project context was treated as a substitute for explicit user answers.
- Creating a context file was treated as completing the discussion phase, even
  though no discussion happened.

### Guards Added

- The invalid Phase 3 context was moved out of canonical `03-CONTEXT.md` to
  `03-CONTEXT-DRAFT-NOT-USER-DISCUSSED.md`, so planning cannot silently proceed
  from it.
- Operating rule: interactive GSD workflows must present plain-text numbered
  choices and stop for the user when structured prompts are unavailable.
- Operating rule: discussion workflows run one question at a time when the user
  wants sequential discussion, with the recommended option and a brief "why"
  shown before the answer is requested.
- Operating rule: fresh discussions must not derail into "Skip", "Use existing
  context", or "View it" prompts unless the user explicitly asks for a bypass.
- Operating rule: canonical decision/context/spec/approval artifacts require
  actual user answers or an explicitly requested `--auto`/`--chain` mode.
- Attempted local GSD skill adapter patch was blocked because installed skill
  files under `/home/agent/.codex/skills/gsd-*` are root-owned in this
  environment. The project-level guard is therefore enforced through
  `.planning/OPERATING-NOTES.md`, `.planning/SESSION-START.md`,
  `scripts/operational-check.sh start`, and the active checkpoint until the
  upstream/root-owned adapter text can be updated.

## 2026-04-25: Context Resets Need Explicit Rehydration

### What Went Wrong

- Corrective rules existed in planning docs, but future sessions could still
  start from the active task and miss the operating constraints.
- GSD context clearing is part of the workflow, so "remember this next time" is
  insufficient unless the next session has a startup gate.

### False Assumptions

- Updating one durable note was enough to change behavior across context resets.
- A future agent would naturally inspect the right operational files before
  handoff.

### Guards Added

- `.planning/SESSION-START.md` defines the mandatory rehydration order,
  startup checks, handoff gate, and readiness reporting format.
- `scripts/operational-check.sh start` verifies that core operating constraints
  are present before work begins.
- `scripts/operational-check.sh handoff` verifies phase, commit, tests, and
  evidence paths before a workflow is called ready.
