# Phase 02: AI Backend Skeleton & Voice Lab - Research

**Researched:** 2026-04-24 [VERIFIED: system date]
**Domain:** FastAPI AI processing service, SvelteKit Voice Lab UI, SQLite/filesystem voice storage, local STT/VAD/TTS runtime residency [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md]
**Confidence:** HIGH for codebase/API/storage/UI boundaries; MEDIUM for TTS runtime placement until live adapter self-tests run on OMEN-PC [VERIFIED: codebase grep; VERIFIED: .planning/phases/00-measurement-gate/results/tts_runtime_matrix_v2.json]

<user_constraints>
## User Constraints (from CONTEXT.md)

Source: `.planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md` [VERIFIED: file read]

### Locked Decisions

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

### Claude's Discretion
- Exact database table/column names for voices, voice assets, engine metadata, and tombstones, as long as the stable-ID/delete semantics above are preserved.
- Exact component decomposition for Voice Lab, Voice Library, engine picker, and Settings panels, subject to the UI-SPEC plus supersessions above.
- Exact wording of engine caveat chips, as long as labels are concise and honest.
- Exact processing endpoint shape between Web UI and AI backend, as long as Web UI remains durable owner and AI backend remains processing owner.
- Exact implementation of aiortc signaling skeleton and license-notice placement, unless later research finds a requirement conflict.

### Deferred Ideas (OUT OF SCOPE)

## Deferred Ideas

None - discussion stayed within Phase 2 scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-02 | AI backend is a stateless real-time orchestrator for RTX 3060 with STT, VAD, and one resident TTS engine coexisting. [VERIFIED: .planning/REQUIREMENTS.md] | Use AI backend lifespan/model manager, one-hot resident TTS registry, `/health` residency payload, and OMEN-PC GPU self-tests. [VERIFIED: ai-backend/app/main.py; VERIFIED: .planning/phases/00-measurement-gate/results/phase0_summary.json] |
| REQ-05 | Settings exposes endpoint configuration and connection tests. [VERIFIED: .planning/REQUIREMENTS.md] | Extend existing Settings service/API/UI and preserve save-before-test behavior. [VERIFIED: web-ui/server/app/domain/settings_service.py; VERIFIED: web-ui/server/app/api/settings.py; VERIFIED: web-ui/client/src/routes/settings/+page.svelte] |
| REQ-15 | Characters have default voices; per-chat override is later. [VERIFIED: .planning/REQUIREMENTS.md; VERIFIED: .planning/ROADMAP.md] | Add character default voice ID/schema/API/UI and Gallery state; leave in-call use and per-chat override verification to later phases. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md] |
| REQ-20 | Voice Lab accepts WAV/MP3/FLAC 6-15s samples with warnings outside the envelope. [VERIFIED: .planning/REQUIREMENTS.md] | Web UI server should validate/upload with multipart, store original blob atomically, and return metadata/warnings. [CITED: https://fastapi.tiangolo.com/tutorial/request-files; VERIFIED: web-ui/server/app/storage/blob_store.py] |
| REQ-21 | Uploaded samples are auto-transcribed into editable reference transcript. [VERIFIED: .planning/REQUIREMENTS.md] | AI backend STT endpoint should use faster-whisper with explicit English transcription, VAD gating, and `condition_on_previous_text=False` to reduce hallucination carryover. [CITED: https://context7.com/systran/faster-whisper/llms.txt; VERIFIED: .planning/ROADMAP.md] |
| REQ-22 | Voice save captures name, engine, sample path, transcript, timestamps, and selected engine. [VERIFIED: .planning/REQUIREMENTS.md] | Supersede three-engine language with six-engine registry while preserving default-engine-per-voice metadata. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md] |
| REQ-23 | Voice Library supports list, rename, delete, and test-play. [VERIFIED: .planning/REQUIREMENTS.md] | Add voice service/routes/client API plus row-scoped synthesis calls to AI backend; test-play audio remains transient unless later saved by a call phase. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md] |
| REQ-24 | Deleting referenced voices must not leave dangling references. [VERIFIED: .planning/REQUIREMENTS.md] | Use soft-delete/tombstone or deleted-at voice row; characters render `Voice unavailable` from stable voice ID lookup. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md] |
| REQ-80 | Settings includes endpoint tests, STT/TTS defaults, VAD placeholders, devices later, and save-audio toggles. [VERIFIED: .planning/REQUIREMENTS.md] | Phase 2 stores endpoint tests, save-audio defaults, STT/TTS status/defaults, and VAD placeholders; device wiring and clear-data can remain later unless already supported. [VERIFIED: .planning/ROADMAP.md; VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md] |
| REQ-A3 | English-only STT/TTS with Spanish-accented English STT quality bar. [VERIFIED: .planning/REQUIREMENTS.md] | Use Phase 0 frozen `distil-large-v3` `int8_float16` default and set STT language/task to English/transcribe. [VERIFIED: .planning/phases/00-measurement-gate/KEY_DECISIONS.md; CITED: https://context7.com/systran/faster-whisper/llms.txt] |
| REQ-90 | UI implements Ethereal Core / True Dark screen inventory. [VERIFIED: .planning/REQUIREMENTS.md] | Follow approved Phase 2 UI-SPEC plus context supersessions; reuse local Svelte components and True Dark tokens. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-UI-SPEC.md; VERIFIED: docs/stitch/DESIGN.md] |
</phase_requirements>

## Summary

Phase 2 should be planned as a contract-first vertical slice: Web UI server owns durable voice records and audio blobs, AI backend owns transient STT/VAD/TTS/model residency processing, and the Svelte client owns Voice Lab/Library/Settings workflows against RayMe-owned APIs. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md; VERIFIED: web-ui/server/app/storage/models.py; VERIFIED: ai-backend/app/main.py]

The safest implementation order is schema/storage/API first, client routes/components second, AI backend residency/status third, then adapter self-tests and live OMEN-PC evidence gates before enabling each engine. [VERIFIED: .planning/OPERATING-NOTES.md; VERIFIED: .planning/phases/00-measurement-gate/results/tts_runtime_matrix_v2.json] This avoids binding UI persistence to runtime guesses and respects the locked decision that split runtime is not allowed without evidence. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md]

The biggest planning risks are not UI complexity; they are runtime drift from the measured Phase 0 stack, TTS package/license confusion, Whisper hallucination on short/quiet samples, and accidentally treating preview synthesis as a save prerequisite. [VERIFIED: .planning/ROADMAP.md; VERIFIED: .planning/phases/00-measurement-gate/requirements-phase0.txt; CITED: https://pypi.org/project/f5-tts/; CITED: https://huggingface.co/coqui/XTTS-v2]

**Primary recommendation:** Plan Phase 2 as four waves: durable voice schema/API/storage, Voice Lab/Library/Settings UI, AI backend model manager/status/STT/VAD endpoints, then per-engine TTS adapter enablement with one runtime evidence gate per engine. [VERIFIED: codebase inspection; VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Voice record persistence | Web UI server | Database / filesystem storage | Durable voice records, uploaded samples, transcripts, and persisted blobs are locked to the Web UI server. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md] |
| Sample upload validation | Web UI server | Browser / client | Browser validates obvious file type/duration UX; server performs authoritative multipart validation and atomic blob write. [CITED: https://fastapi.tiangolo.com/tutorial/request-files; VERIFIED: web-ui/server/app/storage/blob_store.py] |
| STT transcription | AI backend | Web UI server | AI backend owns processing; Web UI server sends transient bytes/path and stores final editable transcript. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md] |
| VAD readiness and thresholds | AI backend | Web UI server / client | Silero VAD is processing-side; Phase 2 stores placeholder settings while call wiring is deferred. [CITED: https://context7.com/snakers4/silero-vad/llms.txt; VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md] |
| TTS synthesis preview/test-play | AI backend | Web UI server | AI backend synthesizes transient audio; Web UI server decides whether any audio is persisted later. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md] |
| Engine registry/status | AI backend | Web UI server / client | AI backend reports resident/loading/available/unavailable engines and reasons; client renders caveat chips from metadata. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md] |
| Character default voice | Web UI server | Browser / client | Character storage/API owns stable voice ID references; client edits/surfaces state. [VERIFIED: web-ui/server/app/storage/models.py; VERIFIED: web-ui/client/src/routes/characters/[id]/+page.svelte] |
| Settings endpoint tests | Web UI server | Browser / client | Existing Settings API persists form values then probes configured endpoints; client must preserve save-before-test. [VERIFIED: web-ui/server/app/api/settings.py; VERIFIED: web-ui/client/src/routes/settings/+page.svelte] |
| AI backend health | AI backend | Web UI server / client | Current AI backend owns `/health`; Web UI Settings probes it and displays compact residency status. [VERIFIED: ai-backend/app/main.py; VERIFIED: web-ui/server/app/api/settings.py] |
| aiortc signaling skeleton | AI backend | Browser / client | aiortc belongs in AI backend for later media transport; Phase 2 should only expose a non-call skeleton if planned. [CITED: https://context7.com/aiortc/aiortc/llms.txt; VERIFIED: .planning/ROADMAP.md] |

## Project Constraints

- No `./AGENTS.md` or `./CLAUDE.md` file exists in the repo root, so no root-level agent instruction file was available to apply. [VERIFIED: `find . -maxdepth 2 \( -name AGENTS.md -o -name CLAUDE.md \) -print`]
- No `.claude/skills/` or `.agents/skills/` project skill directory exists, so no project-local skill rules were available to load. [VERIFIED: `find . -maxdepth 3 -type d \( -path './.claude/skills' -o -path './.agents/skills' \) -print`]
- Live LAN/runtime work must target `OMEN-PC` at `192.168.1.199`, keep Windows-side RayMe artifacts under `C:\Users\pmpg\rayme\`, reuse `.local/phase1-tls/`/`C:\Users\pmpg\rayme\phase1-tls\`, and avoid throwaway certificates. [VERIFIED: .planning/OPERATING-NOTES.md]
- The agent must run backend/API, Playwright/browser, and live deployed checks before asking the user for Android product-owner testing. [VERIFIED: .planning/OPERATING-NOTES.md; VERIFIED: .planning/phases/01.1-ui-acceptance-and-regression-test-hardening/01.1-CONTEXT.md]

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | `0.136.1` | Web UI server and AI backend APIs. [VERIFIED: web-ui/server/pyproject.toml; VERIFIED: ai-backend/pyproject.toml; VERIFIED: PyPI JSON] | Already pinned in both services and documented for multipart uploads/dependency injection. [CITED: https://fastapi.tiangolo.com/tutorial/request-files] |
| uvicorn | `0.46.0` | HTTPS ASGI runtime. [VERIFIED: web-ui/server/pyproject.toml; VERIFIED: ai-backend/pyproject.toml; VERIFIED: PyPI JSON] | Existing runners already pass TLS cert/key paths through uvicorn. [VERIFIED: ai-backend/tests/test_health.py] |
| SQLAlchemy | `2.0.49` | ORM storage models. [VERIFIED: web-ui/server/pyproject.toml; VERIFIED: PyPI JSON] | Existing schema uses SQLAlchemy Declarative ORM and async sessions. [VERIFIED: web-ui/server/app/storage/models.py; VERIFIED: web-ui/server/app/storage/session.py] |
| Alembic | `1.18.4` | SQLite migrations. [VERIFIED: web-ui/server/pyproject.toml; VERIFIED: PyPI JSON] | Existing schema is migration-first and Alembic provides create/add/alter operations. [VERIFIED: web-ui/server/alembic/versions/0001_initial_schema.py; CITED: https://alembic.sqlalchemy.org] |
| aiosqlite | `0.22.1` | Async SQLite driver. [VERIFIED: web-ui/server/pyproject.toml; VERIFIED: PyPI JSON] | Existing storage session creates `sqlite+aiosqlite` engines and enables SQLite foreign keys. [VERIFIED: web-ui/server/app/storage/session.py] |
| python-multipart | `0.0.26` | Server-side multipart uploads. [VERIFIED: web-ui/server/pyproject.toml; VERIFIED: PyPI JSON] | FastAPI file upload support requires multipart parsing for `UploadFile`. [CITED: https://fastapi.tiangolo.com/tutorial/request-files] |
| SvelteKit | `2.58.0` | Client routes and static build. [VERIFIED: web-ui/client/package.json; VERIFIED: npm registry] | Existing client is a SvelteKit static app mounted by the FastAPI host. [VERIFIED: web-ui/server/app/main.py; VERIFIED: web-ui/client/package.json] |
| Svelte | `5.55.5` | Component UI. [VERIFIED: web-ui/client/package.json; VERIFIED: npm registry] | Existing components use Svelte 5 patterns and local component primitives. [VERIFIED: web-ui/client/src/lib/components/AppShell.svelte] |
| faster-whisper | `1.2.1` | STT default implementation. [VERIFIED: .planning/phases/00-measurement-gate/requirements-phase0.txt; VERIFIED: PyPI JSON] | Phase 0 selected `distil-large-v3` with `int8_float16` on the RTX 3060 and faster-whisper exposes language/VAD/decoder controls. [VERIFIED: .planning/phases/00-measurement-gate/KEY_DECISIONS.md; CITED: https://context7.com/systran/faster-whisper/llms.txt] |
| silero-vad | `6.2.1` | VAD model and speech timestamp extraction. [VERIFIED: PyPI JSON] | Silero VAD exposes `read_audio`, `get_speech_timestamps`, and threshold/sampling-rate controls. [CITED: https://context7.com/snakers4/silero-vad/llms.txt] |
| PyTorch | `2.5.1+cu118` measured; verify current target before lock update. [VERIFIED: .planning/phases/00-measurement-gate/results/phase0_summary.json] | CUDA runtime for STT/VAD/TTS. [VERIFIED: .planning/phases/00-measurement-gate/results/phase0_summary.json] | Phase 0 measurements were captured on the target RTX 3060 with this torch stack, so adapter evidence should start there or explicitly remeasure. [VERIFIED: .planning/phases/00-measurement-gate/results/phase0_summary.json] |
| f5-tts | Recommend `1.1.17` for Phase 0 parity; current PyPI is `1.1.20` uploaded 2026-04-20. [VERIFIED: .planning/phases/00-measurement-gate/requirements-phase0.txt; VERIFIED: PyPI JSON; CITED: https://pypi.org/project/f5-tts/] | Default TTS engine. [VERIFIED: .planning/STATE.md] | Phase 0 measured F5 as v1 default; newer f5-tts releases need a startup self-test before replacing the measured pin. [VERIFIED: .planning/phases/00-measurement-gate/KEY_DECISIONS.md; CITED: https://pypi.org/project/f5-tts/] |
| coqui-tts | `0.27.5` | XTTS v2 runtime via idiap fork. [VERIFIED: .planning/phases/00-measurement-gate/requirements-phase0.txt; VERIFIED: PyPI JSON; CITED: https://pypi.org/project/coqui-tts/] | Project explicitly forbids abandoned `TTS` package framing and uses `coqui-tts` idiap fork. [VERIFIED: .planning/ROADMAP.md; CITED: https://pypi.org/project/coqui-tts/] |
| qwen-tts | `0.1.1` | Qwen3-TTS 0.6B-Base opt-in runtime. [VERIFIED: .planning/phases/00-measurement-gate/requirements-phase0.txt; VERIFIED: PyPI JSON] | Phase 0 and roadmap pin this version because install friction and later-breaking upgrades are known risks. [VERIFIED: .planning/ROADMAP.md; VERIFIED: .planning/phases/00-measurement-gate/KEY_DECISIONS.md] |
| aiortc | `1.14.0` | Phase 2 signaling skeleton for Phase 3 media path. [VERIFIED: PyPI JSON] | aiortc provides Python `RTCPeerConnection`, media track, and data channel primitives. [CITED: https://context7.com/aiortc/aiortc/llms.txt] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | `0.28.1` | Server-to-server health and processing probes. [VERIFIED: web-ui/server/pyproject.toml; VERIFIED: ai-backend/pyproject.toml; VERIFIED: PyPI JSON] | Use for Web UI server calls to AI backend, matching existing Settings probe infrastructure. [VERIFIED: web-ui/server/app/api/settings.py] |
| pydantic | `2.13.3` | Request/response validation. [VERIFIED: web-ui/server/pyproject.toml; VERIFIED: PyPI JSON] | Use for voice payloads, engine metadata, Settings extension, and health schemas. [VERIFIED: web-ui/server/app/api/settings.py] |
| soundfile | `0.13.1` | WAV/FLAC read/write and TTS output serialization. [VERIFIED: .planning/phases/00-measurement-gate/requirements-phase0.txt; VERIFIED: PyPI JSON; CITED: https://github.com/QwenLM/Qwen3-TTS] | Use inside AI backend adapters for generated WAV output where the engine returns arrays. [CITED: https://github.com/QwenLM/Qwen3-TTS] |
| librosa | `0.11.0` | Audio loading/resampling metadata fallback. [VERIFIED: .planning/phases/00-measurement-gate/requirements-phase0.txt; VERIFIED: PyPI JSON] | Use only if `soundfile`/engine helpers cannot produce duration/sample-rate/channel metadata. [VERIFIED: .planning/phases/00-measurement-gate/requirements-phase0.txt] |
| pynvml | `13.0.1` | NVIDIA VRAM telemetry alternative. [VERIFIED: .planning/phases/00-measurement-gate/requirements-phase0.txt; VERIFIED: PyPI JSON] | Use when PyTorch CUDA memory stats do not reflect full device residency across subprocesses. [VERIFIED: .planning/phases/00-measurement-gate/requirements-phase0.txt] |
| `torch.cuda.memory.*` | PyTorch API | CUDA allocated/reserved/free memory stats. [CITED: https://docs.pytorch.org/docs/stable/generated/torch.cuda.memory.mem_get_info.html] | Use in `/health` to report VRAM/headroom, backed by live `nvidia-smi` acceptance on OMEN-PC. [CITED: https://docs.pytorch.org/docs/stable/generated/torch.cuda.memory.mem_get_info.html; VERIFIED: .planning/OPERATING-NOTES.md] |
| lucide-svelte | `1.0.1` | UI icons. [VERIFIED: web-ui/client/package.json; VERIFIED: npm registry] | Use for Voice Lab, Library, Settings, and nav icons per UI-SPEC. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-UI-SPEC.md] |
| @playwright/test | `1.59.1` | Browser/E2E validation. [VERIFIED: web-ui/client/package.json; VERIFIED: npm registry] | Use default desktop/mobile projects and live OMEN-PC opt-in tests. [VERIFIED: web-ui/client/playwright.config.ts; CITED: https://github.com/microsoft/playwright] |
| vitest | `4.1.5` | Client unit/static contract tests. [VERIFIED: web-ui/client/package.json; VERIFIED: npm registry] | Use for source-level UI contract/API wrapper assertions. [VERIFIED: web-ui/client/vitest.config.ts] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Web UI server durable storage | AI backend stores voices | Reject; locked service boundary says AI backend is not source of truth. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md] |
| SQLAlchemy/Alembic | Ad hoc SQLite DDL | Reject; existing repo already uses migration-first ORM schema. [VERIFIED: web-ui/server/alembic/versions/0001_initial_schema.py] |
| Filesystem blobs | SQLite BLOB columns | Reject; Phase 1 established filesystem blobs and atomic temp-rename writes. [VERIFIED: web-ui/server/app/storage/blob_store.py; VERIFIED: .planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md] |
| faster-whisper built-in VAD only | Explicit Silero VAD service plus faster-whisper VAD parameters | Use explicit Silero readiness for Phase 2 health and optional STT gating; faster-whisper VAD parameters remain a transcription helper. [CITED: https://context7.com/snakers4/silero-vad/llms.txt; CITED: https://context7.com/systran/faster-whisper/llms.txt] |
| One process for every TTS adapter | Split runtime/subprocess per engine | Not decided; allowed only after per-engine evidence gate because user preference is one runtime. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md] |
| Package `TTS` | Package `coqui-tts` | Reject package `TTS` framing; roadmap explicitly says idiap fork `coqui-tts`, never `TTS`. [VERIFIED: .planning/ROADMAP.md; CITED: https://pypi.org/project/coqui-tts/] |

**Installation:**

```bash
uv add --project ai-backend faster-whisper==1.2.1 silero-vad==6.2.1 aiortc==1.14.0 soundfile==0.13.1 librosa==0.11.0 pynvml==13.0.1 coqui-tts[server]==0.27.5 qwen-tts==0.1.1
uv add --project ai-backend f5-tts==1.1.17
npm --prefix web-ui/client install
```

**Version verification:** Current versions were checked with PyPI JSON (`curl https://pypi.org/pypi/{package}/json`) and `npm view`, and each table row above records the source. [VERIFIED: PyPI JSON; VERIFIED: npm registry]

## Architecture Patterns

### System Architecture Diagram

```text
Browser Voice Lab / Settings
  |
  | /api/voices multipart upload, save, rename, delete, test-play
  v
Web UI FastAPI server
  |-- validates uploads and writes original sample blobs atomically
  |-- stores voices, voice assets, tombstones, character.default_voice_id, Settings
  |-- calls AI backend for transient processing
  |
  | STT/TTS/VAD/status request with bytes or stored sample reference
  v
AI Backend FastAPI service
  |-- lifespan loads Whisper default + Silero VAD + exactly one resident TTS engine
  |-- engine registry chooses adapter, reports resident/loading/unavailable status
  |-- STT path applies VAD gate, Whisper options, hallucination filters
  |-- TTS path hot-swaps one resident engine when needed
  |
  | transcript/audio bytes + status/metrics
  v
Web UI FastAPI server
  |-- persists transcript and voice metadata
  |-- streams/returns transient preview audio to browser
  v
Browser renders editable transcript, optional preview, save state, library, and Settings status
```

This diagram follows locked ownership: Web UI server persists durable voice state and AI backend performs transient STT/TTS/VAD/model residency work. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md]

### Recommended Project Structure

```text
ai-backend/
├── app/
│   ├── main.py                 # FastAPI app factory and lifespan hook [VERIFIED: ai-backend/app/main.py]
│   ├── config.py               # AI runtime settings, model ids, cache paths [VERIFIED: ai-backend/app/main.py; VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md]
│   ├── models/
│   │   ├── registry.py          # Engine metadata, resident state, hot-swap coordinator [VERIFIED: 02-CONTEXT.md]
│   │   ├── stt.py               # faster-whisper adapter [CITED: https://context7.com/systran/faster-whisper/llms.txt]
│   │   ├── vad.py               # Silero VAD adapter [CITED: https://context7.com/snakers4/silero-vad/llms.txt]
│   │   └── tts_*.py             # One adapter per engine [VERIFIED: 02-CONTEXT.md]
│   ├── api/
│   │   ├── health.py            # Expanded health/status payload [VERIFIED: ai-backend/app/main.py]
│   │   ├── stt.py               # Transcribe/upload processing endpoint [VERIFIED: .planning/REQUIREMENTS.md; VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md]
│   │   ├── tts.py               # Preview/test synthesis endpoint [VERIFIED: .planning/REQUIREMENTS.md; VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md]
│   │   └── webrtc.py            # Optional aiortc signaling skeleton only [CITED: https://context7.com/aiortc/aiortc/llms.txt]
│   └── audio/
│       ├── io.py                # decode/normalize/resample helpers [VERIFIED: .planning/REQUIREMENTS.md; VERIFIED: .planning/phases/00-measurement-gate/requirements-phase0.txt]
│       └── filters.py           # hallucination blocklist and sample checks [VERIFIED: .planning/ROADMAP.md]
web-ui/server/app/
├── api/voices.py                # Voice CRUD/upload/test routes [VERIFIED: .planning/REQUIREMENTS.md; VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md]
├── domain/voice_service.py      # Durable voice business logic [VERIFIED: existing character_service.py pattern]
├── domain/ai_backend_client.py  # Calls AI backend processing/status endpoints [VERIFIED: existing settings probe pattern]
├── storage/models.py            # Voice/asset/character voice columns [VERIFIED: existing schema]
└── storage/blob_store.py        # Reuse atomic blob pattern [VERIFIED: codebase]
web-ui/client/src/
├── lib/api/voices.ts            # Client API wrappers [VERIFIED: existing lib/api pattern]
├── lib/components/voice/        # Voice Lab/Library/picker components [VERIFIED: 02-UI-SPEC.md]
└── routes/voice-lab/+page.svelte # Voice Lab route [VERIFIED: 02-UI-SPEC.md]
```

### Pattern 1: Durable Voice Blob Write On Web UI Server

**What:** Store uploaded audio as filesystem blobs and store only relative storage names/metadata in SQLite. [VERIFIED: web-ui/server/app/storage/blob_store.py; VERIFIED: web-ui/server/app/storage/models.py]

**When to use:** Use for original voice samples and any later persisted audio blobs. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md]

**Example:**

```python
# Source: web-ui/server/app/storage/blob_store.py [VERIFIED: codebase]
blob_path = atomic_write_blob(voice_sample_blob_dir, final_name, sample_bytes)
voice_asset = VoiceAsset(
    id=asset_id,
    voice_id=voice.id,
    asset_kind="sample",
    storage_path=blob_path.name,
    content_type=validated.content_type,
    byte_size=len(sample_bytes),
    sha256=hashlib.sha256(sample_bytes).hexdigest(),
)
```

### Pattern 2: AI Backend Lifespan Model Manager

**What:** Initialize long-lived STT/VAD/default TTS models at FastAPI lifespan startup and expose readiness through `/health`. [CITED: https://fastapi.tiangolo.com/advanced/events/; VERIFIED: ai-backend/app/main.py]

**When to use:** Use when model load is expensive and model residency is part of success criteria. [VERIFIED: .planning/ROADMAP.md; VERIFIED: .planning/phases/00-measurement-gate/results/phase0_summary.json]

**Example:**

```python
# Source pattern: FastAPI lifespan docs + current app factory [CITED: https://fastapi.tiangolo.com/advanced/events/; VERIFIED: ai-backend/app/main.py]
@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = ModelManager.from_settings(load_ai_settings())
    await manager.startup_self_test()
    app.state.models = manager
    yield
    await manager.shutdown()

app = FastAPI(title="RayMe AI Backend", version="0.2.0", lifespan=lifespan)
```

### Pattern 3: STT With Explicit English, VAD, And Hallucination Controls

**What:** Transcribe using explicit English/task options, VAD parameters, and `condition_on_previous_text=False` for independent short clips. [CITED: https://context7.com/systran/faster-whisper/llms.txt; VERIFIED: .planning/ROADMAP.md]

**When to use:** Use for Voice Lab sample transcription where each upload is independent and short. [VERIFIED: .planning/REQUIREMENTS.md]

**Example:**

```python
# Source: faster-whisper docs [CITED: https://context7.com/systran/faster-whisper/llms.txt]
segments, info = model.transcribe(
    sample_path,
    language="en",
    task="transcribe",
    beam_size=5,
    condition_on_previous_text=False,
    vad_filter=True,
    vad_parameters={"threshold": vad_threshold, "min_silence_duration_ms": silence_ms},
)
text = " ".join(segment.text.strip() for segment in segments).strip()
```

### Pattern 4: Settings Save-Before-Test Must Stay Intact

**What:** Client persists current form values before invoking each endpoint test. [VERIFIED: web-ui/client/src/routes/settings/+page.svelte; VERIFIED: web-ui/client/tests/e2e/settings-connection.spec.ts]

**When to use:** Preserve for Web UI, AI backend, and LLM endpoint tests while adding AI residency status. [VERIFIED: .planning/phases/01.1-ui-acceptance-and-regression-test-hardening/01.1-CONTEXT.md]

**Example:**

```typescript
// Source: web-ui/client/src/routes/settings/+page.svelte [VERIFIED: codebase]
if (!(await persistCurrentSettings({ showSuccess: false }))) {
  return;
}
aiBackendStatus = (await testAiBackendSettings()).status;
```

### Runtime Strategy Evidence Gates

| Gate | Evidence Required | Planner Action |
|------|-------------------|----------------|
| Single-runtime attempt | Install/self-test commands for all six engines in one chosen runtime; `/health` marks each engine available/unavailable with reasons. [VERIFIED: 02-CONTEXT.md] | Plan first unless evidence shows impossible. [VERIFIED: 02-CONTEXT.md] |
| Split-runtime proposal | Per-engine failure logs from one-runtime attempt, measured startup/self-test, and a fallback UX/API design that preserves one public AI backend API. [VERIFIED: 02-CONTEXT.md] | Do not commit to split runtime before this gate. [VERIFIED: 02-CONTEXT.md] |
| Engine enablement | Adapter import, model load, short synthesis, peak VRAM, warm switch behavior, and license/caveat metadata. [VERIFIED: .planning/ROADMAP.md; VERIFIED: .planning/phases/00-measurement-gate/results/tts_runtime_matrix_v2.json] | Enable engine only after self-test passes; otherwise mark unavailable with reason. [VERIFIED: 02-CONTEXT.md] |
| F5 package bump | Compare `f5-tts==1.1.17` measured pin against `1.1.20` current PyPI with same short/medium sample self-test. [VERIFIED: requirements-phase0.txt; CITED: https://pypi.org/project/f5-tts/] | Keep measured pin unless the bump passes. [VERIFIED: .planning/phases/00-measurement-gate/KEY_DECISIONS.md] |
| VRAM residency | `/health` reports free/used/headroom and a live `nvidia-smi` check on OMEN-PC confirms `<11 GB`. [CITED: https://docs.pytorch.org/docs/stable/generated/torch.cuda.memory.mem_get_info.html; VERIFIED: .planning/ROADMAP.md; VERIFIED: .planning/OPERATING-NOTES.md] | Make this a phase gate, not only a unit test. [VERIFIED: .planning/ROADMAP.md] |

### Anti-Patterns to Avoid

- **Hard-coded engine if/else chains:** Use a registry because the locked roster has six engines and metadata must drive UI labels/status/caveats. [VERIFIED: 02-CONTEXT.md]
- **AI backend as durable storage owner:** Reject; it violates the locked service boundary and makes Voice Library state depend on model runtime health. [VERIFIED: 02-CONTEXT.md]
- **Preview-gated save:** Reject; context supersedes UI-SPEC and allows save without preview. [VERIFIED: 02-CONTEXT.md; VERIFIED: 02-UI-SPEC.md]
- **Deleting voice rows with hard FK failures:** Use tombstone/soft-delete or a visible unavailable state because referenced deleted voices must remain recoverable in UI. [VERIFIED: 02-CONTEXT.md]
- **Browser direct calls to AI backend for voice processing:** Keep browser on RayMe-owned Web UI server APIs so durable state, file names, and endpoint details stay server-side. [VERIFIED: .planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md; VERIFIED: 02-CONTEXT.md]
- **Treating `curl` as UI readiness:** Browser and console checks are required before product-owner manual testing. [VERIFIED: .planning/OPERATING-NOTES.md]

## Recommended Plan Slices

| Order | Slice | Likely Files Touched | Dependencies |
|-------|-------|----------------------|--------------|
| 1 | Voice schema and migration: voices, voice_assets, voice tombstones/deleted_at, character default voice reference, settings fields. [VERIFIED: storage model/migration patterns] | `web-ui/server/app/storage/models.py`, `web-ui/server/alembic/versions/*`, `web-ui/server/tests/test_migrations.py` | None beyond existing DB harness. [VERIFIED: web-ui/server/tests/test_migrations.py] |
| 2 | Voice blob validation/storage service and API contract. [VERIFIED: blob/character service patterns] | `web-ui/server/app/domain/voice_service.py`, `web-ui/server/app/api/voices.py`, `web-ui/server/app/main.py`, `web-ui/server/tests/test_voices.py`, `web-ui/server/tests/test_blob_store.py` | Slice 1. [VERIFIED: web-ui/server/app/domain/character_service.py] |
| 3 | AI backend client/status model in Web UI server. [VERIFIED: settings probe pattern] | `web-ui/server/app/domain/ai_backend_client.py`, `web-ui/server/app/api/settings.py`, `web-ui/server/tests/test_health_settings.py` | Existing Settings service. [VERIFIED: web-ui/server/app/api/settings.py] |
| 4 | Client API types and Voice Lab route/component shell. [VERIFIED: client route/API pattern] | `web-ui/client/src/lib/api/types.ts`, `web-ui/client/src/lib/api/voices.ts`, `web-ui/client/src/routes/voice-lab/+page.svelte`, `web-ui/client/src/lib/components/voice/*.svelte`, `web-ui/client/src/lib/components/AppShell.svelte` | Slice 2 API contract. [VERIFIED: web-ui/client/src/lib/api/characters.ts] |
| 5 | Voice Library rename/delete/test-play and `Voice unavailable` states. [VERIFIED: 02-CONTEXT.md] | Voice service/API/client components, `CharacterCard.svelte`, Gallery route, Character Editor route | Slices 1-4. [VERIFIED: web-ui/client/src/routes/gallery/+page.svelte] |
| 6 | Character default voice assignment and Gallery badge. [VERIFIED: .planning/REQUIREMENTS.md] | `character_service.py`, `api/characters.py`, client types, `characters/[id]/+page.svelte`, `CharacterCard.svelte` | Voice list/read API. [VERIFIED: web-ui/server/app/domain/character_service.py] |
| 7 | Settings extensions: save-audio toggles, VAD placeholders, compact AI backend residency status. [VERIFIED: 02-CONTEXT.md] | `settings_service.py`, `api/settings.py`, `settings/+page.svelte`, `EndpointSettingsPanel.svelte`, new Settings panels/tests | Existing save-before-test path. [VERIFIED: web-ui/client/tests/e2e/settings-connection.spec.ts] |
| 8 | AI backend model manager, `/health` residency payload, STT/VAD endpoints. [VERIFIED: ai-backend stub] | `ai-backend/app/main.py`, new `ai-backend/app/models/*`, `ai-backend/tests/*`, `ai-backend/pyproject.toml` | Runtime packages and OMEN evidence gate. [VERIFIED: ai-backend/app/main.py] |
| 9 | TTS registry and first resident/default adapter, then remaining adapters as availability-gated tasks. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md] | `ai-backend/app/models/tts_*.py`, registry/status tests, license docs | Slice 8 and per-engine self-tests. [VERIFIED: 02-CONTEXT.md; VERIFIED: .planning/phases/00-measurement-gate/results/tts_runtime_matrix_v2.json] |
| 10 | Live OMEN-PC + desktop/mobile Playwright acceptance before Android handoff. [VERIFIED: operating notes] | `web-ui/client/tests/e2e/voice-lab.spec.ts`, `settings-connection.spec.ts`, `live-voice-lab.spec.ts`, summaries | Slices 1-9. [VERIFIED: .planning/OPERATING-NOTES.md] |

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multipart upload parsing | Custom multipart parser | FastAPI `UploadFile` + `python-multipart`. [CITED: https://fastapi.tiangolo.com/tutorial/request-files] | Handles form-data parsing and async file reads through supported FastAPI APIs. [CITED: https://fastapi.tiangolo.com/tutorial/request-files] |
| Atomic blob writes | Manual direct writes to final paths | Existing `atomic_write_blob`. [VERIFIED: web-ui/server/app/storage/blob_store.py] | Existing helper writes temp file, fsyncs, and atomically replaces final path. [VERIFIED: web-ui/server/app/storage/blob_store.py] |
| Voice activity detection | Energy threshold from scratch | Silero VAD and faster-whisper VAD parameters. [CITED: https://context7.com/snakers4/silero-vad/llms.txt; CITED: https://context7.com/systran/faster-whisper/llms.txt] | VAD has threshold/sampling/chunk semantics that are easy to get wrong in call phases. [VERIFIED: .planning/ROADMAP.md] |
| Speech recognition | Custom Whisper wrapper from raw model APIs | faster-whisper `WhisperModel.transcribe`. [CITED: https://context7.com/systran/faster-whisper/llms.txt] | Existing Phase 0 measured faster-whisper and its options expose the needed hallucination controls. [VERIFIED: .planning/phases/00-measurement-gate/KEY_DECISIONS.md] |
| GPU memory accounting | String parsing only from `nvidia-smi` | PyTorch CUDA memory APIs plus live `nvidia-smi` acceptance. [CITED: https://docs.pytorch.org/docs/stable/generated/torch.cuda.memory.mem_get_info.html; VERIFIED: .planning/OPERATING-NOTES.md] | PyTorch reports allocator stats; live acceptance catches full device/process reality. [CITED: https://docs.pytorch.org/docs/stable/generated/torch.cuda.memory.mem_get_info.html; VERIFIED: .planning/ROADMAP.md] |
| Schema migration | Direct table mutation at app startup | Alembic migration. [CITED: https://alembic.sqlalchemy.org; VERIFIED: web-ui/server/alembic/versions/0001_initial_schema.py] | Existing project already verifies migrations through tests. [VERIFIED: web-ui/server/tests/test_migrations.py] |
| WebRTC primitives | Hand-coded SDP/media stack | aiortc for any Phase 2 signaling skeleton. [CITED: https://context7.com/aiortc/aiortc/llms.txt] | aiortc provides peer connection, track, and data channel abstractions. [CITED: https://context7.com/aiortc/aiortc/llms.txt] |
| UI modal/toast primitives | New component library | Existing `ConfirmDialog`, `ToastStack`, `StatusChip`, local Svelte components. [VERIFIED: web-ui/client/src/lib/components] | Phase 2 UI-SPEC forbids registry/component-library migrations. [VERIFIED: 02-UI-SPEC.md] |
| HTML sanitization | Raw transcript/name rendering logic | Render user strings as text and preserve existing sanitizer for Markdown/card fields. [VERIFIED: 02-UI-SPEC.md; VERIFIED: web-ui/client/src/lib/sanitizer/renderMarkdown.ts] | Voice sample names/transcripts are user-provided content. [VERIFIED: 02-UI-SPEC.md] |

**Key insight:** custom implementations in this phase are risky at boundaries with mature edge cases: multipart uploads, audio decode, VAD, STT decoding, GPU memory telemetry, migrations, and WebRTC signaling. [VERIFIED: official docs above; VERIFIED: .planning/ROADMAP.md]

## Common Pitfalls

### Pitfall 1: Re-Introducing Three-Engine Assumptions

**What goes wrong:** UI/API/status code only handles F5, XTTS, and Qwen3 while context requires six measured engines. [VERIFIED: 02-CONTEXT.md]

**Why it happens:** UI-SPEC and earlier roadmap language predate the full roster correction. [VERIFIED: 02-CONTEXT.md; VERIFIED: 02-UI-SPEC.md]

**How to avoid:** Build `TtsEngineRegistry`/metadata first and make engine picker/status derive from registry rows. [VERIFIED: 02-CONTEXT.md]

**Warning signs:** Enum names hard-code three engines; tests assert only three option labels; Settings status has a single `tts_default_engine` string without `available_engines`. [VERIFIED: codebase planning synthesis]

### Pitfall 2: Preview Accidentally Blocks Save

**What goes wrong:** `Save Voice` is disabled until preview succeeds, contradicting the superseding context. [VERIFIED: 02-CONTEXT.md]

**Why it happens:** The UI-SPEC still contains preview-required language in older sections. [VERIFIED: 02-UI-SPEC.md]

**How to avoid:** Tests must prove a valid uploaded sample/name/transcript can save when preview failed or was skipped. [VERIFIED: 02-CONTEXT.md]

**Warning signs:** Save button state key named `previewSucceeded`; API requires preview asset ID. [VERIFIED: codebase planning synthesis]

### Pitfall 3: AI Backend Becomes Durable Voice Store

**What goes wrong:** Saved voices disappear when AI backend runtime changes or model process fails. [VERIFIED: 02-CONTEXT.md]

**Why it happens:** TTS adapters naturally touch samples/transcripts and can tempt persistence into the processing service. [VERIFIED: 02-CONTEXT.md]

**How to avoid:** Web UI server writes voice record before/after processing and AI backend returns only transcript/audio/status. [VERIFIED: 02-CONTEXT.md]

**Warning signs:** AI backend has a `voices` table, library list endpoint, or durable blob path. [VERIFIED: codebase planning synthesis]

### Pitfall 4: Whisper Hallucinations On Short Samples

**What goes wrong:** STT returns repeated stock phrases or carries context between independent voice samples. [VERIFIED: .planning/ROADMAP.md]

**Why it happens:** Whisper can condition on previous text and short/quiet clips may include too much non-speech. [CITED: https://context7.com/systran/faster-whisper/llms.txt; VERIFIED: .planning/ROADMAP.md]

**How to avoid:** Use VAD-gated input, explicit English transcription, `condition_on_previous_text=False`, and a hallucination blocklist/retry/manual entry fallback. [CITED: https://context7.com/systran/faster-whisper/llms.txt; VERIFIED: .planning/ROADMAP.md; VERIFIED: 02-CONTEXT.md]

**Warning signs:** Transcription endpoint returns text for silent audio without warning; no retry/manual transcript path after STT failure. [VERIFIED: 02-CONTEXT.md]

### Pitfall 5: Runtime Split Without Evidence

**What goes wrong:** Plans commit to Windows+WSL+subprocess topology before proving one runtime fails. [VERIFIED: 02-CONTEXT.md]

**Why it happens:** Phase 0 matrices include mixed runtime results and some engines looked better in different environments. [VERIFIED: .planning/phases/00-measurement-gate/results/tts_runtime_matrix_v2.json]

**How to avoid:** Plan explicit evidence gates and keep one public AI backend API even if adapters later use subprocesses. [VERIFIED: 02-CONTEXT.md]

**Warning signs:** Plan says "use WSL for Qwen" or "Docker/Triton" without install logs, self-test, and fallback. [VERIFIED: 02-CONTEXT.md]

### Pitfall 6: License Notices Are Incomplete

**What goes wrong:** F5 model weights or XTTS v2 are presented as commercially permissive. [CITED: https://pypi.org/project/f5-tts/; CITED: https://huggingface.co/coqui/XTTS-v2]

**Why it happens:** F5 code is MIT while pretrained models are CC-BY-NC, and coqui-tts package code license differs from XTTS-v2 model license. [CITED: https://pypi.org/project/f5-tts/; CITED: https://pypi.org/project/coqui-tts/; CITED: https://huggingface.co/coqui/XTTS-v2]

**How to avoid:** Add `LICENSES.md`/UI caveats from engine metadata and distinguish package license from model license. [VERIFIED: .planning/ROADMAP.md]

**Warning signs:** Engine metadata has only one `license` field without `code_license` vs `model_license`. [VERIFIED: codebase planning synthesis]

### Pitfall 7: Local Shell Is Not The GPU Acceptance Environment

**What goes wrong:** The agent tests only in the current shell and misses OMEN-PC GPU/TLS/Android behavior. [VERIFIED: .planning/OPERATING-NOTES.md]

**Why it happens:** The Codex shell lacks `nvidia-smi` and `ffmpeg`, while the real backend is OMEN-PC. [VERIFIED: environment audit]

**How to avoid:** Keep unit/API tests local, but make model residency, GPU headroom, TLS, and Android acceptance live OMEN-PC gates. [VERIFIED: .planning/OPERATING-NOTES.md]

**Warning signs:** Phase summary claims GPU residency without live `/health` plus `nvidia-smi` evidence from `192.168.1.199`. [VERIFIED: .planning/ROADMAP.md; VERIFIED: .planning/OPERATING-NOTES.md]

## Code Examples

Verified patterns from official and project sources:

### FastAPI Upload Endpoint

```python
# Source: FastAPI UploadFile docs [CITED: https://fastapi.tiangolo.com/tutorial/request-files]
@router.post("/upload")
async def upload_voice_sample(file: UploadFile = File(...)):
    content = await file.read()
    return {"filename": file.filename, "content_type": file.content_type, "bytes": len(content)}
```

### SQLAlchemy Voice Reference Shape

```python
# Source pattern: existing SQLAlchemy models and soft delete [VERIFIED: web-ui/server/app/storage/models.py]
class Voice(TimestampMixin, Base):
    __tablename__ = "voices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    default_engine: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

### AI Backend Health Payload Shape

```python
# Source: Phase 2 context requires resident engine, availability, loading state, VRAM/headroom [VERIFIED: 02-CONTEXT.md]
class AiHealth(BaseModel):
    service: str = "rayme-ai-backend"
    status: Literal["ok", "degraded", "starting", "error"]
    stt_model: str
    vad_ready: bool
    resident_tts_engine: str | None
    available_engines: list[EngineStatus]
    loading_engine: str | None = None
    vram_used_mb: float | None = None
    vram_headroom_mb: float | None = None
```

### Silero Speech Timestamp Gate

```python
# Source: Silero VAD docs [CITED: https://context7.com/snakers4/silero-vad/llms.txt]
wav = read_audio(sample_path, sampling_rate=16000)
speech = get_speech_timestamps(
    wav,
    vad_model,
    threshold=threshold,
    sampling_rate=16000,
    return_seconds=True,
)
```

### Playwright Browser Guard Pattern

```typescript
// Source: existing acceptance helper + Playwright locator assertions [VERIFIED: web-ui/client/tests/e2e/helpers/acceptance.ts; CITED: https://github.com/microsoft/playwright]
const assertNoBrowserErrors = installBrowserErrorGuard(page);
await page.goto('/voice-lab');
await expect(page.getByRole('heading', { name: 'Voice Lab' })).toBeVisible();
assertNoBrowserErrors();
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Three TTS engines only | Six measured engines in registry: F5, XTTS v2, Qwen3 0.6B, LuxTTS, Chatterbox Turbo, TADA 1B. [VERIFIED: 02-CONTEXT.md] | Phase 2 discuss/context on 2026-04-24. [VERIFIED: 02-CONTEXT.md] | Planner must create extensible registry and UI metadata, not fixed three-option code. [VERIFIED: 02-CONTEXT.md] |
| Preview required before save | Preview optional; save can proceed without successful preview. [VERIFIED: 02-CONTEXT.md] | Phase 2 discuss/context on 2026-04-24. [VERIFIED: 02-CONTEXT.md] | Tests must prove save without preview. [VERIFIED: 02-CONTEXT.md] |
| Raw whole-generation long-form TTS comparison | Shared chunk planner in measurement harness; final call behavior later uses chunked playback across engines. [VERIFIED: .planning/STATE.md; VERIFIED: .planning/phases/00-measurement-gate/results/tts_runtime_matrix_v2.json] | Phase 0 follow-up on 2026-04-23. [VERIFIED: .planning/STATE.md] | Phase 2 should expose adapter/chunk capability metadata but Phase 4 wires live call chunking. [VERIFIED: .planning/ROADMAP.md] |
| `TTS` package framing | `coqui-tts` idiap fork package for XTTS v2. [VERIFIED: .planning/ROADMAP.md; CITED: https://pypi.org/project/coqui-tts/] | Phase 2 roadmap/context. [VERIFIED: .planning/ROADMAP.md] | Dependency and docs must avoid installing package `TTS`. [VERIFIED: .planning/ROADMAP.md] |
| Qwen as default candidate | Qwen3-TTS 0.6B-Base is opt-in/non-default after failing Phase 0 acceptance gate. [VERIFIED: .planning/phases/00-measurement-gate/KEY_DECISIONS.md] | Phase 0 completed 2026-04-23. [VERIFIED: .planning/STATE.md] | UI caveats must label Qwen latency/accent risk while keeping it selectable. [VERIFIED: 02-CONTEXT.md] |

**Deprecated/outdated:**

- UI-SPEC "three engine" picker wording is superseded by the full roster. [VERIFIED: 02-CONTEXT.md; VERIFIED: 02-UI-SPEC.md]
- UI-SPEC "Save Voice disabled until preview succeeds" is superseded by optional preview. [VERIFIED: 02-CONTEXT.md; VERIFIED: 02-UI-SPEC.md]
- Package name `TTS` is disallowed for XTTS planning; use `coqui-tts`. [VERIFIED: .planning/ROADMAP.md; CITED: https://pypi.org/project/coqui-tts/]

## TTS Runtime Evidence Snapshot

| Engine | Best/Relevant Phase 0 Evidence | Planning Implication |
|--------|--------------------------------|----------------------|
| F5-TTS | Phase 0 chose `f5` default; optimized Windows-native short TTFA `524.3 ms`, long TTFA `981.2 ms`, peak under `928 MB` in scenario matrix; 30-min soak peak `1990.2 MB`. [VERIFIED: KEY_DECISIONS.md; VERIFIED: tts_runtime_matrix_v2.json; VERIFIED: STATE.md] | Enable first/default if measured pin imports; require evidence gate for f5-tts version bump. [VERIFIED: requirements-phase0.txt; CITED: https://pypi.org/project/f5-tts/] |
| XTTS v2 | Optimized Windows-native short TTFA `491.0 ms`, long TTFA `482.3 ms`, native streaming inside chunks, peak `2664.8 MB` in scenario matrix; soak peak `2104.0 MB`. [VERIFIED: tts_runtime_matrix_v2.json; VERIFIED: STATE.md] | Cache conditioning latents and always route long text through chunk planner later; Phase 2 can expose test-play/preview. [VERIFIED: tts_runtime_matrix_v2.json] |
| Qwen3-TTS 0.6B-Base | Failed Phase 0 acceptance on TTFA/RTF/accent; optimized Windows eager short TTFA `3754.2 ms`; soak peak `3010.0 MB`. [VERIFIED: KEY_DECISIONS.md; VERIFIED: tts_runtime_matrix_v2.json; VERIFIED: STATE.md] | Keep selectable with caveats; mark unavailable if `qwen-tts==0.1.1` import/load self-test fails. [VERIFIED: 02-CONTEXT.md; VERIFIED: ROADMAP.md] |
| LuxTTS | Runtime matrix shows fastest TTFA rows but STATE warns current user-sample quality failures. [VERIFIED: tts_runtime_matrix_v2.json; VERIFIED: STATE.md] | Include in registry and UI caveats; do not choose default by latency alone. [VERIFIED: STATE.md; VERIFIED: 02-CONTEXT.md] |
| Chatterbox Turbo | STATE says baseline long-form is gibberish but optimized long-form normal/seed 1337 samples are acceptable; optimized Windows short TTFA `840.2 ms`, peak about `4667.4 MB`. [VERIFIED: STATE.md; VERIFIED: tts_runtime_matrix_v2.json] | Include adapter only after optimized path self-test; caveat baseline/raw long-form. [VERIFIED: STATE.md] |
| TADA 1B | Windows optimized long is acceptable; WSL is caution; peak about `7.5 GB` in optimized Windows long scenario. [VERIFIED: STATE.md; VERIFIED: tts_runtime_matrix_v2.json] | One-hot residency is mandatory because TADA consumes the most VRAM headroom among measured roster rows. [VERIFIED: tts_runtime_matrix_v2.json; VERIFIED: ROADMAP.md] |

## Assumptions Log

All claims in this research are tagged with verified local files, registry lookups, Context7/official docs, or cited official pages. [VERIFIED: research session]

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| None | No unverified assumptions were used as planning facts. [VERIFIED: research session] | All sections | None. [VERIFIED: research session] |

## Open Questions (RESOLVED)

1. **RESOLVED: Phase 2 production starts with `f5-tts==1.1.17`; optional bump requires a discrete self-test.** [VERIFIED: requirements-phase0.txt; CITED: https://pypi.org/project/f5-tts/]
   - What we know: Phase 0 measured `1.1.17`; PyPI current is `1.1.20`, and `1.1.18`/`1.1.19` were yanked. [VERIFIED: requirements-phase0.txt; CITED: https://pypi.org/project/f5-tts/]
   - Plan-backed decision: Plan `02-08` Task 1 pins `f5-tts==1.1.17` for adapter parity; Plan `02-16` Task 2 creates the runtime evidence gate; Plan `02-18` Task 1 records live OMEN-PC self-test evidence before any package bump is accepted. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-08-PLAN.md; VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-16-PLAN.md; VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-18-PLAN.md]
   - Execution rule: `1.1.20` may replace `1.1.17` only after the same short/medium synthesis, health, and VRAM self-test passes and is captured in runtime evidence. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md]

2. **RESOLVED: Phase 2 includes only a non-call aiortc signaling skeleton.** [VERIFIED: .planning/ROADMAP.md; VERIFIED: 02-CONTEXT.md]
   - What we know: Roadmap mentions FastAPI + aiortc signaling in Phase 2, while live call media is Phase 3. [VERIFIED: .planning/ROADMAP.md]
   - Plan-backed decision: Plan `02-17` adds `GET /webrtc/status` and `POST /webrtc/offer` tests that explicitly return skeleton/not-ready semantics and forbid `/call`, `/captions`, or `/barge-in` routes. It does not implement live media, captions, barge-in, call UI, or playback behavior. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-17-PLAN.md]
   - Execution rule: Any live call behavior remains Phase 3 scope. [VERIFIED: .planning/ROADMAP.md]

3. **RESOLVED: Local tests use mocks/fakes; live OMEN-PC evidence covers runtime self-tests.** [VERIFIED: environment audit]
   - What we know: Current shell lacks `nvidia-smi` and `ffmpeg`; live AI health is reachable at `https://192.168.1.199:9443/health`. [VERIFIED: environment audit]
   - Plan-backed decision: Plans `02-02`, `02-06`, `02-07`, and `02-08` require local unit tests to use lightweight fake adapters rather than GPU downloads; Plan `02-18` records live OMEN-PC `/health`, VRAM/headroom, generated audio, and per-engine unavailable reasons. [VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-02-PLAN.md; VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-06-PLAN.md; VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-07-PLAN.md; VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-08-PLAN.md; VERIFIED: .planning/phases/02-ai-backend-skeleton-voice-lab/02-18-PLAN.md]
   - Execution rule: Local success proves contracts and failure isolation; live OMEN-PC evidence proves runtime residency/self-test behavior. [VERIFIED: .planning/OPERATING-NOTES.md; VERIFIED: 02-CONTEXT.md]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | Local Web UI server tests and AI backend project. [VERIFIED: pyproject files] | ✓ local | `Python 3.12.3` [VERIFIED: `python3 --version`] | OMEN Phase 0 used Python `3.11.15`; AI backend runtime must choose deliberately per engine. [VERIFIED: phase0_summary.json] |
| uv | Python dependency/test runner. [VERIFIED: prior plans and pyproject files] | ✓ local | `uv 0.11.6` [VERIFIED: `uv --version`] | Use existing uv lock/project workflow. [VERIFIED: web-ui/server/pyproject.toml] |
| Node | SvelteKit/Vitest/Playwright. [VERIFIED: package.json] | ✓ local | `v22.22.2` [VERIFIED: `node --version`] | None needed locally. [VERIFIED: environment audit] |
| npm | Client dependency/test runner. [VERIFIED: package.json] | ✓ local | `10.9.7` [VERIFIED: `npm --version`] | None needed locally. [VERIFIED: environment audit] |
| ffmpeg | Robust MP3/FLAC/WAV decode if chosen. [VERIFIED: REQ-20] | ✗ local | — [VERIFIED: `ffmpeg -version` failed] | Use engine/library loaders where possible; verify/install on OMEN-PC before relying on CLI ffmpeg. [VERIFIED: environment audit] |
| nvidia-smi | GPU residency acceptance. [VERIFIED: ROADMAP success criteria] | ✗ local | — [VERIFIED: `nvidia-smi` failed] | Run GPU checks on OMEN-PC only. [VERIFIED: .planning/OPERATING-NOTES.md] |
| Docker | Optional split/Triton runtime. [VERIFIED: runtime strategy context] | ✗ local | — [VERIFIED: `docker --version` failed] | Not required unless evidence gate chooses Docker/Triton. [VERIFIED: 02-CONTEXT.md] |
| SSH | OMEN-PC operational access. [VERIFIED: .planning/OPERATING-NOTES.md] | ✓ client installed; host key not accepted in current shell | OpenSSH `9.6p1` [VERIFIED: `ssh -V`; VERIFIED: SSH probe failed with host key verification] | Use documented `rayme-pmpg` path after known_hosts handling. [VERIFIED: .planning/OPERATING-NOTES.md] |
| Live AI backend | Settings endpoint and live AI status gate. [VERIFIED: OPERATING-NOTES] | ✓ reachable | Phase 1 health payload at `https://192.168.1.199:9443/health`. [VERIFIED: curl -k live health] | None for health; model endpoints are Phase 2 work. [VERIFIED: ai-backend/app/main.py] |
| Live Web UI | LAN browser acceptance. [VERIFIED: OPERATING-NOTES] | ✓ reachable | App shell served at `https://192.168.1.199:8443`. [VERIFIED: curl -k live Web UI] | None for deployed browser checks. [VERIFIED: environment audit] |

**Missing dependencies with no fallback:**
- GPU residency cannot be validated in the local shell because `nvidia-smi` is unavailable; use OMEN-PC. [VERIFIED: environment audit; VERIFIED: .planning/OPERATING-NOTES.md]

**Missing dependencies with fallback:**
- Local `ffmpeg` is unavailable; planners should either avoid hard CLI dependency or add an OMEN-PC install/verify step before MP3/FLAC processing uses it. [VERIFIED: environment audit]
- Docker is unavailable locally; Docker/Triton must remain optional and evidence-gated. [VERIFIED: environment audit; VERIFIED: 02-CONTEXT.md]

## Validation Architecture

Nyquist validation is enabled because `.planning/config.json` has `workflow.nyquist_validation: true`. [VERIFIED: .planning/config.json]

### Test Framework

| Property | Value |
|----------|-------|
| Web UI server framework | pytest `9.0.3`, pytest-asyncio `1.3.0`; config in `web-ui/server/pyproject.toml`. [VERIFIED: web-ui/server/pyproject.toml] |
| AI backend framework | pytest `9.0.3`; config in `ai-backend/pyproject.toml`. [VERIFIED: ai-backend/pyproject.toml] |
| Client unit framework | Vitest `4.1.5`; config in `web-ui/client/vitest.config.ts`. [VERIFIED: package.json; VERIFIED: vitest.config.ts] |
| E2E framework | Playwright `1.59.1`; config in `web-ui/client/playwright.config.ts`. [VERIFIED: package.json; VERIFIED: playwright.config.ts] |
| Quick backend run | `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py web-ui/server/tests/test_health_settings.py -q` after Wave 0 creates files. [VERIFIED: existing pytest command pattern] |
| Quick AI backend run | `uv run --project ai-backend pytest ai-backend/tests -q`. [VERIFIED: ai-backend/tests/test_health.py] |
| Quick client run | `npm --prefix web-ui/client run test:unit -- --run`. [VERIFIED: package.json; VERIFIED: prior phase summaries] |
| Full local suite | `uv run --project web-ui/server pytest web-ui/server/tests -q && uv run --project ai-backend pytest ai-backend/tests -q && npm --prefix web-ui/client run test:unit -- --run && npm --prefix web-ui/client run test:e2e`. [VERIFIED: prior phase summaries; VERIFIED: package.json] |
| Live suite | `RAYME_ENABLE_LIVE_E2E=1 RAYME_LIVE_WEB_URL=https://192.168.1.199:8443 RAYME_LIVE_AI_HEALTH_URL=https://192.168.1.199:9443/health npm --prefix web-ui/client run test:e2e -- live-voice-lab.spec.ts --project=desktop-chromium`. [VERIFIED: .planning/OPERATING-NOTES.md; VERIFIED: prior live-lan pattern] |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| REQ-02 | `/health` reports STT, VAD, resident engine, available engines, loading state, VRAM/headroom, and degraded per-engine failures. [VERIFIED: ROADMAP] | AI backend unit + live OMEN smoke | `uv run --project ai-backend pytest ai-backend/tests/test_health.py ai-backend/tests/test_model_manager.py -q`; live `curl -k https://192.168.1.199:9443/health`. [VERIFIED: existing AI test] | ❌ Wave 0 for `test_model_manager.py`; existing `test_health.py` must be updated. [VERIFIED: ai-backend/tests/test_health.py] |
| REQ-05 | Settings saves current endpoint values before testing Web/AI/LLM and shows AI backend green/status. [VERIFIED: REQ-05] | Backend API + Playwright | `uv run --project web-ui/server pytest web-ui/server/tests/test_health_settings.py -q`; `npm --prefix web-ui/client run test:e2e -- settings-connection.spec.ts`. [VERIFIED: existing tests] | ✅ existing files need extension. [VERIFIED: web-ui/client/tests/e2e/settings-connection.spec.ts] |
| REQ-15 | Character default voice persists and Gallery surfaces assigned/missing/unavailable state. [VERIFIED: REQ-15] | Backend API + client unit + Playwright | `uv run --project web-ui/server pytest web-ui/server/tests/test_characters.py web-ui/server/tests/test_voices.py -q`; `npm --prefix web-ui/client run test:e2e -- voice-lab.spec.ts`. [VERIFIED: existing test patterns] | ❌ `test_voices.py` and voice E2E are Wave 0. [VERIFIED: rg --files] |
| REQ-20 | Upload accepts WAV/MP3/FLAC, warns outside 6-15s, rejects unsupported/unreadable files. [VERIFIED: REQ-20] | Backend API + Playwright | `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py -q`; `npm --prefix web-ui/client run test:e2e -- voice-lab.spec.ts`. [VERIFIED: FastAPI upload docs] | ❌ Wave 0. [VERIFIED: rg --files] |
| REQ-21 | STT auto-transcript appears, can fail without losing sample, and manual transcript is allowed. [VERIFIED: REQ-21; VERIFIED: 02-CONTEXT.md] | AI backend unit + API mocked E2E | `uv run --project ai-backend pytest ai-backend/tests/test_stt.py -q`; `npm --prefix web-ui/client run test:e2e -- voice-lab.spec.ts`. [CITED: faster-whisper docs] | ❌ Wave 0. [VERIFIED: rg --files] |
| REQ-22 | Save captures name, engine, sample path, transcript, timestamps, default engine, and six-engine metadata. [VERIFIED: REQ-22; VERIFIED: 02-CONTEXT.md] | Backend API + migration test | `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py web-ui/server/tests/test_migrations.py -q`. [VERIFIED: existing migrations test pattern] | ❌ `test_voices.py` Wave 0. [VERIFIED: rg --files] |
| REQ-23 | Voice Library list/rename/delete/test-play works and preserves row state. [VERIFIED: REQ-23] | Backend API + Playwright | `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py -q`; `npm --prefix web-ui/client run test:e2e -- voice-lab.spec.ts`. [VERIFIED: 02-UI-SPEC.md] | ❌ Wave 0. [VERIFIED: rg --files] |
| REQ-24 | Force delete referenced voice creates visible `Voice unavailable` state, not crash/corruption. [VERIFIED: REQ-24; VERIFIED: 02-CONTEXT.md] | Backend API + Playwright | `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py web-ui/server/tests/test_characters.py -q`; `npm --prefix web-ui/client run test:e2e -- voice-lab.spec.ts`. [VERIFIED: 02-CONTEXT.md] | ❌ Wave 0. [VERIFIED: rg --files] |
| REQ-80 | Settings stores save-AI-audio ON, save-mic-audio OFF, and VAD placeholder values/status. [VERIFIED: REQ-80; VERIFIED: 02-CONTEXT.md] | Backend API + client unit + Playwright | `uv run --project web-ui/server pytest web-ui/server/tests/test_health_settings.py -q`; `npm --prefix web-ui/client run test:unit -- --run`; `npm --prefix web-ui/client run test:e2e -- settings-connection.spec.ts`. [VERIFIED: existing tests] | ✅ existing files need extension. [VERIFIED: rg --files] |
| REQ-A3 | STT default is `distil-large-v3` `int8_float16`, English-only, with Phase 0 WER decision carried into health/status. [VERIFIED: KEY_DECISIONS.md] | AI backend unit + live health | `uv run --project ai-backend pytest ai-backend/tests/test_stt.py ai-backend/tests/test_health.py -q`. [VERIFIED: KEY_DECISIONS.md] | ❌ `test_stt.py` Wave 0. [VERIFIED: rg --files] |
| REQ-90 | Voice Lab/Settings follow approved True Dark UI and no registry migration. [VERIFIED: 02-UI-SPEC.md] | Client unit + Playwright visual/contract | `npm --prefix web-ui/client run test:unit -- --run`; `npm --prefix web-ui/client run test:e2e -- voice-lab.spec.ts ui-contract.spec.ts`. [VERIFIED: existing UI tests] | ❌ voice E2E Wave 0; existing `ui-contract.spec.ts` can extend. [VERIFIED: rg --files] |

### Sampling Rate

- **Per task commit:** Run the narrow pytest/Vitest/Playwright spec for files touched. [VERIFIED: prior plan pattern]
- **Per wave merge:** Run full local backend + AI backend + client unit + default Playwright suite. [VERIFIED: prior phase summaries]
- **Phase gate:** Full local suite, live OMEN-PC health/model-status checks, live desktop Playwright, then Android Chrome product-owner checkpoint. [VERIFIED: .planning/OPERATING-NOTES.md]

### Wave 0 Gaps

- [ ] `web-ui/server/tests/test_voices.py` - covers voice schema/API/storage/delete semantics for REQ-15, REQ-20, REQ-22, REQ-23, REQ-24. [VERIFIED: rg --files]
- [ ] `ai-backend/tests/test_model_manager.py` - covers one-hot residency, engine status, degraded unavailable engines, VRAM payload for REQ-02. [VERIFIED: rg --files]
- [ ] `ai-backend/tests/test_stt.py` - covers STT option contract, VAD-gated transcription fallback, hallucination blocklist for REQ-21 and REQ-A3. [VERIFIED: rg --files]
- [ ] `ai-backend/tests/test_tts_registry.py` - covers six-engine registry metadata and one-resident switching contract. [VERIFIED: rg --files]
- [ ] `web-ui/client/tests/e2e/voice-lab.spec.ts` - covers upload/transcript/edit/save/library/default voice/delete unavailable states. [VERIFIED: rg --files]
- [ ] `web-ui/client/tests/e2e/live-voice-lab.spec.ts` - opt-in live OMEN-PC acceptance for health/status and one short engine self-test. [VERIFIED: existing live-lan pattern]
- [ ] `web-ui/client/tests/unit/voice-lab.test.ts` - source-level contract checks for six-engine roster, optional preview, and Save Voice behavior. [VERIFIED: existing unit test style]

## Security Domain

Security enforcement is enabled because `.planning/config.json` does not set `security_enforcement: false`. [VERIFIED: .planning/config.json]

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | Project is no-auth LAN-only; do not add auth in Phase 2. [VERIFIED: .planning/PROJECT.md] |
| V3 Session Management | no | No sessions are in scope. [VERIFIED: .planning/PROJECT.md] |
| V4 Access Control | limited | Single-user LAN trust; destructive actions still require confirmation and server validation. [VERIFIED: .planning/PROJECT.md; VERIFIED: 02-UI-SPEC.md] |
| V5 Input Validation | yes | Pydantic request models, FastAPI upload validation, content-type/extension/size checks, transcript/name rendered as text. [VERIFIED: web-ui/server/app/api/settings.py; VERIFIED: 02-UI-SPEC.md] |
| V6 Cryptography | yes for TLS only | Reuse mkcert TLS material; do not generate throwaway certs. [VERIFIED: .planning/OPERATING-NOTES.md] |
| V8 Data Protection | yes | Mic audio default OFF, AI audio default ON, user voice samples stored locally as private blobs, API keys masked. [VERIFIED: .planning/PROJECT.md; VERIFIED: 02-CONTEXT.md; VERIFIED: 02-UI-SPEC.md] |
| V10 Malicious Code | yes | Uploaded audio and transcripts are untrusted; never execute file paths/metadata; keep processing calls server-side. [VERIFIED: 02-UI-SPEC.md] |
| V12 File and Resources | yes | Validate audio files, prevent path traversal, use atomic write helper, serve blobs by ID. [VERIFIED: web-ui/server/app/storage/blob_store.py; VERIFIED: web-ui/server/app/api/characters.py] |
| V14 Configuration | yes | Endpoint URLs validated as absolute HTTP(S), no wildcard CORS/origins, no browser-visible raw API keys. [VERIFIED: web-ui/server/app/config.py; VERIFIED: web-ui/client/tests/e2e/helpers/acceptance.ts] |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal through uploaded filename | Tampering | Ignore user filename for storage; generate internal asset ID and validate blob names. [VERIFIED: web-ui/server/app/storage/blob_store.py; VERIFIED: web-ui/server/app/domain/character_service.py] |
| User transcript/name XSS | Elevation / Information Disclosure | Render transcript/name/file names as text; do not render raw HTML. [VERIFIED: 02-UI-SPEC.md] |
| Raw API key exposure in browser/status/toasts | Information Disclosure | Keep LLM keys server-side and mask configured state. [VERIFIED: web-ui/server/app/domain/settings_service.py; VERIFIED: web-ui/client/tests/unit/settings.test.ts] |
| Voice deletion corrupts character references | Tampering | Stable voice IDs plus tombstone/`Voice unavailable` state. [VERIFIED: 02-CONTEXT.md] |
| Direct browser/provider or AI backend calls leak topology/secrets | Information Disclosure | Browser calls RayMe `/api/*`; helper tests reject direct provider URLs. [VERIFIED: web-ui/client/tests/e2e/helpers/acceptance.ts] |
| Oversized/unreadable audio causes memory pressure | Denial of Service | Validate file type/size/duration before AI backend processing; keep 6-15s UX envelope. [VERIFIED: REQ-20; VERIFIED: 02-UI-SPEC.md] |
| Model OOM during engine hot-swap | Denial of Service | One resident TTS engine, unload before load, `/health` degradation per engine, live VRAM gate `<11 GB`. [VERIFIED: ROADMAP; VERIFIED: 02-CONTEXT.md] |
| License misrepresentation | Compliance / Repudiation | Store code/model license metadata separately and ship license notices for F5/XTTS/Qwen. [CITED: https://pypi.org/project/f5-tts/; CITED: https://huggingface.co/coqui/XTTS-v2; CITED: https://github.com/QwenLM/Qwen3-TTS] |

### Threat Model Blocks Planner Must Include

- `<threat_model>` for voice sample upload/storage: path traversal, oversized file, unsupported codec, malicious filename, transcript XSS, local privacy retention. [VERIFIED: 02-UI-SPEC.md; VERIFIED: blob_store.py]
- `<threat_model>` for AI backend processing calls: model OOM, engine failure isolation, raw exception leakage, timeout/retry behavior, no durable state in AI backend. [VERIFIED: 02-CONTEXT.md; VERIFIED: ROADMAP.md]
- `<threat_model>` for Settings extensions: save-audio privacy defaults, API key masking, endpoint URL validation, save-before-test behavior. [VERIFIED: 02-CONTEXT.md; VERIFIED: settings_service.py]
- `<threat_model>` for voice delete/default references: force-delete confirmation, tombstone state, readable referent names, no dangling crashes. [VERIFIED: 02-CONTEXT.md]
- `<threat_model>` for license notices: non-commercial F5/XTTS caveats and Qwen Apache-2.0 caveat separation. [CITED: f5-tts PyPI; CITED: coqui/XTTS-v2 Hugging Face; CITED: Qwen3-TTS GitHub]

## Sources

### Primary (HIGH confidence)

- `.planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md` - locked Phase 2 decisions and service boundaries. [VERIFIED: file read]
- `.planning/phases/02-ai-backend-skeleton-voice-lab/02-UI-SPEC.md` - approved UI contract and superseded preview/engine picker details. [VERIFIED: file read]
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/PROJECT.md`, `.planning/OPERATING-NOTES.md` - scope, requirements, phase history, LAN/TLS operating rules. [VERIFIED: file read]
- `web-ui/server/app/storage/models.py`, `blob_store.py`, `settings_service.py`, `api/settings.py`, `api/characters.py`, `domain/character_service.py` - existing backend patterns. [VERIFIED: codebase read]
- `web-ui/client/src/routes/settings/+page.svelte`, `AppShell.svelte`, `EndpointSettingsPanel.svelte`, `tests/e2e/settings-connection.spec.ts` - existing client Settings and acceptance patterns. [VERIFIED: codebase read]
- `ai-backend/app/main.py`, `ai-backend/tests/test_health.py` - current AI backend stub and tests. [VERIFIED: codebase read]
- `.planning/phases/00-measurement-gate/KEY_DECISIONS.md`, `results/phase0_summary.json`, `results/tts_runtime_matrix_v2.json`, `requirements-phase0.txt`, `requirements-tts-experimental.txt` - runtime measurements and pins. [VERIFIED: file read]
- Context7 docs for FastAPI, SQLAlchemy, Svelte, faster-whisper, Silero VAD, aiortc, Alembic, Playwright, PyTorch CUDA memory. [CITED: context7 docs output]
- PyPI JSON and npm registry version checks for all recommended packages. [VERIFIED: registry queries]

### Secondary (MEDIUM confidence)

- `https://pypi.org/project/f5-tts/` - package/current version/license note for code vs pretrained models. [CITED: PyPI]
- `https://pypi.org/project/coqui-tts/` - idiap fork package version/license metadata. [CITED: PyPI]
- `https://huggingface.co/coqui/XTTS-v2` - XTTS-v2 model CPML license. [CITED: Hugging Face]
- `https://github.com/QwenLM/Qwen3-TTS` - Qwen3-TTS install, 0.6B/1.7B model list, voice clone reference audio/transcript requirement, FA2 notes. [CITED: official GitHub]

### Tertiary (LOW confidence)

- None used as authoritative planning claims. [VERIFIED: research session]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for existing Web UI/server/client pins and registry versions; MEDIUM for TTS production pins because live OMEN self-tests must confirm runtime drift. [VERIFIED: pyproject/package.json; VERIFIED: PyPI/npm; VERIFIED: Phase 0 results]
- Architecture: HIGH because service ownership is locked in CONTEXT.md and matches existing codebase shape. [VERIFIED: 02-CONTEXT.md; VERIFIED: codebase]
- Runtime placement: MEDIUM because context requires evidence before committing to one runtime vs split runtime. [VERIFIED: 02-CONTEXT.md]
- Pitfalls: HIGH for listed project pitfalls and UI supersessions; MEDIUM for engine-specific adapter friction beyond measured artifacts. [VERIFIED: ROADMAP; VERIFIED: Phase 0 results]
- Validation: HIGH for existing test harness; MEDIUM for live GPU tests because current shell is not the GPU target. [VERIFIED: config/test files; VERIFIED: environment audit]

**Research date:** 2026-04-24 [VERIFIED: system date]
**Valid until:** 2026-05-01 for TTS/runtime/package recommendations; 2026-05-24 for codebase architecture and storage patterns. [VERIFIED: current package churn observed in registry dates]
