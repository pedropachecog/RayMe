# Phase 02: AI Backend Skeleton & Voice Lab - Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 gets the AI backend models resident behind the correct three-service topology and delivers Voice Lab end-to-end before the first call phase. It includes STT, VAD, TTS engine residency/switching, Voice Lab upload -> transcript -> edit -> optional preview -> save, Voice Library list/rename/delete/test-play, character default voice assignment, Settings endpoint tests, compact AI backend status, VAD setting placeholders, and save-audio defaults.

This phase does not implement the live call screen, full WebRTC call flow, barge-in call semantics, call captions, saved call-audio replay in threads, per-chat voice override UX, full Voice Visualizer, PWA/mobile hardening, or later storage housekeeping polish.

</domain>

<spec_lock>
## Design Contract Lock

`.planning/phases/02-ai-backend-skeleton-voice-lab/02-UI-SPEC.md` is an approved Phase 2 UI design contract and downstream agents MUST read it before planning. It is not a standard numbered SPEC.md, but it locks the current screen/component/copy/accessibility contract except where this context explicitly supersedes it.

**Superseded by this context:**
- Any "three TTS engines only" framing is obsolete. RayMe must work with the full measured TTS roster: `F5-TTS`, `XTTS v2`, `Qwen3-TTS 0.6B-Base`, `LuxTTS`, `Chatterbox Turbo`, and `TADA 1B`.
- The UI-SPEC rule that `Save Voice` is disabled until preview succeeds is superseded. Preview is optional; unpreviewed voices may save silently.
- The UI-SPEC engine picker must be expanded from three options to the full roster and should render concise caveat chips from engine metadata.

**In scope from UI-SPEC/roadmap:** Voice Lab, Voice Library, default voice assignment, Gallery voice state, Settings endpoint/audio/VAD controls, AI backend status, and local component extensions.

**Out of scope from UI-SPEC/roadmap:** live WebRTC call screen, call toolbar, live call captions, full Voice Visualizer, per-chat voice override UX, saved per-turn replay in thread, PWA install polish, account/billing/logout surfaces, and unrelated redesign of Phase 1 screens.

</spec_lock>

<decisions>
## Implementation Decisions

### Project-Wide TTS Roster
- **D-01:** Hard project rule: RayMe must work with the full measured TTS engine roster throughout planning and implementation: `F5-TTS`, `XTTS v2`, `Qwen3-TTS 0.6B-Base`, `LuxTTS`, `Chatterbox Turbo`, and `TADA 1B`.
- **D-02:** Do not frame RayMe as supporting only three TTS engines in future planning. The current UI-SPEC and earlier roadmap language are superseded where they imply only three user-facing engines.
- **D-03:** Use an extensible engine registry/metadata model rather than hard-coded fixed-engine conditionals. Engine metadata should drive labels, caveat chips, availability, default status, runtime status, and licensing/runtime/quality notes.

### Voice Storage And Identity
- **D-04:** A saved voice stores the original uploaded sample, editable transcript, voice metadata, and stable internal voice ID. Phase 2 does not persist successful preview audio as part of voice save.
- **D-05:** Voice names are user-facing and mutable. Renaming a voice updates display text only; references use the stable internal voice ID.
- **D-06:** A voice stores a default engine, but the voice is not permanently locked to that engine.

### Voice Delete Semantics
- **D-07:** Referenced voices may be force-deleted after explicit confirmation.
- **D-08:** Deleting a referenced voice must not crash the application and must not silently corrupt character/chat state. Existing references degrade into a visible `Voice unavailable` state whenever a character/chat tries to use a deleted voice.
- **D-09:** Planning should consider a tombstone/soft-delete shape for voices so the app can explain broken references by readable voice/character/chat names after deletion.

### Engine Switching And Caveats
- **D-10:** Engine switching is visible and automatic. When a preview/test/call requires a non-resident engine, RayMe shows a warm/switch state such as loading the target engine, then continues automatically once ready.
- **D-11:** Every supported engine remains selectable unless unavailable. The picker should show concise caveat chips for defaults, quality caveats, runtime caveats, latency caveats, experimental status, or licensing constraints as applicable.
- **D-12:** Backend health/status reports current resident engine, available engines, engine loading/switching state, and VRAM/headroom.

### Transcript And Preview Flow
- **D-13:** If STT transcription fails, keep the uploaded sample and allow both transcription retry and manual transcript entry. Do not force re-upload.
- **D-14:** Preview before save is optional. A voice can be saved without a successful preview and without warning/confirmation.
- **D-15:** Synthesis surfaces should include a `Use default engine` toggle. When enabled, the synthesis run uses the voice's stored default engine. When disabled, the user can choose any supported engine for that preview, test-play, or later call synthesis run.
- **D-16:** If preview synthesis fails, preserve sample, voice name, transcript, selected/default engine settings, and preview text so the user can retry, edit, switch engine, or save anyway.

### Settings
- **D-17:** Settings exposes compact operational AI backend status: endpoint status, STT model, VAD readiness, resident TTS engine, available engines, loading state, and VRAM/headroom.
- **D-18:** Settings shows VAD threshold and end-of-utterance silence placeholders in Phase 2. Values may be stored now, but the UI must clearly mark that call behavior wiring belongs to the later call-feel phase.
- **D-19:** Settings stores editable save-audio toggles in Phase 2. Defaults: Save AI audio ON, Save mic audio OFF. Later call/replay behavior consumes these persisted settings.

### Service Boundary
- **D-20:** The Web UI server owns durable voice storage: saved voice records, uploaded samples, transcripts, metadata, and persisted audio blobs.
- **D-21:** The AI backend is a processing service for STT/TTS/VAD/model residency work. It is not the source of truth for durable app state.
- **D-22:** Web UI and AI backend exchange audio through transient processing requests. Web UI sends the stored sample reference or bytes as needed; AI backend returns transcript/audio bytes or processing results. Web UI decides what to persist.

### Engine Runtime Strategy
- **D-23:** Use one AI backend API with per-engine adapters. Adapters may use different runtime mechanisms if justified, but runtime placement is not pre-decided.
- **D-24:** The user's default preference is one runtime environment for all engines, either Windows or WSL. Research/planning must provide evidence before recommending a split across Windows, WSL, Docker/Triton, subprocesses, or in-process adapters.
- **D-25:** If one engine cannot load or fails startup self-test, degrade only that engine. Keep the backend and other engines available; health marks the failed engine unavailable with a reason, and the UI disables or caveats it without hiding the failure.
- **D-26:** Each engine runtime choice needs an evidence gate before implementation commitment: chosen runtime, rationale, install/self-test command, and fallback if that runtime fails.

### the agent's Discretion
- Exact database table/column names for voices, voice assets, engine metadata, and tombstones, as long as the stable-ID/delete semantics above are preserved.
- Exact component decomposition for Voice Lab, Voice Library, engine picker, and Settings panels, subject to the UI-SPEC plus supersessions above.
- Exact wording of engine caveat chips, as long as labels are concise and honest.
- Exact processing endpoint shape between Web UI and AI backend, as long as Web UI remains durable owner and AI backend remains processing owner.
- Exact implementation of aiortc signaling skeleton and license-notice placement, unless later research finds a requirement conflict.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Scope And Current Decisions
- `.planning/ROADMAP.md` - Phase 2 goal, requirements delivered, pitfalls owned, success criteria, and dependency boundaries.
- `.planning/REQUIREMENTS.md` - Phase 2 requirements, especially REQ-02, REQ-05, REQ-15, REQ-20 through REQ-24, REQ-62, REQ-80, REQ-90, and REQ-A3.
- `.planning/PROJECT.md` - Product vision, core value, constraints, out-of-scope boundaries, and Phase 0 frozen decisions.
- `.planning/STATE.md` - Current project status, full measured TTS engine policy, STT/TTS defaults, VRAM notes, and operating decisions.
- `.planning/OPERATING-NOTES.md` - Live LAN/OMEN-PC/TLS operating rules for backend and Android HTTPS work.

### Phase 2 Design Contract
- `.planning/phases/02-ai-backend-skeleton-voice-lab/02-UI-SPEC.md` - Approved Phase 2 UI contract. Must be read, but three-engine and preview-required language is superseded by this context.
- `docs/stitch/DESIGN.md` - Ethereal Core / True Dark design system.
- `docs/stitch/screens/voice-lab-true-dark.md` - Voice Lab visual/reference notes.
- `docs/stitch/html/voice-lab-true-dark.html` - Voice Lab HTML reference.
- `docs/stitch/screens/settings-true-dark.md` - Settings visual/reference notes.
- `docs/stitch/html/settings-true-dark.html` - Settings HTML reference.

### Prior Phase Context
- `.planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md` - Web UI/FastAPI/SQLite/filesystem blob ownership, app shell, Settings, and design decisions.
- `.planning/phases/01.1-ui-acceptance-and-regression-test-hardening/01.1-CONTEXT.md` - Agent-first browser/live verification rule and Settings save-before-test regression context.
- `.planning/phases/01-foundations-text-chat-end-to-end/01-UI-SPEC.md` - Approved Phase 1 UI design contract.
- `.planning/phases/01.1-ui-acceptance-and-regression-test-hardening/01.1-UI-SPEC.md` - Phase 01.1 UI acceptance constraints.

### Phase 0 Evidence And Engine Measurements
- `.planning/phases/00-measurement-gate/KEY_DECISIONS.md` - Human-readable Phase 0 model/runtime decisions.
- `.planning/phases/00-measurement-gate/results/phase0_summary.json` - Machine-readable Phase 0 roll-up.
- `.planning/phases/00-measurement-gate/results/tts_runtime_matrix.json` - Original TTS runtime matrix.
- `.planning/phases/00-measurement-gate/results/tts_runtime_matrix_v2.json` - Warm-model/runtime matrix including extended engine paths and scenario results.
- `.planning/spikes/MANIFEST.md` - WSL/GPU/runtime spike record, including F5 Triton/TensorRT and extended TTS engine investigation.

### Existing Code Entry Points
- `web-ui/server/app/storage/models.py` - Existing SQLAlchemy schema patterns and unified message-kind values.
- `web-ui/server/alembic/versions/0001_initial_schema.py` - Current migration style.
- `web-ui/server/app/storage/blob_store.py` - Atomic filesystem blob write pattern to reuse for voice samples/audio.
- `web-ui/server/app/storage/reaper.py` - Orphan cleanup pattern.
- `web-ui/server/app/domain/settings_service.py` - Existing persisted Settings service pattern to extend.
- `web-ui/server/app/api/settings.py` - Existing Settings endpoint and connection-test routes.
- `web-ui/client/src/routes/settings/+page.svelte` - Current Settings screen and save-before-test behavior.
- `web-ui/client/src/lib/components/EndpointSettingsPanel.svelte` - Existing endpoint panel component.
- `web-ui/client/src/lib/components/ConfirmDialog.svelte` - Existing confirmation dialog component.
- `web-ui/client/src/lib/components/ToastStack.svelte` - Existing toast component.
- `web-ui/client/src/lib/components/AppShell.svelte` - Current app navigation shell.
- `ai-backend/app/main.py` - Current AI backend health stub to grow into model residency and processing APIs.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `web-ui/server/app/storage/blob_store.py` provides same-directory temp-file + atomic rename blob writes. Use this pattern for voice samples and any persisted audio blobs.
- `web-ui/server/app/storage/reaper.py` provides orphan cleanup mechanics that can be extended for voice/audio blob lifecycle.
- `web-ui/server/app/storage/models.py` and `web-ui/server/alembic/versions/0001_initial_schema.py` establish SQLAlchemy + Alembic schema style.
- `web-ui/server/app/domain/settings_service.py` and `web-ui/server/app/api/settings.py` provide a persisted Settings service and endpoint-test shape.
- `web-ui/client/src/lib/components/EndpointSettingsPanel.svelte`, `ConfirmDialog.svelte`, `ToastStack.svelte`, and `StatusChip.svelte` are existing local UI primitives to reuse.
- `web-ui/client/src/app.css` already defines the approved True Dark tokens.
- `ai-backend/app/main.py` is only a health stub today; it is the integration point for model residency, processing APIs, and compact status.

### Established Patterns
- Durable app state lives in the Web UI server, backed by SQLite and filesystem blobs.
- The browser talks to RayMe-owned routes; provider/backend details stay server-side where possible.
- Settings tests save current form values before probing endpoints.
- UI uses local Svelte components, `lucide-svelte` icons, True Dark tokens, no shadcn/Radix registry, and no broad redesign.
- Agent verification must include backend/API tests plus browser-level Playwright checks before product-owner manual testing.

### Integration Points
- Add voice tables/assets/migrations in `web-ui/server/app/storage` and expose Web UI APIs under `web-ui/server/app/api`.
- Add Voice Lab and Voice Library client routes/components under `web-ui/client/src`.
- Extend Settings payloads and UI to store VAD/audio defaults and display compact backend residency status.
- Grow `ai-backend/app/main.py` into processing/status endpoints while keeping a single public AI backend API surface.
- Character default voice assignment connects to existing character APIs and Gallery/Editor response shapes.

</code_context>

<specifics>
## Specific Ideas

- The full measured TTS roster is a hard correction from the user and should be treated as a durable project rule.
- Engine caveat chips should come from engine metadata, not one-off UI copy.
- Runtime decisions are not to be assumed from previous benchmarks alone. Planning must bring evidence, especially if recommending a split runtime against the user's preference for one environment.
- "Voice unavailable" must be a normal recoverable UI state when a deleted voice is still referenced.
- Preview is a convenience, not a save gate.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within Phase 2 scope.

</deferred>

---

*Phase: 02-ai-backend-skeleton-voice-lab*
*Context gathered: 2026-04-24*
