---
phase: 09
slug: integrate-faster-qwen3-tts-1-7b-into-live-calls
status: approved
shadcn_initialized: false
preset: none
created: 2026-07-31
reviewed_at: 2026-07-31
---

# Phase 09 — UI Design Contract

> Approved visual and interaction contract for the Faster Qwen3-TTS 1.7B integration.

---

## Scope Guard

Phase 09 preserves RayMe's existing Voice Lab, Voice Library, Settings, voice-assignment, and call layouts. It adds only:

- truthful `Qwen3-TTS 1.7B-Base` identity from RayMe server metadata;
- separate model-load and selected-voice preparation states;
- Qwen reference-transcript and authorization validation in the existing creation flow;
- row-scoped preview/test-play progress and retry;
- a call-preparation gate that stays visibly `Connecting` until the selected Qwen voice is ready.

Do not add a dashboard, wizard step, upstream-provider control, model path, cache key, raw runtime log, engine-specific browser route, new call control, or general Voice Lab/call redesign. Do not change non-Qwen behavior. Source: `09-CONTEXT.md` D-02, D-04, D-06–D-11, D-19; `09-08-PLAN.md`; `09-09-PLAN.md`.

## Design System

| Property | Value |
|----------|-------|
| Tool | Existing RayMe CSS custom properties and Svelte components; no shadcn |
| Preset | Not applicable |
| Component library | RayMe-owned Svelte primitives (`TtsEnginePicker`, `SynthPreviewPanel`, `VoiceAssignmentSelect`, `EndpointSettingsPanel`, existing call blocking panel) |
| Icon library | `lucide-svelte` 1.0.1; use existing 1.8px stroke treatment |
| Font | Inter with current system fallbacks for every Phase 09 element |

No new font, component kit, card language, radius scale, or shadow treatment is introduced. Preserve the Ethereal Core / True Dark tonal layering and no-line rule from `docs/stitch/DESIGN.md` and the implemented tokens in `web-ui/client/src/app.css`.

---

## Spacing Scale

Declared values (existing RayMe tokens; multiples of 4):

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | 4px | Icon gaps, status-chip gaps, inline metadata |
| `--space-sm` | 8px | Compact status rows, chips, sibling controls |
| `--space-md` | 16px | Default component gaps, fields, mobile panel padding |
| `--space-lg` | 24px | Engine/readiness panel padding and section gaps |
| `--space-xl` | 32px | Voice Lab workspace and call blocking-panel padding |
| `--space-2xl` | 48px | Existing major section breaks only |
| `--space-3xl` | 64px | Existing page-level spacing only |

Exceptions: preserve the existing 44px minimum interactive target, 20px radio column, 40px Voice Lab step height, and safe-area-aware call control reserve. These are component dimensions, not additions to the spacing scale.

---

## Typography

Use exactly the existing four sizes and two weights. Do not introduce a third weight.

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Label / readiness metadata | 12px | 600 | 1.3 |
| Body / helper and error copy | 14px | 400 | 1.5 |
| Section heading / blocking-panel title | 20px | 600 | 1.2 |
| Voice Lab display heading | 28px | 600 | 1.15 |

Readiness values, timestamps, and stable error copy use label or body text; they never become display text. Long metadata and error text wraps naturally and must not shrink below 12px.

---

## Color

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#060e20` | Page and call-route background; input wells at existing opacity |
| Secondary (30%) | `#091328`, raised `#141f38` | Voice Lab panels, engine cards, readiness rows, Settings status cells, call blocking panel |
| Accent (10%) | `#b6a0ff`; existing pulse gradient to `#70aaff`; `#00e3fd` only for active communication/confirmation | Selected engine inset, primary CTA, retry CTA, ready confirmation, existing active call visualizer |
| Destructive | `#ff716c` | Failed/unavailable status and existing destructive actions only |

Accent reserved for: the selected engine indicator, `Save Voice`, call/retry primary actions, `Model resident` / `Voice ready` confirmation, focus rings, and the existing active Voice Visualizer. Loading and prewarming remain neutral/muted with an icon and text; errors use destructive color. Never color every engine card, status, or button with the accent.

Use background shifts instead of section borders. Existing ghost inset outlines at `rgba(64, 72, 93, 0.28)` and selected inset outlines are allowed; do not add visible 1px dividers.

---

## Component and Layout Contract

### Canonical engine identity

- Every selection, assignment, Settings, Voice Library, and call surface renders the server label `Qwen3-TTS 1.7B-Base` for canonical id `qwen3_1_7b`.
- `qwen3_0_6b` never appears in user-visible copy. It may exist only in compatibility/migration tests.
- Server-returned canonical engines remain visible even when absent from the local fallback roster. Preserve their order from server metadata, then append missing local fallback engines as unavailable.
- The Qwen engine card uses the existing responsive `minmax(180px, 1fr)` grid and card structure. Its chips are `1.7B Base`, `Requires transcript`, and `Native streaming`; do not claim it is the global default.
- Unknown canonical server labels wrap; ids are a last-resort label only. Cards and chips expand vertically without clipping or horizontal scroll.

### Readiness presentation

Model and selected-voice preparation are two independent rows. Do not collapse them into one spinner or boolean.

| Internal state | Visible copy | Visual / semantics |
|----------------|--------------|--------------------|
| model `idle` | `Model not loaded` | Muted label; no spinner |
| model `loading` | `Loading Qwen3-TTS 1.7B…` | Muted row with 16px `RefreshCw`; `role="status"`, polite announcement |
| model `resident` | `Qwen3-TTS 1.7B loaded` | Text plus restrained cyan confirmation treatment |
| model `unavailable` | `Qwen3-TTS 1.7B unavailable` | Destructive text; fixed actionable detail below |
| voice `none` | `Voice not prepared` | Muted label; shown only when a Qwen reference exists |
| voice `prewarming` | `Preparing saved voice…` | Separate muted row with 16px `RefreshCw`; polite announcement |
| voice `ready` | `Saved voice ready` | Text plus restrained cyan confirmation treatment |
| voice `failed` | `Voice preparation failed` | Destructive text plus the applicable retry/navigation action |

- Readiness rows sit inside the selected Qwen engine card for transient Voice Lab preview, and inside the affected Voice Library row for test-play. Settings shows canonical model state only; it must not expose an opaque voice key or become a prompt-cache dashboard.
- Loading/prewarming disables only the initiating Qwen action. Other engine cards, unrelated Voice Library rows, rename/delete actions, transcript editing, and navigation remain responsive.
- Repeated prepare for the same voice reuses the same visible state; do not stack duplicate spinners, toasts, or panels.
- Timestamps may appear as muted label text only when supplied by the server; format them with the existing locale formatter. Never show internal paths, model revisions, provider controls, cache identifiers, or raw worker errors.

### Qwen reference authorization block

When `qwen3_1_7b` is selected, render one compact raised panel immediately after the engine picker and before Preview Voice. Hide it for other engines without clearing entered values.

- Heading: `Reference authorization`
- Body: `Add where this recording came from, why you are authorized to use it, and its permitted RayMe scope.`
- Render the three required typed values from the Phase 09 voice API with labels `Reference source`, `Authorization basis`, and `Use scope`. `Reference source` maps to `voice_data_steward` and must name the speaker/data steward or an opaque steward id; the server binds these three values to its computed reference/transcript SHA-256 values. Use the existing 44px input/select pattern and server-defined option values; do not invent permission, preselect a consent claim, or infer authorization from upload or prior listening.
- All three values begin unconfirmed for a new real-person Qwen voice. Synthetic/evidence values are test-only and must not appear as convenient real-person defaults.
- Preserve these values, the sample, transcript, name, preview text, and engine choice across preview, prewarm, alignment, worker, or network failure and across Qwen/non-Qwen engine switches.
- For Qwen, Save Voice and Preview Voice are disabled until sample, editable nonblank transcript, required authorization values, engine, and relevant target text are locally valid. Server/backend validation remains authoritative.
- Keep Preview optional: a synthesis/runtime preview failure does not by itself block Save Voice when all required fields remain valid. A transcript mismatch or missing authorization is a validation failure and must be corrected before Save.

### Voice Lab and Voice Library

- Keep the existing five-step strip (`Upload`, `Transcript`, `Engine`, `Preview`, `Save`); authorization is conditional content within Engine, not a sixth step.
- Change the Qwen save helper to: `Save Voice needs a sample, name, matching transcript, authorization details, and engine. Preview success is not required.` Preserve the existing helper for non-Qwen engines.
- Preview uses the existing `Preview Voice` button. During load/prewarm it reads `Preparing voice…`; during native synthesis it reads `Synthesizing…`.
- Test-play uses the existing `Test Voice` button. During load/prewarm it reads `Preparing voice…`; during synthesis it reads `Testing voice…`.
- Row progress stays inside the affected card. It must not replace the whole library with a loading state or disable unrelated rows.
- Assignment controls show the canonical engine label but do not start hidden model work. Model/reference preparation begins through preview, test-play, or call preparation.
- Preserve all existing rename/delete/referent behavior and `Voice unavailable` treatment.

### Settings

- Preserve the compact AI backend residency grid within `EndpointSettingsPanel`; do not add a separate Qwen dashboard.
- `Available engines`, `Resident TTS engine`, and `Loading engine` use canonical label `Qwen3-TTS 1.7B-Base`, never raw `qwen3_1_7b`, when metadata supplies the label.
- If the model is unavailable, show only the fixed public reason from the typed RayMe response. Do not render a traceback, package/model cache path, CUDA internals, upstream URL, transcript, or reference filename.
- Testing/saving Settings remains independent of Qwen load/prewarm work.

### Call preparation gate

- For a selected Qwen voice, the route header status remains `Connecting` and the existing blocking panel remains visible until microphone/WebRTC setup, model `resident`, and selected voice `ready` are all authoritative.
- The blocking panel title is `Preparing voice`. Its body progresses from `Loading Qwen3-TTS 1.7B…` to `Preparing {voice name}…`; show both readiness rows when both states are available.
- Do not render the toolbar, Voice Visualizer, transcript canvas, `Listening`, or `Ready to speak` while either readiness state is incomplete.
- Transition once, directly from the preparation panel to the existing `Listening` call surface when all startup gates pass. Preserve the normal toolbar, visualizer, transcript, interrupt, mute, hangup, reconnect, and 44px mobile-control behavior.
- A retry keeps the route in the existing blocking-panel layout and reuses the current call/voice selection. It does not navigate away or erase state unless the corrective action explicitly opens Voice Lab or Settings.
- Barge-in, interrupt, hangup, engine switch, or session close must immediately stop any preparation/speech progress UI; late ready/done events cannot return the UI to `Listening` or `Speaking`.
- Faster Qwen generation continues to use the same `Rehearsing` / `Speaking` visible call states as other engines. Do not expose chunk counts, queue depth, synthesis completion, or final metrics in the call UI.

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Primary CTA | `Save Voice` |
| Preview CTA | `Preview Voice` → `Preparing voice…` → `Synthesizing…` |
| Test-play CTA | `Test Voice` → `Preparing voice…` → `Testing voice…` |
| Retry CTA | `Retry Preparation` |
| Call preparation | Heading `Preparing voice`; body `Loading Qwen3-TTS 1.7B…` then `Preparing {voice name}…` |
| Empty state heading | `No voices yet` |
| Empty state body | `Upload a 6–15 second WAV, MP3, or FLAC sample to create the first voice.` |
| Missing transcript | `Add the matching reference transcript before using Qwen3-TTS 1.7B.` |
| Transcript mismatch | `This transcript does not appear to match the voice sample. Review the transcript or choose a different sample, then try again.` |
| Missing authorization | `Add the reference source, authorization basis, and use scope before using this voice.` |
| Prewarm failure | `RayMe could not prepare this voice. Retry preparation. Your sample, transcript, name, and engine selection are still here.` |
| Generation ceiling | `RayMe stopped this voice because the generated audio exceeded its safe limit. Check the transcript and try again.` |
| Runtime/worker failure | `Qwen3-TTS 1.7B is unavailable right now. Choose another voice or check AI backend status in Settings.` |
| Generic call-preparation failure | `RayMe could not prepare this voice for the call. Retry preparation, choose another voice, or check Settings.` |
| Destructive confirmation | No new destructive action. Preserve existing `Delete Voice` confirmation and referenced-voice `Force Delete Voice` flow. |

Error/action mapping:

- missing transcript, mismatch, or authorization → existing blocking panel with action `Open Voice Lab`;
- retryable voice-preparation failure → action `Retry Preparation`;
- runtime/worker/backend unavailable → action `Open Settings`;
- selected voice missing/deleted → preserve existing `Choose Voice` action.

All failure text is fixed RayMe copy. Never append backend exception text, reference content, paths, ids, scores, or provider/model internals. Use an inline `role="alert"` for operation failures and the existing call blocking `role="alert"`; use `role="status"` for progress and success.

---

## Responsive and Accessibility Contract

- Preserve Voice Lab's desktop split at 1060px and its single-column mobile flow; readiness and authorization panels remain within the creation column.
- Preserve the engine grid's auto-fit behavior. At 320px minimum width, cards, chips, and long engine/error copy wrap without horizontal page scroll.
- Preserve the call route's single-column layout below 800px, safe-area bottom reserve, sticky toolbar behavior after readiness, and minimum 44px controls.
- Do not communicate `loading`, `ready`, or `failed` by color alone. Every state has visible text; loading additionally has an icon, and failure uses an alert.
- Announce model and voice readiness changes through one polite live region per affected surface. Do not announce polling responses when the visible state has not changed.
- Keep focus on the initiating button during inline progress. On validation failure, move focus to the first invalid Qwen field; on call-preparation failure, focus the blocking-panel heading or action.
- Use the global 2px focus-visible outline. Do not remove focus rings from engine radios, authorization controls, retry, or call controls.
- Honor the existing reduced-motion rule. Any rotating progress icon becomes static under `prefers-reduced-motion: reduce`; text still communicates progress.

---

## UI Considerations

> Shape-rooted state coverage for the Phase 09 surfaces. Empty/error copy references the Copywriting Contract rather than duplicating variants.

Applicable state considerations resolved: 8 covered, 0 backstop, 0 unresolved.

| Category | Element(s) | Status | Resolution / Reason |
|----------|------------|--------|---------------------|
| empty | Voice Library list | ✅ covered | Preserve the documented `No voices yet` state and upload next step. Readiness does not replace it. |
| loading | Engine metadata, readiness rows, preview/test controls, call gate | ✅ covered | Separate model and voice progress appears inline; only the initiating action is disabled; call remains `Connecting`. |
| error | Voice form, engine card, row action, call gate | ✅ covered | Fixed sanitized copy plus retry/navigation action; form state is preserved and unrelated engines remain usable. |
| populated | Engine picker and Voice Library | ✅ covered | Canonical metadata renders in existing responsive cards/rows with readiness local to the selected/affected item. |
| partial | Qwen reference form | ✅ covered | Blank transcript or any missing authorization value marks/focuses the first invalid field and blocks only Qwen operations. |
| overflow | Engine grid, chips, readiness/error text | ✅ covered | Auto-fit grid and wrapping expand vertically; no clipping, ellipsis of actionable errors, or horizontal page scroll. |
| zero-one-many | Voice Library and engine roster | ✅ covered | Existing empty, single-row, and spaced multi-row layouts remain intact; dynamic canonical engines are not filtered out. |
| long-text | Engine labels, voice names, authorization values, errors | ✅ covered | Labels/errors wrap; existing voice-name ellipsis retains full accessible name/title; private raw text is never rendered. |

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | Not applicable — `components.json` absent; existing Svelte design system retained — 2026-07-31 |
| Third-party registries | none | Not applicable — no registry block enters this contract — 2026-07-31 |

`lucide-svelte` is an existing pinned project dependency, not a shadcn registry block. Phase 09 adds no third-party UI package.

---

## Source Trace

| Source | Contract decisions used |
|--------|-------------------------|
| `09-CONTEXT.md` | Canonical identity, separate readiness, validation, sanitized errors, call-state truthfulness, no redesign |
| `09-RESEARCH.md` | Existing Svelte surfaces, dynamic-metadata retention, async readiness, failure categories, no internal disclosure |
| `09-PATTERNS.md` | Exact components/analogs, row-scoped progress, normalization bug, call blocking-panel reuse |
| `09-08-PLAN.md` | Fast identity/readiness/validation/retry and no-premature-Listening contracts |
| `09-09-PLAN.md` | Mocked browser state sequence, form preservation, mobile controls, deployed call acceptance boundary |
| `app.css` and `docs/stitch/DESIGN.md` | Implemented tokens, True Dark palette, spacing/type scale, no-line and reduced-motion rules |

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: PASS
- [x] Dimension 6 Registry Safety: PASS

**Approval:** VERIFIED by gsd-ui-checker on 2026-07-31
