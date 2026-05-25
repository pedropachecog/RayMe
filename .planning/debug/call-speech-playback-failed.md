---
status: deployed_verified
trigger: "playback is not working at all. it shows there was an error."
created: "2026-05-25T00:00:00Z"
updated: "2026-05-25T18:41:15Z"
---

# Debug Session: Live Call Speech Playback Failed

## User Goal Preservation

Live-call TTS must begin playing early available assistant audio after a generated response while preserving streaming playback, listening recovery, and interrupt/barge-in behavior; this incident must not be fixed by waiting for the full assistant response or full TTS stream to finish before first playback.

## Symptoms

- Expected behavior: after the user speaks during a live call and the assistant generates a short text response, the TTS audio should play in the call.
- Actual behavior: the call generates visible text but no audio plays.
- Error message: `Call [Notice] Speech playback failed.`
- Timeline: reported 2026-05-25.
- Reproduction: start a live call, speak a short message, observe the UI enter `Rehearsing`, then generated assistant text appears, then playback fails with the notice above.
- Surface: live call, after assistant response generation.

## Current Focus

- reasoning_checkpoint:
    hypothesis: "F5 synthesis mutates `os.environ['PYTHONHASHSEED']` to a random value larger than Python's valid child-interpreter range, and the VoxCPM2 worker inherits that poisoned environment, so the worker fails before it can emit the ready protocol line."
    confirming_evidence:
      - "OMEN standalone manager switch succeeds after F5 load-only but reproduces the deployed `_queue.Empty`/`VoxCPM2 worker timed out` failure after two F5 syntheses."
      - "A diagnostic post-F5 worker probe with stderr merged into captured output exits immediately with `Fatal Python error: config_init_hash_seed: PYTHONHASHSEED must be \"random\" or an integer in range [0; 4294967295]`."
      - "The installed F5 helper `seed_everything(seed)` writes `os.environ['PYTHONHASHSEED'] = str(seed)`, and F5 `infer(seed=None)` chooses `random.randint(0, sys.maxsize)`, which can exceed Python's valid hash-seed range."
    falsification_test: "After F5 synthesis mutates PYTHONHASHSEED to an invalid value, a regression should prove F5 restores the previous environment and VoxCPM2 worker spawning sanitizes any invalid inherited value; if the post-F5 OMEN worker still fails with the same fatal hash-seed error, the fix is incomplete."
    fix_rationale: "Restoring PYTHONHASHSEED after F5 inference removes the parent-process environment poisoning at the source; sanitizing the VoxCPM2 worker environment prevents any future invalid inherited value from killing the child interpreter before the ready protocol."
    blind_spots: "The final browser run covered the real OMEN browser/LLM/STT/VoxCPM2 path with two completed audio turns; residual health remains `degraded` only because non-implemented placeholder TTS engines are reported unavailable."
- next_action: complete handoff; runtime fix is deployed on OMEN at `76bacc7ea5069e1091607bf2ae9cba43dfe56096`.

## Evidence

- timestamp: 2026-05-25T16:48:28Z
  checked: Required context
  found: Loaded AGENTS.md, .planning/LIVE-CALL-INVARIANTS.md, gsd-debug instructions, debugger references, common bug patterns, and the active debug file.
  implication: Investigation and any fix must preserve live-call early playback, streaming TTS, listening recovery, and interrupt/barge-in behavior.
- timestamp: 2026-05-25T16:49:10Z
  checked: Project skill discovery and code search
  found: No `.codex/skills` or `.agents/skills` project skills were present. `rg` found `Speech playback failed` and `call_tts_failed` in `ai-backend/app/call/session.py`, `ai-backend/app/api/webrtc.py`, `web-ui/server/app/api/calls.py`, and related tests.
  implication: The visible notice is produced by an existing call TTS failure contract; investigation should trace upstream from generated text to TTS stream/playback handling.
- timestamp: 2026-05-25T16:51:05Z
  checked: Live-call failure flow
  found: `web-ui/server/app/api/calls.py` streams visible AI text, then calls `_speak_call`; `ai-backend/app/api/webrtc.py` returns HTTP 502 when `CallSession.speak_text()` emits `failed/call_tts_failed`; `CallSession.speak_text()` emits that failure if streaming TTS raises before successful playback.
  implication: The user-visible notice is a sanitized downstream symptom; root cause is likely inside backend TTS streaming or outbound audio enqueue before the `ai_audio_started` event.
- timestamp: 2026-05-25T16:53:12Z
  checked: VoxCPM2 streaming and outbound track implementation
  found: The live VoxCPM2 path uses `adapter.stream()` via a worker/subprocess path, buffers only bounded startup audio, enqueues chunks to `QueuedAudioOutputTrack`, and raises `VoxCPM2 streaming synthesis failed` if no chunks are produced or the worker emits an error.
  implication: A zero-chunk or worker-error stream would exactly surface as `Speech playback failed`; tests are needed to distinguish a runtime stream failure from a web proxy propagation bug.
- timestamp: 2026-05-25T16:54:35Z
  checked: Focused regression tests
  found: `uv run pytest tests/test_call_session.py -k "voxcpm2 or queued_audio_output_track"` passed 10 tests; `uv run pytest tests/test_webrtc_signaling.py -k "voxcpm2 or call_tts_failed or ai_audio_started"` passed 5 tests; `uv run pytest tests/test_calls.py -k "voxcpm2 or call_tts_failed or ai_audio_started or streaming_audio_started"` passed 4 tests.
  implication: Covered streaming, first-playback, public-error, and SSE propagation paths work in tests; the failing path is likely an uncovered runtime/config branch rather than the normal propagation code.
- timestamp: 2026-05-25T17:02:20Z
  checked: Related GSD debug evidence and model/voice routing code
  found: Prior active debug files document two relevant VoxCPM2 incidents: worker isolation fixed native backend crashes, and the current call profile was capped to timesteps 4/normalize off/denoise off because timesteps 10 generated slower than realtime. Model manager marks engines unavailable on load failures; call voice reference is loaded before LLM generation, so missing voice blobs would fail before visible AI text.
  implication: The current symptom of visible AI text followed by `Speech playback failed` is unlikely to be a missing voice sample; it is either a backend VoxCPM2 stream/load failure or a stream error after some chunks that current buffering discards before first playback.
- timestamp: 2026-05-25T17:08:10Z
  checked: Read-only OMEN AI/web log tails
  found: OMEN is on commit `26b4871`. Latest failing calls show voice reference OK, LLM first token/done, browser state entering `rehearsing`, then AI backend `POST /webrtc/sessions/.../speak` returns 502. There are no `tts.enqueue`, `track.enqueue`, `track.send.first_nonzero`, or `ai_audio_started` lines before the 502; outbound track only sends idle silence.
  implication: The real failure occurs before first audio chunk enqueue, so the earlier uncovered "discard chunk after first chunk" branch is not the observed incident. Need expose and fix the backend pre-first-chunk runtime/load/stream failure.
- timestamp: 2026-05-25T17:14:30Z
  checked: OMEN health and VoxCPM2 error logs
  found: `GET /health` reports `voxcpm2` unavailable with `unavailable_reason: engine load failed`; F5 is resident and the backend is degraded. AI logs for VoxCPM2 preview show `ValueError: TTS engine unavailable` raised from `ModelManager.switch_tts_engine` after the engine was marked unavailable.
  implication: Playback cannot start because the selected call engine is rejected before TTS streaming begins. A transient worker/load failure permanently disables VoxCPM2 until process restart/deploy, and call turns discover it only after generating text.
- timestamp: 2026-05-25T17:18:05Z
  checked: Red regression for transient VoxCPM2 load failure retry
  found: Added `test_transient_voxcpm2_load_failure_can_retry_on_later_switch`. Focused run failed as expected because `ModelManager.switch_tts_engine("voxcpm2")` raises `ValueError("TTS engine unavailable")` after the first load failure instead of retrying the adapter.
  implication: The permanent-unavailable mechanism is reproduced locally and can be fixed with a targeted model-manager state transition.
- timestamp: 2026-05-25T17:20:00Z
  checked: Model-manager retry fix and focused WebRTC regressions
  found: Updated `ModelManager.switch_tts_engine()` to retry engines whose unavailable reason is a sanitized load failure, while keeping non-load unavailable reasons blocked. Focused verification passed: model-manager retry/degrade tests 3 passed; WebRTC VoxCPM2/call_tts_failed/ai_audio_started tests 5 passed.
  implication: A transient VoxCPM2 worker/load failure no longer permanently disables live-call TTS until process restart, and the public WebRTC error contract remains sanitized.
- timestamp: 2026-05-25T17:23:20Z
  checked: Broader local verification
  found: Passed focused live-call/TTS suites: call-session VoxCPM2/queued audio 10 passed, VoxCPM2 stream/worker/fallback 6 passed, model-manager 7 passed, web call VoxCPM2/error/audio-started 4 passed. Full AI backend suite passed: 140 passed, 3 dependency warnings. `git diff --check` passed.
  implication: The local fix preserves the live-call streaming invariants covered by tests, including first playback before slow stream completion and no whole-synthesis fallback on the VoxCPM2 streaming path.
- timestamp: 2026-05-25T17:30:00Z
  checked: Parent-session verification after adding non-retry guard
  found: Added `test_startup_self_test_failure_remains_unavailable_without_retry` so the retry path remains limited to load failures. Parent-run checks passed: model-manager suite 8 passed, call-session VoxCPM2/queued audio 10 passed, WebRTC VoxCPM2/failure/audio-started 5 passed, web call VoxCPM2/error/audio-started 4 passed, full AI backend suite 141 passed with 3 dependency warnings, and `git diff --check` passed.
  implication: The patch fixes stale transient load-failure state without retrying startup self-test failures, and preserves the required live-call streaming regressions.
- timestamp: 2026-05-25T17:45:00Z
  checked: Canonical OMEN deploy and post-deploy health
  found: `scripts/deploy-omen.sh` deployed commit `f1e9c3aa4162c31a8939475165b2d498ccc08b5f`, verified CUDA Torch `2.10.0+cu126` on RTX 3060, restarted canonical scheduled tasks, and reported AI/web listeners healthy enough for live calls. Immediately after deploy, `/health` showed `voxcpm2` as `available=true`, `state=idle`, `unavailable_reason=null`.
  implication: The stale-unavailable state was cleared by deployment, and the first fix is deployed, but this does not prove VoxCPM2 can load or stream audio.
- timestamp: 2026-05-25T17:45:00Z
  checked: Deployed Phase 8 direct call-flow evidence
  found: Running `08-run-call-flow-evidence.py --warm-samples 1` against OMEN failed at the VoxCPM2 speak call with `call_tts_failed` status 502. AI logs show `ModelManager.switch_tts_engine("voxcpm2")` attempted `adapter.load()`, then `tts_voxcpm2._iter_worker_lines()` raised `ValueError("VoxCPM2 worker timed out")` after `_queue.Empty`; no `tts.enqueue` or `ai_audio_started` occurred for VoxCPM2. Post-failure `/health` shows `voxcpm2` unavailable with `unavailable_reason: engine load failed`.
  implication: The original `Speech playback failed` symptom remains reproducible after deployment. The first fix changed stale retry behavior but the active root cause is now the deterministic VoxCPM2 worker load timeout before first audio.
- timestamp: 2026-05-25T17:49:00Z
  checked: VoxCPM2 worker/load implementation and historical OMEN runtime evidence
  found: `VoxCpm2TtsAdapter.load()` sends a worker `load` request and waits `WORKER_LOAD_TIMEOUT_SECONDS = 180.0` for a `WORKER_READY_PREFIX` line. Historical OMEN standalone runtime smoke loaded `openbmb/VoxCPM2` in about 19.3-23.5 seconds on the RTX 3060, and prior Phase 8 live-call evidence produced VoxCPM2 first audio around 0.76-0.80 seconds after warmup with streaming enabled and no whole-wav fallback.
  implication: A blanket "180 seconds is too short for VoxCPM2 model load" hypothesis is weak. The remaining failure is specific to the deployed live worker-load context after F5/STT backend startup or to the worker protocol/resource boundary, not normal VoxCPM2 cold-load duration.
- timestamp: 2026-05-25T17:51:00Z
  checked: Read-only deployed health, VRAM, process list, and AI log tail after failed OMEN call-flow
  found: AI health remains degraded with `voxcpm2` unavailable for `engine load failed`, `resident_tts_engine` back to `f5`, and reported VRAM around 2948.5 MB used / 8051.5 MB headroom; `nvidia-smi` reports about 2771 MB used / 9340 MB free. The AI log tail shows F5 calls enqueue audio successfully, then the first VoxCPM2 warmup `/webrtc/speak` fails from `_queue.Empty` in `_iter_worker_lines()` after waiting for worker readiness; no VoxCPM2 worker diagnostic output appears because the subprocess stderr is discarded and stdout is reserved for protocol.
  implication: The backend survives and GPU memory is not stuck after the timeout, but current logs cannot distinguish a hung worker load from blocked/hidden third-party worker output. Need a direct OMEN manager-switch probe to reproduce or eliminate the non-HTTP engine-switch path.
- timestamp: 2026-05-25T17:55:00Z
  checked: Read-only OMEN standalone `ModelManager.startup(); switch_tts_engine("voxcpm2")` probe using the deployed venv while the live backend was running
  found: After one quoting-only failed attempt that loaded F5 but did not run the switch, the base64-encoded probe loaded F5 in about 16.5 seconds and then switched to VoxCPM2 successfully in about 36.3 seconds. The probe ended with `resident_tts_engine: voxcpm2` and health-reported VRAM around 9413.7 MB used.
  implication: The worker subprocess and a plain F5-load-to-VoxCPM2 switch can succeed on OMEN under current deployment. The failing condition is narrower: likely F5 synthesis/call-session state in the long-lived backend before switching, or a call-path-specific worker/protocol interaction.
- timestamp: 2026-05-25T17:59:00Z
  checked: Read-only OMEN standalone probe that starts a manager, runs two F5 syntheses with the Phase 8 reference/text, then switches to VoxCPM2
  found: The probe reproduced the deployed failure outside HTTP. F5 startup took about 19.3 seconds; the two F5 syntheses succeeded in about 2037 ms and 654 ms; then `manager.switch_tts_engine("voxcpm2")` timed out in `_iter_worker_lines()` after `_queue.Empty`, matching the deployed call-flow stack.
  implication: The remaining bug is specifically caused by F5 synthesis state before the VoxCPM2 worker load. Plain timeout tuning is not the fix; the switch must release F5 inference/CUDA resources before spawning/loading the VoxCPM2 worker.
- timestamp: 2026-05-25T18:07:00Z
  checked: OMEN post-F5 release probes before switching to VoxCPM2
  found: Explicit `f5.unload()`, `gc.collect()`, `torch.cuda.empty_cache()`, and `torch.cuda.ipc_collect()` still timed out. Clearing F5 module-level caches (`mel_basis_cache`, `hann_window_cache`, `_ref_audio_cache`, `_ref_text_cache`) still timed out. Moving F5 `ema_model` and `vocoder` to CPU before unload plus CUDA cleanup also still timed out.
  implication: The root cause is not a simple Python reference, global cache, or allocator-cache leak. Need worker-side observability because production currently discards stderr and reports every silent post-F5 worker hang as the same parent-side `_queue.Empty` timeout.
- timestamp: 2026-05-25T18:11:00Z
  checked: OMEN post-F5 diagnostic worker probe with stderr merged into captured output
  found: After two F5 syntheses, directly starting `app.models.tts_voxcpm2_worker` with a load request exited in 37.4 ms with `Fatal Python error: config_init_hash_seed: PYTHONHASHSEED must be "random" or an integer in range [0; 4294967295]`. The installed F5 code calls `seed_everything(seed)` during `infer()`, and that function sets `os.environ["PYTHONHASHSEED"] = str(seed)`; `infer(seed=None)` chooses `random.randint(0, sys.maxsize)`.
  implication: Confirmed root cause: F5 synthesis poisons the process environment with an invalid `PYTHONHASHSEED`, and the VoxCPM2 Python worker inherits it. Production hides the worker fatal error because stderr is discarded, so the parent reports a readiness timeout instead of the real child-interpreter startup failure.
- timestamp: 2026-05-25T18:15:00Z
  checked: RED/green regressions for hash-seed poisoning
  found: Added `test_f5_adapter_restores_pythonhashseed_after_infer` and `test_voxcpm2_worker_spawn_sanitizes_invalid_pythonhashseed`. Both failed before the fix: F5 left `PYTHONHASHSEED=9223372036854775807`, and VoxCPM2 passed that value into the worker env. After the fix, both focused tests passed.
  implication: The confirmed parent-environment poisoning now has direct regression coverage at the F5 source and a defensive guard at the VoxCPM2 worker boundary.
- timestamp: 2026-05-25T18:19:00Z
  checked: Local focused and broad verification
  found: Passed `test_tts_voxcpm2.py` (14 tests), `test_tts_registry.py` (20 tests), call-session VoxCPM2/queued-audio subset (10 tests), WebRTC VoxCPM2/failure/audio-started subset (5 tests), model-manager tests (8 tests), web call VoxCPM2/error/audio-started subset (4 tests), full AI backend suite (143 tests, 3 dependency warnings), and `git diff --check`.
  implication: The fix preserves existing live-call streaming regressions, including slow-stream first playback before stream completion and VoxCPM2 no whole-synthesis fallback coverage, while preventing the confirmed worker environment poisoning.
- timestamp: 2026-05-25T18:22:00Z
  checked: Read-only OMEN mechanism probe after manually clearing F5-poisoned `PYTHONHASHSEED`
  found: In the deployed venv, two real F5 syntheses set `PYTHONHASHSEED` to invalid value `7358197106145542751`. Clearing that env var before `manager.switch_tts_engine("voxcpm2")` made the same post-F5 switch complete in about 32.6 seconds with `resident_tts_engine: voxcpm2`.
  implication: This validates the fix mechanism against the deployed runtime without deploying code: removing the invalid F5-mutated hash seed allows the VoxCPM2 worker to start and load after F5 synthesis.
- timestamp: 2026-05-25T18:23:00Z
  checked: Parent-session verification of F5/VoxCPM2 hash-seed fix
  found: Passed focused checks in parent context: F5/VoxCPM2 registry suites 34 passed, call-session VoxCPM2/queued-audio subset 10 passed, WebRTC VoxCPM2/failure/audio-started subset 5 passed, web call VoxCPM2/error/audio-started subset 4 passed, full AI backend suite 143 passed with 3 dependency warnings, and `git diff --check` passed.
  implication: The final patch is locally verified in the parent context and ready for canonical OMEN deployment.
- timestamp: 2026-05-25T18:27:30Z
  checked: Deployed Phase 8 direct call-flow evidence after canonical OMEN deploy
  found: `08-run-call-flow-evidence.py --warm-samples 1` wrote `.planning/debug/evidence/call-speech-playback-failed-live-call-flow.json`. VoxCPM2 emitted `ai_audio_started` at 1305.7 ms with `streaming_used=true`, `chunk_count_at_start=5`, final `chunk_count=17`, `whole_wav_fallback_used=false`, and `total_generation_ms=3263.4`. OMEN `/health` then reported `resident_tts_engine=voxcpm2`, `voxcpm2.available=true`, `voxcpm2.state=resident`, and `unavailable_reason=null`.
  implication: The deployed backend no longer fails before first playback; VoxCPM2 streams chunks into the live-call audio path and does not regress to whole-synthesis fallback.
- timestamp: 2026-05-25T18:31:00Z
  checked: Browser live-call acceptance after deploy
  found: The first post-deploy non-mocked browser run reached `/api/calls/{id}/end` successfully instead of the earlier 500, but exposed that a cancelled request could leave a stale aiosqlite connection in the pool and that the live spec could click hangup before the second turn was durably/audio-complete. Added SQLite `pool_pre_ping=True` with a regression, aligned the stale Phase 1 settings expectation, and hardened the live spec to wait for persisted rows plus playback signals before hangup.
  implication: The original playback fix held under browser verification; the remaining failures were hangup/test synchronization defects discovered while closing the live-call evidence loop.
- timestamp: 2026-05-25T18:40:45Z
  checked: Final canonical OMEN deploy and non-mocked browser live-call acceptance
  found: `scripts/deploy-omen.sh` deployed `76bacc7ea5069e1091607bf2ae9cba43dfe56096`. The OMEN browser command `npm --prefix web-ui\client run test:e2e -- tests/e2e/live-call.spec.ts --project=desktop-chromium --reporter=line` passed 1 test in 1.6 minutes with VoxCPM2, requiring two unique `ai_audio_started` turn ids, two `ai_done` events, two persisted `ai_speech` rows, and a successful hangup/return-to-thread flow. Final AI health reported VoxCPM2 resident and available.
  implication: The user-reported live-call path is deployed and verified end to end: generated responses now start TTS playback, complete audio turns, persist transcript rows, and hang up cleanly.

## Eliminated

- hypothesis: The web SSE proxy fails to surface nested `ai_audio_started_event`, causing a false playback failure after successful backend audio.
  evidence: Existing web test `test_turn_yields_ai_audio_started_event_when_nested_inside_speak_result_event` was included in the focused run and passed.
  timestamp: 2026-05-25T16:54:35Z

- hypothesis: The current VoxCPM2 streaming call-session implementation waits for full stream completion before first playback.
  evidence: Existing backend test `test_voxcpm2_slow_stream_starts_playback_before_stream_completion` was included in the focused run and passed.
  timestamp: 2026-05-25T16:54:35Z

- hypothesis: The observed incident is caused by a late stream error after some audio was already enqueued, with only the UI failing to surface `ai_audio_started`.
  evidence: OMEN AI logs for the failing sessions show `/webrtc/speak` returning 502 without any preceding `tts.enqueue`, `track.enqueue`, or `ai_audio_started` event.
  timestamp: 2026-05-25T17:08:10Z

- hypothesis: The remaining worker failure is caused by a generally too-short 180-second VoxCPM2 load timeout.
  evidence: Historical OMEN standalone runtime smoke loaded VoxCPM2 in about 19.3-23.5 seconds, and a fresh standalone manager switch to VoxCPM2 completed in about 36.3 seconds.
  timestamp: 2026-05-25T17:55:00Z

- hypothesis: F5 synthesis leaves unreleased CUDA memory/cache references, and stronger unload/GC/cache clearing is sufficient to make the VoxCPM2 worker load.
  evidence: OMEN probes still reproduced the worker timeout after explicit `f5.unload()`, `gc.collect()`, `torch.cuda.empty_cache()`, `torch.cuda.ipc_collect()`, clearing F5 module caches, and moving F5 `ema_model`/`vocoder` to CPU before unload.
  timestamp: 2026-05-25T18:07:00Z

## Specialist Review

## Resolution

- root_cause: F5 synthesis calls third-party `seed_everything()` with a random 63-bit seed and mutates `PYTHONHASHSEED` in the long-lived AI backend process. The subsequent VoxCPM2 Python worker inherits an invalid hash seed and fails during interpreter startup before it can emit `WORKER_READY_PREFIX`; production discards worker stderr, so the parent surfaces this as `VoxCPM2 worker timed out` and `call_tts_failed`.
- fix: `F5TtsAdapter.synthesize()` now preserves and restores the previous `PYTHONHASHSEED` around third-party F5 inference; `VoxCpm2TtsAdapter._ensure_worker()` now sanitizes invalid inherited `PYTHONHASHSEED` values to `random` before spawning the Python worker.
- verification: Local verification passed in parent context: new hash-seed regressions, focused VoxCPM2/F5/model-manager/live-call/WebRTC/web-call suites, full AI backend suite, full web server suite, client sync check, and `git diff --check`. Canonical OMEN deployments passed, direct Phase 8 live-call flow evidence passed, and the non-mocked OMEN browser live-call spec passed with two VoxCPM2 playback-start and completion events.
- files_changed: ai-backend/app/models/tts_f5.py, ai-backend/app/models/tts_voxcpm2.py, ai-backend/tests/test_tts_registry.py, ai-backend/tests/test_tts_voxcpm2.py, web-ui/server/app/storage/session.py, web-ui/server/tests/test_storage_session.py, web-ui/server/tests/test_phase1_acceptance.py, web-ui/client/tests/e2e/live-call.spec.ts
