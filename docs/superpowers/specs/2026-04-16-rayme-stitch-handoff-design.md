# RayMe Stitch Handoff Design

**Goal:** Create a local handoff package in this repo that captures the canonical Stitch source material for RayMe and makes it usable as input for a later GSD project bootstrap.

## Scope

This work produces documentation and source assets only. It does not initialize `.planning/`, generate a roadmap, or implement application code.

## Source Of Truth

- Stitch project: `projects/715592942983517637`
- Canonical visual direction: `RayMe AI (True Dark)`
- Output style: curated handoff package, not a raw export dump

## Canonical Screen Set

Use the `True Dark` RayMe screens as the canonical set:

- Home
- Voice Lab
- Character Gallery
- Character Editor
- Voice Call
- Settings

## Deliverables

Create these files and folders:

- `docs/stitch/manifest.md`
  - Project metadata
  - Canonical screen list
  - Stitch project ID and screen IDs
  - Local file mapping for screenshots and HTML
- `docs/stitch/screens/`
  - One markdown file per selected screen
  - Each file documents purpose, main regions, likely user actions, implementation notes, and source status
- `docs/stitch/screenshots/`
  - Downloaded local screenshot files for each selected screen
- `docs/stitch/html/`
  - Downloaded local HTML exports for each selected screen
- `docs/rayme-source.md`
  - Concise product brief synthesizing the screen set into a GSD-friendly source document

## Naming Rules

Use stable lowercase kebab-case names:

- `home-true-dark`
- `voice-lab-true-dark`
- `character-gallery-true-dark`
- `character-editor-true-dark`
- `settings-true-dark`
- `voice-call-true-dark`

Apply the same stem across markdown, screenshot, and HTML files so manifest references are predictable.

## Content Requirements

### `docs/stitch/manifest.md`

Must contain:

- Project title
- Stitch project ID
- Export date
- Chosen canonical theme
- Table of selected screens
- For each screen: title, canonical status, Stitch screen ID, local markdown path, local screenshot path, local HTML path
- A short “gaps and assumptions” section

### `docs/stitch/screens/*.md`

Each screen file must contain:

- Screen title
- Canonical or gap-fill status
- Stitch screen ID
- Original Stitch title
- Short purpose statement
- Primary layout regions
- Likely interactions or user tasks visible from the design
- Notes for later implementation in GSD

These notes should describe what the screen appears to do, without inventing backend or domain behavior that is not visible from the design.

### `docs/rayme-source.md`

Must summarize:

- What RayMe appears to be from the selected screens
- Core user journeys implied by the screens
- The role of characters, voice lab, settings, and voice call
- Theme decision: `True Dark` is canonical

## Constraints

- Prefer direct artifact preservation over paraphrase where possible
- Do not create extra interpretation-heavy product requirements beyond what the screens support
- Keep the package human-readable so it can be used later with `$gsd-new-project --auto @docs/rayme-source.md`

## Non-Goals

- No `.planning/` initialization
- No GSD roadmap generation
- No UI-SPEC generation
- No code scaffolding

## Verification

The handoff is complete when:

- All selected screen markdown files exist
- All selected screenshots are stored locally
- All selected HTML exports are stored locally
- `docs/stitch/manifest.md` links the full set together
- `docs/rayme-source.md` can stand alone as a project brief for later GSD initialization
