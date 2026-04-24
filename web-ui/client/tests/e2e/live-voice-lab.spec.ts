import { expect, test, type Request } from '@playwright/test';

import { expectRayMeApiRequest, installBrowserErrorGuard } from './helpers/acceptance';

const canonicalLiveWebUrl = 'https://192.168.1.199:8443';
const canonicalLiveAiHealthUrl = 'https://192.168.1.199:9443/health';

const liveEnabled = process.env.RAYME_ENABLE_LIVE_E2E === '1';
const liveWebUrl = process.env.RAYME_LIVE_WEB_URL;
const liveAiHealthUrl = process.env.RAYME_LIVE_AI_HEALTH_URL;

test.skip(
  !liveEnabled || !liveWebUrl || !liveAiHealthUrl,
  'Set RAYME_ENABLE_LIVE_E2E=1, RAYME_LIVE_WEB_URL, and RAYME_LIVE_AI_HEALTH_URL to run live Voice Lab acceptance.'
);

test.use({ ignoreHTTPSErrors: true });

test('live OMEN-PC Voice Lab upload transcribe save and test-play path passes before Android handoff', async ({
  page
}) => {
  test.setTimeout(300_000);
  expect(liveWebUrl).toBe(canonicalLiveWebUrl);
  expect(liveAiHealthUrl).toBe(canonicalLiveAiHealthUrl);

  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  const voiceRequests: string[] = [];

  page.on('request', (request) => {
    expectRayMeApiRequest(request);
    recordVoiceRequest(request, voiceRequests);
  });

  const healthResponse = await page.goto(canonicalLiveAiHealthUrl);
  expect(healthResponse?.ok(), `AI backend health at ${canonicalLiveAiHealthUrl}`).toBe(true);
  await expect(page.locator('body')).toContainText(/ok|healthy|status/i);

  await page.goto(`${canonicalLiveWebUrl}/voice-lab`);
  await expect(page.getByRole('heading', { name: 'Voice Lab' })).toBeVisible({ timeout: 60_000 });

  await page.getByLabel('Upload Sample').setInputFiles({
    name: 'sample.wav',
    mimeType: 'audio/wav',
    buffer: makeTinyWav()
  });
  await page.getByRole('button', { name: 'Transcribe Sample' }).click();
  await expect(page.getByLabel('Reference transcript')).not.toHaveValue('', { timeout: 120_000 });

  const liveVoiceName = `Live Voice Lab ${Date.now()}`;
  await page.getByLabel('Voice name').fill(liveVoiceName);
  await page.getByLabel('Preview text').fill('Short live Voice Lab acceptance phrase.');
  await page.getByRole('button', { name: 'Save Voice' }).click();
  await expect(page.getByRole('row', { name: new RegExp(escapeRegExp(liveVoiceName)) })).toBeVisible({
    timeout: 120_000
  });

  const voiceRow = page.getByRole('row', { name: new RegExp(escapeRegExp(liveVoiceName)) });
  await voiceRow.getByLabel('Test voice text').fill('One short live test phrase.');
  await voiceRow.getByRole('button', { name: 'Test Voice' }).click();
  await expect(voiceRow).toContainText(/ready|playing|complete/i, { timeout: 180_000 });

  expect(voiceRequests).toEqual(
    expect.arrayContaining([
      'POST /api/voices/assets',
      expect.stringMatching(/^POST \/api\/voices\/assets\/.+\/transcribe$/),
      'POST /api/voices',
      expect.stringMatching(/^POST \/api\/voices\/.+\/test-play$/)
    ])
  );
  assertNoBrowserErrors();
});

function recordVoiceRequest(request: Request, events: string[]) {
  const url = new URL(request.url());
  if (!url.pathname.startsWith('/api/voices')) {
    return;
  }

  events.push(`${request.method()} ${url.pathname}${url.search}`);
}

function makeTinyWav() {
  return Buffer.from([
    0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00, 0x57, 0x41, 0x56, 0x45,
    0x66, 0x6d, 0x74, 0x20, 0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
    0x40, 0x1f, 0x00, 0x00, 0x80, 0x3e, 0x00, 0x00, 0x02, 0x00, 0x10, 0x00,
    0x64, 0x61, 0x74, 0x61, 0x00, 0x00, 0x00, 0x00
  ]);
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
