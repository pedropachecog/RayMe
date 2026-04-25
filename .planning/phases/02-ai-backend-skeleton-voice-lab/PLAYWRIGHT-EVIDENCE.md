# Phase 02 Playwright Evidence

## Live Voice Lab Manual Preview

- Saved test: `web-ui/client/tests/e2e/live-voice-lab-manual-preview.spec.ts`
- Live target: `https://192.168.1.199:8443/voice-lab`
- AI health target: `https://192.168.1.199:9443/health`
- Deployed commit for passing run: `8d0a215`

Command:

```bash
cd web-ui/client
RAYME_ENABLE_LIVE_E2E=1 \
RAYME_LIVE_WEB_URL=https://192.168.1.199:8443 \
RAYME_LIVE_AI_HEALTH_URL=https://192.168.1.199:9443/health \
npx playwright test tests/e2e/live-voice-lab-manual-preview.spec.ts --project=desktop-chromium --reporter=json
```

Results:

- `playwright-results/live-voice-lab-manual-preview-20260425T112430Z.json`:
  failed, 0 passed / 1 failed, duration 231389.769 ms. This run found the
  CSP media playback defect: data URL audio was blocked because `media-src`
  was not configured.
- `playwright-results/live-voice-lab-manual-preview-20260425T113230Z.json`:
  passed, 1 passed / 0 failed, duration 212401.167 ms.

Additional live checks after deploy:

- Direct AI STT accepted the saved Libb sample and returned a transcript using
  CPU `int8` fallback.
- Web `/api/voices/assets/{asset_id}/transcribe` returned HTTP 200 with an
  editable transcript for Libb.
- Voice Library cleanup verified only `Libb` remained; no generated test voices
  were left in the library.
