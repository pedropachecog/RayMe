# Voice Lab - RayMe AI (True Dark)

- Status: `Canonical`
- Stitch screen ID: `projects/715592942983517637/screens/16e42018955242389fc4dcc97eb004df`
- Original Stitch title: `Voice Lab - RayMe AI (True Dark)`

## Purpose

This screen appears to be the workspace for cloning, configuring, and browsing custom RayMe voices.

## Primary Layout Regions

- Left navigation rail with the main product sections
- Page header describing voice cloning and configuration
- File-drop upload zone for audio samples
- Voice configuration form with voice name, synthesis engine, and optional style tags
- Voice library list showing saved voices such as `Narrator Alpha` and `Podcast Host`
- Processing state row for an in-progress voice sample import

## Likely User Tasks

- Upload source audio to create a new voice
- Name the voice and choose a synthesis engine
- Tag a voice with style descriptors like Warm or Energetic
- Preview existing voices
- Monitor processing status for uploaded audio samples

## Implementation Notes For GSD

- Plan for a multipart workflow: upload, configure, process, and preview.
- The engine selector and style-tag controls should be treated as core inputs, not secondary settings.
- The saved-voice list likely needs row actions and playback support.
