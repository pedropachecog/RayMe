import { defineConfig, devices } from '@playwright/test';

const liveEnabled = process.env.RAYME_ENABLE_LIVE_E2E === '1';

export default defineConfig({
  testDir: './tests/e2e',
  testIgnore: liveEnabled ? [] : ['**/live-voice-lab*.spec.ts'],
  fullyParallel: true,
  // The live acceptance suite drives one canonical GPU runtime. Running the
  // desktop and mobile projects concurrently makes their reconnect probes
  // contend for that single call engine and invalidates the evidence.
  workers: liveEnabled ? 1 : undefined,
  // Deployed acceptance navigates the canonical OMEN URL directly. Starting
  // an unrelated local preview can block the real call for two minutes before
  // Playwright ever reaches the target runtime.
  webServer: liveEnabled
    ? undefined
    : {
        command: 'npm run build && npm run preview -- --host 127.0.0.1 --port 4173',
        url: 'http://127.0.0.1:4173',
        reuseExistingServer: !process.env.CI,
        timeout: 120_000
      },
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'on-first-retry'
  },
  projects: [
    {
      name: 'desktop-chromium',
      use: { ...devices['Desktop Chrome'] }
    },
    {
      name: 'mobile-chromium',
      use: { ...devices['Pixel 5'] }
    }
  ]
});
