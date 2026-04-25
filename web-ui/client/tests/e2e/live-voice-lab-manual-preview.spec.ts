import { expect, test, type Request } from '@playwright/test';

import { expectRayMeApiRequest, installBrowserErrorGuard } from './helpers/acceptance';

const canonicalLiveWebUrl = 'https://192.168.1.199:8443';
const canonicalLiveAiHealthUrl = 'https://192.168.1.199:9443/health';

const liveEnabled = process.env.RAYME_ENABLE_LIVE_E2E === '1';
const liveWebUrl = process.env.RAYME_LIVE_WEB_URL;
const liveAiHealthUrl = process.env.RAYME_LIVE_AI_HEALTH_URL;

test.skip(
  !liveEnabled || !liveWebUrl || !liveAiHealthUrl,
  'Set RAYME_ENABLE_LIVE_E2E=1, RAYME_LIVE_WEB_URL, and RAYME_LIVE_AI_HEALTH_URL to run live Voice Lab preview acceptance.'
);

test.use({ ignoreHTTPSErrors: true, viewport: { width: 390, height: 844 } });

test('live OMEN-PC Voice Lab manual transcript preview returns playable audio before handoff', async ({
  page
}) => {
  test.setTimeout(420_000);
  expect(liveWebUrl).toBe(canonicalLiveWebUrl);
  expect(liveAiHealthUrl).toBe(canonicalLiveAiHealthUrl);

  const assertNoBrowserErrors = installBrowserErrorGuard(page, {
    allowConsoleErrors: [/Failed to load resource: the server responded with a status of 500 \(Internal Server Error\)/]
  });
  const voiceRequests: string[] = [];

  page.on('request', (request) => {
    expectRayMeApiRequest(request);
    recordVoiceRequest(request, voiceRequests);
  });

  const healthResponse = await page.goto(canonicalLiveAiHealthUrl);
  expect(healthResponse?.ok(), `AI backend health at ${canonicalLiveAiHealthUrl}`).toBe(true);

  await page.goto(`${canonicalLiveWebUrl}/voice-lab`);
  await expect(page.getByRole('heading', { name: 'Voice Lab', exact: true })).toBeVisible({
    timeout: 60_000
  });

  await page.getByLabel('Upload Sample').setInputFiles({
    name: 'Android Probe Sample.wav',
    mimeType: 'audio/wav',
    buffer: makeToneWav()
  });
  await expect(page.getByLabel('Voice name')).toHaveValue('Android Probe Sample');

  await page.getByRole('button', { name: 'Transcribe Sample' }).click();
  const transcript = page.getByLabel('Reference transcript');
  await expect(transcript).toBeEnabled({ timeout: 120_000 });
  await transcript.fill('Manual Android probe transcript.');

  await expect(page.getByRole('button', { name: 'Preview Voice' })).toBeEnabled();
  const previewResponsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/voices/preview') &&
      response.request().method() === 'POST',
    { timeout: 300_000 }
  );
  await page.getByRole('button', { name: 'Preview Voice' }).click();
  const previewResponse = await previewResponsePromise;
  expect(previewResponse.ok(), 'Voice preview should return generated audio').toBe(true);
  const previewBody = await previewResponse.json();
  expect(Boolean(previewBody.audio_url || previewBody.audio_base64), 'preview audio payload').toBe(true);
  expect(previewBody.content_type, 'preview content type').toMatch(/^audio\//);

  await expect(page.getByText('Preview ready.')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('button', { name: 'Play preview audio' })).toBeEnabled();

  expect(voiceRequests).toEqual(
    expect.arrayContaining([
      'POST /api/voices/assets',
      expect.stringMatching(/^POST \/api\/voices\/assets\/.+\/transcribe$/),
      'POST /api/voices/preview'
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

function makeToneWav() {
  const sampleRate = 16_000;
  const durationSeconds = 6;
  const samples = sampleRate * durationSeconds;
  const dataBytes = samples * 2;
  const buffer = Buffer.alloc(44 + dataBytes);

  buffer.write('RIFF', 0);
  buffer.writeUInt32LE(36 + dataBytes, 4);
  buffer.write('WAVE', 8);
  buffer.write('fmt ', 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write('data', 36);
  buffer.writeUInt32LE(dataBytes, 40);

  for (let i = 0; i < samples; i += 1) {
    const sample = Math.round(Math.sin((2 * Math.PI * 220 * i) / sampleRate) * 12000);
    buffer.writeInt16LE(sample, 44 + i * 2);
  }

  return buffer;
}
