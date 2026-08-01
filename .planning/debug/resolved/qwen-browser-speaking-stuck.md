---
status: resolved
created: 2026-08-01T04:09:45Z
updated: 2026-08-01T07:04:00Z
trigger: "Plan 09-15's exact deployed browser acceptance completes the first Qwen user turn, then remains in speaking for over four minutes, drops more than 11,000 inbound frames, and never emits the second user turn or ai_done."
---

# Debug Session: Qwen Browser Speaking Stuck

## Current Focus

user_goal_preservation: "RayMe must be ready for a real multi-turn call using the selected Faster Qwen3-TTS 1.7B cloned voice, with early playback, recovery to listening, and working interrupt/barge-in behavior."
bug_class: "bohrbug"
known_pattern_candidate: "none — MemPalace is unavailable and no debug knowledge base exists."
hypothesis: "Confirmed: SpeechTurn's missing synthesis-free terminal marker caused the original stuck-speaking turn, and the follow-on deployed acceptance blocker was an ineffective Windows Firewall rule bound to uv's venv redirector instead of the live base cpython image."
test: "Completed: canonical OMEN deployment plus exact desktop/mobile live browser suite, independent decision-ready verifier, and exact operational handoff gate."
expecting: "Met: live transport connects, rayme-events opens, both browser profiles complete two user-to-Qwen cycles with two ai_audio_started and two ai_done/listening recoveries."
next_action: "Commit only .planning/debug/resolved/qwen-browser-speaking-stuck.md; leave protected Plan 09-15 evidence unstaged."
candidate_causes:
  - "code: SpeechTurn treated a boundary-emitted sentence followed by an empty segmenter tail as locally complete without sending the backend's required final_chunk terminal marker."
  - "config/environment: the deployment firewall contract used the venv redirector path while Windows attributed the live aiortc process and sockets to uv's base cpython image."
  - "code/UI: initial startup exposed Listening before ICE connected; this masked the transport failure but did not cause the missing packets or the original missing ai_done."
  - "environment/routing: WSL-to-LAN routing was a viable alternative but was refuted when the corrected live-image rule produced connected ICE and six passing real-live tests."
and_gate: "yes across the complete acceptance failure: the terminalization defect caused the original speaking hang, and the distinct firewall executable-identity mismatch then blocked deployed counter-verification until both were fixed."
reasoning_checkpoint:
  hypothesis: "RayMeAIWebRTCMediaUDP cannot authorize aiortc's inbound UDP because deploy-omen.sh binds the rule to the venv pythonw redirector, but uv's Windows venv re-executes the service as the base cpython pythonw image that WFP identifies."
  confirming_evidence:
    - "Win32_Process for the live 9443 owner reports uv's base cpython-3.11.15 pythonw.exe, while the active firewall application filter reports the repo .venv Scripts pythonw.exe."
    - "The venv pyvenv.cfg home and sys._base_executable both resolve to that same uv-managed base runtime; the derived sibling pythonw path exactly equals the live process image."
    - "The exact browser counterfactual still sent ICE checks and received zero responses with the mis-targeted rule, while signaling and valid OMEN candidates remained healthy."
  falsification_test: "A canonical deploy that targets Python's resolved base pythonw image and asserts it equals the post-start 9443 owner would falsify this diagnosis if the same browser probe still receives zero ICE responses."
  fix_rationale: "Resolve the OS-owned base executable before installing the program-scoped rule and verify the running listener image matches its application filter; this repairs effective WFP applicability without changing SDP, call timing, playback, reconnect, or barge-in."
  blind_spots: "The deployed counterfactual is still required to prove WSL NAT/source classification also passes LocalSubnet; current evidence confirms the rule cannot match, but does not yet prove it is the only downstream packet blocker."
  candidate_causes:
    - "config/code: deploy-omen.sh assumes the venv launcher path is the WFP process image and only statically compares the rule back to that input."
    - "environment: uv's Windows venv redirector runs the base cpython pythonw.exe image instead of retaining the .venv executable identity."
    - "environment/routing: WSL NAT could still source packets outside LocalSubnet, to be falsified by the corrected deployed counterfactual."
    - "code/UI: initial startup exposes Listening before ICE connects, which masks failure but cannot cause dropped UDP."
  and_gate: "no for the confirmed applicability defect — the wrong application identity alone prevents this allow rule from matching under the active firewall; routing remains a separate candidate that the corrected deployment must test."
previous_reasoning_checkpoint_firewall:
  hypothesis: "The deployed aiortc socket receives no ICE packets because OMEN's enabled Public-profile firewall has no allow rule for RayMe's repo-local AI pythonw.exe dynamic UDP sockets."
  confirming_evidence:
    - "OMEN is on NetworkCategory Public with Windows Firewall enabled; effective-rule inspection finds zero RayMe rules and zero broad applicable UDP-any rules."
    - "The exact Chromium probe completed ICE gathering in 129 ms, received a valid private-192 aiortc UDP answer candidate, sent roughly 240 connectivity-check requests, and received zero requests and zero responses while remaining checking."
    - "HTTPS signaling and service health at deployed commit 98161b2 pass, isolating the failure from process availability, offer proxying, SDP answer creation, Qwen residency, and prompt readiness."
  falsification_test: "A canonical deploy that installs the program-scoped LocalSubnet UDP rule would falsify this diagnosis if the same sanitized probe still sends checks but receives zero responses and remains ICE checking."
  fix_rationale: "aiortc binds dynamic UDP ports, so the stable least-privilege deployment contract is to allow inbound UDP only for the canonical AI pythonw.exe and only from LocalSubnet; asserting it in deploy-omen.sh fixes packet ingress without changing live-call timing, playback, reconnect, or barge-in logic."
  blind_spots: "Windows blocked-packet logging is disabled, so the exact drop was inferred from the active firewall/rule state plus zero-response ICE stats rather than a WFP drop event; deployed counterfactual verification must be performed by the parent."
  candidate_causes:
    - "environment/config: enabled Public firewall plus missing canonical RayMe AI UDP exception blocks dynamic aiortc ports."
    - "code: 1500 ms gathering cutoff could omit candidates, but the reproduction completed in 129 ms and is eliminated for this failure."
    - "environment/routing: unreachable WSL candidate could prevent server-initiated checks, but Chromium's checks to OMEN's valid private-192 answer also received no response."
  and_gate: "no — the missing effective inbound rule under the active Public firewall is sufficient to produce zero-response ICE; the premature Listening UI masks the failure but does not cause packet loss."
reasoning_checkpoint:
  hypothesis: "SpeechTurn's empty-tail local finish causes missing backend terminalization because it never sends final_chunk=true after a boundary-emitted final sentence."
  confirming_evidence:
    - "Deployed rtc_c453 logs show successful generation, completed playout, HTTP 200, no backend ai_done, and CallSession still speaking through 12,233 frames."
    - "The agent-authored one-sentence regression fails with actual final_chunk calls [False] instead of required [False, True]."
  falsification_test: "The hypothesis would be false if a boundary-terminated turn already issued a final backend call, or if backend state/listening and ai_done still failed after an explicit synthesis-free terminal marker."
  fix_rationale: "A terminal-only marker closes the state machine at LLM EOS without repeating audio or delaying the already-early first segment; it addresses the missing transition rather than forcing the client to fake listening."
  blind_spots: "Local tests cannot prove OMEN's real data channel delivery or repeated fake-microphone cycle until the canonical deployed browser gate is rerun."
  candidate_causes:
    - "code: SpeechTurn treats empty tail as local completion instead of explicit backend terminalization."
    - "config: segment boundary thresholds influence branch frequency but do not independently cause missing terminalization."
    - "environment: RTP/worker stalls were refuted by completed playout and continued idle RTP."
    - "data: sentence-boundary input selects the broken branch but is valid and requires no sanitization/change."
  and_gate: "no — the code transition is sufficient; data/config/environment only select or expose it."

## Symptoms

expected: "A deployed RayMe browser call completes the first streamed Qwen response, emits ai_done, returns to listening, accepts a second user turn, and preserves barge-in."
actual: "ICE, Qwen residency and prompt readiness, first VAD finalization, STT, and ai_audio_started pass. The browser then remains in speaking for more than four minutes, over 11,000 inbound microphone frames are dropped, and no second user turn or ai_done arrives."
errors:
  - "Decision-ready verifier: FAIL: browser readiness and call event order is incomplete"
  - "live-call.spec.ts: two_user_to_ai_cycles failed after first user turn"
timeline: "First exposed on 2026-08-01 during Plan 09-15 real deployed browser acceptance at exact commit c392d26264a28b7f00c1dd8ced6f864ef7ee5a14."
reproduction: "Canonical deploy through scripts/deploy-omen.sh, then run the Phase 09 real deployed Qwen Playwright gate on OMEN-PC using the permitted generated non-person fixture."

## Evidence

- timestamp: 2026-08-01T04:09:45Z
  checked: "Plan 09-15 executor checkpoint, deferred-items.md, and qwen3-browser.json."
  found: "Canonical deployment/core evidence, WavLM speaker stability, private leak scan, ICE, prompt readiness, first VAD/STT, and first audio start pass. The exact browser gate fails only after first playback starts, while the session remains speaking and drops inbound frames."
  implication: "The new engine can load and begin live streamed playback; the blocking defect is in turn terminalization, playout draining, or client/server state recovery rather than model startup."

- timestamp: 2026-08-01T04:11:27Z
  checked: "Semantic recall availability and .planning/debug/knowledge-base.md."
  found: "MemPalace recall tools are unavailable and no durable knowledge-base.md exists."
  implication: "There is no known-pattern candidate to privilege; proceed with direct evidence gathering."

- timestamp: 2026-08-01T04:12:11Z
  checked: "Exact qwen3-browser.json, deferred-items.md, git status, source symbol inventory, and deployed commit c392d26."
  found: "The evidence contains only model_resident, prompt_ready, user_final, and ai_audio_started. It records no browser error and no ai_done. The worktree has only pre-existing Plan 09-15 evidence changes plus this debug file; c392d26 changed evidence/test topology, not the Qwen terminal path."
  implication: "The failure is a runtime terminalization hang with no surfaced exception. The browser correctly entered speaking on ai_audio_started; investigation should work backwards from the backend terminal response before changing the client FSM."

- timestamp: 2026-08-01T04:14:02Z
  checked: "Qwen worker/adapter stream, CallSession streaming bridge, outbound track accounting, SpeechTurn scheduler, server ai_done forwarding, and live browser fixture."
  found: "Qwen emits a validated terminal or adapter timeout after 60 seconds without events. CallSession only starts its bounded playback wait after every chunk has been enqueued. Each enqueue can wait indefinitely for max-pending-sample credit because _admit_samples has no timeout. Inbound frames are explicitly discarded throughout speaking."
  implication: "An RTP playout-credit stall can strand CallSession in speaking indefinitely before ai_done or even the bounded wait, while also making barge-in-by-microphone impossible. Deployed logs can confirm or refute this exact mechanism."

- timestamp: 2026-08-01T04:18:07Z
  checked: "Deployed OMEN AI/web logs for rtc_c453026bac8f410b9ee0592a73fad2c2 and the corresponding browser turn."
  found: "The Qwen request enqueued 11 chunks, emitted ai_audio_started, entered playback_wait for 3439 ms, completed the wait successfully, held 750 ms, and returned HTTP 200. It emitted no backend ai_done. The outbound track then sent only idle frames while CallSession stayed speaking through 12,233 inbound frames. The web layer later logged its own ai_done for the 56-character reply."
  implication: "Generation and playout completed. The web/backend split-brain is deterministic: local SpeechTurn completion does not terminalize CallSession when the segmenter has no final tail."

- timestamp: 2026-08-01T04:18:07Z
  checked: "Phase 1.25 spectrum-based fault localization eligibility."
  found: "No existing failing automated test reproduces the no-tail terminal transition, so per-test failing/passing coverage is unavailable."
  implication: "SBFL is skipped; use the deterministic deployed trace plus a new minimal regression."

- timestamp: 2026-08-01T04:20:14Z
  checked: "Agent-authored regression test_qwen_boundary_terminated_turn_still_submits_one_backend_terminal."
  found: "The test deterministically fails: backend speak calls contain final_chunk flags [False], while the specified terminal contract requires [False, True]."
  implication: "The deployed mechanism is reproduced locally at the exact SpeechTurn/CallSession boundary and is ready for a minimal fix."

- timestamp: 2026-08-01T04:23:58Z
  checked: "Focused web no-tail regression and backend Qwen empty-terminal regression after the fix."
  found: "Both tests pass. The backend response moves state from speaking to listening, preserves completed playout metrics, and adapter stream identities prove no second synthesis occurred. Empty non-final speech remains rejected."
  implication: "The fix closes the exact missing transition without replaying audio or weakening request validation."

- timestamp: 2026-08-01T04:25:28Z
  checked: "Held-out adjacent web, CallSession, WebRTC, and live-stream invariant tests."
  found: "27 tests pass: 7 web Qwen scheduling/cancellation tests, 16 CallSession Qwen/VoxCPM2 streaming and terminal-control tests, and 4 WebRTC Qwen readiness/terminal tests."
  implication: "Early playback, bounded buffering, no whole-synthesis fallback, cancellation, and nonempty-tail behavior remain intact."

- timestamp: 2026-08-01T04:25:28Z
  checked: "Mutation tooling availability."
  found: "No Stryker or other mutation runner is configured in repository package/pyproject manifests."
  implication: "Guardrail mutation signal is skipped with an explicit tooling-unavailable reason."

- timestamp: 2026-08-01T04:27:08Z
  checked: "Path-scoped revert-and-reconfirm of the three production files, retaining both agent-authored regressions."
  found: "Without the fix, the web regression failed with [False] instead of [False, True] and the backend marker was rejected with HTTP 422. After restoring the fix, both regressions passed. Unrelated Plan 09-15 artifacts were unchanged."
  implication: "The production changes are causally necessary and sufficient for the automated reproduction."

- timestamp: 2026-08-01T04:31:02Z
  checked: "Pending-terminal interrupt regression plus both focused empty-tail terminal regressions."
  found: "All 3 pass. After a completed non-final Qwen segment, interrupt returns to listening; a late empty terminal marker returns cancelled, emits no ai_done, and does not invoke synthesis again."
  implication: "The explicit terminal handshake preserves barge-in semantics and cannot revive or falsely complete an interrupted turn."

- timestamp: 2026-08-01T04:32:06Z
  checked: "Python compilation, web Ruff lint, web changed-production Ruff format, and repository diff integrity."
  found: "Both backend and web changed Python compile; Ruff lint passes for the changed web source/test; ai_backend_client.py is already Ruff-formatted; git diff --check passes. AI-backend has no Ruff installation. The agent-authored web test produces no formatter hunk, while unrelated pre-existing test_calls.py formatting drift remains untouched."
  implication: "All available static signals pass without broad formatting churn or changes to the user's uncommitted Plan 09-15 evidence."

- timestamp: 2026-08-01T04:32:51Z
  checked: "Final diff for the five fix/test files against the confirmed state-machine mechanism and LIVE-CALL-INVARIANTS.md."
  found: "The diff keeps incremental Qwen segments non-final, adds one synthesis-free terminal handshake at LLM EOS, carries completed playout proof into exactly one ai_done, and clears/cancels pending terminal state on interrupt, engine switch, end, and failure. It adds no startup wait, whole-response buffering, whole-synthesis fallback, or changes to unrelated Plan 09-15 artifacts."
  implication: "The local fix-acceptance guardrail is accepted. Exact OMEN deployment and the two-cycle browser gate remain the only verification gap."

- timestamp: 2026-08-01T04:44:00Z
  checked: "Canonical scripts/deploy-omen.sh run with RAYME_OMEN_VERIFY_QWEN3=1 at fix commit 98161b25845cd75654b42382e3bd1ded9ffb93a8."
  found: "Deployment, CUDA attestation, production hardware tracer, exact-commit core evidence, independent verifier, Qwen residency, and selected prompt readiness all passed. The remote same-commit acoustic/leak finish also passed and restored Qwen readiness."
  implication: "The terminal fix is deployed on a healthy exact runtime; autonomous browser verification remains authoritative."

- timestamp: 2026-08-01T04:49:00Z
  checked: "First exact browser command after deployment."
  found: "Playwright spent its full 120-second webServer timeout building an irrelevant localhost preview and never reached OMEN. Live-mode config was corrected locally to omit the localhost webServer; the exact command then began six real tests immediately."
  implication: "The first failure was test-runner topology, not product behavior; keep the live-mode webServer fix as supporting evidence tooling."

- timestamp: 2026-08-01T05:00:50Z
  checked: "Exact real browser suite after the live-mode runner correction, across desktop and mobile Chromium, plus sanitized OMEN event/state logs."
  found: "Four provenance/path cases passed. Both deployed call cases failed after 240 seconds with zero user_speech turns. OMEN logged ICE checking/connection connecting, no open data channel, reconnect backfill, media reconnect timeout, session close, and late undelivered user_final. No Qwen synthesis or stuck-speaking state was reached."
  implication: "The original Qwen terminal defect did not recur, but a distinct ICE/data-channel regression now blocks the same acceptance guardrail and must be repaired before release readiness."

- timestamp: 2026-08-01T05:03:18Z
  checked: "Mandatory debugger references, gsd-debug workflow, RayMe AGENTS.md and LIVE-CALL-INVARIANTS.md, project-skill discovery, and gsd-debugger agent-skill bootstrap."
  found: "The incident must remain on the GSD path, any transport fix must preserve early playback/reconnect/barge-in, no project-local skills exist, and no extra gsd-debugger agent skills are configured."
  implication: "Proceed with differential WebRTC investigation; deployment remains parent-owned and may only use scripts/deploy-omen.sh."

- timestamp: 2026-08-01T05:05:02Z
  checked: "Worktree status, recent commits, and recent Playwright/planning artifacts."
  found: "The worktree contains only the protected Phase 09 evidence, debug record, and parent-authored playwright.config.ts change. test-results retains only .last-run.json; no trace/video archive is present locally. The connected baseline was c392d26 and the terminal fix 98161b2 changed five Python state-machine/test files, not client signaling."
  implication: "Do not infer a client regression from the terminal patch. Work from complete current signaling code, git differential, result metadata, and any accessible deployment logs."

- timestamp: 2026-08-01T05:07:11Z
  checked: "Playwright live configuration, failure IDs, signaling symbol map, and commit file-level diffs."
  found: "Both projects failed without retained first-run traces because trace capture is on-first-retry and the serial live tests did not produce retried artifacts. The browser creates rayme-events before offer, waits for ICE gathering, and uses non-trickle SDP. The only uncommitted runner change disables irrelevant localhost webServer startup in live mode."
  implication: "The next discriminating evidence is the actual offer/answer candidate inventory and end-to-end signaling lifecycle, not UI screenshots."

- timestamp: 2026-08-01T05:10:02Z
  checked: "Browser connectBrowserMedia, peer debug/reconnect path, and ICE gathering helper."
  found: "Initial signaling creates the data channel and audio sender before offer, waits at most 1500 ms for non-trickle ICE gathering, sends localDescription, sets the answer, then exposes Listening without waiting for connected ICE. Only replacement connections get a bounded connected-state gate."
  implication: "A slow/incomplete initial gather can produce a visibly ready but transport-dead call, but this remains a candidate hypothesis until actual offer/answer candidates and timing are observed."

- timestamp: 2026-08-01T05:13:44Z
  checked: "Web offer proxy, backend aiortc offer handler/lifecycle, canonical deployment launchers, and prior resolved Android ICE investigations."
  found: "The web proxy preserves the complete SDP unchanged and the backend synchronously awaits aiortc setRemoteDescription/createAnswer/setLocalDescription. The deployment binds HTTPS to 192.168.1.199 but has no explicit canonical firewall rule for ai-backend Python/aiortc UDP. A prior incident confirms that exposing Listening before proven ICE can leave a visibly live but dead call, though that incident involved offer failure rather than a 200 answer stuck in checking."
  implication: "Current candidates span code/lifecycle (1.5-second gather and no initial connected gate) and environment (Windows firewall/route after deployment); the live candidate and firewall probe can falsify one branch without changing behavior."

- timestamp: 2026-08-01T05:16:06Z
  checked: "Local HTTPS reachability plus OMEN adapter, network profile, firewall profiles, and program-filter rules through read-only SSH."
  found: "The exact deployed AI service is healthy at 98161b2. OMEN uses 192.168.1.199 on Ethernet, but that network is Public and all Windows firewall profiles are enabled. No enabled application rule references C:\\Users\\pmpg\\rayme\\RayMe\\ai-backend\\.venv\\Scripts\\pythonw.exe or python.exe."
  implication: "The canonical deploy proves TCP listeners only and leaves dynamic aiortc UDP outside an explicit firewall contract. This strongly supports, but does not yet confirm, the firewall hypothesis."

- timestamp: 2026-08-01T05:19:51Z
  checked: "Bounded exact-topology Chromium offer using the production 1500 ms ICE gather behavior and direct deployed aiortc answer."
  found: "ICE gathering completed in 129 ms, so the cutoff did not truncate this offer. The aiortc answer contained UDP host candidates including OMEN's private-192 LAN class. After 15 seconds Chromium remained ICE checking/connection connecting/datachannel connecting. Eight candidate pairs each sent about 30-31 requests and received zero requests and zero responses; no pair was selected. The probe session was closed through the normal end endpoint."
  implication: "The 1500 ms gather hypothesis is eliminated for this reproduction. Valid OMEN candidates exist, but all inbound connectivity checks vanish before any response; this sharply localizes the failure to OMEN packet ingress/firewall or lower-level routing, not SDP, Qwen, data-channel ownership, or application state."

- timestamp: 2026-08-01T05:23:08Z
  checked: "Effective Public-profile inbound allow rules and Windows firewall packet logging."
  found: "There is no RayMe program rule and no broad applicable inbound UDP-any rule. Public firewall blocked/allowed packet logging is disabled, so no WFP packet log is available for retrospective confirmation."
  implication: "Together with the zero-response candidate-pair stats, the missing dynamic-UDP firewall contract is the confirmed deployment blocker. Fix it only through scripts/deploy-omen.sh and require the parent to run the deployed counterfactual."

- timestamp: 2026-08-01T05:26:01Z
  checked: "New focused static deployment contract regression before production change."
  found: "test_omen_deploy_allows_aiortc_udp_only_for_rayme_runtime_and_lan fails because deploy-omen.sh has no canonical AI pythonw path variable or program-scoped LocalSubnet UDP rule/assertion."
  implication: "The missing deployment contract is reproduced as a deterministic red test; apply the minimal script fix."

- timestamp: 2026-08-01T05:29:12Z
  checked: "Minimal canonical deployment change and first focused integrity run."
  found: "deploy-omen.sh now creates RayMeAIWebRTCMediaUDP for the canonical AI pythonw.exe, inbound UDP, Profile Any, RemoteAddress LocalSubnet, then validates effective application/port/address filters. The focused contract plus no-synthetic-production-path test pass; bash syntax and diff integrity pass."
  implication: "The code fix is minimal and least-privilege. Continue with causal revert and adjacent regression verification before requesting deployment."

- timestamp: 2026-08-01T05:30:17Z
  checked: "Final focused deployment contract, no-synthetic production guard, bash syntax, and diff integrity after Profile Any assertion."
  found: "Both pytest checks pass, bash -n passes, and path-scoped diff integrity passes."
  implication: "Proceed with revert-and-reconfirm before broader adjacent tests."

- timestamp: 2026-08-01T05:32:11Z
  checked: "Path-scoped revert-and-reconfirm with the new regression retained."
  found: "Removing only the firewall/runtime production hunk makes the contract test fail; restoring the exact hunk makes it pass again. bash syntax and diff integrity remain clean after restoration."
  implication: "The production hunk is causally necessary for the recurrence guard. Run adjacent tests before the deployment checkpoint."

- timestamp: 2026-08-01T05:36:24Z
  checked: "Adjacent backend WebRTC/production guards, Phase 09 evidence contracts, client check, and live Playwright test discovery."
  found: "40 backend tests pass with only known dependency deprecations; all 48 Phase 09 evidence tests pass; client check passes; live-mode Playwright loads exactly six intended desktop/mobile tests without starting the irrelevant localhost server."
  implication: "Existing Qwen/WebRTC contracts and the parent-authored live runner correction remain intact. Complete the local fix-acceptance audit."

- timestamp: 2026-08-01T05:40:18Z
  checked: "Final local acceptance audit, remote PowerShell parser/token feasibility, mutation/shellcheck availability, and protected-worktree integrity."
  found: "The embedded remote PowerShell parses successfully; the SSH deployment identity is an administrator; PowerShell reports Profile Any comparisons as expected. The focused regression passes after the final quoting/assertion refinement. No mutation runner or shellcheck is installed, so mutation is explicitly skipped and bash -n is the available shell gate. Path-scoped diff checks pass; whole-worktree diff check noise comes only from protected pre-existing CRLF evidence files, which remain untouched by this debugger."
  implication: "All applicable local guardrail signals pass. The fix is accepted locally but the real packet-ingress counterfactual requires canonical deployment and browser verification by the parent."

- timestamp: 2026-08-01T05:47:18Z
  checked: "Canonical bf76a545455b28287279d6ff3bdc0269b1a15ab6 deployment, independent firewall-filter query, same-commit acoustic/leak finish, and exact six-test desktop/mobile browser counterfactual."
  found: "Deploy/core/scorer/privacy gates passed. RayMeAIWebRTCMediaUDP is Enabled=True, Profile=Any, Direction=Inbound, Action=Allow, Program=the canonical AI pythonw.exe, Protocol=UDP, LocalPort=Any, RemoteAddress=LocalSubnet. Nevertheless both browser calls stayed ICE checking/connecting, never opened rayme-events, produced zero user_speech turns, and failed after 240 seconds; four non-call guards passed."
  implication: "The firewall-only hypothesis is falsified as a sufficient root cause. Keep the rule as a missing deployment hardening contract, but continue below the application layer to actual source/interface/routing and effective-filter behavior."

- timestamp: 2026-08-01T06:04:00Z
  checked: "Continuation mandatory reads, RayMe live-call/deployment invariants, common patterns, bug taxonomy, RCA branching, project-skill discovery, and gsd-debugger skill bootstrap."
  found: "No project-local or configured gsd-debugger skills add rules. The failure remains a deterministic environment/config Bohrbug; the failed firewall counterfactual requires differential packet-path tracing, not another speculative call-state change."
  implication: "Preserve early playback/reconnect/barge-in and the committed firewall hardening. Read every producer/consumer boundary completely, then measure NIC arrival, WFP classification, and socket ownership one variable at a time."

- timestamp: 2026-08-01T06:11:00Z
  checked: "Complete deploy script, backend WebRTC offer/aiortc lifecycle, browser call connection implementation, and exact live Playwright gate."
  found: "The scheduled AI task runs the venv pythonw.exe under S4U/RunLevel Limited; aiortc creates dynamic UDP sockets inside that service process. Chromium is launched inside this Linux/WSL environment with default_public_interface_only, no mDNS hiding, and no STUN/TURN configuration. Initial UI still exposes Listening before ICE connection, but the measured transport failure precedes all call-state behavior."
  implication: "The high-value discriminator is the real process image plus WSL-to-LAN egress identity. Static SDP and rule shape are already proven; do not touch client lifecycle until packet flow is measured."

- timestamp: 2026-08-01T06:15:00Z
  checked: "OMEN listener owner, Win32_Process live image, active firewall application filter, and OMEN IPv4 interfaces/routes."
  found: "TCP 9443 is owned by PID 29140. Win32_Process reports its actual ExecutablePath and CommandLine executable as C:\\Users\\pmpg\\AppData\\Roaming\\uv\\python\\cpython-3.11.15-windows-x86_64-none\\pythonw.exe, but RayMeAIWebRTCMediaUDP targets C:\\Users\\pmpg\\rayme\\RayMe\\ai-backend\\.venv\\Scripts\\pythonw.exe. OMEN's 192.168.1.0/24 route is directly attached to Ethernet 192.168.1.199."
  implication: "The deployed rule is not program-applicable to the running aiortc process despite passing its static assertion. This is a direct executable-identity divergence; confirm the uv venv redirect metadata before fixing the deploy contract."

- timestamp: 2026-08-01T06:18:00Z
  checked: "OMEN uv venv metadata, sys.executable, sys._base_executable, derived base pythonw path, and both executable files."
  found: "pyvenv.cfg home is uv's cpython-3.11.15 runtime. sys.executable remains the repo .venv python.exe for Python semantics, but sys._base_executable is uv's base python.exe and its pythonw sibling exactly matches Win32_Process.ExecutablePath. The redirector and base pythonw are distinct files and sizes."
  implication: "The mechanism is confirmed, falsifiable, and below call code: the deployment rule validates its own wrong input instead of the live Windows process identity. Add a red contract for base-image resolution and live-owner matching."

- timestamp: 2026-08-01T06:22:00Z
  checked: "New focused regression test_omen_deploy_targets_live_windows_python_image_for_aiortc_udp against deployed bf76a54 source."
  found: "The test fails at the first required invariant because deploy-omen.sh never resolves sys._base_executable; it consequently has no live-image firewall target or post-start owner comparison."
  implication: "The exact missing effective-applicability contract is reproduced locally. The structured reasoning checkpoint is complete; apply the minimal deployment-only fix."

- timestamp: 2026-08-01T06:27:00Z
  checked: "Minimal deploy fix, both focused deployment-contract tests, bash syntax, and path-scoped diff integrity."
  found: "Both focused tests pass. deploy-omen.sh resolves uv's base pythonw via sys._base_executable, targets the LAN-only UDP rule to that process image, and rejects deployment if the live 9443 owner's ExecutablePath differs from the active application filter. bash -n and diff integrity pass."
  implication: "The target test is green and the change adds effective validation rather than deleting behavior. Run the mandatory causal revert/reapply signal."

- timestamp: 2026-08-01T06:31:00Z
  checked: "Path-scoped revert-and-reconfirm with the new live-image regression retained."
  found: "Removing only the base-image resolution/rule/live-owner hunk makes the regression fail at missing sys._base_executable. Reapplying the exact hunk makes it pass; bash syntax and path-scoped diff integrity remain clean."
  implication: "The production change is causally necessary and sufficient for the automated deployment contract. Run held-out adjacent and parser gates before requesting canonical deployment."

- timestamp: 2026-08-01T06:38:00Z
  checked: "Held-out backend WebRTC/deployment guards, Phase 09 evidence contracts, web client check, and remote PowerShell parser."
  found: "41 backend tests pass with only known dependency warnings; all 48 Phase 09 evidence tests pass; the Svelte client check passes; and OMEN PowerShell parses the embedded canonical deploy body successfully without executing it."
  implication: "Adjacent application/evidence behavior and remote script syntax remain intact. Complete the final scoped diff/tooling audit, then stop for exact deployment and browser counterfactual."

- timestamp: 2026-08-01T06:42:00Z
  checked: "Final scoped diff, mutation-tool inventory, diff integrity, and protected worktree state."
  found: "The fix is additive (23 insertions, 3 replacements in deploy code) and adds fail-closed identity checks; it does not delete or bypass behavior. No Stryker or other mutation runner is configured, so mutation is skipped explicitly. Scoped diff integrity passes. Protected Plan 09 exact-commit artifacts remain the same pre-existing modified/untracked paths and were not edited by this continuation."
  implication: "All applicable local guardrail signals pass. The only remaining proof is the canonical deployed counterfactual, owned by the parent and constrained to scripts/deploy-omen.sh."

- timestamp: 2026-08-01T07:01:00Z
  checked: "Exact-commit qwen3-browser.json plus 09-verify-evidence.py --decision-ready at deployed commit 3501a1a1e2b4371a46d6d65322975134b0d35a5f."
  found: "The artifact is real-live and unmocked, records six passing Playwright cases, and records two completed user-to-Qwen cycles with two ai_done events on both desktop and mobile. The independent decision-ready verifier returned PASS."
  implication: "The corrected process-image deployment falsification test passes in the real topology: the browser no longer stalls before transport or after first Qwen playback, and exact-commit evidence is internally consistent."

- timestamp: 2026-08-01T07:03:00Z
  checked: "Exact scripts/operational-check.sh handoff command using the independently printed deployed commit and canonical browser/call-flow/runtime evidence paths."
  found: "The handoff gate passed for commit 3501a1a1e2b4371a46d6d65322975134b0d35a5f. The protected evidence bundle remains unstaged; integrated human listening and physical-call acceptance remain honestly pending as broader Plan 09 product-owner checks."
  implication: "Every automated gate applicable to the qwen-browser-speaking-stuck incident is accepted. The pending listening/physical-call fields do not exercise or invalidate the resolved transport and turn-terminalization mechanisms."

## Eliminated

- hypothesis: "The browser never connects or the Qwen prompt/model is unavailable."
  evidence: "ICE connected, model_resident and prompt_ready were observed, STT finalized the first user turn, and ai_audio_started was emitted."

- hypothesis: "QueuedAudioOutputTrack enqueue admission or outbound RTP consumption stalls after ai_audio_started."
  evidence: "Deployed logs show all 11 chunks enqueued, playback_wait completed=True, queue and buffer remained empty, and track recv continued for thousands of frames."

- hypothesis: "The browser's 1500 ms ICE-gathering cutoff truncates the offer before host candidates are available."
  evidence: "The exact-topology probe reached iceGatheringState=complete in 129 ms before sending the offer, yet stayed checking with zero received connectivity-check requests/responses."

## Resolution

root_cause: "Original defect: SpeechTurn.finalize omitted backend terminalization for an empty Qwen segmenter tail. Follow-on deployed verification blocker: deploy-omen.sh targeted the uv venv pythonw redirector in RayMeAIWebRTCMediaUDP, but Windows runs and attributes aiortc sockets to uv's base cpython pythonw.exe, so the otherwise-valid inbound allow rule did not match the live service image."
fix: "Original defect: explicit synthesis-free Qwen terminal marker with interrupt-safe pending state. Transport hardening: deploy-omen.sh resolves uv's Windows base pythonw process image, uses that image for the LocalSubnet-only UDP rule, and fails deployment unless the live 9443 owner matches the active application filter."
verification:
  target_test: {result: pass}
  mutation_check: {result: skipped, reason_if_skipped: "No Stryker or other mutation runner is configured in repository manifests.", mutant_killed: null}
  no_op_deletion: {result: pass, deletion_justified_by_rca: true}
  adjacent_tests:
    result: pass
    suites_run:
      - "7 web Qwen scheduling/cancellation tests"
      - "16 CallSession Qwen/VoxCPM2 streaming and terminal-control tests"
      - "4 WebRTC Qwen readiness/terminal tests"
      - "1 pending-terminal interrupt regression"
  revert_and_reconfirm: {result: pass, bug_returned_on_revert: true, fixed_on_reapply: true}
  guardrail_verdict: accepted
  transport_firewall_fix:
    target_test: {result: pass}
    mutation_check: {result: skipped, reason_if_skipped: "No Stryker or other mutation runner is configured for the PowerShell deployment script.", mutant_killed: null}
    no_op_deletion: {result: pass, deletion_justified_by_rca: false}
    adjacent_tests:
      result: pass
      suites_run:
        - "40 AI backend WebRTC, no-synthetic-path, and deployment-contract tests"
        - "48 Phase 09 evidence contract tests"
        - "web-ui client check"
        - "six-test live Playwright discovery in deployed mode"
        - "bash -n plus remote PowerShell parse"
    revert_and_reconfirm: {result: pass, bug_returned_on_revert: true, fixed_on_reapply: true}
    guardrail_verdict: accepted
  deployment_browser_gate: {result: failed, reason: "Exact bf76a54 deployment and firewall attestation passed, but both desktop/mobile calls still failed before a user turn with ICE checking and no data channel."}
  transport_process_image_fix:
    target_test: {result: pass}
    mutation_check: {result: skipped, reason_if_skipped: "No Stryker or other mutation runner is configured for the PowerShell deployment path.", mutant_killed: null}
    no_op_deletion: {result: pass, deletion_justified_by_rca: false}
    adjacent_tests:
      result: pass
      suites_run:
        - "41 AI backend WebRTC, production-path, and deployment-contract tests"
        - "48 Phase 09 evidence contract tests"
        - "web-ui client check"
        - "bash -n and remote embedded-PowerShell parse"
    revert_and_reconfirm: {result: pass, bug_returned_on_revert: true, fixed_on_reapply: true}
    guardrail_verdict: accepted
  corrected_process_image_deployment_gate:
    result: pass
    deployed_commit: "3501a1a1e2b4371a46d6d65322975134b0d35a5f"
    canonical_deploy: "pass via RAYME_OMEN_VERIFY_QWEN3=1 scripts/deploy-omen.sh"
    live_rule_owner_exact_match: true
    browser_suite: "6/6 passed in 11.1 minutes; desktop and mobile each completed two user-to-Qwen cycles with two ai_audio_started and two ai_done/listening recoveries"
    decision_ready: pass
    operational_handoff: pass
  human_verification:
    result: pass
    basis: "The continuation response confirmed the exact real-live deployed workflow and original two-cycle browser reproduction pass. Human listening quality and a physical handset call remain separate Plan 09 acceptance items."
  final_guardrail_verdict: accepted
files_changed:
  - "web-ui/server/app/domain/ai_backend_client.py"
  - "web-ui/server/tests/test_calls.py"
  - "ai-backend/app/api/webrtc.py"
  - "ai-backend/app/call/session.py"
  - "ai-backend/tests/test_webrtc_signaling.py"
  - "ai-backend/tests/test_omen_deploy_contract.py"
  - "scripts/deploy-omen.sh"
oracle_type: "specified for Qwen terminal recovery; derived for transport — a real WebRTC call requires a selected candidate pair and an open rayme-events channel before microphone turns can flow."

## Prevention

blameless_branches:
  code_terminalization:
    - "A sentence boundary could emit the final audible segment before LLM EOS."
    - "SpeechTurn.finalize then observed an empty tail and completed only its local scheduler state."
    - "The backend state machine requires an explicit final_chunk marker to emit ai_done and recover listening."
    - "No focused regression covered the valid boundary-ended/empty-tail equivalence class, so the split-brain path survived ordinary unit coverage."
  config_environment_transport:
    - "aiortc needs a dynamic inbound UDP firewall exception on OMEN's enabled Public profile."
    - "The first deployment contract bound that exception to the venv pythonw redirector."
    - "uv's Windows launcher re-executes the base cpython image, which is the executable identity Windows Firewall applies to the live sockets."
    - "The deploy assertion compared the rule with its configured input rather than the post-start listener owner's real image, so a statically correct but ineffective rule passed."
why_not_caught: "No test covered synthesis-free backend terminalization after a boundary-ended Qwen turn, and the initial deployment gate did not compare the firewall application filter with the live 9443 owner. The exact deployed browser gate caught both gaps before handoff."
recurrence_guard: "web-ui/server/tests/test_calls.py::test_qwen_boundary_terminated_turn_still_submits_one_backend_terminal; ai-backend/tests/test_webrtc_signaling.py::test_webrtc_qwen_interrupt_cancels_pending_empty_terminal; ai-backend/tests/test_omen_deploy_contract.py::test_omen_deploy_targets_live_windows_python_image_for_aiortc_udp; scripts/deploy-omen.sh now fails closed when the live listener image and firewall application filter differ."
