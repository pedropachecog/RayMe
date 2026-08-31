---
schema_version: 1
open_count: 3
waived_count: 0
fixed_count: 10
total_count: 13
last_updated: 2026-08-31T06:11:41.172Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 09 | deviation | ai-backend/app/models/tts_qwen3_worker.py |  | Extended worker protocol and saved-call assertions for exact owner eviction semantics | open |  | 2026-07-31T19:05:52.973Z |  |
| 2 | 09 | stub | .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py | 967 | _browser_placeholder emits awaiting_real_live_e2e until Plan 15 records real browser and physical-call evidence | fixed |  | 2026-07-31T22:00:46.604Z | 2026-08-01T06:39:37.685Z |
| 3 | 09 | deviation | ai-backend/app/api/webrtc.py |  | Authorized deterministic release-evidence seed contract added across production API and Qwen worker | fixed |  | 2026-07-31T22:00:46.695Z | 2026-07-31T22:00:58.618Z |
| 4 | 09 | stub | .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py | 1025 | Browser evidence remains an explicit awaiting_real_live_e2e placeholder for Plan 09-15 physical-call handoff | fixed |  | 2026-08-01T02:27:33.764Z | 2026-08-01T06:39:37.851Z |
| 5 | 09 | deviation | .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py |  | Acoustic and leak completion ran on OMEN because the private scorer state and audio remained local to that host. | fixed |  | 2026-08-01T06:39:18.549Z | 2026-08-01T06:39:38.005Z |
| 6 | 09 | deviation | .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-speaker-score.py |  | Speaker evidence needed an explicit critical_gates entry before the decision verifier could trust it. | fixed |  | 2026-08-01T06:39:18.693Z | 2026-08-01T06:39:38.156Z |
| 7 | 09 | deviation | .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-hardware-tracer.py |  | Switch transcripts and deployment logs needed public-text substitution and redaction to keep private reference content out of evidence. | fixed |  | 2026-08-01T06:39:18.861Z | 2026-08-01T06:39:38.309Z |
| 8 | 09 | deviation | web-ui/client/tests/e2e/live-call.spec.ts |  | The real browser evidence harness needed repo-root fixture resolution, serialized GPU use, and trailing microphone silence. | fixed |  | 2026-08-01T06:39:19.027Z | 2026-08-01T06:39:38.495Z |
| 9 | 09 | deviation | web-ui/server/app/domain/ai_backend_client.py |  | Boundary-emitted Qwen turns needed a synthesis-free terminal marker to recover Listening without whole-synthesis fallback. | fixed |  | 2026-08-01T06:39:19.196Z | 2026-08-01T06:39:38.655Z |
| 10 | 09 | deviation | scripts/deploy-omen.sh |  | Canonical WebRTC required a LocalSubnet-only UDP rule bound to the base Python executable that owns live port 9443. | fixed |  | 2026-08-01T06:39:19.348Z | 2026-08-01T06:39:38.808Z |
| 11 | 09 | stub | .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py | 1028 | Finish-acoustic mode emits a deliberately rejected intermediate browser artifact; the real live suite must overwrite it before decision-ready verification. | open |  | 2026-08-01T06:40:34.486Z |  |
| 12 | 09.1 | deviation | web-ui/server/app/domain/refusal_guard.py |  | Narrowed an over-broad policy secondary signal so benign safe sentences retain early release | open |  | 2026-08-31T03:18:36.517Z |  |
| 13 | 09.1 | deviation | .planning/STATE.md |  | Legacy STATE header required manual completed-plan and phase-label reconciliation after SDK writes. | fixed |  | 2026-08-31T06:10:40.971Z | 2026-08-31T06:11:41.172Z |

````json
[
  {
    "id": 1,
    "kind": "deviation",
    "phase": "09",
    "file": "ai-backend/app/models/tts_qwen3_worker.py",
    "line": null,
    "description": "Extended worker protocol and saved-call assertions for exact owner eviction semantics",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-07-31T19:05:52.973Z",
    "resolved_at": null
  },
  {
    "id": 2,
    "kind": "stub",
    "phase": "09",
    "file": ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py",
    "line": 967,
    "description": "_browser_placeholder emits awaiting_real_live_e2e until Plan 15 records real browser and physical-call evidence",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-07-31T22:00:46.604Z",
    "resolved_at": "2026-08-01T06:39:37.685Z"
  },
  {
    "id": 3,
    "kind": "deviation",
    "phase": "09",
    "file": "ai-backend/app/api/webrtc.py",
    "line": null,
    "description": "Authorized deterministic release-evidence seed contract added across production API and Qwen worker",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-07-31T22:00:46.695Z",
    "resolved_at": "2026-07-31T22:00:58.618Z"
  },
  {
    "id": 4,
    "kind": "stub",
    "phase": "09",
    "file": ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py",
    "line": 1025,
    "description": "Browser evidence remains an explicit awaiting_real_live_e2e placeholder for Plan 09-15 physical-call handoff",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-08-01T02:27:33.764Z",
    "resolved_at": "2026-08-01T06:39:37.851Z"
  },
  {
    "id": 5,
    "kind": "deviation",
    "phase": "09",
    "file": ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py",
    "line": null,
    "description": "Acoustic and leak completion ran on OMEN because the private scorer state and audio remained local to that host.",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-08-01T06:39:18.549Z",
    "resolved_at": "2026-08-01T06:39:38.005Z"
  },
  {
    "id": 6,
    "kind": "deviation",
    "phase": "09",
    "file": ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-speaker-score.py",
    "line": null,
    "description": "Speaker evidence needed an explicit critical_gates entry before the decision verifier could trust it.",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-08-01T06:39:18.693Z",
    "resolved_at": "2026-08-01T06:39:38.156Z"
  },
  {
    "id": 7,
    "kind": "deviation",
    "phase": "09",
    "file": ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-hardware-tracer.py",
    "line": null,
    "description": "Switch transcripts and deployment logs needed public-text substitution and redaction to keep private reference content out of evidence.",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-08-01T06:39:18.861Z",
    "resolved_at": "2026-08-01T06:39:38.309Z"
  },
  {
    "id": 8,
    "kind": "deviation",
    "phase": "09",
    "file": "web-ui/client/tests/e2e/live-call.spec.ts",
    "line": null,
    "description": "The real browser evidence harness needed repo-root fixture resolution, serialized GPU use, and trailing microphone silence.",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-08-01T06:39:19.027Z",
    "resolved_at": "2026-08-01T06:39:38.495Z"
  },
  {
    "id": 9,
    "kind": "deviation",
    "phase": "09",
    "file": "web-ui/server/app/domain/ai_backend_client.py",
    "line": null,
    "description": "Boundary-emitted Qwen turns needed a synthesis-free terminal marker to recover Listening without whole-synthesis fallback.",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-08-01T06:39:19.196Z",
    "resolved_at": "2026-08-01T06:39:38.655Z"
  },
  {
    "id": 10,
    "kind": "deviation",
    "phase": "09",
    "file": "scripts/deploy-omen.sh",
    "line": null,
    "description": "Canonical WebRTC required a LocalSubnet-only UDP rule bound to the base Python executable that owns live port 9443.",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-08-01T06:39:19.348Z",
    "resolved_at": "2026-08-01T06:39:38.808Z"
  },
  {
    "id": 11,
    "kind": "stub",
    "phase": "09",
    "file": ".planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py",
    "line": 1028,
    "description": "Finish-acoustic mode emits a deliberately rejected intermediate browser artifact; the real live suite must overwrite it before decision-ready verification.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-01T06:40:34.486Z",
    "resolved_at": null
  },
  {
    "id": 12,
    "kind": "deviation",
    "phase": "09.1",
    "file": "web-ui/server/app/domain/refusal_guard.py",
    "line": null,
    "description": "Narrowed an over-broad policy secondary signal so benign safe sentences retain early release",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-31T03:18:36.517Z",
    "resolved_at": null
  },
  {
    "id": 13,
    "kind": "deviation",
    "phase": "09.1",
    "file": ".planning/STATE.md",
    "line": null,
    "description": "Legacy STATE header required manual completed-plan and phase-label reconciliation after SDK writes.",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-08-31T06:10:40.971Z",
    "resolved_at": "2026-08-31T06:11:41.172Z"
  }
]
````
