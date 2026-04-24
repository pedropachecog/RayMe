import { expect, test, type Locator, type Page } from '@playwright/test';

import {
  expectRayMeApiRequest,
  fulfillJson,
  installBrowserErrorGuard
} from './helpers/acceptance';
import { makeAiMessage, makeCharacter, makeThreadDetail } from './helpers/fixtures';
import { alternatePortraitPng, fulfillPortraitImage, portraitPng } from './helpers/images';

const importCharacterId = 'portrait-import-character';
const importThreadId = 'portrait-import-thread';
const importPortraitAssetId = 'portrait-import-asset';
const importPortraitUrl =
  '/api/characters/portrait-import-character/portrait?asset_id=portrait-import-asset';
const uploadCharacterId = 'portrait-upload-character';
const uploadThreadId = 'portrait-upload-thread';
const uploadFirstPortraitUrl =
  '/api/characters/portrait-upload-character/portrait?asset_id=asset-upload-one';
const uploadSecondPortraitUrl =
  '/api/characters/portrait-upload-character/portrait?asset_id=asset-upload-two';
const uploadFallbackInitials = 'PU';

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
  const portraitRequests = new Set<string>();
  let currentPortraitUrl: string | null = null;
  let currentPortraitAssetId: string | null = null;
  let uploadCount = 0;
  let saved = false;
  let removed = false;

  const uploadCharacter = () =>
    makeCharacter({
      id: uploadCharacterId,
      name: 'Portrait Upload',
      first_mes: 'Portrait upload opening greeting.',
      alternate_greetings: [],
      portrait_url: currentPortraitUrl,
      portrait_asset_id: currentPortraitAssetId,
      portrait_storage_path: currentPortraitAssetId
        ? `characters/${uploadCharacterId}/${currentPortraitAssetId}.png`
        : null,
      portrait_mime_type: currentPortraitAssetId ? 'image/png' : null,
      portrait_size_bytes: currentPortraitAssetId ? 68 : null
    });
  const uploadThread = () =>
    makeThreadDetail({
      id: uploadThreadId,
      character_id: uploadCharacterId,
      title: 'Portrait Upload',
      character_name: 'Portrait Upload',
      character_portrait_url: currentPortraitUrl,
      character_portrait_asset_id: currentPortraitAssetId,
      character_portrait_storage_path: currentPortraitAssetId
        ? `characters/${uploadCharacterId}/${currentPortraitAssetId}.png`
        : null,
      last_message_snippet: 'Portrait upload opening greeting.',
      messages: [
        makeAiMessage(
          'portrait-upload-opening-message',
          uploadThreadId,
          0,
          'Portrait upload opening greeting.',
          'first_mes'
        )
      ]
    });

  page.on('request', expectRayMeApiRequest);
  page.on('request', (request) => {
    const url = new URL(request.url());
    const pathAndSearch = `${url.pathname}${url.search}`;
    if (pathAndSearch === uploadFirstPortraitUrl || pathAndSearch === uploadSecondPortraitUrl) {
      portraitRequests.add(pathAndSearch);
    }
  });

  await fulfillPortraitImage(page, uploadFirstPortraitUrl, portraitPng());
  await fulfillPortraitImage(page, uploadSecondPortraitUrl, alternatePortraitPng());

  await page.route(`**/api/characters/${uploadCharacterId}`, async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, uploadCharacter());
      return;
    }

    expect(route.request().method()).toBe('PATCH');
    expect(route.request().postDataJSON()).toMatchObject({
      name: 'Portrait Upload',
      first_mes: 'Portrait upload opening greeting.'
    });
    saved = true;
    await fulfillJson(route, uploadCharacter());
  });

  await page.route(new RegExp(`/api/characters/${uploadCharacterId}/portrait$`), async (route) => {
    if (route.request().method() === 'PUT') {
      uploadCount += 1;
      const expectedFilename = uploadCount === 1 ? 'first-upload.png' : 'second-upload.png';
      expect(route.request().postData() ?? '').toContain(`filename="${expectedFilename}"`);
      currentPortraitAssetId = uploadCount === 1 ? 'asset-upload-one' : 'asset-upload-two';
      currentPortraitUrl = uploadCount === 1 ? uploadFirstPortraitUrl : uploadSecondPortraitUrl;
      await fulfillJson(route, uploadCharacter());
      return;
    }

    expect(route.request().method()).toBe('DELETE');
    currentPortraitAssetId = null;
    currentPortraitUrl = null;
    removed = true;
    await fulfillJson(route, uploadCharacter());
  });

  await page.route('**/api/characters', async (route) => {
    expect(route.request().method()).toBe('GET');
    await fulfillJson(route, { items: [uploadCharacter()] });
  });

  await page.route('**/api/threads', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, { items: [uploadThread()] });
      return;
    }

    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toEqual({ character_id: uploadCharacterId });
    await fulfillJson(route, { thread_id: uploadThreadId }, 201);
  });

  await page.route(`**/api/threads/${uploadThreadId}`, async (route) => {
    expect(route.request().method()).toBe('GET');
    await fulfillJson(route, uploadThread());
  });

  await page.goto(`/characters/${uploadCharacterId}`);
  await expect(page.getByLabel('Upload character portrait')).toBeVisible();
  await expect(page.locator('.portrait-control').getByText(uploadFallbackInitials, { exact: true })).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: 'first-upload.png',
    mimeType: 'image/png',
    buffer: portraitPng()
  });
  await assertVisiblePortrait(
    page.locator('img[alt="Character portrait preview"]'),
    uploadFirstPortraitUrl
  );
  await expect.poll(() => portraitRequests.has(uploadFirstPortraitUrl)).toBe(true);

  await page.getByRole('button', { name: 'Save Character' }).click();
  await expect(page.getByText('Character saved.')).toBeVisible();
  await page.reload();
  await assertVisiblePortrait(
    page.locator('img[alt="Character portrait preview"]'),
    uploadFirstPortraitUrl
  );
  await assertPortraitAcrossSurfaces(page, uploadFirstPortraitUrl);

  await page.goto(`/characters/${uploadCharacterId}`);
  await page.locator('input[type="file"]').setInputFiles({
    name: 'second-upload.png',
    mimeType: 'image/png',
    buffer: alternatePortraitPng()
  });
  await assertVisiblePortrait(
    page.locator('img[alt="Character portrait preview"]'),
    uploadSecondPortraitUrl
  );
  await expect(page.locator('img[src*="asset-upload-one"]')).toHaveCount(0);
  await expect.poll(() => portraitRequests.has(uploadSecondPortraitUrl)).toBe(true);
  await assertPortraitAcrossSurfaces(page, uploadSecondPortraitUrl, [uploadFirstPortraitUrl]);

  await page.goto(`/characters/${uploadCharacterId}`);
  await page.getByRole('button', { name: 'Remove portrait' }).click();
  await expect(page.locator('img[alt="Character portrait preview"]')).toHaveCount(0);
  await expect(page.locator('.portrait-control').getByText(uploadFallbackInitials, { exact: true })).toBeVisible();
  await expect(page.locator('img[src*="asset-upload-one"]')).toHaveCount(0);
  await expect(page.locator('img[src*="asset-upload-two"]')).toHaveCount(0);
  await assertStalePortraitsAbsent(page, [uploadFirstPortraitUrl, uploadSecondPortraitUrl]);
  await assertFallbackAcrossSurfaces(page, [uploadFirstPortraitUrl, uploadSecondPortraitUrl]);

  expect({ uploadCount, saved, removed }).toEqual({
    uploadCount: 2,
    saved: true,
    removed: true
  });
  assertNoBrowserErrors();
});

async function assertVisiblePortrait(locator: Locator, portraitUrl = importPortraitUrl) {
  await expect(locator).toHaveAttribute('src', portraitUrl);
  await expect(locator).toBeVisible();
}

async function assertPortraitAcrossSurfaces(
  page: Page,
  portraitUrl: string,
  stalePortraitUrls: string[] = []
) {
  await page.goto('/gallery');
  await assertVisiblePortrait(
    page.getByTestId('character-card-portrait-upload-character').locator('img'),
    portraitUrl
  );
  await assertStalePortraitsAbsent(page, stalePortraitUrls);

  await page.goto('/');
  await assertVisiblePortrait(
    page.getByTestId('thread-row-portrait-upload-thread').locator('img'),
    portraitUrl
  );
  await page.getByRole('button', { name: 'Start Chat' }).first().click();
  const characterDialog = page.getByRole('dialog', { name: 'Choose a character' });
  await assertVisiblePortrait(characterDialog.locator('img'), portraitUrl);
  await characterDialog.getByRole('button', { name: /Portrait Upload/ }).click();
  await characterDialog.getByTestId('create-thread-submit').click();

  await expect(page).toHaveURL(new RegExp(`/chat/${uploadThreadId}$`));
  await assertVisiblePortrait(page.locator('.chat-header .portrait img'), portraitUrl);
  await assertStalePortraitsAbsent(page, stalePortraitUrls);
}

async function assertFallbackAcrossSurfaces(page: Page, stalePortraitUrls: string[]) {
  await page.goto('/gallery');
  const galleryCard = page.getByTestId('character-card-portrait-upload-character');
  await expect(galleryCard.locator('img')).toHaveCount(0);
  await expect(galleryCard.getByText(uploadFallbackInitials, { exact: true })).toBeVisible();
  await assertStalePortraitsAbsent(page, stalePortraitUrls);

  await page.goto('/');
  const threadRow = page.getByTestId('thread-row-portrait-upload-thread');
  await expect(threadRow.locator('img')).toHaveCount(0);
  await expect(threadRow.getByText(uploadFallbackInitials, { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Start Chat' }).first().click();
  const characterDialog = page.getByRole('dialog', { name: 'Choose a character' });
  await expect(characterDialog.locator('img')).toHaveCount(0);
  await expect(characterDialog.getByText(uploadFallbackInitials, { exact: true })).toBeVisible();
  await characterDialog.getByRole('button', { name: /Portrait Upload/ }).click();
  await characterDialog.getByTestId('create-thread-submit').click();

  await expect(page).toHaveURL(new RegExp(`/chat/${uploadThreadId}$`));
  await expect(page.locator('.chat-header .portrait img')).toHaveCount(0);
  await expect(page.locator('.chat-header .portrait').getByText(uploadFallbackInitials, { exact: true })).toBeVisible();
  await assertStalePortraitsAbsent(page, stalePortraitUrls);
}

async function assertStalePortraitsAbsent(page: Page, stalePortraitUrls: string[]) {
  for (const portraitUrl of stalePortraitUrls) {
    const assetId = new URL(`http://127.0.0.1${portraitUrl}`).searchParams.get('asset_id');
    await expect(page.locator(`img[src*="${assetId}"]`)).toHaveCount(0);
  }
}
