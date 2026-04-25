import { expect, test, type Page, type Route } from '@playwright/test';

import { fulfillJson, installBrowserErrorGuard } from './helpers/acceptance';
import { makeCharacter, makeThreadDetail } from './helpers/fixtures';

const characterId = 'call-start-character';
const threadId = 'call-start-thread';

test('starts a call from the thread header Start call control', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installCallStartRoutes(page);

  await page.goto(`/chat/${threadId}`);

  await expect(page.getByRole('heading', { name: 'Call Start Aster' })).toBeVisible();
  await page.getByRole('button', { name: 'Start call' }).click();

  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Mute' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'End Call' })).toBeVisible();
  assertNoBrowserErrors();
});

test('starts a call from a character card Start Call control', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installCallStartRoutes(page);

  await page.goto('/gallery');

  const card = page.getByTestId(`character-card-${characterId}`);
  await expect(card).toBeVisible();
  await card.getByRole('button', { name: 'Start Call' }).click();

  await expect(page).toHaveURL(new RegExp(`/call/${threadId}`));
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  assertNoBrowserErrors();
});

async function installCallStartRoutes(page: Page) {
  const character = makeCharacter({
    id: characterId,
    name: 'Call Start Aster',
    default_voice_state: 'assigned',
    default_voice_label: 'Assigned voice',
    default_voice: {
      id: 'voice-call-start',
      name: 'Call Start Voice',
      default_engine: 'f5',
      reference_transcript: 'Reference text.',
      sample_asset_id: 'asset-call-start',
      preview_audio_url: null,
      metadata: {},
      deleted_at: null,
      created_at: null,
      updated_at: null
    }
  });
  const thread = makeThreadDetail({
    id: threadId,
    character_id: characterId,
    title: 'Call Start Aster',
    character_name: 'Call Start Aster',
    messages: []
  });

  await page.route('**/api/characters', async (route) => {
    await fulfillJson(route, { items: [character] });
  });
  await page.route('**/api/threads', async (route) => {
    if (route.request().method() === 'POST') {
      await fulfillJson(route, { thread_id: threadId }, 201);
      return;
    }
    await fulfillJson(route, { items: [] });
  });
  await page.route(`**/api/threads/${threadId}`, async (route) => {
    await fulfillJson(route, thread);
  });
  await page.route('**/api/characters/*/portrait**', async (route) => {
    await route.fulfill({ status: 204 });
  });
  await page.route('**/api/calls/start', async (route: Route) => {
    expect(route.request().method()).toBe('POST');
    await fulfillJson(route, {
      call_id: 'call-start-01',
      session_id: 'rtc-call-start-01',
      thread_id: threadId,
      state: 'listening'
    }, 201);
  });
  await page.route('**/webrtc/offer', async (route) => {
    await fulfillJson(route, { type: 'answer', sdp: 'v=0\r\n' });
  });
}
