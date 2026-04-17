# Voice Call - RayMe AI (True Dark)

- Status: `Canonical`
- Stitch screen ID: `projects/715592942983517637/screens/5d6bd2d72c7c4e589a3cb5230540f9e6`
- Original Stitch title: `Voice Call - RayMe AI (True Dark)`

## Purpose

This screen appears to be the active real-time voice conversation view between the user and RayMe.

## Primary Layout Regions

- Left navigation rail
- Top bar with status, connection state, time, notifications, and account controls
- Center conversation area with alternating AI and user transcript bubbles
- Prominent waveform or audio-reactive visualizer
- Bottom control bar with `SETTINGS`, `SHARE`, `MUTE`, and `END`

## Likely User Tasks

- Monitor live call status
- Read the recent transcript exchange
- Mute the microphone
- Open in-call settings
- Share the current session
- End the call

## Implementation Notes For GSD

- Treat this as the highest-interactivity screen in the current set.
- The transcript and control bar should be designed as separate UI units so they can evolve independently.
- The connected state and processing text imply live updates, so later planning should account for streaming or event-driven state changes.
