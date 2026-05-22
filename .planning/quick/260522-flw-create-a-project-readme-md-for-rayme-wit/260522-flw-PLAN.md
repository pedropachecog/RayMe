---
phase: quick-260522-flw
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - web-ui/client/tests/e2e/readme-screenshots.spec.ts
  - docs/screenshots/home.png
  - docs/screenshots/gallery.png
  - docs/screenshots/call.png
  - README.md
autonomous: true
requirements: []
must_haves:
  truths:
    - "A top-level README.md exists at the repo root introducing RayMe to a public audience"
    - "README.md embeds at least one screenshot captured live from the running web UI build"
    - "The embedded screenshot is a real browser render of the SvelteKit client, not a docs/stitch mockup"
  artifacts:
    - path: "README.md"
      provides: "Public project introduction with embedded live screenshot"
      min_lines: 40
    - path: "web-ui/client/tests/e2e/readme-screenshots.spec.ts"
      provides: "Playwright capture spec that boots the client and writes screenshots"
    - path: "docs/screenshots/home.png"
      provides: "Live screenshot of the running web UI home screen"
  key_links:
    - from: "README.md"
      to: "docs/screenshots/home.png"
      via: "markdown image embed"
      pattern: "docs/screenshots/.*\\.png"
    - from: "web-ui/client/tests/e2e/readme-screenshots.spec.ts"
      to: "docs/screenshots/"
      via: "page.screenshot path"
      pattern: "screenshot"
---

<objective>
Create a public-facing top-level `README.md` for RayMe and embed at least one
screenshot captured LIVE from the running web UI client (the real SvelteKit
build in a real browser), per the user's explicit choice of "run app, capture
live" over reusing the `docs/stitch/screenshots/*.png` design mockups.

Purpose: the repo is about to be made public and currently has no root README.
Output: `README.md` at the repo root, a Playwright capture spec, and tracked
screenshot PNGs under `docs/screenshots/`.
</objective>

<execution_context>
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/workflows/execute-plan.md
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md

<interfaces>
<!-- Key facts the executor needs. No codebase exploration required. -->

The web UI client (`web-ui/client/`) is a SvelteKit static-adapter SPA:
- `web-ui/client/src/routes/+layout.ts` sets `ssr = false` — pure client-side render.
- Home route (`src/routes/+page.svelte`) fetches `/api/threads` and `/api/characters`
  on mount. Routes also exist for `/gallery`, `/call`, `/voice-lab`, `/settings`.
- Without the `web-ui/server` Python backend, those `/api/*` calls fail and the
  page renders an empty/error state. The page chrome (header, nav, copy) still
  renders correctly.

Playwright is already configured (`web-ui/client/playwright.config.ts`):
- `webServer.command` is `npm run build && npm run preview -- --host 127.0.0.1 --port 4173`
  — Playwright boots the REAL built client automatically before the spec runs.
- `baseURL` is `http://127.0.0.1:4173`. Two projects: `desktop-chromium`, `mobile-chromium`.
- `reuseExistingServer: true` outside CI.

Existing E2E specs populate realistic content by mocking `/api/*` with
`page.route(...)` instead of running the Python backend. Reusable helpers:
- `tests/e2e/helpers/acceptance.ts` — `fulfillJson(route, body, status)`,
  `installEmptyVoiceLibraryRoute(page)`, `installMockCallMedia(page)`,
  `installBrowserErrorGuard(page)`.
- `tests/e2e/helpers/fixtures.ts` — `makeCharacter()`, `makeThreadDetail()`,
  `makeAiMessage()`, `makeUserMessage()` deterministic data fixtures.
- `tests/e2e/helpers/images.ts` — `portraitPng()`, `fulfillPortraitImage(page, url)`.

Pattern from `home-start-chat.spec.ts`: route `**/api/threads` and
`**/api/characters` (GET) with `fulfillJson` to render a populated home screen.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write the live screenshot capture spec</name>
  <files>web-ui/client/tests/e2e/readme-screenshots.spec.ts</files>
  <action>
    Create a Playwright spec that captures README screenshots from the live
    running client. Playwright's `webServer` config already builds and serves
    the real SvelteKit client at `http://127.0.0.1:4173` — this IS a live
    capture of the running app, not a mockup.

    The spec must:
    - Run only under the `desktop-chromium` project (use `test.skip` when
      `test.info().project.name !== 'desktop-chromium'`) so it does not also
      emit Pixel-5 sized duplicates.
    - For each captured screen, mock the relevant `/api/*` routes with
      `fulfillJson` and the `makeCharacter` / `makeThreadDetail` fixtures so the
      live build renders realistic, populated content (the Python backend is
      not booted — route mocking is the established pattern in this repo).
    - Capture at minimum the HOME screen. Also capture GALLERY and CALL screens
      if cheap (nice-to-have): gallery via mocked `/api/characters`, call via
      `installMockCallMedia` + a mocked `/api/calls/start` and thread routes.
    - Use a deterministic desktop viewport (e.g. 1280x800) via
      `page.setViewportSize` before navigation.
    - Wait for meaningful content (e.g. a heading or character card) to be
      visible before `page.screenshot`, to avoid blank/loading captures.
    - Write PNGs to repo-relative `docs/screenshots/home.png`,
      `docs/screenshots/gallery.png`, `docs/screenshots/call.png` using a path
      resolved from the spec file location (the spec runs with cwd at
      `web-ui/client/`, so target `../../docs/screenshots/<name>.png`).
    - If GALLERY or CALL prove impractical to render meaningfully, the spec may
      still pass by capturing only HOME — but HOME is mandatory and must be a
      live render. Do NOT copy `docs/stitch/screenshots/*.png`.

    Create the `docs/screenshots/` directory if it does not exist (the spec can
    `fs.mkdir(..., { recursive: true })` before writing).
  </action>
  <verify>
    <automated>cd web-ui/client && npx playwright test readme-screenshots.spec.ts --project=desktop-chromium</automated>
  </verify>
  <done>
    `npx playwright test readme-screenshots.spec.ts --project=desktop-chromium`
    passes, and `docs/screenshots/home.png` exists as a non-empty PNG produced
    by the real running client build.
  </done>
</task>

<task type="auto">
  <name>Task 2: Write the public README.md and embed the live screenshot</name>
  <files>README.md</files>
  <action>
    Create a top-level `README.md` introducing RayMe to a public audience.
    Verify all claims against `.planning/PROJECT.md` — do not invent features.

    Required sections:
    - Title and a one-line tagline: RayMe is a self-hosted live phone-call
      simulator for AI characters — full-duplex voice calls with barge-in and
      live captions, not a generated-audio player.
    - "What it is" — brief overview from PROJECT.md: import SillyTavern v2/v3
      character cards, clone voices from short samples, then call characters
      with full-duplex audio, VAD barge-in, and live bidirectional captions.
      Threads interleave typed messages and call transcripts.
    - At least one embedded screenshot: `![RayMe home](docs/screenshots/home.png)`
      placed prominently near the top. Embed the gallery/call shots too if
      Task 1 produced them.
    - "Architecture" — three independently configurable services over LAN:
      `web-ui/` (SvelteKit client + FastAPI server for characters, chat,
      threads, voices, settings), `ai-backend/` (FastAPI — STT, TTS engines,
      VAD, WebRTC), and an OpenAI-compatible LLM server.
    - "Tech stack" — Python (uv), SvelteKit/TypeScript, Playwright, WebRTC;
      TTS engines F5-TTS, XTTS v2, Qwen3-TTS, VoxCPM2 (VoxCPM2 is the live-call
      default); faster-whisper STT; Silero VAD. AI backend targets an NVIDIA
      RTX 3060 (12 GB VRAM).
    - "Status / scope" — single-user, LAN-only, no authentication, English-only
      v1. Note it is a personal project.
    - A short "Running it" pointer that directs to the per-service directories
      rather than duplicating full setup steps (avoid documentation churn).
    - License: reference the existing `LICENSES.md` at the repo root.

    Keep the tone public-facing and accurate. This is documentation only — no
    production code changes.
  </action>
  <verify>
    <automated>test -f README.md && grep -q 'docs/screenshots/home.png' README.md && test -s docs/screenshots/home.png</automated>
  </verify>
  <done>
    `README.md` exists at the repo root, introduces RayMe accurately per
    PROJECT.md, and embeds at least the live `docs/screenshots/home.png`
    screenshot. No `docs/stitch/screenshots/*.png` mockup is referenced as the
    README screenshot.
  </done>
</task>

</tasks>

<verification>
- `README.md` exists at repo root and renders as valid Markdown.
- At least one embedded screenshot resolves to a file under `docs/screenshots/`.
- `docs/screenshots/home.png` is a non-empty PNG generated by the live client.
- The capture spec passes under `desktop-chromium` and reuses existing E2E helpers.
- No reference to `docs/stitch/screenshots/*.png` as a README screenshot.
</verification>

<success_criteria>
- Public-facing root `README.md` accurately introduces RayMe (verified against PROJECT.md).
- At least one LIVE screenshot of the running web UI client is captured and embedded.
- Screenshot artifacts are tracked under `docs/screenshots/`.
- The Playwright capture spec is a repeatable dev artifact, no production code changed.
</success_criteria>

<output>
After completion, create `.planning/quick/260522-flw-create-a-project-readme-md-for-rayme-wit/260522-flw-SUMMARY.md`
</output>
