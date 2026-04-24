# Phase 02: AI Backend Skeleton & Voice Lab - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `02-CONTEXT.md` - this log preserves the alternatives considered.

**Date:** 2026-04-24
**Phase:** 02-ai-backend-skeleton-voice-lab
**Areas discussed:** Voice Storage And Delete Semantics, Model Residency And Engine Switching, Transcript And Preview Failure Recovery, Settings Status Detail, Voice Lab Service Boundary, Engine Runtime Strategy

---

## Voice Storage And Delete Semantics

| Question | Option | Description | Selected |
|---|---|---|---|
| What should RayMe keep when a voice is saved? | Keep original sample + transcript + voice metadata only | Matches blob-storage pattern and avoids storing preview audio in Phase 2. | yes |
| What should RayMe keep when a voice is saved? | Also keep the successful preview audio | Useful for quick replay/debugging, but adds audio lifecycle work now. | no |
| What should RayMe keep when a voice is saved? | Keep only processed backend artifacts | Saves space, but makes transcript/voice debugging harder. | no |
| How should deleting a referenced voice behave? | Block deletion and list referents | Safest default; requires reassignment first. | no |
| How should deleting a referenced voice behave? | Allow reassignment during delete | Smoother UX but more scope. | no |
| How should deleting a referenced voice behave? | Cascade to no voice | Fast but silently unvoices characters/chats. | no |
| How should deleting a referenced voice behave? | Other / force delete after confirmation | User chose force-delete after confirmation; references must show `Voice unavailable` and app must not crash. | yes |
| How should rename and identity work? | Stable internal ID; mutable display name | Rename updates display only; references stay stable. | yes |
| How should rename and identity work? | Rename creates a new voice version | More audit history, heavier UI/storage. | no |
| How should rename and identity work? | Name is unique identity | Simple but brittle. | no |

**User's choices:** Keep original sample/transcript/metadata only; allow confirmed force-delete of referenced voices; references degrade to `Voice unavailable`; stable ID with mutable name.

---

## Model Residency And Engine Switching

| Question | Option | Description | Selected |
|---|---|---|---|
| Which TTS engines are in scope? | Three v1 Voice Lab engines only | Earlier roadmap/UI-SPEC framing. | no |
| Which TTS engines are in scope? | Three visible engines with extensible backend | Backend-ready for future engines, UI limited now. | no |
| Which TTS engines are in scope? | Full measured engine roster throughout project | F5-TTS, XTTS v2, Qwen3-TTS 0.6B-Base, LuxTTS, Chatterbox Turbo, TADA 1B. | yes |
| How should switching feel? | Visible warm/switch state, then continue automatically | Honest about loading, no manual load chore. | yes |
| How should switching feel? | Require explicit engine load action | More control, more friction. | no |
| How should switching feel? | Hide switching unless it fails | Clean UI, can feel stalled. | no |
| How should caveats appear? | Concise per-engine caveat chips in picker | Selectable engines with labels for caveats/defaults. | yes |
| How should caveats appear? | Detailed warning modal | Explicit but interrupts experimentation. | no |
| How should caveats appear? | Hide until preview fails or sounds bad | Clean but hides important context. | no |
| What should health report? | Resident engine + available engines + loading state + VRAM/headroom | Enough for Settings/debugging without full dashboard. | yes |
| What should health report? | Only current resident engine and connected status | Too little insight. | no |
| What should health report? | Detailed per-engine diagnostics and benchmark history | Useful but heavy for Phase 2. | no |

**User's choices:** Full measured roster is mandatory; visible automatic switching; caveat chips; compact residency/engine/VRAM health.

---

## Transcript And Preview Failure Recovery

| Question | Option | Description | Selected |
|---|---|---|---|
| If STT transcription fails after upload, what should happen? | Keep sample; allow manual transcript entry plus retry | No re-upload; works for transcript-requiring engines. | yes |
| If STT transcription fails after upload, what should happen? | Keep sample but require STT retry before preview/save | Stricter but blocks manual recovery. | no |
| If STT transcription fails after upload, what should happen? | Force re-upload | Simplest backend path, worst UX. | no |
| What if preview synthesis fails? | Preserve everything and keep Save locked | Initial recommendation, but conflicts with optional preview. | no |
| What if preview synthesis fails? | Preserve sample/transcript but clear engine choice | Annoying after transient failures. | no |
| What if preview synthesis fails? | Clear preview text and force default phrase | Loses user input. | no |
| What if preview synthesis fails? | Other / default engine + optional preview | User chose voice default engine, per-run override, optional preview before save. | yes |
| What should `Use default engine` mean? | Per-voice default, overrideable at use time | Each synthesis can use default or any supported engine. | yes |
| What should `Use default engine` mean? | Global app default unless voice overrides it | More global policy-driven. | no |
| What should `Use default engine` mean? | Backend policy decides defaults | More opaque. | no |
| What happens when saving an unpreviewed voice? | Allow save with `untested voice` state | More explicit. | no |
| What happens when saving an unpreviewed voice? | Allow save silently | User chose no warning/confirmation. | yes |
| What happens when saving an unpreviewed voice? | Ask confirmation before saving | Adds modal friction. | no |

**User's choices:** STT failure preserves upload and allows manual transcript/retry; voices have default engines; preview optional; unpreviewed voices save silently; per-run engine override is allowed.

---

## Settings Status Detail

| Question | Option | Description | Selected |
|---|---|---|---|
| What should Settings expose for AI backend? | Compact operational status | Endpoint, STT, VAD, resident TTS, available engines, loading, VRAM/headroom. | yes |
| What should Settings expose for AI backend? | Minimal endpoint status only | Connected/unreachable/unauthorized/not configured. | no |
| What should Settings expose for AI backend? | Detailed diagnostics panel | Per-engine paths, benchmark history, dependencies, logs. | no |
| How should VAD controls work? | Stored placeholders marked for later call wiring | Save values now, call behavior later. | yes |
| How should VAD controls work? | Hide VAD until calls exist | Avoids fake controls, conflicts with UI contract. | no |
| How should VAD controls work? | Fully wire VAD controls now | Moves Phase 4 behavior into Phase 2. | no |
| How should save-audio defaults work? | Store toggles now with Phase 2 defaults | Save AI audio ON, Save mic audio OFF. | yes |
| How should save-audio defaults work? | Show read-only defaults only | Visible but not editable. | no |
| How should save-audio defaults work? | Hide until calls exist | Simpler UI, conflicts with requirements. | no |

**User's choices:** Compact backend operational status; stored VAD placeholders; persisted save-audio toggles with AI ON/mic OFF defaults.

---

## Voice Lab Service Boundary

| Question | Option | Description | Selected |
|---|---|---|---|
| Which service owns uploads, saved voices, and audio files? | Web UI owns durable storage; AI backend processes audio | Matches SQLite/blob ownership. | yes |
| Which service owns uploads, saved voices, and audio files? | Browser talks directly to AI backend | Lower latency but splits storage/CORS concerns. | no |
| Which service owns uploads, saved voices, and audio files? | AI backend owns voice storage entirely | Processing and files together, but app state split. | no |
| How should Web UI and AI backend exchange audio? | Temporary processing requests; backend returns results | Web UI stays source of truth and persists selectively. | yes |
| How should Web UI and AI backend exchange audio? | Backend fetches stored sample by URL | Useful for large files, requires permissions/reachability. | no |
| How should Web UI and AI backend exchange audio? | Shared filesystem | Fast locally, brittle across LAN machines. | no |

**User's choices:** Web UI is durable owner; AI backend receives transient processing requests and returns transcript/audio/results.

---

## Engine Runtime Strategy

| Question | Option | Description | Selected |
|---|---|---|---|
| How flexible should runtime adapters be? | Per-engine adapters under one AI backend API | One API, adapters can differ if justified. | yes |
| How flexible should runtime adapters be? | Force all engines in-process in one Python runtime | Simple but likely unrealistic. | no |
| How flexible should runtime adapters be? | Separate service per engine | Flexible but operationally heavy. | no |
| What if one engine fails startup/self-test? | Degrade that engine only | Backend and other engines stay available. | yes |
| What if one engine fails startup/self-test? | Fail AI backend startup | One broken optional engine blocks all voice work. | no |
| What if one engine fails startup/self-test? | Hide failed engines silently | Clean UI but bad debugging. | no |
| How validate runtime choices? | Evidence gate per engine | Chosen runtime, rationale, self-test, fallback. | yes |
| How validate runtime choices? | Use fastest known Phase 0 path automatically | Efficient but may skip runtime-unification preference. | no |
| How validate runtime choices? | Implement first, document after | Faster upfront, weaker decision trail. | no |

**User's choices:** One AI backend API with per-engine adapters; default preference is one runtime environment, Windows or WSL; planner must justify splits with evidence; failed engines degrade individually; each engine requires an evidence gate.

---

## the agent's Discretion

- Exact database and API names.
- Exact UI component breakdown.
- Exact caveat chip wording.
- Exact processing endpoint payload shape.
- aiortc signaling skeleton details and license-notice placement, unless research finds a requirement conflict.

## Deferred Ideas

None.
