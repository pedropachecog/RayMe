---
schema_version: 1
open_count: 1
waived_count: 0
fixed_count: 0
total_count: 1
last_updated: 2026-07-31T19:05:52.973Z
---

# Broken Windows Ledger

> Cross-phase defect register. `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 09 | deviation | ai-backend/app/models/tts_qwen3_worker.py |  | Extended worker protocol and saved-call assertions for exact owner eviction semantics | open |  | 2026-07-31T19:05:52.973Z |  |

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
  }
]
````
