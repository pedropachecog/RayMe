---
status: resolved
trigger: "we don't need this \"reference authorization\" remove that, assume they're authorized. and also, even when I upload, transcribe, and add reference authorization fields, voicelab says \" The transcript does not appear to match the voice sample\""
created: 2026-08-01T13:11:36Z
updated: 2026-08-01T17:24:30Z
---

# Debug: Qwen Voice Lab Transcript Rejection

## User-Goal Preservation

An uploader must be able to create a Qwen3-TTS 1.7B saved voice from Voice Lab's own transcription without completing reference-authorization fields. Transcript validation must accept a genuinely matching machine transcript while still rejecting unrelated text, and the change must preserve early streamed live-call playback, barge-in, listening recovery, and the prohibition on whole-synthesis fallback.

## Symptoms

### Expected behavior

- Reference authorization fields are absent; uploading a reference is treated as the uploader's authorization.
- Uploading a voice sample, using Voice Lab's Transcribe action, and saving the resulting Qwen voice succeeds when that transcript came from the uploaded sample.

### Actual behavior

- Voice Lab requires reference-authorization fields the product owner no longer wants.
- Even after those fields are completed, saving fails with: `The transcript does not appear to match the voice sample`.

### Error messages

`The transcript does not appear to match the voice sample`

### Timeline

Observed during the first physical Voice Lab acceptance attempt after the Faster Qwen3-TTS 1.7B release was deployed on 2026-08-01. Whether an earlier Qwen build accepted this exact sample is unknown.

### Reproduction

1. Open RayMe Voice Lab on the deployed OMEN UI.
2. Upload a reference voice sample.
3. Run the built-in transcription action.
4. Select Faster Qwen3-TTS 1.7B.
5. Complete the currently visible reference-authorization fields.
6. Save the voice.
7. Observe transcript/sample mismatch rejection.

## Current Focus

reasoning_checkpoint:
  hypothesis: "Confirmed: already-sent RTP crosses the server cancellation acknowledgement under variable WebRTC scheduling; without a browser receiver-drain mute it remains audible, while the hardware tracer's unrelated fixed 100-ms grace misclassifies the same transport tail."
  confirming_evidence:
    - "Ten-cycle OMEN probe reproduced post-ack sequential RTP in 5/10 runs while every interrupted event reported track_pending_audio_ms=0.0 and server logs showed no post-cancel enqueue."
    - "Desktop and mobile browser acceptance now observe immediate interrupt-drain mute and bounded automatic unmute on both button and server-event paths."
    - "All contract tests and targeted counterfactual mutations prove the shared event/API/client/tracer boundary is necessary."
  falsification_test: "Canonical OMEN verification fails if audio appears beyond 250 ms, server pending audio is nonzero/missing, a normal completion appears after interrupt, or a later turn cannot recover and begin early streaming."
  fix_rationale: "The 250-ms advertised receiver drain suppresses only unretractable transport tail and leaves generation/startup untouched; the tracer separately validates server quiescence and rejects every audible frame beyond the same bound."
  blind_spots: "The old failed run did not retain its exact late-frame offset. The new fail-closed hardware tracer and physical browser workflow must validate the conservative bound on canonical OMEN hardware."
  candidate_causes:
    - "code: missing browser receiver mute/drain and ignored interrupted data event"
    - "measurement/config: unshared fixed 100-ms tracer allowance"
    - "environment: variable WebRTC delivery/jitter retains already-sent RTP"
    - "data/state: stale prior-turn audio eliminated by a clean 525-ms receiver-silence reproduction"
  and_gate: "yes — environment transport retention plus missing receiver mute cause audible continuation; the separate measurement-contract defect causes false deployment rejection."
hypothesis: confirmed, fixed, and verified in production
test: completed canonical OMEN deployment plus real Voice Lab, test-play, hardware tracer, and deployed browser live-call acceptance
expecting: satisfied — exact deployed commit passed every required product and live-call invariant
next_action: archive this resolved session and append its prevention pattern to the durable debug knowledge base
bug_class: heisenbug-mandelbug (intermittent WebRTC delivery ordering; SBFL is inapplicable and no flaky spectrum was used)

## Evidence

- timestamp: 2026-08-01T17:24:30Z
  checked: Canonical production and physical human verification reported after exact deployment commit 288c05b4742dda0aac76050658aa12a44041102e
  found: `scripts/deploy-omen.sh` ran with `RAYME_OMEN_VERIFY_QWEN3=1` and exited 0. Hardware tracing passed short/medium/long early streaming, first audio before completion, no whole-WAV fallback, exact zero pending cancellation samples, the bounded 250-ms receiver drain, and recovery. Real Voice Lab verification used the 48-kHz stereo `ref_audio_3.wav`; upload preserved 48000 Hz, transcription returned the exact spoken transcript, Qwen voice creation without authorization fields returned 201, and Qwen test-play returned HTTP 200 WAV. The deployed browser exposed zero reference authorization/source/basis/scope controls and no page errors. The temporary verification voice was deleted. The deployed Playwright live-call suite passed all four desktop/mobile two-cycle tests in 2.8 minutes.
  implication: The original Voice Lab symptoms, the exact-core deployment continuation, and the receiver-drain continuation are all resolved end to end on canonical OMEN hardware without weakening the live-call invariants.

- timestamp: 2026-08-01T17:24:30Z
  checked: Semantic knowledge-base indexing availability at archive
  found: No MemPalace CLI or connector is available in this environment.
  implication: Persist the resolved pattern in `.planning/debug/knowledge-base.md`; semantic indexing is skipped explicitly and keyword recall remains the durable fallback.

- timestamp: 2026-08-01T16:38:00Z
  checked: Final hardened fix-acceptance guardrail on the restored tree
  found: The fail-closed pending-metric and client lower-bound tests failed before implementation and pass after it; the exact missing-metric fallback mutant was killed, then the restored test passed. Final focused contract tests pass (AI 2, Web server 1, client audio 9, tracer 2), browser acceptance passes desktop/mobile 2/2 with full automatic mute/unmute, the final Phase 09 evidence suite passes 61/61, Python compilation and git diff checks pass, and no configured mutation runner exists. Earlier full restored suites remain AI backend 276, Web server 243, client unit 109, and production build success.
  implication: All applicable local guardrail signals accept the minimal fix. Only canonical hardware/deployed and physical human verification remain; no commit or deployment was performed by this debugger.

- timestamp: 2026-08-01T16:32:00Z
  checked: Final production diff review after restored counterfactuals
  found: The restored focused tests and browser acceptance are green and the temporary probe is removed. One oracle weakness remains: `float(playback_final.get("track_pending_audio_ms") or 0.0)` maps a missing metric to zero, so the tracer does not truly require the server's quiescence evidence. Client normalization also allows a positive fractional value to round down to zero, and the automatic-event E2E only counted drain start rather than its full mute/recovery cycle.
  implication: Tighten these boundary assertions before accepting the fix; otherwise malformed evidence could pass the production gate despite correct behavior in the observed run.

- timestamp: 2026-08-01T16:29:00Z
  checked: Four independent targeted counterfactual mutations
  found: Removing receiver_drain_ms from the server event failed both session and AI HTTP regressions; dropping it at the Web-server boundary failed the endpoint regression; forcing browser audibility to ignore active drain failed the client mute regression; restoring the old 100-ms tracer classification failed the +250/+251 boundary regression. Every mutation was restored before the next experiment.
  implication: The tests kill mutations at every causal boundary and prove the implementation is necessary, not a green-by-suppression patch. Final restored-tree confirmation remains.

- timestamp: 2026-08-01T16:25:00Z
  checked: Full adjacent automated and build gate after receiver-drain implementation
  found: AI backend passed 276/276 (including canonical OMEN deploy-contract and all live streaming/cancellation tests), Web server passed 243/243, client unit passed 109/109, Phase 09 evidence passed 60/60, focused browser acceptance passed 2/2, and the SvelteKit static production build completed. Existing mandatory regressions still prove Qwen/Vox slow-stream first playback before completion, no whole-synthesis fallback, immediate/final metric separation, interrupted-turn late event rejection, and recovery.
  implication: The change does not alter generation/startup behavior or regress adjacent call, storage, API, deployment, or evidence contracts. Counterfactual necessity testing and final restored-tree hygiene remain.

- timestamp: 2026-08-01T16:20:00Z
  checked: Browser-level manual and automatic interruption acceptance on desktop and mobile Chromium
  found: The focused call-toolbar acceptance passed 2/2. It observed the real call route change the detached WebRTC Audio element to muted under `interrupt-drain`, emit bounded drain completion, restore audible policy automatically, and start a fresh drain when an `interrupted` data-channel event was injected.
  implication: The helper is not dead code: both button and VAD/server-event paths invoke it in an actual built browser. Broad regression and live-call invariant gates can now judge integration safety.

- timestamp: 2026-08-01T16:17:00Z
  checked: Exact four red regressions after minimal shared-contract implementation
  found: AI session/API tests pass 2/2, Web server propagation passes 1/1, client audio helper tests pass 9/9, and the tracer boundary classifier passes 1/1. The 250-ms boundary is inclusive and +251 ms remains rejected.
  implication: Each unit/contract layer is green. A browser-level regression is still needed to prove the call route actually invokes the tested mute helper on both manual and automatic interruption, rather than only defining unused helpers.

- timestamp: 2026-08-01T16:13:00Z
  checked: Agent-authored specified-oracle regressions before production implementation
  found: All four boundaries failed exactly as predicted: CallSession event and AI HTTP response lacked receiver_drain_ms; the Web server discarded the backend field; client receiver-drain normalization/audibility helpers did not exist; and the hardware tracer had no bounded transport-drain classifier. The tracer boundary seed proves +1 ms and +250 ms are inside the drain while +251 ms is a true late-audio violation.
  implication: The test suite now reproduces each contract gap independently. Implementing the missing propagation and receiver state is necessary; merely increasing the tracer sleep cannot satisfy the browser audibility regression.

- timestamp: 2026-08-01T15:35:00Z
  checked: Second canonical OMEN deployment of exact reviewed/pushed commit 3bc310024d9484397a9978f97dc0179c98d13cd5, reported by the parent workflow
  found: Migration was already at head, CUDA/runtime attestation, client build, service listeners, and startup passed. The earlier hidden core-runner TypeError was no longer the failure boundary. The production hardware tracer instead failed earlier with the exact sanitized diagnostic `FAIL: Audible Qwen frames arrived after cancellation acknowledgement`.
  implication: The cancellation invariant is reopened as a live-call incident. Because the prior production tracer passed cancellation at f598858 while this run failed at 3bc3100, classify it as intermittent until exact event/frame ordering proves a deterministic mechanism; do not rerun blindly or weaken the gate.

- timestamp: 2026-08-01T15:38:00Z
  checked: Exact failure producer and current cancellation implementation inventory
  found: The production failure is raised by `09-run-hardware-tracer.py::_run_cancel_sample` when `post_cancel_nonzero_frames` is nonzero. The server interrupt route awaits `CallSession.interrupt`; CallSession has separate active-generation cancellation and outbound-track stop paths, while QueuedAudioOutputTrack maintains pending/discard metrics. Existing tests include delayed worker-cancel acknowledgement coverage.
  implication: The next experiment must align four clocks/boundaries—worker terminal, track discard, HTTP response, and remote aiortc frame reception—rather than assuming the tracer's post-response frame count directly proves post-cancel enqueue.

- timestamp: 2026-08-01T15:41:00Z
  checked: Cancellation implementation and tracer measurement semantics
  found: `_run_cancel_sample` timestamps acknowledgement only after the interrupt HTTP call returns, then ignores frames through 100 ms after that local timestamp and rejects later nonzero frames. Server interrupt starts worker cancellation, awaits track `stop_current()` queue/buffer discard, then awaits the worker terminal before responding. Track `recv()` paces before pulling one 20-ms frame; `stop_current()` clears only track-held queue/buffer and cannot retract a frame already returned to aiortc or an RTP packet already in transport.
  implication: The current gate conflates post-ack remote arrival with post-cancel server production. A real violation remains possible, but pre-cancel frames delayed in RTP/jitter beyond the arbitrary 100-ms grace are a competing measurement hypothesis that OMEN ordering evidence must test.

- timestamp: 2026-08-01T15:43:00Z
  checked: First read-only OMEN inspection attempt
  found: Local and expected deployed HEAD are both 3bc310024d9484397a9978f97dc0179c98d13cd5. The remote shell reinterpreted the inline PowerShell pattern pipe before the inspection body ran, so no OMEN artifact/log evidence was collected.
  implication: Retry via literal PowerShell stdin; this command-shaping failure neither supports nor refutes any cancellation hypothesis.

- timestamp: 2026-08-01T15:45:00Z
  checked: Partial literal-stdin OMEN inspection
  found: OMEN HEAD is confirmed as 3bc310024d9484397a9978f97dc0179c98d13cd5. The tracer directory produced no file inventory, consistent with the failed tracer never writing its final JSON; the multiline stdin program stopped before log extraction.
  implication: The final tracer artifact cannot supply the failing turn timeline. Use encoded PowerShell for reliable, read-only filtered log extraction.

- timestamp: 2026-08-01T15:49:00Z
  checked: Exact-commit OMEN tracer directory and filtered AI backend logs for both cancellation runs
  found: The final tracer JSON is stale from 15:00; the failed 15:26 run left only new baseline WAVs. Its cancel turn is `trace-cancel-db58e757fd5f41b4` in session `phase09-77624cd2e94d469781d2`. Server logs show exactly two 320-ms track enqueues, then `speak.cancelled`, then the `interrupted` event, followed by track progress with queue_size=0 and buffer_size=0. No enqueue appears after cancellation/interrupted. The earlier passing run shows the same server-side pattern.
  implication: Direct evidence contradicts post-ack server enqueue. The failure is at receiver attribution/transport drain: audio already sent before `stop_current` or stale prior-turn RTP was received late. The tracer needs turn-boundary observability or a receiver quiescence protocol; runtime cancellation queue discard itself is operating.

- timestamp: 2026-08-01T15:53:00Z
  checked: Tracer baseline-to-cancel orchestration and browser interrupt behavior
  found: The tracer runs short, medium, and long samples then immediately resets capture for cancellation; it never proves remote silence between turns, and capture frames have no turn identity. Browser button interrupt cancels text streaming and awaits the API but never mutes/pauses the remote audio element; server-driven `interrupted` handling likewise has no local audio flush/mute boundary.
  implication: Receiver-tail audio is user-visible, not merely a harmless test artifact. A complete fix may need both an evidence attribution barrier and a bounded client/server transport-silence contract, but the instrumented probe must quantify the tail before choosing the smallest mechanism.

- timestamp: 2026-08-01T15:58:00Z
  checked: Instrumented exact-commit OMEN cancellation probe with incoming frame PTS and monotonic timing
  found: After a normal long sample, cancel HTTP completed in 90.4 ms and the interrupted event arrived 0.1 ms later. Eight audible 20-ms frames arrived with strictly sequential PTS; exactly one final frame arrived 21.8 ms after acknowledgement, then only silence. After a proven 524.9-ms receiver-silence boundary, a second cancel completed in 135.4 ms with the same eight-frame sequential burst and zero frames after acknowledgement. Both speak requests returned cancelled status 502 and the session was ended in finally.
  implication: This directly reproduces the ordering race without deployment changes. It is not late server enqueue or out-of-order stale speech: a final already-sent paced frame can straddle acknowledgement depending on scheduling. The failed >100-ms case is the same class but needs stress measurement before selecting a shared bounded receiver drain.

- timestamp: 2026-08-01T16:03:00Z
  checked: Ten-cycle clean-boundary cancellation stress probe on current exact-commit OMEN
  found: Five of ten runs delivered sequential audible RTP after HTTP/event acknowledgement; the maximum last-frame offset was 71.0 ms and no run exceeded 100 ms in this sample. Every interrupted event independently reported track_pending_audio_ms=0.0, bridge_queue_high_water=1, and 20,160-24,000 discarded track samples. All cancelled speak calls returned 502; no second audible burst appeared; the diagnostic session ended cleanly.
  implication: The AND-gate is confirmed: variable WebRTC delivery retains already-sent audio after a correctly quiescent server, and the browser lacks a bounded local mute/drain response. The production failure above 100 ms is a rare tail outside the tracer's arbitrary allowance, not evidence of new generation. Fix product audibility and make evidence validate the same explicit bounded contract plus zero server pending audio.

- timestamp: 2026-08-01T15:02:23Z
  checked: Canonical OMEN deployment of exact reviewed commit f5988587f683de376e9987b0b9f673dd4e48fee9, reported by the parent workflow
  found: Migration 0007 to 0008, client build, pinned CUDA runtime, and production saved-voice/WebRTC Qwen tracer all passed, including short/medium/long early playback and cancellation recovery. The later exact-commit Phase 09 core-evidence step failed with "FAIL: evidence runner returned no sanitized diagnostic" at deploy-omen.sh remote line 818, so no core-ready marker was written and deployment exited 1.
  implication: The original application/runtime fix and live-streaming path survived production hardware verification. Investigation is reopened specifically at the exact-core evidence wrapper boundary; the hidden runner failure and its swallowed diagnostic must be isolated without redeploying.

- timestamp: 2026-08-01T15:05:00Z
  checked: Exact deployment failure producer and diagnostic filter
  found: deploy-omen.sh captures the Python runner with PowerShell `2>&1`, prints only objects matching `PASS*` or `FAIL:*`, and on nonzero status selects only the last object matching `FAIL:*`; if none matches exactly, it substitutes the observed generic message. The later verifier was never reached.
  implication: The visible message proves only that no captured PowerShell object began exactly with `FAIL:`. It does not identify the runner's underlying failure and may be caused by stream wrapping, an unhandled traceback, or an output-contract gap.

- timestamp: 2026-08-01T15:09:00Z
  checked: Complete 09-run-omen-evidence.py failure boundary and core preflight path
  found: main sanitizes only EvidenceRunnerError, OSError, RuntimeError, and ValueError. Other production/tracer/programming exceptions escape as raw tracebacks. Before any RayMe request, `_run_core_cli` generates/selects a local fixture and `write_permitted_fixture_bundle` dereferences `selection.authorization_basis` and `selection.use_scope`, even though explicit authorization was removed from the product and current tracer caller.
  implication: There are two testable layers: a likely stale evidence-field dereference causing the exact post-refactor failure, and an independently incomplete top-level diagnostic boundary that hides uncaught failures from the deploy wrapper.

- timestamp: 2026-08-01T15:10:00Z
  checked: Current hardware tracer ReferenceSelection and saved-voice helper contract
  found: ReferenceSelection still contains authorization_basis and use_scope, disproving the stale fixture-attribute hypothesis. The decisive mismatch is elsewhere: hardware tracer `_create_saved_voice(api, reference_audio, transcript)` no longer accepts `selection`, while `RayMeProductionPath.open` still calls it with `selection=self.selection`.
  implication: Core evidence deterministically raises TypeError before saved-voice creation. TypeError is absent from the runner's sanitized catch list, so Python produces a traceback and the deploy filter replaces it with the generic diagnostic.

- timestamp: 2026-08-01T15:13:00Z
  checked: No-network signature reproduction and introducing commit df9346f
  found: Calling the current tracer helper with the core runner's exact arguments raises `TypeError: _create_saved_voice() got an unexpected keyword argument 'selection'`. Commit df9346f deleted the selection parameter and authorization payload fields from the helper and updated the hardware tracer's own caller, but did not modify 09-run-omen-evidence.py.
  implication: The exact hidden runner failure and its introduction mechanism are confirmed without touching OMEN. The fix must update the second caller and harden the outer diagnostic boundary against future uncaught ordinary exceptions.

- timestamp: 2026-08-01T15:16:00Z
  checked: Initial focused regression invocation
  found: The host `/usr/bin/python3` does not contain pytest, so no test code executed.
  implication: This is an environment selection issue, not test evidence; rerun through the project's pinned ai-backend uv environment.

- timestamp: 2026-08-01T15:18:00Z
  checked: Two focused pre-fix regressions in the pinned ai-backend environment
  found: Both failed exactly as predicted. The caller-contract test received unexpected keyword `selection` at RayMeProductionPath.open line 570. The outer-boundary test propagated a TypeError containing a private Windows path/transcript sentinel instead of returning a sanitized FAIL marker.
  implication: The regressions reproduce both contributing causes independently and provide specified-oracle protection for the minimal fix.

- timestamp: 2026-08-01T15:21:00Z
  checked: Focused regressions after the minimal production fix
  found: Both tests pass. RayMeProductionPath reaches the current upload-implied saved-voice helper contract, and an injected unexpected TypeError returns `FAIL: Unexpected evidence runner failure (TypeError)` without its private path/transcript message or a traceback.
  implication: Both causal defects are fixed locally. Broader Phase 09 and deploy-contract verification remains before accepting the continuation fix.

- timestamp: 2026-08-01T15:24:00Z
  checked: Full adjacent evidence/deployment contract suite, Python compilation, and diff hygiene after the continuation fix
  found: All 57 tests pass (52 Phase 09 evidence tests plus 5 OMEN deploy-contract tests); both changed Python files compile; git diff --check passes.
  implication: The minimal fix preserves all adjacent historical evidence, privacy, live-call, and canonical deployment contracts represented by these suites. Counterfactual hunk testing remains for causal acceptance.

- timestamp: 2026-08-01T15:27:00Z
  checked: Saved-voice caller hunk counterfactual
  found: Restoring only `selection=self.selection` makes the contract regression fail with the exact unexpected-keyword TypeError; removing it again makes the same test pass 1/1.
  implication: The caller edit is necessary and sufficient for the locally reproducible core-runner failure. The independent diagnostic-normalization hunk still needs its own counterfactual.

- timestamp: 2026-08-01T15:30:00Z
  checked: Unexpected-exception normalization hunk counterfactual
  found: Removing only the outer Exception handler makes the diagnostic regression propagate the injected TypeError and its private path/transcript sentinel; restoring the handler makes the same test pass 1/1 with a class-only FAIL marker.
  implication: The diagnostic edit independently prevents traceback/private-detail escape and gives deploy-omen.sh a usable sanitized failure line. Both fix hunks have now passed revert-and-reconfirm.

- timestamp: 2026-08-01T15:34:00Z
  checked: Final restored-tree fix-acceptance guardrail
  found: All 57 adjacent tests pass again; runner dry-run prints PASS; both changed files compile; git diff --check passes. No configured Python mutation tool is present, but both production hunks were manually mutated and each paired regression killed its mutant before passing after restoration. The only deletion is the stale caller keyword proven by RCA.
  implication: Every applicable self-verification signal accepts the continuation fix. Production core acquisition and the original physical Voice Lab workflow remain the required human/deployment checkpoint; no deployment was performed by this debugger.

- timestamp: 2026-08-01T13:22:00Z
  checked: Phase-0 semantic/knowledge-base recall
  found: No MemPalace connector is available, and knowledge-base.md contains no transcript-alignment match; the prior qwen-saved-voice-422 session involved a different top-level authorization payload omission.
  implication: Treat prior authorization work only as code-history context, not as a diagnosis for the current transcript mismatch.

- timestamp: 2026-08-01T13:23:00Z
  checked: Working-tree state and project/agent skill discovery
  found: The only reported worktree item is this new debug artifact; no project-local skills or configured gsd-debugger agent skills were found.
  implication: Implementation can proceed without overlapping known user edits, while continuing to preserve unrelated files.

- timestamp: 2026-08-01T13:24:00Z
  checked: Exact user-facing error producer/consumer search
  found: Voice Lab maps both qwen3_transcript_mismatch and qwen3_alignment_failed to the reported text. qwen3_transcript_mismatch originates in ai-backend/app/models/model_manager.py; server/API layers sanitize and forward the code.
  implication: The visible rejection is not a client-side text comparison. Reproduction must reach Qwen prompt preparation and inspect the reference/transcript validation there.

- timestamp: 2026-08-01T13:30:00Z
  checked: Built-in transcription and Qwen save-time alignment audio preparation
  found: POST /stt/transcribe calls uploaded_bytes_to_temp_wav, which decodes, mixes to mono, and resamples every upload to 16 kHz before Whisper. ModelManager._qwen_reference_alignment independently decodes with soundfile, retains the source sample count, discards sample_rate, and passes the raw ndarray to the same STT adapter.
  implication: Any non-16-kHz upload follows two acoustically different transcription paths even though alignment compares their text as if they heard identical audio.

- timestamp: 2026-08-01T13:31:00Z
  checked: Reference-authorization requirement boundaries
  found: Voice Lab gates save/preview on three fields; VoiceSave/VoicePreview expose them; VoiceService builds and persists qwen3_authorization and runtime validation rejects missing/stale authorization. This is deliberate policy code, not the transcript mismatch mechanism.
  implication: The authorized policy change needs a separate minimal removal across UI/API/persistence/runtime while retaining asset containment, byte-integrity, nonblank transcript, and Qwen acoustic alignment.

- timestamp: 2026-08-01T13:32:00Z
  checked: Spectrum-based fault localization eligibility and common-pattern classification
  found: Existing tests do not currently fail and there is no per-test coverage spectrum for this report, so SBFL is skipped. The symptom is deterministic data-shape/API-contract behavior for non-16-kHz input, classified as a Bohrbug.
  implication: Use a deterministic minimized sample-rate reproduction and working-backwards boundary test rather than flaky/stress techniques.

- timestamp: 2026-08-01T13:37:00Z
  checked: Existing focused Qwen alignment suite before adding the regression
  found: All 5 existing alignment tests passed; none asserts that save-time alignment receives the same 16-kHz audio representation as Voice Lab transcription.
  implication: The current suite protects text scoring and mismatch rejection but misses the producer/consumer sample-rate contract.

- timestamp: 2026-08-01T13:38:00Z
  checked: Installed faster-whisper 1.2.1 transcription source
  found: faster-whisper resamples path/file-like input to the model sampling rate, but explicitly skips decode_audio when input is already an np.ndarray and computes duration as ndarray length divided by 16 kHz.
  implication: Passing a 48-kHz ndarray makes Whisper interpret 0.2 seconds as 0.6 seconds and changes the acoustic content/speed; ModelManager must resample before passing an ndarray.

- timestamp: 2026-08-01T13:39:00Z
  checked: Agent-authored 48-kHz Voice Lab alignment regression before production fix
  found: test_qwen_alignment_resamples_uploaded_reference_like_voice_lab_transcription failed exactly with qwen3_transcript_mismatch. The adapter only returned the built-in matching transcript for the correct 3,200-sample 16-kHz representation, while current alignment supplied the source-rate sample count.
  implication: The hypothesis is causally confirmed. Reusing the canonical 16-kHz decoder should make the reported path pass without weakening the independent text-alignment predicate.

- timestamp: 2026-08-01T13:42:00Z
  checked: Local persisted Voice Lab asset metadata
  found: The workspace SQLite database contains no voice_assets rows, so the deployed physical sample's sample rate is not locally observable.
  implication: The causal minimized reproduction is the available pre-fix proof; physical OMEN verification must remain a human/deployment checkpoint rather than being invented.

- timestamp: 2026-08-01T14:01:00Z
  checked: Canonical 16-kHz alignment change against the matching 48-kHz regression and existing unrelated-text regression
  found: Both focused tests pass after ModelManager reuses decode_audio_bytes; the matching path supplies exactly 3,200 samples and prewarms Qwen, while the existing gross mismatch remains rejected.
  implication: The fix removes the producer/consumer audio mismatch without weakening transcript alignment thresholds or unrelated-text protection.

- timestamp: 2026-08-01T14:02:00Z
  checked: Production authorization-policy removal shape
  found: Voice Lab and client payload types no longer expose the three fields; API schemas forbid them; VoiceService no longer persists or validates qwen3_authorization; call/test-play still validate active saved voice, contained asset path, stored asset SHA-256, nonblank transcript, and opaque voice key. Migration 0008 removes legacy qwen3_authorization metadata.
  implication: Upload becomes the authorization event while integrity, containment, acoustic alignment, and live-call prompt identity remain intact.

- timestamp: 2026-08-01T14:10:00Z
  checked: Focused Web server voice, call, and migration regressions after policy removal
  found: Voice tests passed 17/17, Qwen call preparation/integrity tests passed 4/4, and Qwen migration tests passed 3/3. Coverage includes save/preview without authorization, rejection of removed API fields, blank transcript rejection, byte/path containment, exact call forwarding, and legacy metadata removal.
  implication: Server/API/runtime/migration behavior matches upload-implies-authorization without weakening reference containment or call preparation.

- timestamp: 2026-08-01T14:11:00Z
  checked: Initial Voice Lab unit command
  found: The command used npm test, but this package exposes test:unit instead; no client test executed.
  implication: This is a tooling invocation error, not product evidence; rerun through the declared package script before accepting the client change.

- timestamp: 2026-08-01T14:24:00Z
  checked: Corrected Voice Lab client unit test and production build
  found: Voice Lab unit tests passed 17/17 and the static SvelteKit production build completed successfully after removal of the now-unused authorization select styling.
  implication: The visible form, payload types, readiness UI, and fixed error-copy contracts compile without the removed authorization controls.

- timestamp: 2026-08-01T14:28:00Z
  checked: Current acceptance/evidence callers and operator-facing documentation
  found: Mocked/live Voice Lab and live-call voice-create payloads now omit removed fields; live-call acceptance no longer requires a provenance sidecar. The hardware tracer's actual POST /api/voices payload now relies on upload authorization. STATE, UI-SPEC, UAT, OMEN handoff, and ROADMAP supersession text describe the new policy. Completed Phase 09 result/verifier provenance schemas remain historical evidence rather than product API gates.
  implication: Current workflows cannot reintroduce the deleted form/API contract, while immutable historical phase evidence remains interpretable.

- timestamp: 2026-08-01T14:35:00Z
  checked: Mocked Qwen browser readiness and live-call Playwright contract collection
  found: Desktop Qwen readiness passed 4/4, including upload-implied authorization through failure/switch/retry; live-call.spec.ts collected for desktop/mobile without requiring a provenance sidecar.
  implication: The current browser acceptance path exercises the new payload contract and remains available for deployed human verification.

- timestamp: 2026-08-01T14:38:00Z
  checked: Mandatory live-call invariant regressions after the preparation-path fix
  found: 7/7 passed: Qwen first playback before slow-stream completion, late-event rejection after cancel, VoxCPM2 bounded startup without final metrics, post-first-chunk interrupt discard, and three no-whole-synthesis-fallback cases.
  implication: The fix does not buffer full Qwen output, alter immediate/final metrics, break interruption, or introduce VoxCPM2 whole-synthesis fallback.

- timestamp: 2026-08-01T14:47:00Z
  checked: Full adjacent automated suites
  found: AI backend passed 266/266, Web server passed 238/238, client unit passed 107/107 across 16 files, and Phase 09 evidence contracts passed 50/50. The SvelteKit production build and focused mocked browser readiness 4/4 also passed.
  implication: The fix is compatible with unrelated engines, call/session behavior, storage/migrations, current evidence tooling, and all local client contracts.

- timestamp: 2026-08-01T14:53:00Z
  checked: Fix-acceptance revert-and-reconfirm counterfactual
  found: Temporarily restoring only the old source-rate soundfile alignment hunk made the 48-kHz regression fail again with qwen3_transcript_mismatch; reapplying the canonical 16-kHz decode made the same test pass 1/1.
  implication: The resampling hunk, not another concurrent change, causally fixes the reported transcript rejection.

- timestamp: 2026-08-01T14:55:00Z
  checked: Final diff/no-op/mutation/static guardrail
  found: git diff --check and Python compilation pass; no Stryker or Python mutation runner is configured. The diff's large deletion component is the explicitly authorized removal of the reference-authorization policy, while transcript checks, byte/path integrity, acoustic mismatch rejection, prompt readiness, and live-call streaming remain exercised by passing tests. No authorization fields/copy remain in current client/server runtime code.
  implication: Mutation tooling is honestly skipped; the agent-authored regression and exact-hunk counterfactual provide independent causal protection, and the deletion is justified by the recorded RCA/product-policy change rather than behavior suppression.

## Eliminated

- hypothesis: Upload-implies-authorization removed ReferenceSelection.authorization_basis/use_scope, causing fixture-bundle AttributeError.
  evidence: The current frozen ReferenceSelection dataclass and both resolver/fallback constructors still define and populate both fields; fixture-bundle writing can dereference them.
  timestamp: 2026-08-01T15:10:00Z

## Resolution

root_cause: The original Voice Lab defect remains fixed as recorded. The first deployment continuation was a stale exact-core saved-voice caller plus an incomplete sanitized exception boundary. The second deployment failure required three confirmed contributors: WebRTC can deliver already-sent sequential RTP after the server has correctly drained producer/bridge/track and acknowledged cancellation; the browser had no bounded receiver-side mute/drain and ignored automatic interrupted events, leaving that tail audible; and the hardware tracer used an undocumented fixed 100-ms grace instead of a shared contract and independent zero-pending-audio evidence.
fix: Reuse RayMe's canonical mono 16-kHz decoder for Qwen alignment; remove reference-source/basis/scope UI and API fields plus qwen3_authorization persistence/runtime gates; add migration 0008 to purge legacy metadata; update current Voice Lab/live-call/evidence callers and operator docs to upload-implies-authorization while preserving asset integrity, transcript alignment, opaque prompt identity, and live streaming. Remove the stale exact-core `selection` keyword and sanitize unexpected runner exceptions. For cancellation, advertise a 250-ms receiver-drain value on the backend interrupted event and control response, preserve it through the Web server, immediately mute the browser through that bounded drain on button and automatic-event paths, then unmute automatically. The hardware tracer now records transport-tail frames inside the bound, rejects audible frames beyond it, requires explicit zero server pending audio, and still forbids false normal completion.
verification:
  target_test: { result: pass, test: ai-backend/tests/test_model_manager.py::test_qwen_alignment_resamples_uploaded_reference_like_voice_lab_transcription }
  mutation_check: { result: skipped, reason_if_skipped: no Stryker or Python mutation runner is configured; exact-hunk counterfactual was killed by the target regression, mutant_killed: true }
  no_op_deletion: { result: pass, deletion_justified_by_rca: true, reason: explicit product-policy removal; alignment, integrity, and live-call behavior remain active }
  adjacent_tests: { result: pass, suites_run: [AI backend 266, Web server 238, client unit 107, Phase 09 evidence 50, mocked Qwen browser 4, live-call invariants 7, SvelteKit production build] }
  revert_and_reconfirm: { result: pass, bug_returned_on_revert: true, fixed_on_reapply: true }
  guardrail_verdict: accepted
  deployment_continuation:
    target_tests: { result: pass, tests: [test_core_runner_uses_current_saved_voice_helper_contract, test_runner_main_sanitizes_unexpected_exceptions_without_private_detail], red_before_fix: true, green_after_fix: true }
    mutation_check: { result: pass, tooling: manual targeted counterfactuals because no configured Python mutation runner exists, mutants_killed: [restored stale selection keyword, removed unexpected-exception normalization] }
    no_op_deletion: { result: pass, deletion_justified_by_rca: true, reason: the only production deletion removes the obsolete keyword that deterministically caused the TypeError; the class-only failure path is an additive safety boundary }
    adjacent_tests: { result: pass, suites_run: [Phase 09 evidence 52, OMEN deploy contract 5, runner dry-run, Python compilation, git diff check] }
    revert_and_reconfirm: { result: pass, both_bugs_returned_on_independent_revert: true, both_fixed_on_reapply: true }
    guardrail_verdict: accepted
  cancellation_continuation:
    target_tests: { result: pass, tests: [CallSession event contract, AI interrupt response contract, Web server propagation, client mute and drain boundary, hardware tracer drain partition and fail-closed pending metric, desktop/mobile browser manual and automatic drain], red_before_fix: true, green_after_fix: true }
    mutation_check: { result: pass, tooling: manual targeted counterfactuals because no configured mutation runner exists, mutants_killed: [missing backend event field, discarded Web-server field, receiver drain ignored by client, restored arbitrary 100-ms tracer window, missing pending metric treated as zero] }
    no_op_deletion: { result: pass, deletion_justified_by_rca: true, reason: behavior is additive and bounded; the only replaced behavior is the disproven arbitrary tracer grace and always-audible receiver policy during interruption }
    adjacent_tests: { result: pass, suites_run: [AI backend 276, Web server 243, client unit 109, Phase 09 evidence 61, call-toolbar desktop/mobile 2, SvelteKit production build, Python compilation, git diff check] }
    revert_and_reconfirm: { result: pass, all_bugs_returned_on_independent_mutation: true, all_fixed_on_reapply: true }
    guardrail_verdict: accepted
    human_verification: { result: pass, deployed_commit: 288c05b4742dda0aac76050658aa12a44041102e, canonical_deploy_exit: 0, hardware_tracer: pass, physical_voice_lab: pass, deployed_live_call_playwright: 4_of_4 }
files_changed:
  - ai-backend/app/models/model_manager.py
  - ai-backend/tests/test_model_manager.py
  - web-ui/client/src/lib/api/types.ts
  - web-ui/client/src/lib/api/calls.ts
  - web-ui/client/src/lib/call/audio.ts
  - web-ui/client/src/routes/voice-lab/+page.svelte
  - web-ui/client/src/routes/call/[threadId]/+page.svelte
  - web-ui/client/tests/unit/voice-lab.test.ts
  - web-ui/client/tests/e2e/qwen3-readiness.spec.ts
  - web-ui/client/tests/e2e/live-call.spec.ts
  - web-ui/client/tests/e2e/call-toolbar.spec.ts
  - web-ui/client/tests/e2e/helpers/acceptance.ts
  - web-ui/client/tests/unit/call-audio.test.ts
  - web-ui/server/app/api/voices.py
  - web-ui/server/app/domain/voice_service.py
  - web-ui/server/app/domain/call_service.py
  - web-ui/server/alembic/versions/0008_remove_qwen3_authorization.py
  - web-ui/server/tests/test_voices.py
  - web-ui/server/tests/test_calls.py
  - ai-backend/app/call/session.py
  - ai-backend/app/api/webrtc.py
  - ai-backend/tests/test_call_session.py
  - ai-backend/tests/test_webrtc_signaling.py
  - web-ui/server/tests/test_migrations.py
  - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-hardware-tracer.py
  - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py
  - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/test_phase09_evidence.py
  - .planning/STATE.md
  - .planning/ROADMAP.md
  - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-UI-SPEC.md
  - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-UAT.md
  - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-OMEN-HANDOFF.md
oracle_type: specified

## Prevention

### Blameless branching 5-Whys

- **Code / contract branch:** Voice Lab transcription canonicalized uploads to mono 16 kHz, while save-time Qwen alignment passed a source-rate ndarray into faster-whisper, whose ndarray path assumes 16 kHz. The two callers looked equivalent but had no shared representation contract or regression comparing their actual samples. Authorization policy was also duplicated through UI, API, persistence, and runtime, making an obsolete product requirement expensive to remove consistently. The exact-core runner had a second saved-voice caller and a narrow exception boundary that the initial refactor tests did not exercise.
- **Environment / timing branch:** A real 48-kHz stereo sample exposed the hidden ndarray sample-rate assumption. Separately, WebRTC can retain already-sent RTP after server-side producer, bridge, and track queues are empty; variable delivery timing crossed the cancellation acknowledgement. The browser had no receiver-side drain state, and the hardware tracer used an unrelated fixed 100-ms grace, so one environmental scheduling tail caused both audible continuation and a misleading deployment rejection.
- **AND-gate:** The cancellation symptom required both retained transport audio and a receiver that stayed audible. The deployment rejection additionally required a measurement gate that conflated post-ack arrival with post-cancel server production.

### Why this was not caught

No existing gate compared Voice Lab transcription and Qwen alignment at a non-16-kHz input representation. Tests covered server queue cancellation but not detached browser Audio-element audibility after manual and automatic interruption, and the hardware tracer did not require independent zero-pending-audio evidence. Exact-core tests also did not cover every saved-voice caller or ordinary unexpected exception normalization.

### Recurrence guards

- `ai-backend/tests/test_model_manager.py::test_qwen_alignment_resamples_uploaded_reference_like_voice_lab_transcription` binds save-time alignment to canonical 16-kHz decoding while existing mismatch tests continue rejecting unrelated transcripts.
- Voice Lab client/server and migration regressions require upload-implied authorization and reject removed authorization fields while preserving asset hashes, containment, and nonblank transcript validation.
- `web-ui/client/tests/unit/call-audio.test.ts` and `web-ui/client/tests/e2e/call-toolbar.spec.ts` enforce bounded manual and automatic receiver mute/unmute on desktop and mobile Chromium.
- `test_phase09_evidence.py::test_hardware_tracer_distinguishes_bounded_transport_drain_from_late_audio` and `::test_hardware_tracer_requires_explicit_zero_pending_audio_metric` separate transport tail from true late audio and fail closed on missing server quiescence evidence.
- The canonical OMEN deploy gate now exercises Qwen short/medium/long early playback, no whole-WAV fallback, bounded cancellation drain, zero pending samples, recovery, and deployed live-call browser cycles.
