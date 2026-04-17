# Character Gallery - RayMe AI (True Dark)

- Status: `Canonical`
- Stitch screen ID: `projects/715592942983517637/screens/c36c7502cbea4adb9a07a4796ed07822`
- Original Stitch title: `Character Gallery - RayMe AI (True Dark)`

## Purpose

This screen appears to manage a library of AI personas and the voices assigned to them.

## Primary Layout Regions

- Left navigation rail
- Header with account context and gallery title
- Primary actions for upload and `Create New`
- Character card grid showing persona name, short description, assigned voice, and per-card action menu

## Likely User Tasks

- Browse existing characters
- Create a new persona from scratch
- Inspect which voice is assigned to each character
- Open per-character actions from the overflow menu

## Implementation Notes For GSD

- The gallery likely needs a reusable persona-card component shared with other parts of the app.
- Voice assignment is visible at the gallery level, so the future data model should make character-to-voice association easy to surface.
- Expect the create flow to route directly into the Character Editor.
