# Phase 03.1 Results

This directory stores machine-readable Phase 03.1 stabilization evidence. Keep
raw logs, secrets, absolute local reference-audio paths, model cache paths, and
tracebacks out of committed files.

## Artifacts

| Artifact | Purpose | Producer |
|---|---|---|
| `03.1-defect-triage.json` | Wave 0 evidence-backed defect and scope ledger | Plan 03.1-01 |
| `03.1-local-regression.json` | Focused local regression command results | Later local regression plan |
| `03.1-live-dual-engine.json` | OMEN live call smoke results for `voxcpm2` and `f5` | Later live evidence plan |
| `03.1-mute-frame-drops.json` | Backend server-side mute frame-drop evidence | Later backend/live plan |
| `03.1-reconnect-outcome.json` | Reconnect/drop terminal-state proof | Later reconnect stabilization plan |
| `03.1-missing-chunks.json` | Long-turn missing-chunks evidence and acceptance result | Later missing-chunks plan |
| `03.1-writeback-counts.json` | Durable call row counts and writeback proof | Later writeback evidence plan |

## Hygiene

- Store only sanitized summaries and structured pass/fail fields.
- Do not commit API keys, tokens, passwords, TLS private keys, raw stack traces,
  absolute reference-audio paths, model cache paths, or full raw logs.
- Link runtime-sensitive evidence back to `03.1-EVIDENCE.md` and the selected
  `CALL-STAB-*` defect ID.
