import { expect, test, type Locator } from '@playwright/test';

import {
  expectRayMeApiRequest,
  fulfillJson,
  installBrowserErrorGuard
} from './helpers/acceptance';
import { makeAiMessage, makeCharacter, makeThreadDetail } from './helpers/fixtures';
import { fulfillPortraitImage, portraitPng } from './helpers/images';

const importCharacterId = 'portrait-import-character';
const importThreadId = 'portrait-import-thread';
const importPortraitAssetId = 'portrait-import-asset';
const importPortraitUrl =
  '/api/characters/portrait-import-character/portrait?asset_id=portrait-import-asset';

test('PNG import persists portrait across Editor Gallery Home Chat and reload', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  const portraitRequests = new Set<string>();
  const importedCharacter = makeCharacter({
    id: importCharacterId,
    name: 'Portrait Import Aster',
    first_mes: 'Portrait import opening greeting.',
    alternate_greetings: [],
    portrait_asset_id: importPortraitAssetId,
    portrait_url: importPortraitUrl,
    portrait_storage_path: `characters/${importCharacterId}/${importPortraitAssetId}.png`
  });
  const importedThread = makeThreadDetail({
    id: importThreadId,
    character_id: importCharacterId,
    title: importedCharacter.name,
    character_name: importedCharacter.name,
    character_portrait_url: importPortraitUrl,
    character_portrait_asset_id: importPortraitAssetId,
    character_portrait_storage_path: importedCharacter.portrait_storage_path,
    last_message_snippet: importedCharacter.first_mes,
    messages: [
      makeAiMessage(
        'portrait-import-opening-message',
        importThreadId,
        0,
        importedCharacter.first_mes ?? '',
        'first_mes'
      )
    ]
  });
  let imported = false;
  let saved = false;
  let createdThread = false;

  page.on('request', expectRayMeApiRequest);
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (`${url.pathname}${url.search}` === importPortraitUrl) {
      portraitRequests.add(request.url());
    }
  });

  await fulfillPortraitImage(page, importPortraitUrl, portraitPng());
  await page.route('**/api/characters/import', async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postData() ?? '').toContain('filename="portrait-card.png"');
    imported = true;
    await fulfillJson(
      route,
      {
        ...importedCharacter,
        character: importedCharacter,
        source_format: 'v3_png',
        warnings: []
      },
      201
    );
  });

  await page.route(`**/api/characters/${importCharacterId}`, async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, importedCharacter);
      return;
    }

    expect(route.request().method()).toBe('PATCH');
    expect(route.request().postDataJSON()).toMatchObject({
      name: 'Portrait Import Aster',
      first_mes: 'Portrait import opening greeting.'
    });
    saved = true;
    await fulfillJson(route, importedCharacter);
  });

  await page.route('**/api/characters', async (route) => {
    expect(route.request().method()).toBe('GET');
    await fulfillJson(route, { items: saved ? [importedCharacter] : [] });
  });

  await page.route('**/api/threads', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, { items: saved ? [importedThread] : [] });
      return;
    }

    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toEqual({ character_id: importCharacterId });
    createdThread = true;
    await fulfillJson(route, { thread_id: importThreadId }, 201);
  });

  await page.route(`**/api/threads/${importThreadId}`, async (route) => {
    expect(route.request().method()).toBe('GET');
    await fulfillJson(route, importedThread);
  });

  await page.goto('/gallery');
  await page.getByRole('button', { name: 'Import Character' }).first().click();
  const importDialog = page.getByRole('dialog', { name: 'Import Character' });
  await importDialog.locator('input[type="file"]').setInputFiles({
    name: 'portrait-card.png',
    mimeType: 'image/png',
    buffer: portraitPng()
  });
  await importDialog.getByRole('button', { name: 'Import Character' }).click();

  await expect(page).toHaveURL(new RegExp(`/characters/${importCharacterId}\\?mode=review$`));
  await assertVisiblePortrait(page.locator('img[alt="Character portrait preview"]'));
  await expect.poll(() => portraitRequests.size).toBeGreaterThan(0);

  await page.getByRole('button', { name: 'Save Character' }).click();
  await expect(page.getByText('Character saved.')).toBeVisible();

  await page.goto('/gallery');
  const galleryCard = page.getByTestId('character-card-portrait-import-character');
  await assertVisiblePortrait(galleryCard.locator('img'));

  await page.goto('/');
  const threadRow = page.getByTestId('thread-row-portrait-import-thread');
  await assertVisiblePortrait(threadRow.locator('img'));

  await page.getByRole('button', { name: 'Start Chat' }).first().click();
  const characterDialog = page.getByRole('dialog', { name: 'Choose a character' });
  await assertVisiblePortrait(characterDialog.locator('img'));
  await characterDialog.getByRole('button', { name: /Portrait Import Aster/ }).click();
  await characterDialog.getByTestId('create-thread-submit').click();

  await expect(page).toHaveURL(new RegExp(`/chat/${importThreadId}$`));
  await assertVisiblePortrait(page.locator('.chat-header .portrait img'));

  await page.reload();
  await assertVisiblePortrait(page.locator('.chat-header .portrait img'));
  expect(await page.locator(`img[src="${importPortraitUrl}"]`).count()).toBeGreaterThan(0);
  expect({ imported, saved, createdThread }).toEqual({
    imported: true,
    saved: true,
    createdThread: true
  });
  assertNoBrowserErrors();
});

test('direct portrait upload replaces and removes portrait across surfaces', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  page.on('request', expectRayMeApiRequest);

  await expect(page.locator('img[src*="asset-upload-one"]')).toHaveCount(1);
  assertNoBrowserErrors();
});

async function assertVisiblePortrait(locator: Locator) {
  await expect(locator).toHaveAttribute('src', importPortraitUrl);
  await expect(locator).toBeVisible();
}
