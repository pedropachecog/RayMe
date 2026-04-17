# RayMe Source Brief

RayMe appears to be a desktop-first AI voice assistant product centered on persona-driven voice conversations. The selected canonical design source is the `RayMe AI (True Dark)` screen set exported from Stitch project `projects/715592942983517637` on `2026-04-17`.

## Product Shape

The screen set implies six core product surfaces:

- Home dashboard for starting calls, resuming active conversations, and jumping into quick-start personas
- Voice Lab for uploading audio, configuring synthesis engines, tagging voice styles, and managing saved voices
- Character Gallery for browsing personas and seeing assigned voices
- Character Editor for creating or editing a persona, choosing its voice, and defining initial greeting behavior
- Voice Call for live conversation, transcript display, and in-call controls
- Settings for model provider setup, runtime preferences, and account configuration

## Likely User Journeys

The clearest end-to-end flow implied by the screens is:

1. Create or edit a voice in Voice Lab
2. Create or edit a character in Character Editor
3. Review saved personas in Character Gallery
4. Start or resume a conversation from Home
5. Conduct the live session in Voice Call

A second visible flow is application setup:

1. Open Settings
2. Configure the model provider and API key
3. Choose a model
4. Adjust behavior controls such as screen awareness or wake-word sensitivity

## Key Product Concepts

- Characters: named AI personas with a distinct description and an assigned voice
- Voices: cloned or configured speech profiles with synthesis-engine choices and style tags
- Conversations: resumable voice sessions surfaced from the home dashboard and handled in the voice-call view
- Configuration: user-managed provider, model, and behavior settings exposed directly in the product UI

## Design Direction

`True Dark` is the canonical theme for this handoff package. Future GSD planning should treat these six screens as the primary visual reference rather than the lighter or standard dark variants in the same Stitch project.

## Scope Guidance For Later GSD Initialization

Use this brief together with `docs/stitch/manifest.md` and the per-screen notes under `docs/stitch/screens/` as the seed inputs for a later:

```bash
$gsd-new-project --auto @docs/rayme-source.md
```

That later project-init step should preserve the current boundaries: this handoff package captures the visible product shape and the exported design artifacts, not implementation details beyond what the screens explicitly show.
