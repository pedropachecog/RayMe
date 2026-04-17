# Home - RayMe AI (True Dark)

- Status: `Canonical`
- Stitch screen ID: `projects/715592942983517637/screens/bb3e3a5612064c5d9b1cc58cb07b1318`
- Original Stitch title: `Home - RayMe AI (True Dark)`

## Purpose

This screen appears to be the primary dashboard for starting or resuming RayMe voice sessions.

## Primary Layout Regions

- Left navigation rail with Home, Gallery, Voice Lab, Editor, Settings, Help, and Logout
- Top utility area with notifications and account controls
- Main hero area with greeting and the primary `Start New Voice Call` action
- Active conversations list with recent status and resume actions
- Quick-start voice cards for predefined persona types
- Usage stats panel showing recent voice-generation usage

## Likely User Tasks

- Start a new voice call with an AI persona
- Resume an active or paused conversation
- Jump into a quick-start persona such as Therapist, Translator, or Gamer
- Check recent voice usage at a glance

## Implementation Notes For GSD

- Treat this as the main entry screen and routing hub for the RayMe experience.
- The dashboard likely needs reusable card patterns for conversation summaries and quick-start personas.
- The copy emphasizes low-latency voice sessions, so the future implementation should keep the main call-start action prominent.
