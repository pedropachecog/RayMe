import { readFile } from 'node:fs/promises';

import { expect, test, type Route } from '@playwright/test';

import { installBrowserErrorGuard } from './helpers/acceptance';

const deleteConfirmation =
  'Delete this character? Existing chats stay in history, but the character leaves the gallery.';

const homeCharacter = {
  id: 'home-character',
  name: 'Home Aster',
  description: 'Chosen from the Home modal.',
  first_mes: 'Home default greeting.',
  alternate_greetings: ['Home alternate zero.', 'Home alternate selected.'],
  tags: ['home'],
  deleted_at: null,
  updated_at: null,
  portrait_url: null
};

const galleryCharacter = {
  id: 'gallery-character',
  name: 'Gallery Nova',
  description: '<img src=x onerror=alert(1)> Sanitized gallery card.',
  first_mes: 'Gallery default greeting.',
  alternate_greetings: ['Gallery alternate zero.', 'Gallery alternate selected.'],
  tags: ['gallery', 'export', 'delete'],
  deleted_at: null,
  updated_at: null,
  portrait_url: null
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

function threadDetail(threadId: string, character: typeof homeCharacter) {
  return {
    id: threadId,
    character_id: character.id,
    title: character.name,
    character_name: character.name,
    character_portrait_url: null,
    character_snapshot: { name: character.name, first_mes: character.first_mes },
    messages: [
      {
        id: `${threadId}-opening`,
        thread_id: threadId,
        message_kind: 'ai_text',
        role: 'assistant',
        sequence: 0,
        content_text: character.alternate_greetings[1],
        selected_alternate_id: `${threadId}-opening-alt`,
        alternates: [
          {
            id: `${threadId}-opening-alt`,
            message_id: `${threadId}-opening`,
            alternate_index: 1,
            content_text: character.alternate_greetings[1],
            source_action: 'first_mes',
            created_at: null
          }
        ],
        stale_after_edit: false,
        created_at: null,
        updated_at: null
      }
    ],
    last_message_at: null,
    created_at: null,
    updated_at: null
  };
}

test('home and gallery start chat use POST /api/threads and returned thread IDs', async ({
  page
}) => {
  const expectNoBrowserErrors = installBrowserErrorGuard(page);
  const createRequests: unknown[] = [];
  let galleryDeleted = false;
  let exportCalled = false;

  await page.route('**/api/threads', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, { items: [] });
      return;
    }

    expect(route.request().method()).toBe('POST');
    const payload = route.request().postDataJSON();
    createRequests.push(payload);
    if ((payload as { character_id: string }).character_id === homeCharacter.id) {
      expect(payload).toEqual({ character_id: homeCharacter.id, alternate_greeting_index: 1 });
      await fulfillJson(route, { thread_id: 'home-thread' }, 201);
      return;
    }

    expect(payload).toEqual({ character_id: galleryCharacter.id, alternate_greeting_index: 1 });
    await fulfillJson(route, { thread_id: 'gallery-thread' }, 201);
  });

  await page.route('**/api/characters', async (route) => {
    expect(route.request().method()).toBe('GET');
    await fulfillJson(route, { items: galleryDeleted ? [homeCharacter] : [homeCharacter, galleryCharacter] });
  });

  await page.route('**/api/threads/home-thread', async (route) => {
    await fulfillJson(route, threadDetail('home-thread', homeCharacter));
  });
  await page.route('**/api/threads/gallery-thread', async (route) => {
    await fulfillJson(route, threadDetail('gallery-thread', galleryCharacter));
  });

  await page.route('**/api/characters/gallery-character/export-v2', async (route) => {
    expect(route.request().method()).toBe('GET');
    exportCalled = true;
    await fulfillJson(route, {
      spec: 'chara_card_v2',
      spec_version: '2.0',
      data: {
        name: galleryCharacter.name,
        description: galleryCharacter.description,
        alternate_greetings: galleryCharacter.alternate_greetings
      }
    });
  });

  await page.route('**/api/characters/gallery-character', async (route) => {
    expect(route.request().method()).toBe('DELETE');
    galleryDeleted = true;
    await fulfillJson(route, {
      character_id: galleryCharacter.id,
      deleted_at: '2026-04-24T00:00:00Z',
      preserved_thread_ids: ['gallery-thread'],
      strategy: 'soft_delete'
    });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Start Chat' }).first().click();
  const homeDialog = page.getByRole('dialog', { name: 'Choose a character' });
  await homeDialog.getByRole('button', { name: /Home Aster/ }).click();
  await homeDialog.getByLabel('Home alternate selected.').check();
  await homeDialog.getByTestId('create-thread-submit').click();

  await expect(page).toHaveURL(/\/chat\/home-thread$/);
  await expect(page.getByText('Home alternate selected.')).toBeVisible();

  await page.goto('/gallery');
  const card = page.getByTestId('character-card-gallery-character');
  await expect(card.getByText('Gallery Nova')).toBeVisible();
  await card.getByRole('button', { name: 'Start Chat' }).click();
  const galleryDialog = page.getByRole('dialog', { name: 'Gallery Nova' });
  await galleryDialog.getByLabel('Gallery alternate selected.').check();
  await galleryDialog.getByRole('button', { name: 'Start Chat' }).click();

  await expect(page).toHaveURL(/\/chat\/gallery-thread$/);
  await expect(page.getByText('Gallery alternate selected.')).toBeVisible();
  expect(createRequests).toHaveLength(2);

  await page.goto('/gallery');
  const downloadPromise = page.waitForEvent('download');
  await page.getByTestId('character-card-gallery-character').getByRole('button', { name: 'Export JSON' }).click();
  const download = await downloadPromise;
  const downloadPath = await download.path();
  expect(downloadPath).not.toBeNull();
  const exported = JSON.parse(await readFile(downloadPath as string, 'utf-8'));
  expect(exportCalled).toBe(true);
  expect(exported).toMatchObject({
    spec: 'chara_card_v2',
    spec_version: expect.stringMatching(/^2\./),
    data: { name: 'Gallery Nova' }
  });

  await page.getByTestId('character-card-gallery-character').getByRole('button', { name: 'Delete' }).click();
  const deleteDialog = page.getByRole('dialog', { name: 'Delete character' });
  await expect(deleteDialog.getByText(deleteConfirmation, { exact: true })).toBeVisible();
  await deleteDialog.getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByTestId('character-card-gallery-character')).toHaveCount(0);
  await expectNoBrowserErrors();
});
