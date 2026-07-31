---
schema_version: 1
open_count: 2
waived_count: 0
fixed_count: 1
total_count: 3
last_updated: 2026-07-31T22:00:58.618Z
---

# Broken Windows Ledger

> Cross-phase defect register. `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 09 | deviation | ai-backend/app/models/tts_qwen3_worker.py |  | Extended worker protocol and saved-call assertions for exact owner eviction semantics | open |  | 2026-07-31T19:05:52.973Z |  |
| 2 | 09 | stub | .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py | 967 | _browser_placeholder emits awaiting_real_live_e2e until Plan 15 records real browser and physical-call evidence | open |  | 2026-07-31T22:00:46.604Z |  |
| 3 | 09 | deviation | ai-backend/app/api/webrtc.py |  | Authorized deterministic release-evidence seed contract added across production API and Qwen worker | fixed |  | 2026-07-31T22:00:46.695Z | 2026-07-31T22:00:58.618Z |

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
    "status": "open",
    "reason": "",
    "recorded_at": "2026-07-31T22:00:46.604Z",
    "resolved_at": null
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
  }
]
````
