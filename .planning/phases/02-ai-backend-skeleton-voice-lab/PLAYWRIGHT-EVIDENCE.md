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
- `playwright-results/live-voice-lab-manual-preview-20260425T123912Z.json`:
  passed, 1 passed / 0 failed, duration 86492.028 ms. This run was after the
  GPU runtime guard deployment and verified the live browser flow still
  uploads, transcribes, accepts an edited manual transcript, previews, and
  exposes playable preview audio.

Additional live checks after deploy:

- Direct AI STT accepted the saved Libb sample and returned a transcript using
  GPU `int8_float16` on deployed commit `f4846ca` after CUDA 12.6 runtime
  installation.
- Web `/api/voices/assets/{asset_id}/transcribe` returned HTTP 200 with an
  editable transcript for Libb.
- Voice Library cleanup verified only `Libb` remained; no generated test voices
  were left in the library.

## Live GPU Runtime Regression Check

- Saved result:
  `playwright-results/live-gpu-runtime-20260425T123812Z.json`
- Deployed commit: `0f34713`
- Deploy path: `scripts/deploy-omen.sh`
- Deploy GPU gate: passed with `torch 2.10.0+cu126`, CUDA `12.6`,
  `torchaudio 2.10.0+cu126`, device `NVIDIA GeForce RTX 3060`

Results:

- F5 preview via `POST /api/voices/preview` for saved Libb voice returned
  playable `audio/wav` JSON. Cold after restart: 12 seconds. Warm repeat:
  1 second.
- STT via `POST /stt/transcribe` for saved Libb sample returned the expected
  transcript with `compute_type: int8_float16`. Cold after restart: 82 seconds.
  Warm repeat: 1 second.
- The cold timings are model-load warmup; the warm timings are the steady-state
  runtime path relevant to call-latency behavior.

## Voice Lab Playback And Speed Controls

- Saved tests:
  - `web-ui/client/tests/e2e/voice-lab.spec.ts`
  - `web-ui/client/tests/e2e/live-voice-lab.spec.ts`
- Deployed commit for passing live run: `f9dd3cd`
- Live target: `https://192.168.1.199:8443/voice-lab`
- AI health target: `https://192.168.1.199:9443/health`

Commands:

```bash
cd web-ui/client
npx playwright test tests/e2e/voice-lab.spec.ts --project=desktop-chromium --reporter=json
```

```bash
cd web-ui/client
RAYME_ENABLE_LIVE_E2E=1 \
RAYME_LIVE_WEB_URL=https://192.168.1.199:8443 \
RAYME_LIVE_AI_HEALTH_URL=https://192.168.1.199:9443/health \
npx playwright test tests/e2e/live-voice-lab.spec.ts --project=desktop-chromium --reporter=json
```

Results:

- `playwright-results/live-voice-lab-playback-speed-20260425T135243Z.json`:
  failed, 0 passed / 1 failed, duration 79032.473 ms. This run found that the
  live Voice Library already had saved voices with row-level speech speed
  sliders, making the test's generic `Speech speed` locator ambiguous.
- `playwright-results/live-voice-lab-playback-speed-20260425T135525Z.json`:
  passed, 1 passed / 0 failed, duration 96763.603 ms. This live deployed run
  verified uploaded-sample playback, speech-speed submission, saved-voice
  test-play, generated test audio controls, and cleanup of the temporary live
  test voice.
- `playwright-results/local-voice-lab-playback-speed-20260425T135811Z.json`:
  passed, 6 passed / 0 failed, duration 78618.173 ms. This mocked browser run
  covers Voice Lab save after preview failure, manual transcript after failed
  transcription, mobile-width layout, row-scoped test-play, blocked delete, and
  gallery voice states with the new playback/speed controls.
