# 02-18 Summary - Full Local, Live OMEN-PC, and Android Acceptance

## Outcome

Phase 02 plan 02-18 is complete.

The local automated suite passed, the live OMEN-PC Voice Lab browser flow passed with saved Playwright evidence, live health showed real GPU-backed F5 residency with faster-whisper CUDA `int8_float16`, and Android Chrome product-owner acceptance was reported as passed.

## Verification

Full local acceptance passed on 2026-04-25:

```text
uv run --project web-ui/server pytest web-ui/server/tests -q
120 passed

uv run --project ai-backend pytest ai-backend/tests -q
44 passed, 1 warning

npm --prefix web-ui/client run test:unit -- --run
78 passed

npm --prefix web-ui/client run test:e2e
40 passed
```

Live OMEN-PC acceptance passed:

```text
RAYME_ENABLE_LIVE_E2E=1 RAYME_LIVE_WEB_URL=https://192.168.1.199:8443 RAYME_LIVE_AI_HEALTH_URL=https://192.168.1.199:9443/health npx playwright test tests/e2e/live-voice-lab.spec.ts --project=desktop-chromium --reporter=json
```

Saved result:

```text
.planning/phases/02-ai-backend-skeleton-voice-lab/playwright-results/live-voice-lab-02-18-20260425T145656Z.json
1 expected, 0 unexpected, 0 skipped, 0 flaky
```

Live runtime evidence before Android handoff:

- Deployed commit: `e5fcccf0f318fd4f658fdd10a680a2a99995ed79`
- Resident TTS engine: `f5`
- STT model: `distil-large-v3`
- STT compute type: `int8_float16`
- VAD ready: `true`
- Health VRAM used/headroom: `2591.4 MB` used, `8408.6 MB` headroom
- `nvidia-smi`: RTX 3060, driver `560.94`, `2414 MiB / 12288 MiB`

## Android Acceptance

The product owner reported that Android Chrome Voice Lab testing passed:

- Opened `https://192.168.1.199:8443/voice-lab`
- Uploaded a sample
- Confirmed transcript/edit path
- Saved the voice
- Ran test-play
- Accepted the generated audio as sufficient for Phase 3 call testing

## Notes For Phase 3

- Phase 02 intentionally has F5 as the only implemented synthesis engine. XTTS v2, Qwen3-TTS, LuxTTS, Chatterbox Turbo, and TADA 1B remain in the registry but report unavailable with the explicit reason `engine synthesis is not implemented in Phase 02`.
- Voice Lab can now provide the saved voice input Phase 3 needs, but Phase 3 still owns actual call media plumbing and in-call voice usage.
- The local health route test uses fake TTS adapters to verify the route contract without local model loading. Real GPU residency is proven by the live OMEN-PC health and Playwright evidence, not by the fake-adapter local test.
