# Phase 03 Playwright Evidence

## Local Call MVP Acceptance

- Timestamp: `2026-04-25T22:03:07Z`
- commit SHA: `c298e6e`
- Scope: local mocked Phase 3 call acceptance before live OMEN-PC deployment.
- Browser projects: `desktop-chromium`, `mobile-chromium`
- Live split: local tests mock same-origin browser APIs; `live-call.spec.ts` is present, gated, not run locally without `RAYME_ENABLE_LIVE_E2E=1`, and contains no `/api/calls/*` or `/webrtc/*` route mocks.
- Browser console/page-error guard: installed in local call specs and passed. The microphone-denial spec allows the expected 403 resource console entry only.
- Screenshots/traces: none produced; Playwright `trace: on-first-retry` did not emit traces because the runs passed without retry.

Commands and results:

```bash
uv run --project ai-backend pytest ai-backend/tests -q
```

Result: passed, `60 passed, 1 warning in 22.57s`.

```bash
uv run --project web-ui/server pytest web-ui/server/tests -q
```

Result: passed, `138 passed in 19.11s`.

```bash
npm --prefix web-ui/client run test:unit -- --run
```

Result: passed, `14 passed` test files, `86 passed` tests.

```bash
npm --prefix web-ui/client run test:e2e -- tests/e2e/call-start.spec.ts tests/e2e/call-toolbar.spec.ts tests/e2e/call-permissions.spec.ts tests/e2e/call-visualizer.spec.ts tests/e2e/call-summary.spec.ts --project=desktop-chromium
```

Result: passed, `7 passed`.

Covered desktop call specs:

- `call-start.spec.ts` - thread header `Start call`, character card `Start Call`, two user to AI cycles, and durable `ai_speech` rows.
- `call-toolbar.spec.ts` - `Mute`, `Unmute`, `Interrupt`, device picker fallback copy, and `End Call`.
- `call-permissions.spec.ts` - microphone denial recovery copy and `Retry Microphone`.
- `call-visualizer.spec.ts` - `Listening`, `Thinking`, and `Speaking` visualizer states with RMS attributes.
- `call-summary.spec.ts` - chronological `call_start`, `user_speech`, `ai_speech`, and `call_end` rows after returning to thread.

```bash
npm --prefix web-ui/client run test:e2e -- tests/e2e/call-mobile.spec.ts --project=mobile-chromium
```

Result before acceptance hardening: passed, `1 passed`.

```bash
npm --prefix web-ui/client run test:e2e -- tests/e2e/call-mobile.spec.ts --project=mobile-chromium
```

Result after acceptance hardening commit `c298e6e`: passed, `1 passed`.

Covered mobile-emulation call spec:

- `call-mobile.spec.ts` - Pixel 5 emulation keeps `Mute`, `Interrupt`, `End Call`, input picker, and output picker visible with at least 44px touch targets above the bottom navigation.

Additional acceptance checks:

```bash
python3 - <<'PY'
from pathlib import Path
files=[Path(p) for p in ['web-ui/client/tests/e2e/call-start.spec.ts','web-ui/client/tests/e2e/call-toolbar.spec.ts','web-ui/client/tests/e2e/call-permissions.spec.ts','web-ui/client/tests/e2e/call-visualizer.spec.ts','web-ui/client/tests/e2e/call-summary.spec.ts','web-ui/client/tests/e2e/call-mobile.spec.ts']]
for token in ['.skip(', 'test.only', 'TODO']:
    hits=[str(f) for f in files if token in f.read_text()]
    print(f'{token}: {hits or "none"}')
live=Path('web-ui/client/tests/e2e/live-call.spec.ts').read_text()
print('live env gate:', 'RAYME_ENABLE_LIVE_E2E' in live)
print('live skip count:', live.count('test.skip('))
print('live route mock calls:', any('page.route' in line and ('/api/calls' in line or '/webrtc' in line) for line in live.splitlines()))
PY
```

Result: passed; local mocked call specs contain no `.skip(`, `test.only`, or `TODO`; `live-call.spec.ts` contains `RAYME_ENABLE_LIVE_E2E`, exactly one env-gated `test.skip(`, and no call/WebRTC route mocks.

## Known caveats

None.
