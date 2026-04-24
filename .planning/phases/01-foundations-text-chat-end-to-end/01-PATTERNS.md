# Phase 01: Foundations & Text Chat End-to-End - Pattern Map

**Mapped:** 2026-04-24
**Files analyzed:** 25 planned file groups
**Analogs found:** 17 / 25

## File Classification

| New/Modified File Group | Role | Data Flow | Closest Analog | Match Quality |
|-------------------------|------|-----------|----------------|---------------|
| `web-ui/client/package.json`, `svelte.config.js`, `vite.config.ts`, `vitest.config.ts`, `playwright.config.ts` | config | build/test | `01-RESEARCH.md` lines 159-204, 274-299, 703-708 | scaffold-first |
| `web-ui/client/src/routes/+layout.*`, `src/lib/components/AppShell.svelte`, `StatusChip.svelte`, `GlassPanel.svelte` | component/provider | request-response + browser checks | `docs/stitch/html/home-true-dark.html` lines 34-80; `01-UI-SPEC.md` lines 153-159 | visual-match |
| `web-ui/client/src/routes/+page.svelte`, `ThreadListItem.svelte` | component | CRUD request-response | `docs/stitch/html/home-true-dark.html` lines 111-140; `01-UI-SPEC.md` lines 161-168 | visual-match |
| `web-ui/client/src/routes/gallery/+page.svelte`, `CharacterCard.svelte`, `ImportCardDialog.svelte` | component | CRUD + file-I/O | `docs/stitch/html/character-gallery-true-dark.html` lines 87-126; `01-UI-SPEC.md` lines 170-178 | visual-match |
| `web-ui/client/src/routes/characters/[id]/+page.svelte`, `CharacterFormSection.svelte`, `PortraitDropzone.svelte` | component | CRUD + file-I/O | `docs/stitch/html/character-editor-true-dark.html` lines 171-214, 286-299 | visual-match |
| `web-ui/client/src/routes/chat/[threadId]/+page.svelte`, `ChatMessageBubble.svelte`, `Composer.svelte`, `MessageActionMenu.svelte`, `SwipeStepper.svelte` | component | streaming + event-driven | `docs/stitch/html/voice-call-true-dark.html` lines 124-143; `01-UI-SPEC.md` lines 191-205 | partial visual |
| `web-ui/client/src/routes/settings/+page.svelte`, `EndpointSettingsPanel.svelte` | component | request-response config | `docs/stitch/html/settings-true-dark.html` lines 127-169; `01-UI-SPEC.md` lines 207-213 | visual-match |
| `web-ui/client/src/lib/api/*.ts`, `src/lib/api/stream.ts` | utility/service | request-response + streaming | `01-RESEARCH.md` lines 595-613 | scaffold-first |
| `web-ui/client/src/lib/sanitizer/renderMarkdown.ts` and tests | utility | transform + security | `01-RESEARCH.md` lines 418-430; `01-UI-SPEC.md` lines 289-295 | scaffold-first |
| `web-ui/client/tests/**/*.test.ts`, `tests/e2e/*.spec.ts` | test | validation | `01-RESEARCH.md` lines 703-755 | scaffold-first |
| `web-ui/server/pyproject.toml`, app config modules | config | build/runtime | `01-RESEARCH.md` lines 203-204, 703-708, 747-755 | scaffold-first |
| `web-ui/server/app/main.py` | app/controller | request-response + static + HTTPS | `01-RESEARCH.md` lines 244-270, 579-593; `https_serve.py` lines 78-82 | scaffold-first |
| `web-ui/server/app/api/health.py`, `settings.py` | route/controller | request-response probe | `https_serve.py` lines 40-47, 62-82; `01-RESEARCH.md` lines 714-716 | partial role |
| `web-ui/server/app/api/characters.py`, `app/domain/cards.py`, `app/domain/card_export.py` | controller/service | CRUD + file-I/O + transform | `01-RESEARCH.md` lines 389-405, 620-633 | scaffold-first |
| `web-ui/server/app/api/threads.py`, `app/domain/message_actions.py` | controller/service | CRUD + branching | `01-RESEARCH.md` lines 349-375, 714-733 | scaffold-first |
| `web-ui/server/app/api/chat.py`, `app/domain/llm_stream.py`, `prompt_builder.py` | controller/service | streaming | `01-RESEARCH.md` lines 311-334, 595-613 | scaffold-first |
| `web-ui/server/app/storage/models.py`, `session.py`, `blob_store.py` | model/storage | CRUD + file-I/O | `01-RESEARCH.md` lines 349-375, 443-465 | scaffold-first |
| `web-ui/server/alembic/**` and initial migration | migration | batch/schema | `01-RESEARCH.md` lines 349-375, 747-749 | scaffold-first |
| `web-ui/server/tests/test_*.py` | test | validation | `01-RESEARCH.md` lines 703-755 | scaffold-first |
| `ai-backend/pyproject.toml`, `app/main.py`, `tests/test_health.py` | app/controller/test | request-response probe | `01-RESEARCH.md` lines 263-265, 714-716; `https_serve.py` lines 40-47 | scaffold-first |
| `llm/README.md`, `llm/*.example.*` | docs/config | request-response external probe | `01-RESEARCH.md` lines 263-270, 567-573, 664-666 | scaffold-first |
| HTTPS setup docs/scripts under `docs/` or service README | docs/config | file-I/O + request-response probe | `HTTPS-SETUP.md` lines 21-49, 57-75; `https_serve.py` lines 62-82 | exact |
| Character card import fixtures and malicious-card tests | test/fixture | file-I/O + transform/security | `01-RESEARCH.md` lines 389-405, 418-430, 620-633 | scaffold-first |
| Chat schema/action fixtures and migration tests | test/fixture | CRUD + branching | `01-RESEARCH.md` lines 349-375, 723-731 | scaffold-first |
| Phase validation docs/results for Playwright/Vitest/pytest | docs/test | validation | `01-RESEARCH.md` lines 703-755; `HTTPS-SETUP.md` lines 67-75 | scaffold-first |

## Pattern Assignments

### `web-ui/client` shell, screens, components, and tests

**Analog:** Stitch design handoff plus UI contract.

**Imports/config pattern** (`01-RESEARCH.md` lines 280-299):
```js
// web-ui/client/svelte.config.js
// Source: Context7 /sveltejs/kit adapter-static docs
import adapter from '@sveltejs/adapter-static';

export default {
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      fallback: '200.html'
    })
  }
};

// web-ui/client/src/routes/+layout.js
export const ssr = false;
```

**Design tokens to copy** (`docs/stitch/DESIGN.md` lines 15-31, 61-71):
```markdown
**Explicit Instruction:** 1px solid borders are strictly prohibited for sectioning.
Structure must be defined through background shifts.

- **Base Layer:** `surface` (#060e20)
- **Secondary Workspaces:** `surface-container-low` (#091328)
- **Interactive Cards/Panels:** `surface-container-high` (#141f38)
- **Floating Modals:** `surface-container-highest` (#192540)

To elevate the UI, floating elements must utilize **Glassmorphism**.
Combine `surface-container-highest` at 60% opacity with a `backdrop-filter: blur(20px)`.

* **Primary:** Solid `primary` (#b6a0ff) with `on_primary` (#34000) text.
* **Secondary (Glass):** `surface-container-high` at 40% opacity with a `backdrop-filter`.
* **Structure:** No background stroke. Use `surface-container-highest` background.
* **The "No-Divider" Rule:** Forbid 1px dividers.
```

**Scope correction pattern** (`01-UI-SPEC.md` lines 43-49, 136-138):
```markdown
- Use the `docs/stitch/DESIGN.md` tokens as canonical when the static HTML export palette differs.
- Preserve the True Dark, tonal-layered interface: no bright app chrome, no pure white text, no account/billing/logout affordances, and no marketing hero.
- Apply the no-line rule for layout sectioning.
- Glass surfaces are allowed for floating menus, modals, composer, and sticky headers.
- Use direct operational labels: `Import Character`, `Create Character`, `Save Character`, `Export JSON`, `Test Connection`, `Send`, `Regenerate`, `Edit`, `Continue`.
- Avoid future-facing labels for Phase 2+ features. Do not show disabled Voice Lab, Call, billing, account, logout, or voice-model controls in Phase 1.
```

**App shell pattern** (`docs/stitch/html/home-true-dark.html` lines 34-80; apply UI-SPEC trimming):
```html
<!-- SideNavBar (Web Only) -->
<nav class="hidden md:flex flex-col h-screen w-64 fixed left-0 top-0 bg-[#050B14] border-r border-white/5 z-40 overflow-y-auto">
  ...
  <a class="flex items-center gap-4 px-4 py-3 rounded-xl text-white bg-gradient-to-r from-blue-600/30 to-violet-600/30 ...">
    <span class="material-symbols-outlined text-blue-400">home</span>
    Home
  </a>
  ...
</nav>
<!-- Main Content Canvas -->
<main class="flex-1 md:ml-64 p-6 md:p-10 lg:p-12 pb-24 md:pb-12 max-w-7xl mx-auto w-full z-10 relative">
```
Planner note: copy the desktop rail/main workspace proportions, but include only Home, Gallery, Settings at top level per `01-UI-SPEC.md` lines 153-159.

**Home/thread pattern** (`docs/stitch/html/home-true-dark.html` lines 111-140):
```html
<section>
  <div class="flex justify-between items-center mb-6">
    <h3 class="font-headline text-xl font-bold text-white">Active Conversations</h3>
  </div>
  <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
    <div class="bg-[#0B162C] rounded-2xl p-5 ... flex flex-col gap-4">
      <div class="flex items-start justify-between">
        <div class="flex items-center gap-3">
          <img alt="Avatar" class="w-12 h-12 rounded-full object-cover ..." />
          <div>
            <h4 class="font-bold text-white ...">Sarah (Tutor)</h4>
            <p class="text-xs text-on-surface-variant ...">Active 2m ago</p>
          </div>
        </div>
        <div class="... w-8 h-8 rounded-full ...">
          <span class="material-symbols-outlined text-lg">more_horiz</span>
        </div>
      </div>
```
Planner note: convert mock "Active Conversations" cards into Phase 1 thread rows with portrait, character name, thread title, snippet, timestamp, and rename/delete menu.

**Gallery/card pattern** (`docs/stitch/html/character-gallery-true-dark.html` lines 87-126):
```html
<div class="px-6 py-8 md:px-10 lg:px-12 flex flex-col sm:flex-row sm:items-end justify-between gap-6">
  <h2 class="text-3xl md:text-4xl font-bold text-on-background font-headline tracking-tight">Character Gallery</h2>
  <button class="flex items-center gap-2 px-4 py-2.5 bg-surface-container-high ...">
    <span class="material-symbols-outlined text-[18px]">upload</span>
    Import Silly Tavern
  </button>
</div>
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
  <div class="group relative flex flex-col h-[320px] rounded-2xl bg-surface-container-lowest ...">
    <div class="h-40 relative overflow-hidden bg-surface-variant">
      <img alt="Character Portrait" class="w-full h-full object-cover ..." />
      <div class="absolute top-3 right-3 bg-background/80 backdrop-blur-sm p-1.5 rounded-full ...">
        <span class="material-symbols-outlined text-[18px] text-on-surface">more_vert</span>
      </div>
    </div>
```
Planner note: copy grid/card proportions, but rename "Import Silly Tavern" to `Import Character`, remove voice-assignment badges, and route successful import to editor review.

**Editor/form pattern** (`docs/stitch/html/character-editor-true-dark.html` lines 171-214, 286-299):
```html
<div class="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-8">
  <div>
    <h1 class="text-3xl md:text-4xl font-headline font-black text-on-surface tracking-tight mb-2">Character Editor</h1>
    <p class="text-on-surface-variant font-body">Craft the persona, voice, and initial behavior...</p>
  </div>
  <div class="flex items-center gap-3">
    <button class="px-5 py-2.5 rounded-lg border border-outline-variant ...">Discard</button>
    <button class="px-5 py-2.5 rounded-lg bg-primary text-on-primary ...">
      <span class="material-symbols-outlined text-sm">save</span>
      Save Character
    </button>
  </div>
</div>
<form class="space-y-6 md:space-y-8" id="character-form">
  <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8">
    <div class="lg:col-span-5 space-y-6 lg:space-y-8">
      <div class="bg-surface-container-lowest rounded-2xl p-6 ...">
        <label class="block text-sm font-label font-semibold text-on-surface mb-1.5" for="char-name">Character Name</label>
        <input class="w-full px-4 py-2.5 rounded-lg border border-outline-variant bg-surface ..." />
```
```html
<textarea class="w-full px-4 py-3 rounded-xl border border-outline-variant bg-surface text-sm ... resize-y" id="first-message" name="first-message" rows="4"></textarea>
<button class="text-xs font-semibold text-primary hover:text-primary-dim transition-colors flex items-center gap-1" type="button">
  <span class="material-symbols-outlined text-[14px]">add_circle</span> Add Alternate Greeting
</button>
```
Planner note: keep two-column identity/media/meta left and prompts/greetings right, but remove active voice model selectors/templates/optimizer per `01-UI-SPEC.md` lines 180-189.

**Chat visual pattern** (`docs/stitch/html/voice-call-true-dark.html` lines 124-143; only transcript/message treatment):
```html
<div class="w-full max-w-2xl z-10 mb-8 px-4 h-32 md:h-48 overflow-y-auto rounded-2xl bg-slate-900/50 backdrop-blur-xl border border-white/5 p-4 flex flex-col justify-end space-y-3 shadow-2xl">
  <div class="opacity-50 flex gap-3">
    <div class="w-8 h-8 rounded-full bg-blue-500/20 text-blue-300 flex items-center justify-center flex-shrink-0">
      <span class="material-symbols-outlined text-sm">robot_2</span>
    </div>
    <p class="text-slate-400 text-sm md:text-base leading-relaxed">I've analyzed the recent data patterns...</p>
  </div>
  <div class="flex gap-3 animate-pulse">
    <div class="w-8 h-8 rounded-full bg-blue-500/20 text-blue-300 flex items-center justify-center flex-shrink-0">
      <span class="material-symbols-outlined text-sm">robot_2</span>
    </div>
    <p class="text-blue-400 font-medium text-sm md:text-base leading-relaxed">Processing...</p>
  </div>
</div>
```
Planner note: do not copy call controls, visualizer orb, or live-call framing. Use this only for AI/user bubble spacing, avatar anchors, and streaming/processing state.

**Settings endpoint pattern** (`docs/stitch/html/settings-true-dark.html` lines 127-169):
```html
<div class="bg-slate-900/60 backdrop-blur-xl rounded-xl shadow-[0_8px_32px_0_rgba(0,0,0,0.3)] border border-white/10 overflow-hidden relative group">
  <div class="p-6 border-b border-white/10 bg-slate-800/40 relative z-10">
    <div class="flex items-center space-x-3">
      <div class="p-2 bg-blue-500/20 rounded-lg text-blue-400 ...">
        <span class="material-symbols-outlined">api</span>
      </div>
      <div>
        <h3 class="text-lg font-semibold text-slate-100">LLM Configuration</h3>
        <p class="text-xs text-slate-400">Connect your preferred language model provider.</p>
      </div>
    </div>
  </div>
  <div class="p-6 space-y-5 relative z-10">
    <input id="server-url" placeholder="https://api.openai.com/v1" type="text" />
    <input id="api-key" type="password" value="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" />
    <button class="absolute inset-y-0 right-0 px-3 ..."><span class="material-symbols-outlined text-sm">visibility</span></button>
```
Planner note: keep URL/key/model panel ergonomics, but rename action to `Test Connection` and add Web UI, AI backend, LLM, HTTPS secure-context, and media-device status panels. Do not copy account/billing/danger-zone sections.

**Component inventory** (`01-UI-SPEC.md` lines 221-237):
```markdown
| `AppShell` | Desktop rail, mobile bottom nav, main workspace, status chip area |
| `StatusChip` | Endpoint/secure-context state with icon, label, and accessible text |
| `GlassPanel` | Reusable tonal/glass container for floating menus, modals, composer, and endpoint panels |
| `ThreadListItem` | Stable Home row with portrait, metadata, snippet, menu |
| `CharacterCard` | Gallery card with portrait ratio, sanitized snippet, actions |
| `ImportCardDialog` | JSON/PNG import, parsing progress, warnings, unsafe error state |
| `CharacterFormSection` | Labeled editor section with stable spacing and field error slot |
| `PortraitDropzone` | Upload/preview/replace/remove with keyboard focus and drag state |
| `ChatMessageBubble` | User/AI message rendering, streaming state, stale state, action anchor |
| `MessageActionMenu` | Per-role actions, desktop hover/focus and mobile tap behavior |
| `SwipeStepper` | Previous/current/next/generate controls for AI alternates |
| `Composer` | Multiline input, send action, disabled/streaming/error states |
| `EndpointSettingsPanel` | URL/key/model fields, test action, result state |
```

**Client stream utility pattern** (`01-RESEARCH.md` lines 595-613):
```ts
export async function readChatStream(response: Response, onToken: (token: string) => void) {
  if (!response.body) throw new Error('No response stream');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    for (const line of chunk.split('\n')) {
      if (line.startsWith('data: ')) onToken(line.slice(6));
    }
  }
}
```

**Sanitizer pattern** (`01-RESEARCH.md` lines 418-430):
```ts
import { marked } from 'marked';
import DOMPurify from 'dompurify';

export function renderTrustedMarkdown(untrustedMarkdown: string): string {
  const html = marked.parse(untrustedMarkdown, { async: false }) as string;
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'code', 'pre', 'blockquote', 'ul', 'ol', 'li', 'a'],
    ALLOWED_ATTR: ['href', 'title'],
    ALLOW_DATA_ATTR: false
  });
}
```

### `web-ui/server` FastAPI app, API, domain, storage, migrations, and tests

**Analog:** `01-RESEARCH.md` scaffold patterns; no existing FastAPI production code exists.

**Project structure pattern** (`01-RESEARCH.md` lines 244-270):
```text
web-ui/
├── client/
│   ├── src/routes/              # SvelteKit app shell and screens
│   ├── src/lib/components/      # Local Stitch-derived components
│   ├── src/lib/api/             # Typed API wrappers and stream readers
│   ├── src/lib/sanitizer/       # marked + DOMPurify rendering boundary
│   ├── static/                  # Manifest, icons, static assets
│   └── tests/                   # Vitest unit/component tests
├── server/
│   ├── app/main.py              # FastAPI app factory/static mount
│   ├── app/api/                 # health, settings, characters, threads, chat
│   ├── app/domain/              # card parsing, prompt building, chat actions
│   ├── app/storage/             # SQLAlchemy models, sessions, blob store
│   ├── alembic/                 # SQLite migrations
│   ├── data/                    # local SQLite DB and blobs, gitignored
│   └── tests/                   # pytest contract tests
ai-backend/
├── app/main.py                  # FastAPI /health stub
└── tests/                       # health test
llm/
└── README.md                    # External OpenAI-compatible endpoint setup notes
```

**CORS/origin pattern** (`01-RESEARCH.md` lines 581-592):
```python
from fastapi.middleware.cors import CORSMiddleware

def configure_cors(app, allowed_origins: list[str]) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )
```
Planner note: add origin tests and do not use `allow_origins=["*"]`.

**Streaming proxy pattern** (`01-RESEARCH.md` lines 311-334):
```python
from collections.abc import AsyncIterator
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI

router = APIRouter()

async def token_events(client: AsyncOpenAI, messages: list[dict[str, str]]) -> AsyncIterator[bytes]:
    final: list[str] = []
    async with client.chat.completions.stream(
        model="configured-model",
        messages=messages,
    ) as stream:
        async for event in stream:
            if event.type == "content.delta":
                final.append(event.delta)
                yield f"data: {event.delta}\n\n".encode("utf-8")
    # Store ''.join(final) in the same operation boundary that marks stream completion.

@router.post("/api/chat/{thread_id}/send")
async def send_message(thread_id: str, client: AsyncOpenAI = Depends(...)) -> StreamingResponse:
    messages = await build_prompt_context(thread_id)
    return StreamingResponse(token_events(client, messages), media_type="text/event-stream")
```
Planner note: implementation must use configured `base_url`, API key, and model from server-side settings, never browser-supplied secrets.

**Message schema/migration pattern** (`01-RESEARCH.md` lines 349-375):
```sql
CREATE TABLE messages (
  id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL REFERENCES threads(id),
  parent_message_id TEXT REFERENCES messages(id),
  message_kind TEXT NOT NULL CHECK (
    message_kind IN ('user_text', 'ai_text', 'user_speech', 'ai_speech', 'call_start', 'call_end')
  ),
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'event')),
  sequence INTEGER NOT NULL,
  content_text TEXT,
  selected_alternate_id TEXT,
  edited_from_message_id TEXT REFERENCES messages(id),
  stale_after_edit INTEGER NOT NULL DEFAULT 0,
  branch_root_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE message_alternates (
  id TEXT PRIMARY KEY,
  message_id TEXT NOT NULL REFERENCES messages(id),
  alternate_index INTEGER NOT NULL,
  content_text TEXT NOT NULL,
  source_action TEXT NOT NULL CHECK (source_action IN ('first_mes', 'regenerate', 'swipe', 'continue')),
  created_at TEXT NOT NULL,
  UNIQUE (message_id, alternate_index)
);
```
Planner note: exact names can change, but migration tests must prove six `message_kind` values, selected alternates, edit lineage, stale downstream turns, and chronological rendering.

**Character PNG parse pattern** (`01-RESEARCH.md` lines 389-405):
```python
import base64
import json
from PIL import Image

PNG_KEYS_IN_ORDER = ("ccv3", "chara")

def parse_png_card(path: str) -> dict:
    with Image.open(path) as image:
        metadata = dict(image.text)

    for key in PNG_KEYS_IN_ORDER:
        if key in metadata:
            raw = base64.b64decode(metadata[key], validate=True)
            return json.loads(raw.decode("utf-8"))

    raise ValueError("PNG does not contain a supported character-card chunk")
```

**Pydantic source-card boundary** (`01-RESEARCH.md` lines 620-633):
```python
from pydantic import BaseModel, ConfigDict

class CharacterCardV3(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    description: str | None = None
    personality: str | None = None
    scenario: str | None = None
    first_mes: str | None = None
```
Planner note: use `extra="allow"` at the source-card boundary to preserve unknown fields, then map supported fields into normalized storage plus import warnings.

**Atomic blob write pattern** (`01-RESEARCH.md` lines 443-465):
```python
import os
import tempfile
from pathlib import Path

def atomic_write_blob(blob_dir: Path, final_name: str, data: bytes) -> Path:
    blob_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{final_name}.", suffix=".tmp", dir=blob_dir)
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        final_path = blob_dir / final_name
        os.replace(tmp_name, final_path)
        return final_path
    except Exception:
        try:
            os.unlink(tmp_name)
        finally:
            raise
```

**Validation map pattern** (`01-RESEARCH.md` lines 703-755):
```markdown
| Backend framework | pytest 9.0.3 + pytest-asyncio 1.3.0. |
| Frontend unit framework | Vitest 4.1.5 + happy-dom 20.9.0. |
| Browser/E2E framework | Playwright 1.59.1. |
| Quick run command | `uv run --project web-ui/server pytest web-ui/server/tests -q && npm --prefix web-ui/client run test:unit -- --run` |
| Full suite command | `uv run --project web-ui/server pytest web-ui/server/tests -q && npm --prefix web-ui/client run test:unit -- --run && npm --prefix web-ui/client run test:e2e` |

- [ ] `web-ui/server/tests/test_migrations.py`
- [ ] `web-ui/server/tests/test_card_import.py`
- [ ] `web-ui/server/tests/test_sanitizer_contract.py` or frontend equivalent
- [ ] `web-ui/server/tests/test_chat_stream.py`
- [ ] `web-ui/server/tests/test_message_actions.py`
- [ ] `web-ui/client/package.json`, `vitest.config.ts`, `playwright.config.ts`
- [ ] `web-ui/client/tests/`
```

### `ai-backend` health stub and tests

**Analog:** scaffold-first from research structure; use Phase 0 probe for "minimal, no-state response" shape.

**Minimal response pattern** (`https_serve.py` lines 40-47):
```python
class ProbeHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PROBE_HTML)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(PROBE_HTML)
```
Planner note: implement this as FastAPI `/health` JSON, not `http.server`. Keep it stateless and test it with FastAPI test client/httpx.

**Scope boundary** (`01-RESEARCH.md` lines 263-270):
```text
ai-backend/
├── app/main.py                  # FastAPI /health stub
└── tests/                       # health test
llm/
└── README.md                    # External OpenAI-compatible endpoint setup notes

... `ai-backend` owns only `/health` in this phase.
```

### `llm` docs/config

**Analog:** scaffold-first docs; no local LLM runtime should be created.

**Boundary pattern** (`01-RESEARCH.md` lines 567-573, 664-666):
```markdown
Planner tries to implement a local LLM service health endpoint even though Phase 1 says `llm/` is docs/config only.

Treat `web-ui/server /health` and `ai-backend /health` as RayMe-owned endpoints, and implement LLM status as a Settings connection test against the configured OpenAI-compatible endpoint.

Recommendation: Plan `web-ui/server` and `ai-backend` `/health`; plan LLM status as `web-ui/server` probing configured OpenAI-compatible endpoint.
```

**Docs style pattern** (`HTTPS-SETUP.md` lines 21-42):
```powershell
# On OMEN-PC, from the phase 0 directory:
cd .planning/phases/00-measurement-gate
mkcert -install
mkcert rayme.local 192.168.1.199
# Produces:
#   rayme.local+1.pem
#   rayme.local+1-key.pem

.venv-phase0\Scripts\python.exe probes\https_serve.py `
  --host 192.168.1.199 `
  --cert rayme.local+1.pem `
  --key rayme.local+1-key.pem `
  --bind 192.168.1.199 `
  --port 8443
```
Planner note: `llm/README.md` should mirror this direct setup style: prerequisites, one-time setup, runtime config variables, Settings test behavior, troubleshooting, and explicit "RayMe does not ship local inference".

### HTTPS/mkcert guidance and secure-context probe

**Analog:** exact Phase 0 HTTPS workflow.

**Acceptance pattern** (`HTTPS-SETUP.md` lines 6-11, 44-49):
```markdown
**Acceptance:** `window.isSecureContext === true` and `navigator.mediaDevices`
defined when the Android phone loads the served URL.

- [x] mkcert on LAN (the only supported Phase 0 path)

1. Open Chrome first.
2. Navigate to `https://192.168.1.199:8443` first. Use `https://rayme.local:8443` only if local hostname resolution is configured on the LAN.
3. Confirm there is no certificate warning.
4. Confirm the page shows all green rows.
```

**Secure-context browser checks** (`https_serve.py` lines 31-35):
```js
row("window.isSecureContext", window.isSecureContext, window.isSecureContext === true);
row("navigator.mediaDevices defined", !!navigator.mediaDevices, !!navigator.mediaDevices);
row("location.protocol", location.protocol, location.protocol === "https:");
row("location.href", location.href, true);
row("userAgent", navigator.userAgent, true);
```

**Explicit bind/TLS pattern** (`https_serve.py` lines 62-82):
```python
parser.add_argument(
    "--bind",
    default="192.168.1.199",
    help="IP to bind. Use the LAN IP or a future Tailscale IP, never 0.0.0.0.",
)
...
if args.bind == "0.0.0.0":
    parser.error("Do not bind 0.0.0.0 for this probe; use the LAN or Tailscale IP only.")

context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certfile=args.cert, keyfile=args.key)

server = http.server.HTTPServer((args.bind, args.port), ProbeHandler)
server.socket = context.wrap_socket(server.socket, server_side=True)
```

**Known-good result pattern** (`HTTPS-SETUP.md` lines 67-75):
```markdown
- Chosen path: mkcert on LAN
- Probe URL: `https://192.168.1.199:8443`
- Browser: Android Chrome
- Certificate source: `mkcert rayme.local 192.168.1.199`, with the mkcert root CA installed on the Android phone
- `window.isSecureContext`: `true`
- `navigator.mediaDevices`: defined / `true`
- Notes: `rayme.local` was included in the cert SANs, but the actual passing verification used the direct LAN IP because local hostname resolution was not configured.
```

## Shared Patterns

### Scaffold-First Boundary

**Source:** `01-CONTEXT.md` lines 152-159
**Apply to:** all production code tasks

No production `src/`, `web-ui/`, or `ai-backend/` code exists yet. Treat all implementation files as first scaffold files. Use docs/research snippets as seed patterns, then create tests before relying on behavior.

### Visual System

**Source:** `docs/stitch/DESIGN.md` lines 15-31, `01-UI-SPEC.md` lines 43-49
**Apply to:** all Svelte components

Use True Dark tonal layering, no divider borders for layout sectioning, glass only for floating menus/modals/composer/sticky headers, and the UI-SPEC token values over the raw Stitch HTML palette when they conflict.

### Scope Trimming

**Source:** `01-UI-SPEC.md` lines 29, 136-138, 153-159, 207-213
**Apply to:** shell, Home, Gallery, Editor, Settings, Chat

Remove fake account, billing, logout, Voice Lab, Call, voice-model controls, wake-word controls, and future-feature placeholders. Phase 1 top-level nav is Home, Gallery, Settings only; Editor and Chat are contextual.

### HTTPS And LAN Bind

**Source:** `HTTPS-SETUP.md` lines 21-49; `https_serve.py` lines 62-82
**Apply to:** FastAPI server config, docs, Settings status checks, Playwright/manual validation

Default to explicit configured LAN host/IP. Do not silently bind `0.0.0.0`. Surface `window.isSecureContext` and `navigator.mediaDevices` in Home/Settings.

### Explicit Origin Policy

**Source:** `01-RESEARCH.md` lines 579-593
**Apply to:** `web-ui/server/app/main.py`, API tests, future WebSocket planning

Configure CORS from explicit allowlists. Add tests for allowed and rejected origins.

### Text Streaming Contract

**Source:** `01-RESEARCH.md` lines 311-334 and 595-613
**Apply to:** `web-ui/server/app/api/chat.py`, `web-ui/client/src/lib/api/stream.ts`, chat UI tests

Server yields token chunks, browser renders token-by-token, and final AI text is persisted atomically after stream completion. Do not persist partial tokens as final messages.

### Character Card Safety

**Source:** `01-RESEARCH.md` lines 389-405, 418-430, 620-633; `01-UI-SPEC.md` lines 289-295
**Apply to:** card parser, exporter, import dialog, editor preview, chat bubbles, tests

Prefer `ccv3` over `chara`, strictly base64-decode, preserve unknown/source fields, render only sanitized Markdown, and include malicious-card fixtures.

### Message Branching Semantics

**Source:** `01-RESEARCH.md` lines 349-375; `01-UI-SPEC.md` lines 191-205
**Apply to:** migrations, models, `message_actions.py`, chat API, chat components, tests

Regenerate replaces selected AI content, swipes are alternates with one selected branch, edits mark downstream stale, and Continue extends the previous AI turn using optional composer text.

### File Blob Writes

**Source:** `01-RESEARCH.md` lines 443-465
**Apply to:** portrait upload/import, future audio blob compatibility

Write to a temp file in the target directory, flush/fsync, `os.replace`, then commit SQLite metadata. Add cleanup/orphan tests.

### Validation Gates

**Source:** `01-RESEARCH.md` lines 703-755
**Apply to:** all implementation plans

Use pytest/pytest-asyncio for backend contracts, Vitest/happy-dom for frontend units, Playwright for browser/mobile/import-chat-reload and HTTPS status, plus manual Android HTTPS verification using Phase 0 workflow.

## No Direct Analog Found

These areas have no close production-code analog in the current repository. Planner should treat them as scaffold-first and use `01-RESEARCH.md` plus UI-SPEC contracts as implementation seed patterns.

| File Group | Role | Data Flow | Reason |
|------------|------|-----------|--------|
| SvelteKit project config and route files | config/component | request-response | No `web-ui/client` or Svelte code exists. |
| FastAPI app, routers, dependencies, settings models | app/controller/config | request-response | No FastAPI app exists; only Phase 0 `http.server` probe exists. |
| SQLAlchemy models/session and Alembic env | model/migration | CRUD/batch | No database code exists. |
| Character card parser/exporter | service/utility | file-I/O + transform | No parser code exists; use research snippets and fixtures. |
| Chat streaming proxy and message actions | service/controller | streaming + CRUD | No chat code exists; use research contract and schema-first tests. |
| ai-backend FastAPI app | app/controller | request-response | No `ai-backend` exists; implement health-only stub. |
| LLM docs/config | docs/config | external request-response | `llm/` is docs/config only, no local service. |
| Vitest/Playwright/pytest configs | test/config | validation | No test harness exists yet. |

## Metadata

**Analog search scope:** `rg --files`; `.planning/phases/01-foundations-text-chat-end-to-end`; `.planning/phases/00-measurement-gate`; `docs/stitch/screens`; `docs/stitch/html`; `docs/stitch/DESIGN.md`.

**Files scanned:** 26 repository files. No root `CLAUDE.md` and no project `.claude/skills/` or `.agents/skills/` directories were found.

**Strongest analogs:**
- Exact: `.planning/phases/00-measurement-gate/HTTPS-SETUP.md`
- Exact: `.planning/phases/00-measurement-gate/probes/https_serve.py`
- Visual: `docs/stitch/html/home-true-dark.html`
- Visual: `docs/stitch/html/character-gallery-true-dark.html`
- Visual: `docs/stitch/html/character-editor-true-dark.html`
- Visual: `docs/stitch/html/settings-true-dark.html`
- Partial visual: `docs/stitch/html/voice-call-true-dark.html`
- Scaffold patterns: `.planning/phases/01-foundations-text-chat-end-to-end/01-RESEARCH.md`

**Pattern extraction date:** 2026-04-24
