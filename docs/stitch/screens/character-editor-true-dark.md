# Character Editor - RayMe AI (True Dark)

- Status: `Canonical`
- Stitch screen ID: `projects/715592942983517637/screens/49e70870e2ad4fab9274aaa871146a7c`
- Original Stitch title: `Character Editor - RayMe AI (True Dark)`

## Purpose

This screen appears to define a character’s identity, selected voice, and initial prompt-style behavior.

## Primary Layout Regions

- Left navigation rail
- Header with editor title and `Discard` and `Save` actions
- Avatar upload area
- Character naming input
- Voice model selector with preview buttons for options such as `Nova (Neutral)` and `Echo (Deep)`
- Tooling row with options like `Silly Tavern Compatible`, `Templates`, and `Optimize`
- Prompt or greeting area described as the initial greeting or scenario setup

## Likely User Tasks

- Upload or change a character avatar
- Name a character
- Choose and preview a voice model
- Apply a template or optimization shortcut
- Write the initial greeting or scenario setup
- Save or discard edits

## Implementation Notes For GSD

- This screen suggests a form-heavy flow with media upload, structured controls, and a longer free-text field.
- Voice preview is visible inside the editor, so the future implementation should support inline sample playback.
- The compatibility and optimization affordances imply optional advanced tooling that can be added after the base editor works.
