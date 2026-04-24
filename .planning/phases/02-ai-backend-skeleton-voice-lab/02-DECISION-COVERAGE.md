# Phase 02 Decision Coverage

This file maps every locked Phase 02 decision from `02-CONTEXT.md` to the plan task(s) that implement or verify it. All Phase 02 plans reference this file in their `<context>` block; executors should treat the decision IDs below as implementation constraints, not optional rationale.

## Coverage Table

| Decision | Required Outcome | Implemented / Verified In |
|----------|------------------|---------------------------|
| D-01 | Full measured TTS roster is supported: F5-TTS, XTTS v2, Qwen3-TTS 0.6B-Base, LuxTTS, Chatterbox Turbo, TADA 1B. | 02-02 Task 2 registry tests; 02-08 Tasks 1-3 registry/adapters/API; 02-12 Task 2 engine picker; 02-16 Task 1 notices; 02-18 Task 1 live evidence. |
| D-02 | No future three-engine-only framing. | 02-03 Task 1/2 UI contract tests; 02-08 Task 1 full roster metadata; 02-12 Task 2 picker; 02-14 Task 1 Settings status. |
| D-03 | Engine registry/metadata drives labels, caveats, availability, default status, runtime status, and notes. | 02-02 Task 2 tests; 02-08 Task 1 registry metadata; 02-12 Task 2 `TtsEnginePicker`; 02-16 Task 1 license/caveat notices. |
| D-04 | Saved voice stores original sample, editable transcript, metadata, and stable internal ID; preview audio is not persisted as part of save. | 02-01 Task 1 tests; 02-04 Tasks 1-2 schema/assets; 02-09 Task 1 service save semantics. |
| D-05 | Voice names are mutable display text; references use stable internal voice IDs. | 02-01 Task 1 tests; 02-09 Task 1 `rename_voice`; 02-13 Task 1 rename UI. |
| D-06 | Voice stores a default engine but is not locked permanently to it. | 02-04 Task 1 `default_engine`; 02-09 Task 1 save/test-play; 02-12 Task 2 and 02-13 Task 1 `Use default engine` toggle. |
| D-07 | Referenced voices may be force-deleted after explicit confirmation. | 02-01 Task 1 tests; 02-09 Task 2 delete API; 02-13 Task 2 delete dialog. |
| D-08 | Referenced voice deletion must not crash or silently corrupt character/chat state; UI shows `Voice unavailable`. | 02-01 Task 1 tests; 02-11 Task 2 response hydration; 02-15 Task 2 Gallery badges. |
| D-09 | Tombstone/soft-delete shape preserves readable unavailable voice context. | 02-04 Task 1 `deleted_at`; 02-09 Task 1 soft delete; 02-11 Task 2 tombstoned voice labels. |
| D-10 | Engine switching is visible and automatic when a non-resident engine is needed. | 02-02 Task 2 switch-state tests; 02-06 Task 1 model manager; 02-08 Task 3 synthesis switch; 02-12 Task 2 preview state; 02-18 Task 1 live evidence. |
| D-11 | Every supported engine remains selectable unless unavailable, with concise caveat chips. | 02-02 Task 2 metadata tests; 02-08 Task 1 registry; 02-12 Task 2 picker; 02-16 Task 1 notices. |
| D-12 | Backend health/status reports resident engine, available engines, loading/switching state, and VRAM/headroom. | 02-02 Task 1 tests; 02-05 Task 2 status bridge; 02-06 Task 2 health; 02-10 Task 2 Settings API; 02-14 Task 1 Settings UI; 02-18 Task 1 live evidence. |
| D-13 | STT failure keeps the uploaded sample and allows retry/manual transcript entry. | 02-01 Task 1 tests; 02-03 Task 2 E2E; 02-07 Task 2 STT route; 02-12 Task 2 transcript UI. |
| D-14 | Preview before save is optional with no warning/confirmation gate. | 02-01 Task 1 tests; 02-03 Task 2 E2E; 02-09 Task 1 save service; 02-12 Task 2 save state. |
| D-15 | Synthesis surfaces include `Use default engine`; disabling it allows any supported engine. | 02-08 Task 3 synthesis payload; 02-12 Task 2 preview UI; 02-13 Task 1 test-play UI. |
| D-16 | Preview synthesis failure preserves sample, name, transcript, engine settings, and preview text. | 02-01 Task 1 tests; 02-03 Task 2 E2E; 02-12 Task 2 preview error state. |
| D-17 | Settings exposes compact AI backend operational status. | 02-01 Task 2 tests; 02-05 Task 2 status bridge; 02-10 Task 2 Settings API; 02-14 Task 1 Settings UI. |
| D-18 | Settings shows VAD placeholders stored now but clearly marked as later call behavior. | 02-01 Task 2 tests; 02-10 Task 1 fields; 02-14 Task 1 VAD panel. |
| D-19 | Settings stores save-audio toggles; defaults are AI audio ON and mic audio OFF. | 02-01 Task 2 tests; 02-10 Task 1 persisted defaults; 02-14 Task 1 audio panel. |
| D-20 | Web UI server owns durable voice storage, samples, transcripts, metadata, and persisted blobs. | 02-04 Tasks 1-2 storage; 02-09 Task 1 service; 02-16 Task 2 runbook. |
| D-21 | AI backend is a processing service, not durable app-state source of truth. | 02-05 Task 1 client boundary; 02-06 Task 1 model manager; 02-07 Task 2 STT; 02-08 Task 3 TTS; 02-09 Task 1 service persistence. |
| D-22 | Web UI and AI backend exchange audio through transient processing requests; Web UI decides persistence. | 02-05 Task 1 client; 02-07 Task 2 STT; 02-08 Task 3 TTS; 02-09 Task 1 processing calls. |
| D-23 | One AI backend API with per-engine adapters; adapter runtime mechanisms remain evidence-gated. | 02-06 Task 1 manager; 02-08 Tasks 1-3 registry/adapters/API; 02-17 Task 2 non-call signaling router boundary. |
| D-24 | Prefer one runtime environment; split runtime requires evidence before recommendation. | 02-08 Task 1/2 no premature split; 02-16 Task 2 runtime evidence gates; 02-18 Task 1 live evidence. |
| D-25 | Failed engine self-test degrades only that engine; backend and other engines remain available. | 02-02 Task 1 tests; 02-06 Task 1 health model; 02-08 Task 3 adapter failures; 02-18 Task 1 live evidence. |
| D-26 | Each engine runtime choice needs evidence: runtime, rationale, install/self-test command, fallback. | 02-08 Task 1 metadata `runtime_evidence`; 02-16 Task 2 `RUNTIME-EVIDENCE.md`; 02-18 Task 1 `OMEN-PC-LIVE-EVIDENCE.md`. |

## Execution Rule

If an implementation task appears to conflict with this table, the executor must preserve the locked decision from `02-CONTEXT.md` and document the resolution in the plan summary. Deferred ideas from `02-CONTEXT.md` are empty and no out-of-scope ideas are introduced here.
