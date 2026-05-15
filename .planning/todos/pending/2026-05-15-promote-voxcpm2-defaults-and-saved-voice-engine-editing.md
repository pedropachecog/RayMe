---
created: 2026-05-15T11:13:57.148Z
title: Promote VoxCPM2 defaults and saved voice engine editing
area: general
files:
  - web-ui/client/src/routes/voice-lab/+page.svelte:320
  - web-ui/client/src/lib/components/voice/VoiceLibraryRow.svelte:88
  - web-ui/client/src/lib/api/voices.ts:60
  - web-ui/server/app/domain/voice_service.py:168
  - web-ui/server/app/domain/settings_service.py:137
  - ai-backend/app/config.py
  - ai-backend/app/models/engine_metadata.py
  - ai-backend/app/models/tts_registry.py
  - scripts/deploy-omen.sh:342
---

## Problem

Phase 8 promoted VoxCPM2 as the preferred/default live-call TTS engine, but the deployed product still has several F5-centered defaults and editing gaps:

- The active Beau Brown repro voice was still saved with `default_engine = f5`, so long-call debugging could accidentally test the wrong engine.
- Voice Lab can create a new voice with `default_engine = voxcpm2`, but the saved Voice Library UI does not expose an edit path for changing an existing voice's default engine.
- The client PATCH helper only sends `{ name }`, while the server PATCH schema accepts `default_engine` but `VoiceService.rename_voice()` only applies `name` and `metadata`; `default_engine` is ignored.
- Web UI settings, AI backend config, engine metadata, registry invariants, client fallbacks, tests, and `scripts/deploy-omen.sh` still encode F5 as the global/resident default.
- Existing voices/settings, including Beau Brown voices, need an explicit migration or operator flow rather than relying on hidden database edits.

This was intentionally deferred from the current long-message live-call freeze investigation so that the immediate repro can use a newly created VoxCPM2 voice without mixing product-default migration into the debugging patch.

## Solution

Plan a focused follow-up that:

- Adds saved-voice engine editing in the Voice Library with VoxCPM2 settings controls or a clear edit flow.
- Updates the client API helper and server service so PATCH persists `default_engine`, reference transcript changes if exposed, and normalized engine metadata.
- Promotes VoxCPM2 as the actual live-call default where appropriate, while preserving F5 as fallback/comparator.
- Updates or deliberately documents the AI backend resident-engine default and `scripts/deploy-omen.sh` health semantics; if script behavior changes, do it in the canonical deploy script only.
- Updates tests for creation, editing, settings defaults, call engine selection, and OMEN health expectations.
- Provides an explicit migration/repair path for existing voices/settings, especially Beau Brown, with evidence that calls report/use `engine_id = voxcpm2` after migration.
