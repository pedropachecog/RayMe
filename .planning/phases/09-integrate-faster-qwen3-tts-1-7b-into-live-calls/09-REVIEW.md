---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
reviewed: 2026-08-02T12:33:35Z
depth: deep
diff_base: b5dbb2d
reviewed_head: 2773fed1fd0fb0b60cd10ce86a98a412cc0a8a6d
files_reviewed: 38
files_reviewed_list:
  - ai-backend/app/api/auth.py
  - ai-backend/app/api/health.py
  - ai-backend/app/api/webrtc.py
  - ai-backend/app/call/session.py
  - ai-backend/app/config.py
  - ai-backend/app/main.py
  - ai-backend/app/models/tts_qwen3.py
  - ai-backend/app/models/tts_qwen3_protocol.py
  - ai-backend/app/models/tts_qwen3_worker.py
  - ai-backend/app/models/tts_registry.py
  - ai-backend/tests/test_call_session.py
  - ai-backend/tests/test_omen_deploy_contract.py
  - ai-backend/tests/test_stt.py
  - ai-backend/tests/test_tts_qwen3.py
  - ai-backend/tests/test_tts_registry.py
  - ai-backend/tests/test_webrtc_signaling.py
  - scripts/deploy-omen.sh
  - web-ui/client/src/lib/api/calls.ts
  - web-ui/client/src/lib/api/types.ts
  - web-ui/client/src/lib/call/audio.ts
  - web-ui/client/src/lib/call/reconnectBackfill.ts
  - web-ui/client/src/lib/components/call/CallToolbar.svelte
  - web-ui/client/src/routes/call/[threadId]/+page.svelte
  - web-ui/client/tests/e2e/call-start.spec.ts
  - web-ui/client/tests/e2e/call-toolbar.spec.ts
  - web-ui/client/tests/e2e/helpers/acceptance.ts
  - web-ui/client/tests/unit/call-audio.test.ts
  - web-ui/client/tests/unit/call-state.test.ts
  - web-ui/client/tests/unit/reconnect-backfill.test.ts
  - web-ui/server/app/api/ai_backend.py
  - web-ui/server/app/api/calls.py
  - web-ui/server/app/api/settings.py
  - web-ui/server/app/api/voices.py
  - web-ui/server/app/config.py
  - web-ui/server/app/domain/ai_backend_client.py
  - web-ui/server/app/domain/settings_service.py
  - web-ui/server/tests/test_calls.py
  - web-ui/server/tests/test_health_settings.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 09: Code Review Report

**Reviewed:** 2026-08-02T12:33:35Z
**Depth:** deep
**Diff:** `b5dbb2d..2773fed`
**Files Reviewed:** 38
**Status:** clean

## Narrative Findings (AI reviewer)

### Summary

All reviewed files meet quality standards. No blocker or warning remains in the complete Phase 09 diff.

The final repair closes the test-process leak from the previous review. Every thread-side rendezvous in the long Qwen reconnect/barge-in regression is bounded; unconditional cleanup releases both producer gates, cancels and settles the speech task, and the induced-failure branch proves the producer generator exits and its executor thread is gone. Ten consecutive induced-failure runs and ten consecutive complete 40-second workflow runs passed. Replaying the original immediate rendezvous-helper failure propagated the expected error and returned in 0.011 seconds with no worker thread alive, instead of hanging until the external watchdog.

No product source changed after the prior redirect, terminal-control, and lifecycle repairs at `826811e`. Their boundaries were rechecked against the final head. Authenticated AI-backend requests remain pinned to the configured trusted HTTPS origin, force redirects off even on a supplied redirect-following client, reject every 3xx response, and never authenticate public health. A fresh adversarial matrix covering injected and internal clients, 301/302/303/307/308, private JSON reference data, and multipart audio blocked all 20 cases after exactly one trusted request and made zero foreign requests.

### Contract audit

| Required behavior | Verdict at `2773fed` | Evidence |
|---|---|---|
| Saved voice/model identity | Pass | Voice-key/content identity, exact reference transcript, model manifest, pinned source, and narrow legacy-engine normalization coverage passed. |
| Greater-than-30-second live speech | Pass | The paced 40-second Qwen stream passed ten consecutive complete reconnect/barge-in runs and the full backend suite. |
| Early playback before stream completion | Pass | Qwen and VoxCPM2 slow-stream regressions observe playback while producer completion remains false. |
| No whole-synthesis fallback | Pass | Streaming doubles reject `synthesize()` and the Qwen/VoxCPM2 fallback-exclusion coverage passed. |
| Barge-in and listening recovery | Pass | Request cancellation, pending-terminal interruption, receiver drain, real playout silence, and post-interrupt Listening recovery passed. |
| Reconnect, mute, and terminal ownership | Pass | Peer-generation promotion, capture epoch/revision, backfill, terminal transaction, programmatic toolbar guards, late callback rejection, and desktop/mobile matrices passed. |
| Prompt lease lifecycle | Pass | Offer, replacement, switch-away, finish-evidence, terminal, and release ownership coverage passed. |
| Service auth, redirects, TLS, and public health | Pass | Foreign origins and every redirect code fail closed; canonical stateful requests authenticate; health does not; configured CA verification remains enabled. |
| Canonical OMEN deployment | Pass | Deployment-contract coverage, canonical launcher/task ownership, pinned source/model, TLS/token wiring, LocalSubnet media rule, and shell syntax passed. |

## Verification Performed

- Forced long-call failure regression: `10/10` consecutive runs passed; each asserted producer exit and no live producer thread.
- Complete paced 40-second Qwen reconnect/barge-in/recovery regression: `10/10` consecutive runs passed.
- Original immediate rendezvous-helper failure reproduction: expected assertion propagated in `0.011s`; no non-main worker thread survived.
- Redirect boundary matrix: `20/20` injected/internal, 301/302/303/307/308, JSON/multipart combinations blocked; zero foreign requests.
- Trusted-origin Settings/client suite: `37 passed`.
- Full AI backend suite: `430 passed, 4 third-party dependency warnings`.
- Full Web server suite: `281 passed`.
- Full client unit suite: `16 files, 113 passed`.
- Full call-start Playwright suite: `102 passed` across desktop and mobile Chromium.
- `npm run check` and `npm run build`: passed.
- `git diff --check b5dbb2d..2773fed`: passed.
- `bash -n scripts/deploy-omen.sh`: passed; the full backend suite includes the canonical OMEN deployment-contract tests.
- No source files, tests, launchers, deployment state, commits, pushes, or remote branches were modified by this review.

---

_Reviewed: 2026-08-02T12:33:35Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
