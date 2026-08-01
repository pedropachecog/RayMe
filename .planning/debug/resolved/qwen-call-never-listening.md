---
status: resolved
trigger: "Exact deployed Phase 09 live-call.spec.ts at OMEN commit 2ed38e33d2d475b7465cdaa788f00858e0b6d6d6 passed four provenance/path guards, but both desktop and mobile real-call cases never reached Listening and observed no /api/calls/{id}/offer response within 60 seconds."
created: 2026-08-01T11:20:00Z
updated: 2026-08-01T14:08:00Z
---

# Qwen Call Never Reaches Listening

## Symptoms

**Expected behavior:** The exact deployed desktop and mobile Chromium live-call cases open the generated fixture call route, reach `Listening`, connect ICE/datachannel, and complete two real user-to-Qwen cycles.

**Actual behavior:** The provenance and fixture-path tests pass on both browser projects. The real desktop and mobile cases each time out after 60 seconds waiting for `voice-visualizer` text `Listening`. Their pending `POST /api/calls/{id}/offer` response wait ends when the test stops.

**Error messages:**

```text
Locator: getByTestId('voice-visualizer').getByText('Listening')
Expected: visible
Timeout: 60000ms
Error: element(s) not found

page.waitForResponse: Test ended while waiting for POST /api/calls/{id}/offer
```

**Timeline:** First observed in the final real-browser rerun after deploying `2ed38e3`. The same suite passed 6/6 at pre-review commit `3501a1a`. The new exact commit already passed Alembic `0002 -> 0007`, the production Qwen streaming/cancellation tracer, 50-turn core evidence, canonical public-call scenario, independent verifier, acoustic stability, and leak scan.

**Reproduction:** Run the exact Plan 09-15 live E2E command with `RAYME_ENABLE_LIVE_E2E=1`, canonical OMEN URLs, expected commit `2ed38e3`, Qwen engine, and the four hash-bound `.local` fixtures. Results: 4 passed, 2 failed in 2.8 minutes.

## Current Focus

hypothesis: RESOLVED — the loop-safe fake-mic response window permits completed AI turns, and closed-peer cleanup prevents retained Qwen ownership.
test: Canonical deployment at exact commit 2721a4ef3ddfadf9cbc47acb0522cb41bc62fbae plus the exact six-case desktop/mobile browser suite and pre/post WebRTC status checks.
expecting: MET — both real browser profiles complete two user/AI cycles, all four guards pass, and active_sessions returns to zero.
next_action: None — the session is archived; the durable knowledge-base entry is the fallback because MemPalace is disabled for this project.
bug_class: heisenbug-mandelbug across sequential browser tests (persistent server state after an earlier deterministic timeout)
user_goal_preservation: "This repair changes only Phase-09 evidence-session cleanup. Real live calls still stream early audio, remain interruptible, and keep the existing WebRTC/TTS path unchanged."
reasoning_checkpoint:
  hypothesis: "The live browser suite fails because its 2.5 s fake-mic tail is shorter than VAD-close plus STT/LLM/TTS response latency, causing the newly correct spoken-barge-in path to cancel every AI turn; when Playwright tears down the failed desktop peer, CallSession ignores connectionState=closed and leaves the capacity-one prompt lease owned."
  confirming_evidence:
    - "The exact 8.843 s WAV is voiced through 5.42 s and silent only 3.44 s; after 1.8 s VAD close, 0.63–0.75 s STT, and about 0.8 s LLM first token, only roughly 0.1–0.2 s remains before loop restart."
    - "For at least 35 desktop turns, OMEN logs show non-silent ai_audio_started followed 140–420 ms later by vad.barge_in, speak.cancelled, /speak 502, and interrupted; no ai_done is emitted."
    - "After Playwright closes the desktop peer, logs show connectionState=closed and current /webrtc/status still reports active_sessions=1; handle_connection_state_change handles only failed. Mobile offer then returns 502 Voice preparation failed."
  falsification_test: "The timing cause would be false if cancellation occurred without vad.barge_in or outside the loop restart budget; the lifecycle cause would be false if connectionState=closed released the lease or status returned zero active sessions after teardown. Direct logs contradict all of those falsifiers."
  fix_rationale: "A bounded 12 s trailing response window keeps the looping synthetic mic silent across turn close, STT, LLM, early streaming, and short playout while leaving production barge-in unchanged. Treating an unterminalized closed peer as ended releases the lease at the backend owner boundary and also protects real abrupt tab closure."
  blind_spots: "Local tests cannot prove exact OMEN timing or Chromium loop behavior after source change; parent must canonically deploy and rerun the same desktop/mobile suite. The 12 s bound is deliberately conservative but still permits many cycles inside the 300 s test window."
  candidate_causes:
    - "code: 4f6efd9 adds correct speaking-state VAD barge-in, while handle_connection_state_change ignores closed peers."
    - "config/data: FAKE_MICROPHONE_TRAILING_SILENCE_MS remains 2500 and the exact copied WAV has only 3.44 s closing silence."
    - "environment: Chromium loops the finite fake-audio file and both projects share one capacity-one Qwen process."
  and_gate: "yes — desktop requires the short looping fixture plus real response latency plus correct barge-in; mobile additionally requires the resulting desktop abort plus ignored closed-peer cleanup plus shared capacity-one prompt ownership."

## Evidence

- timestamp: 2026-08-01T11:00:51Z
  checked: "Exact deployed core and acoustic release gates."
  found: "Commit 2ed38e3 passed Qwen runtime/model identity, early streaming, no whole-WAV fallback, cancellation/recovery, 50-turn soak, public-call scenario, independent verification, speaker scoring, and privacy scan."
  implication: "The runtime and backend production seams can complete calls; the browser failure occurs earlier or through a distinct fixture/UI path."

- timestamp: 2026-08-01T11:20:00Z
  checked: "Exact desktop/mobile live-call.spec.ts output."
  found: "Four provenance/path tests passed. Both call cases timed out at the same Listening locator after 60 seconds, and neither waitForResponse observed a completed offer response. Error contexts were saved under web-ui/client/test-results for desktop and mobile."
  implication: "The failure is deterministic across device profiles and lies before the first completed offer/Listening transition."

- timestamp: 2026-08-01T12:01:00Z
  checked: "Phase-0 semantic and durable debug knowledge-base recall."
  found: "No MemPalace tool or CLI is available. The durable knowledge base contains only qwen-core-invalid-json, whose retained-schema/500 signature has no two-token overlap or behavioral match with the browser's missing Listening/offer transition."
  implication: "There is no known-pattern candidate to privilege; proceed from captured browser evidence."

- timestamp: 2026-08-01T12:02:00Z
  checked: "Desktop and mobile Playwright error-context page snapshots."
  found: "Both routes loaded their distinct fixture thread/character successfully, showed secure context and media devices ready, then rendered call state Failed with alert text Voice preparation failed. Neither rendered the live controls or Listening state."
  implication: "The browser route is not stalled or missing; it deterministically entered a voice-preparation failure branch before offer creation. The relevant categories are data/API-contract, error handling, or environment/config at preparation—not synthesis/playout."

- timestamp: 2026-08-01T12:03:00Z
  checked: "Exact error-text producers and offer/preparation symbol map."
  found: "The client call page has explicit blocking branches for qwen3_* and call_tts_prepare_* codes. Server create_call_offer calls _prepare_call_voice when reference_payload exists; that helper can raise call_tts_prepare_failed/mismatch/unavailable before returning the offer response. The live test's response waiter requires response.ok()."
  implication: "A failed offer can be present on the wire yet appear as 'no offer response' to the test. The next discriminating evidence is the exact failed readiness/error payload and the commit diff that changed it."

- timestamp: 2026-08-01T12:04:00Z
  checked: "Complete browser beginCall/connectBrowserMedia failure flow and server create_call_offer/_prepare_call_voice readiness flow."
  found: "The browser does create and send the offer. Server create_call_offer first obtains an AI SDP answer, then synchronously calls /webrtc/sessions/{session}/prepare and withholds its 2xx response until preparation is ready. _call_preparation_readiness forcibly changes prompt state to failed with call_tts_prepare_mismatch whenever returned prompt.voice_key differs from service.voice_preparation_for_call().backend_voice_id. Any processing error is parsed by CallApiError and shown as the exact blocking panel observed."
  implication: "The failure is inside synchronous Qwen voice preparation on the offer request, not before offer issuance. A strict identity mismatch, worker failure, or preparation environment error remains; commit differential and exact server logs can distinguish them."

- timestamp: 2026-08-01T12:05:00Z
  checked: "Known-good 3501a1a to deployed 2ed38e3 revision delta and worktree state."
  found: "HEAD exactly matches deployed 2ed38e3. The delta contains 24 commits and changes the entire call/preparation stack (session.py, model_manager.py, tts_qwen3*, webrtc.py, calls.py, call_service.py) plus authorization migrations. The final 2ed38e3 commit is migration/deploy-specific, while several earlier review fixes add prompt leases and terminal-state coordination. Existing modified phase result JSON files are user/orchestrator evidence and must remain untouched."
  implication: "The initial revision range is too broad for a single inference; path-scoped commit delta is required. Deployment migration remains a separate config/data candidate, not yet ruled out."

- timestamp: 2026-08-01T12:06:00Z
  checked: "Path-scoped commit history for the call/Qwen preparation boundary."
  found: "Sixteen commits in the range touch relevant runtime files. The strongest code candidates are 647bd23 (lease live-call Qwen prompts), 7cdcc2e (refcount shared prompt leases), 2af2746 (coordinate prompt leases with session terminal state), plus worker provenance commits 3b13d70/ae56c71 and the 0005 authorization repair 0383315."
  implication: "The patch set remains branched across code, environment, and retained data. Exact deployed logs should select the branch before patch inspection."

- timestamp: 2026-08-01T12:07:00Z
  checked: "Read-only OMEN web log offer statuses at the end of the failed browser run."
  found: "The last two offer entries are call_a36be2f97cd4483b9ab8b4eabb62e97d and call_6cb8212d50d746d8af21b3722e02e58a; both POST /api/calls/{id}/offer requests returned 502 Bad Gateway. Earlier exact-commit calls in the same log returned 200."
  implication: "The Playwright 'no offer response' interpretation is false: both offer responses completed non-ok. The shared regression is a server/AI processing failure surfaced correctly by the UI; server reachability and route issuance are eliminated."

- timestamp: 2026-08-01T12:08:00Z
  checked: "Read-only filtered OMEN AI-backend tail corresponding to the two failed offers."
  found: "The final two prepare requests are POST /webrtc/sessions/rtc_554953e6813e47699dd5a1c76d4ab8bd/prepare and rtc_4f3446a802d44913893ccda8284be9a9/prepare; both returned 409 Conflict. Earlier Phase-09 prepare calls in the same process returned 200."
  implication: "Hardware/model loading, network reachability, and generic Qwen preparation are eliminated. The bug is an explicit per-session conflict for fresh browser sessions, strongly implicating session lifecycle or lease ownership rather than fixture audio/transcript processing."

- timestamp: 2026-08-01T12:09:00Z
  checked: "All current 409 branches in AI prepare_session_speech and the 2af2746 terminal/lease coordination patch."
  found: "Prepare returns 409 only when the session is already ended/failed, when payload voice/engine differs from the offer session, or when the session becomes terminal during preparation. Commit 2af2746 added both terminal guards. The web server's create_call_offer obtains the AI answer first but does not return it to the browser until /prepare succeeds, so the browser cannot set the remote description during this window."
  implication: "A server-side peer failure while its answer is withheld would deterministically become the observed new 409 only after 2af2746. Exact session lifecycle logs can confirm or falsify this without changing OMEN."

- timestamp: 2026-08-01T12:10:00Z
  checked: "Exact AI lifecycle logs for both failed rtc sessions."
  found: "Each session logged offer.answered after about 5 seconds, then ICE checking and connection state connecting, then the 409 prepare response. Only after the 409 did the web server call /end and close the session."
  implication: "The terminal-session guard was not the initial conflict. The 409 must come from selection mismatch or a Qwen/model-manager exception mapped to conflict."

- timestamp: 2026-08-01T12:11:00Z
  checked: "Qwen exception mapping, ModelManager prompt-lease rules, and current deployed /webrtc/status."
  found: "Qwen3PromptLeaseError(qwen3_prompt_leased) is explicitly mapped to HTTP 409. ModelManager rejects a different voice/cache identity while any lease owner remains. Current status is healthy at commit 2ed38e3 with one active session and selected prompt ready for voice_ca2fb1c7086049389cafde0842b74cbf. The immediately preceding AI-log prepare was phase09-finish-dadadcea26b24b60 with 200, followed by both browser 409s."
  implication: "A retained Phase-09 evidence lease now explains the exact status, ordering, and both fresh-fixture failures more completely than payload mismatch. The missing end/cleanup must be confirmed at producer and log level."

- timestamp: 2026-08-01T12:12:00Z
  checked: "Every retained AI log line for phase09-finish-dadadcea26b24b60."
  found: "The session offered and connected, its final /prepare returned 200, and later its data channel and peer states closed. There is no POST /webrtc/sessions/phase09-finish-dadadcea26b24b60/end anywhere in the log. Status later still reports one active session and the prepared voice."
  implication: "The evidence session is the surviving lease owner. Closing the client peer alone does not run CallSession.end/fail because the handler reacts only to connectionState=failed, so the capacity-one prompt remains locked."

- timestamp: 2026-08-01T12:13:00Z
  checked: "Finish evidence producer and normal hardware-tracer cleanup paths."
  found: "OmenFinishLifecycle.reload_qwen creates phase09-finish-* and opens WebRtcCapture; prewarm_selected_voice acquires the prompt lease; assert_qwen_ready calls only peer.close(). The normal hardware tracer explicitly POSTs /webrtc/sessions/{session_id}/end before peer.close(), and another core lifecycle cleanup at lines 608-614 does the same."
  implication: "The lease leak is a concrete omission in one evidence lifecycle, not a backend lease bug. The deployed browser regression requires the omitted end plus the new capacity-one lease enforcement (AND-gate)."

- timestamp: 2026-08-01T12:14:00Z
  checked: "Finish orchestration and regression coverage."
  found: "run_finish_acoustic_leak has no cleanup/finally hook; assert_qwen_ready owns the peer close only on the success path. Existing fake lifecycle tests assert stages through readiness but have no close event and no assertion that an AI session is ended."
  implication: "Both success and post-reload failure paths can leak. The smallest durable fix is an explicit idempotent lifecycle close contract that POSTs /end before closing the peer, invoked on success and exception, with regression coverage."

- timestamp: 2026-08-01T12:16:00Z
  checked: "First RED regression invocation with system python3."
  found: "No tests executed because /usr/bin/python3 has no pytest module."
  implication: "This is an environment-selection issue, not evidence about the regression; locate the project test environment and rerun."

- timestamp: 2026-08-01T12:17:00Z
  checked: "Focused regression suite with uv-managed ai-backend test environment before implementation."
  found: "All five selected cases failed for the intended reason: success and three failure stages never recorded close, and OmenFinishLifecycle has no close method."
  implication: "The minimized regression is RED with a specified oracle and directly exercises both the missing orchestration hook and missing AI /end behavior."

- timestamp: 2026-08-01T12:18:00Z
  checked: "Focused regression suite after minimal cleanup implementation."
  found: "All five selected cases pass: success cleanup, scorer failure, reload failure, prewarm failure, and explicit /end-before-peer-close ordering."
  implication: "The target regression is GREEN and covers the root-cause cleanup contract across the defect boundary (no session, session creation failure, leased session, successful finish)."

- timestamp: 2026-08-01T12:19:00Z
  checked: "Full adjacent Phase-09 evidence suite, Python compilation, and diff hygiene."
  found: "test_phase09_evidence.py passed 50/50; both changed Python files compile; git diff --check passes."
  implication: "Adjacent evidence acquisition, verification, privacy, and lifecycle contracts remain intact locally."

- timestamp: 2026-08-01T12:20:00Z
  checked: "Exact fix diff and configured mutation tooling."
  found: "The source diff adds explicit session termination, failure cleanup, and cleanup-error recording; the only deletion moves peer close out of readiness into the owner cleanup method and is justified by the RCA. Tests add rather than weaken assertions. No Stryker/Python mutation configuration is present."
  implication: "No-op/deletion signal passes. Automated mutation signal must be recorded skipped; the focused test's RED/GREEN and explicit revert-reconfirm provide the available causal check."

- timestamp: 2026-08-01T12:21:00Z
  checked: "Controlled source-only revert with new regressions retained."
  found: "All five focused cleanup cases returned to the same intended failures: no success/failure close event and no OmenFinishLifecycle.close method."
  implication: "The bug returned when only the source fix was removed; reapplication must restore GREEN to complete causal verification."

- timestamp: 2026-08-01T12:22:00Z
  checked: "Focused regression suite after reapplying the identical source fix."
  found: "All five focused tests pass again."
  implication: "Revert-and-reconfirm passes: the regression returns without the source fix and disappears when the same fix is reapplied."

- timestamp: 2026-08-01T12:23:00Z
  checked: "Global diff hygiene and worktree scope."
  found: "Global git diff --check reports thousands of pre-existing trailing-whitespace findings in modified Phase-09 result JSON files. Worktree status confirms those result files and resolved debug artifacts were already outside this fix's ownership; this debugger changed only the runner, its test, and the active debug file."
  implication: "Do not normalize or revert parent/user evidence. Use owned-file diff hygiene, which passed before the controlled revert, as the applicable signal."

- timestamp: 2026-08-01T12:24:00Z
  checked: "Final owned-file diff hygiene after fix reapplication."
  found: "git diff --check passes for 09-run-omen-evidence.py and test_phase09_evidence.py."
  implication: "The owned fix is clean and ready for parent commit/deployment verification."

- timestamp: 2026-08-01T12:31:00Z
  checked: "Canonical deployment and focused evidence rerun reported by parent."
  found: "Commit f7feb6c was deployed canonically; the exact core/finish evidence slice passed, and immediately before the browser run /webrtc/status showed active_session_count=0 with the selected Qwen prompt ready."
  implication: "The original finish-evidence lifecycle leak is fixed in the deployed environment and did not contaminate the new browser run."

- timestamp: 2026-08-01T12:31:00Z
  checked: "Same-commit desktop/mobile browser-suite result reported by parent."
  found: "Four tests passed and two failed. Desktop persisted at least two ai_speech events and observed at least two aiAudioStartedTurnIds, but aiDoneEvents stayed zero for 300000 ms at live-call.spec.ts:216. Mobile then failed to reach visible Listening within 60000 ms at line 192."
  implication: "A later completion-signal failure is now the primary defect; the mobile startup failure may be independent or downstream state contamination after desktop abort."

- timestamp: 2026-08-01T12:33:00Z
  checked: "Live browser test control flow through the desktop timeout and normal hangup."
  found: "The test waits for ai_done before the only explicit End Call action and has no try/finally cleanup. Therefore any assertion failure or timeout at line 216 prevents the browser from POSTing /api/calls/{id}/end."
  implication: "The mobile failure can be caused by desktop failure cleanup omission even if its own startup path is healthy; this is a concrete second link to verify against logs rather than an independent mobile regression by default."

- timestamp: 2026-08-01T12:36:00Z
  checked: "Complete live signal recorder and desktop/mobile Playwright error contexts."
  found: "aiDoneEvents counts browser debug POSTs for received datachannel.message events whose event_type is ai_done; it is not inferred from transcript persistence. The desktop page remained in Composing with many finalized user/AI turns, but every AI turn was followed by a visible Speech playback failed notice. Mobile entered Failed with Voice preparation failed."
  implication: "Desktop has a real post-ai_audio_started failure and no ai_done, not merely a faulty transcript oracle. Mobile's later preparation failure is consistent with the desktop test abort leaving its active call/lease behind."

- timestamp: 2026-08-01T12:39:00Z
  checked: "Source map for ai_audio_started, ai_done, and call_tts_failed."
  found: "The browser debug recorder sees every received data-channel event before UI dispatch. AI session tests and handlers establish that ai_done is terminal only after successful stream/playout completion, while the recoverable synthesis exception maps to call_tts_failed and the visible Speech playback failed notice."
  implication: "Zero ai_done is consistent with the repeated real playback failures. The next discriminating evidence is the raw exception in OMEN logs, not a relaxation of the browser oracle."

- timestamp: 2026-08-01T12:43:00Z
  checked: "Browser failure recovery and AI `speak_text` exception boundary."
  found: "The browser correctly turns retryable call_tts_failed into a transcript notice and returns to listening. AI `speak_text` catches generic exceptions, emits call_tts_failed, and discards exception type/message without logging it."
  implication: "Repeated calls demonstrate intentional recovery, but current observability may hide the precise post-start exception. The complete streaming path and any lower-layer Qwen logs are needed before a fix can be justified."

- timestamp: 2026-08-01T12:48:00Z
  checked: "Complete streaming bridge and broad read-only OMEN log slice."
  found: "The producer catches its adapter exception and publishes that exception through the bounded bridge; the async consumer re-raises it, and the outer boundary emits call_tts_failed without the cause. Web logs identify desktop call_7e9613b0458a4f2caa6f164f466e4b8d with at least 35 consecutive speech_turn.failed results and no observed /end before mobile. Mobile call_92237cc2464a442ba9857318d31ffdc3 received offer 502 and then /end 200."
  implication: "The desktop failure is stable per turn, not intermittent playback policy. The unended desktop-to-mobile contamination link is directly supported; the remaining root-cause question is why the Qwen producer fails after initial chunks."

- timestamp: 2026-08-01T12:52:00Z
  checked: "Live OMEN `/webrtc/status` after the failed serial browser suite."
  found: "Status reports active_sessions=1 with Qwen resident and the selected prompt still ready/leased after mobile ended its own failed call."
  implication: "The suite leaves exactly one active owner behind, matching the desktop call that timed out before /end. This directly confirms mobile contamination; concise log filters still need rerun because the first PowerShell predicate was misquoted."

- timestamp: 2026-08-01T12:57:00Z
  checked: "Concise exact-call web log and lower-level AI session log."
  found: "Desktop session rtc_6f0acc1fc1004471b93401389f758ca7 received offer 200. For every observed turn, the browser received ai_audio_started with a non-silent 320 ms chunk while remoteAudioContextState=running, immediately followed by speech_turn.failed/call_tts_failed. AI logs show many 15404-byte streamed chunks, completed playback waits, and an asyncio.exceptions.InvalidStateError: invalid state during this exact session."
  implication: "Browser autoplay and empty audio are refuted. The first concrete lower-layer failure is an invalid async state in the streamed outbound-audio lifecycle; full traceback is required to establish whether it causes or merely accompanies the call_tts_failed events."

- timestamp: 2026-08-01T13:02:00Z
  checked: "Full InvalidStateError traceback and exact desktop session event sequence."
  found: "InvalidStateError originates in aioice.stun.Transaction.__retry after its future was already resolved and is unrelated to the speech request. Every TTS request instead follows the repeatable sequence ai_audio_started, VAD barge_in after 7–21 voiced frames (140–420 ms), speak.cancelled, /speak 502, and interrupted. Playback waits themselves report completed=True."
  implication: "The playback state-machine hypothesis is eliminated. Desktop ai_done is absent because real barge-in cancels every reply; investigate why the automated mic overlaps each AI response while preserving production interruption behavior."

- timestamp: 2026-08-01T13:06:00Z
  checked: "Known-good 3501a1a to current path-scoped CallSession diff."
  found: "The speaking-state VAD/barge-in path, onset buffer, energy gate, and interrupt handoff were added after the known-good revision. The current handler requires sustained energetic VAD-positive input and intentionally cancels active speech; this is production behavior required by the live-call invariant. The same live E2E fake-mic contract was not visibly adapted in the diff."
  implication: "The revision difference explains why a continuously looping fixture that previously passed can now self-interrupt. The safe repair target is deterministic fixture/test pacing plus failure cleanup, not disabling or delaying real barge-in."

- timestamp: 2026-08-01T13:10:00Z
  checked: "Fake-microphone provenance and concise revision history."
  found: "The 390036-byte qwen3-fake-mic.wav is produced by the canonical hardware tracer as one SAPI utterance followed by a fixed closing-silence append, then copied by deploy-omen.sh. The live test supplies it through Chromium's looping fake-audio capture. Commit 4f6efd9 introduced spoken VAD barge-in after the known-good run; no later live-test/fixture commit appears in the path history. ffprobe/ffmpeg are unavailable locally."
  implication: "The fixture contract was designed only to close VAD, not to coexist with newly interruptible AI playback. Exact stdlib waveform measurement can establish whether its loop silence budget is the causal timing boundary."

- timestamp: 2026-08-01T13:14:00Z
  checked: "Exact copied fake-microphone waveform and VAD/latency budget."
  found: "The WAV is mono PCM16 at 22050 Hz, 8.843 s total. Its voiced content runs through about 5.42 s and closing silence through 8.86 s, only 3.44 s. The generator explicitly appends 2500 ms and its regression asserts merely >1800 ms. Production barge-in requires 120 ms at RMS >=200. Server logs show 1.8 s turn-closing silence, 0.63–0.75 s STT, ~0.8 s LLM first token, then barge-in 0.14–0.42 s after AI start."
  implication: "The measured loop budget quantitatively predicts the deployed failure. A larger bounded trailing response window is a falsifiable, root-directed fixture fix that preserves early playback and barge-in."

- timestamp: 2026-08-01T13:22:00Z
  checked: "Focused pre-fix regressions for loop-safe fake-mic pacing and remote-closed lease cleanup."
  found: "Both tests fail for their specified reasons: FAKE_MICROPHONE_TRAILING_SILENCE_MS is 2500 instead of >=12000, and handle_connection_state_change leaves a closed peer's session in listening with no prompt-lease release."
  implication: "The minimized reproduction is RED on both contributing defects. Source behavior can now be changed one boundary at a time without weakening barge-in or lease enforcement."

- timestamp: 2026-08-01T13:25:00Z
  checked: "Focused post-fix regressions."
  found: "Both specified-oracle cases pass after the minimal source changes: the generated fixture window is >=12000 ms, and a closed peer ends the session with connection_closed while releasing the installed prompt lease."
  implication: "Both defect boundaries are GREEN. Broader adjacent and causal verification remain before the fix can be accepted."

- timestamp: 2026-08-01T13:29:00Z
  checked: "First full CallSession adjacent-suite run."
  found: "67 tests passed and the existing spoken-VAD/Qwen cancellation stress case failed when its speech task raised CancelledError at a one-second wait. The failure path does not invoke the changed connection-state handler or evidence constant; later chained suites did not run."
  implication: "The guardrail is not yet accepted. Repeated isolated execution is required to classify a timing-sensitive adjacent failure before deciding whether it is a regression or pre-existing flake."

- timestamp: 2026-08-01T13:33:00Z
  checked: "Initial isolated reruns of the spoken-VAD/Qwen cancellation case."
  found: "Two independent isolated executions passed. The ten-process loop exceeded the command's execution window before completing, so no ten-run verdict was recorded."
  implication: "The deterministic-regression hypothesis is weakened but not eliminated; use repeated node IDs in one pytest process for a complete stability sample."

- timestamp: 2026-08-01T13:36:00Z
  checked: "Additional isolated spoken-VAD/Qwen cancellation rerun."
  found: "The case passed again; pytest deduplicated repeated identical node IDs, yielding three isolated passes total after the one suite-order failure."
  implication: "The failure is timing/order-sensitive rather than deterministic. A second full-suite run is the next applicable stability check."

- timestamp: 2026-08-01T13:39:00Z
  checked: "Second full CallSession adjacent-suite run."
  found: "All 68 tests passed, including spoken VAD barge-in, Qwen early streaming, whole-synthesis rejection, cancellation, failed reconnect, idempotent end, and the new closed-peer lease cleanup."
  implication: "The one prior cancellation timeout is a non-causal existing timing debt: neither changed branch is reachable in that test, three isolated reruns and the complete rerun pass. Record it explicitly, but continue the remaining applicable signals."

- timestamp: 2026-08-01T13:43:00Z
  checked: "Full Phase-09 evidence suite and attempted full WebRTC signaling suite."
  found: "Phase-09 evidence passed 50/50. The full signaling process exceeded the command execution window after emitting progress dots; it produced no test failure or final verdict, and subsequent chained static checks did not run."
  implication: "Evidence/generator adjacency is green. Use a focused signaling selection covering Qwen, leases, connection, and end rather than misreport an interrupted suite."

- timestamp: 2026-08-01T13:46:00Z
  checked: "Focused WebRTC signaling adjacency."
  found: "The Qwen/prompt-lease/connection/end selection passed 20/20 with 21 unrelated cases deselected. Only existing dependency deprecation warnings were emitted."
  implication: "Direct signaling and lease contracts remain green. Static and causal guardrail signals remain."

- timestamp: 2026-08-01T13:49:00Z
  checked: "Compilation, owned diff hygiene, and exact fix diff."
  found: "All four changed Python files compile; owned git diff --check passes. The source diff changes one fixture constant and adds one closed-state terminal branch; tests strengthen the response-window oracle and add closed-peer lease cleanup. There are no behavior deletions or weakened assertions."
  implication: "No-op/deletion and static signals pass. Controlled source-only revert remains to prove both tests depend on the behavior changes."

- timestamp: 2026-08-01T13:52:00Z
  checked: "Controlled source-only revert with both regressions retained."
  found: "Both focused tests returned to the exact pre-fix failures: 2500 < 12000 and closed peer leaves state listening rather than ended/released."
  implication: "The defects return when only the source fix is removed. Reapplying the identical changes must restore GREEN to complete causal verification."

- timestamp: 2026-08-01T13:57:00Z
  checked: "Reapplication, final focused tests, mutation configuration, and owned hygiene."
  found: "The identical source changes restore 2/2 focused passes and owned diff hygiene remains clean. No configured Python/Stryker mutation runner is present."
  implication: "Revert-and-reconfirm and all applicable self-verification signals pass. Exact OMEN browser timing remains the required deployed human/environment check."

- timestamp: 2026-08-01T14:05:00Z
  checked: "Human-confirmed canonical deployment and exact deployed reproduction."
  found: "RAYME_OMEN_VERIFY_QWEN3=1 scripts/deploy-omen.sh passed at exact commit 2721a4ef3ddfadf9cbc47acb0522cb41bc62fbae, including the production tracer and exact-commit core evidence. The refreshed fake mic is about 18.343 seconds with the intended 12-second tail. The exact browser suite passed 6/6 in 3.4 minutes: desktop and mobile each completed the real two-cycle call, and all four guards passed. Pre- and post-suite status showed live/media ready, selected Qwen prompt ready, and active_sessions=0."
  implication: "The original and later reproduction paths are fixed end to end on the exact deployed commit; cleanup is stable across both browser projects and the session can be archived."

- timestamp: 2026-08-01T14:08:00Z
  checked: "Project semantic-recall configuration during archive."
  found: "state.load reports mempalace.enabled=false and commit_docs=true."
  implication: "Skip MemPalace indexing by configuration; append the redacted resolution pattern to .planning/debug/knowledge-base.md and commit the resolved documentation."

## Hypotheses

- hypothesis: The call route renders a fixed error state because fixture voice authorization/readiness changed after forward migration 0005.
  status: eliminated
  reason: "Fresh fixture routes loaded and offers reached AI; exact AI 409s followed a retained different-voice lease, while migration and runtime gates had already passed."
- hypothesis: The post-review durable turn/call lifecycle changes broke call start or offer bootstrap.
  status: confirmed_with_refinement
  reason: "The new prompt lease made the older finish-runner cleanup omission user-visible; browser call-start code itself issued the offer correctly."
- hypothesis: Qwen synthesis or late playout is failing.
  status: eliminated
  reason: "Both failures occurred at prompt lease acquisition before synthesis/playout, while same-process prepare/synthesis evidence passed."

## Eliminated

- hypothesis: An outbound-audio completion future raises InvalidStateError and directly causes each call_tts_failed.
  evidence: "The full traceback is an independent aioice STUN retry callback. Speech failures are preceded by explicit VAD barge_in and speak.cancelled, while outbound playback waits complete successfully."
  timestamp: 2026-08-01T13:02:00Z

- hypothesis: Commit 2af2746's terminal-session guard rejects preparation because the AI peer connection fails while the SDP answer is withheld.
  evidence: "Exact OMEN session logs show offer.answered, ICE checking, and connection state connecting immediately before each 409. There is no failed/ended transition until the web server handles the 409 and calls /end."
  timestamp: 2026-08-01T12:10:00Z

## Specialist Review

## Resolution

root_cause: "The original finish-runner lease omission was fixed by f7feb6c. The later browser failure has two contributing causes: the canonical fake microphone appends only 2500 ms silence, leaving 3.44 s total closing silence—too short for VAD close plus observed STT/LLM/TTS latency—so Chromium loop restart triggers correct spoken barge-in 140–420 ms after every ai_audio_started and prevents ai_done; after desktop times out, CallSession ignores remote connectionState=closed, so its capacity-one Qwen lease remains and mobile preparation fails."
fix: "Prior fix: explicit OmenFinishLifecycle /end cleanup. Current fix: expanded only the canonical synthetic fake-mic trailing response window from 2500 ms to 12000 ms, and made an unterminalized CallSession treat peer connectionState=closed as connection_closed end so its prompt lease is released. Production VAD/barge-in and streaming paths are unchanged."
verification:
  target_test: {result: pass, detail: "2 focused regressions pass: loop-safe response window and closed-peer prompt-lease release"}
  mutation_check: {result: skipped, reason_if_skipped: "No configured Python or Stryker mutation runner exists", mutant_killed: null}
  no_op_deletion: {result: pass, deletion_justified_by_rca: false, detail: "Source diff is one constant replacement plus one additive terminal-state branch; tests strengthen rather than weaken assertions"}
  adjacent_tests: {result: pass, suites_run: ["test_call_session.py: 68 passed", "test_phase09_evidence.py: 50 passed", "test_webrtc_signaling.py focused Qwen/lease/connection/end: 20 passed", "py_compile changed files", "owned git diff --check"], technical_debt_note: "One pre-existing one-second spoken-VAD cancellation timing case failed in the first full run; it cannot reach either changed branch, then passed three isolated reruns and the complete 68-test rerun."}
  revert_and_reconfirm: {result: pass, bug_returned_on_revert: true, fixed_on_reapply: true, detail: "2 failed with only source behavior reverted; same 2 passed after identical reapplication"}
  human_verify: {result: pass, deployed_commit: "2721a4ef3ddfadf9cbc47acb0522cb41bc62fbae", detail: "Canonical deploy passed; exact browser suite 6/6; desktop/mobile real calls completed two cycles; pre/post active_sessions=0"}
  guardrail_verdict: accepted
  deployed_original_repro: "pass — exact six-case browser suite 6/6 in 3.4 minutes at 2721a4ef3ddfadf9cbc47acb0522cb41bc62fbae"
files_changed: ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-hardware-tracer.py, .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/test_phase09_evidence.py, ai-backend/app/call/session.py, ai-backend/tests/test_call_session.py"
oracle_type: specified

## Postmortem

why_not_caught: "The fake-mic test asserted only enough silence to close VAD (>1800 ms), not enough for the looping fixture to leave a complete AI-response window after spoken barge-in was added. Connection lifecycle tests covered failed but not remote closed, so abrupt peer teardown could retain a prompt lease."
prevention_guard: "test_hardware_tracer_fake_microphone_has_loop_safe_response_window requires >=12000 ms closing silence; test_closed_connection_ends_session_and_releases_prompt_lease requires closed peers to terminalize and release ownership."
