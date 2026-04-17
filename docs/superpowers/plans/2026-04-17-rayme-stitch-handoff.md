# RayMe Stitch Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local RayMe handoff package from the Stitch true-dark screens so the repo contains screenshots, HTML exports, a manifest, per-screen notes, and a GSD-ready source brief.

**Architecture:** Preserve the Stitch artifacts locally under `docs/stitch/`, then layer small markdown documents on top that describe what each screen appears to do. Keep the handoff package traceable by using one normalized stem per screen across markdown, screenshot, and HTML files.

**Tech Stack:** Stitch MCP, markdown docs, shell download commands

---

### Task 1: Prepare Directories And Update The Spec

**Files:**
- Modify: `docs/superpowers/specs/2026-04-16-rayme-stitch-handoff-design.md`
- Create: `docs/stitch/`
- Create: `docs/stitch/screens/`
- Create: `docs/stitch/screenshots/`
- Create: `docs/stitch/html/`

- [ ] **Step 1: Update the design spec to reflect the now-available true-dark voice call screen**

Confirm the canonical screen set is six true-dark screens and remove the previous voice-call gap-fill assumption.

- [ ] **Step 2: Create the handoff directories**

Run: `mkdir -p /d/Pedro/Repos/Program/RayMe/docs/stitch/screens /d/Pedro/Repos/Program/RayMe/docs/stitch/screenshots /d/Pedro/Repos/Program/RayMe/docs/stitch/html`
Expected: directories created with no output

### Task 2: Download The Stitch Assets

**Files:**
- Create: `docs/stitch/screenshots/home-true-dark.png`
- Create: `docs/stitch/screenshots/voice-lab-true-dark.png`
- Create: `docs/stitch/screenshots/character-gallery-true-dark.png`
- Create: `docs/stitch/screenshots/character-editor-true-dark.png`
- Create: `docs/stitch/screenshots/voice-call-true-dark.png`
- Create: `docs/stitch/screenshots/settings-true-dark.png`
- Create: `docs/stitch/html/home-true-dark.html`
- Create: `docs/stitch/html/voice-lab-true-dark.html`
- Create: `docs/stitch/html/character-gallery-true-dark.html`
- Create: `docs/stitch/html/character-editor-true-dark.html`
- Create: `docs/stitch/html/voice-call-true-dark.html`
- Create: `docs/stitch/html/settings-true-dark.html`

- [ ] **Step 1: Download the six screenshot assets**

Use the Stitch-provided `screenshot.downloadUrl` values and save them under the normalized filenames.

- [ ] **Step 2: Download the six HTML exports**

Use the Stitch-provided `htmlCode.downloadUrl` values and save them under the normalized filenames.

- [ ] **Step 3: Verify the local assets exist**

Run: `find /d/Pedro/Repos/Program/RayMe/docs/stitch -maxdepth 2 -type f | sort`
Expected: all twelve asset files are present

### Task 3: Write The Handoff Docs

**Files:**
- Create: `docs/stitch/manifest.md`
- Create: `docs/stitch/screens/home-true-dark.md`
- Create: `docs/stitch/screens/voice-lab-true-dark.md`
- Create: `docs/stitch/screens/character-gallery-true-dark.md`
- Create: `docs/stitch/screens/character-editor-true-dark.md`
- Create: `docs/stitch/screens/voice-call-true-dark.md`
- Create: `docs/stitch/screens/settings-true-dark.md`
- Create: `docs/rayme-source.md`

- [ ] **Step 1: Write the manifest**

Include project metadata, export date, theme decision, the six screen IDs, and the local file mapping table.

- [ ] **Step 2: Write one screen note per canonical screen**

Each file must document the visible purpose, main layout regions, likely tasks, and GSD implementation notes without inventing unsupported backend behavior.

- [ ] **Step 3: Write the GSD-ready source brief**

Summarize the RayMe product shape, the primary journeys implied by the six screens, and the fact that true-dark is the canonical design direction.

### Task 4: Verify The Package

**Files:**
- Modify: `docs/stitch/manifest.md`
- Modify: `docs/rayme-source.md`

- [ ] **Step 1: Verify the asset and doc inventory**

Run: `find /d/Pedro/Repos/Program/RayMe/docs -maxdepth 4 -type f | sort`
Expected: spec, plan, manifest, six screen docs, source brief, six screenshots, and six HTML files

- [ ] **Step 2: Check the manifest against the actual files**

Open `docs/stitch/manifest.md` and verify every listed local path exists and every screen ID matches the true-dark Stitch screen list.

- [ ] **Step 3: Check the source brief for unsupported claims**

Read `docs/rayme-source.md` and remove any statements that go beyond what is visible in the selected screens.
