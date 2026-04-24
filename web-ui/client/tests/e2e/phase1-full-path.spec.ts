import { readFile } from 'node:fs/promises';

import { expect, test, type Page, type Route } from '@playwright/test';

import { fulfillJson, fulfillSse, installBrowserErrorGuard } from './helpers/acceptance';

type AlternateSourceAction = 'first_mes' | 'regenerate' | 'swipe' | 'continue';

type ThreadMessage = {
  id: string;
  thread_id: string;
  message_kind: 'user_text' | 'ai_text';
  role: 'user' | 'assistant';
  sequence: number;
  content_text: string;
  selected_alternate_id: string | null;
  alternates: {
    id: string;
    message_id: string;
    alternate_index: number;
    content_text: string;
    source_action: AlternateSourceAction;
    created_at: string | null;
  }[];
  stale_after_edit: boolean;
  created_at: string | null;
  updated_at: string | null;
};

const maliciousDescription = '<img src=x onerror=alert(1)> Phase 1 safe text.';
const characterId = 'phase1-full-character';
const deleteCharacterId = 'phase1-delete-character';
const threadId = 'phase1-full-thread';
const renameDeleteThreadId = 'phase1-thread-rename-delete';
const exportV2Path = '/api/characters/phase1-full-character/export-v2';
const renameDeleteInitialTitle = 'Phase 01.1 thread to rename';
const renamedThreadTitle = 'Renamed Phase 01.1 thread';
const deleteThreadConfirmation = 'Delete this thread? This removes the conversation history.';

const fullCharacter = {
  id: characterId,
  name: 'Phase 1 Full Path',
  description: maliciousDescription,
  personality: 'End-to-end acceptance focused.',
  scenario: 'A full browser relay room.',
  first_mes: 'Default full path greeting.',
  mes_example: '<START>\n{{char}}: The browser path stays deterministic.',
  system_prompt: 'Stay concise and deterministic.',
  creator_notes: 'Full path creator notes.',
  character_notes: 'Full path character notes.',
  tags: ['phase-01.1', 'full-path'],
  alternate_greetings: ['Phase one alternate zero.', 'Phase one selected opening.'],
  post_history_instructions: 'Preserve selected alternates.',
  creator: 'RayMe',
  character_version: '1.0',
  raw_source_json: {
    spec: 'chara_card_v3',
    spec_version: '3.0',
    data: {
      name: 'Phase 1 Full Path',
      description: maliciousDescription,
      first_mes: 'Default full path greeting.'
    }
  },
  lorebook_status: 'present_not_used_in_v1',
  lorebook_json: { entries: [{ keys: ['phase'], content: 'Stored only for later versions.' }] },
  source_format: 'v3_json',
  warnings: ['Lorebook present - not used in v1'],
  deleted_at: null,
  updated_at: null,
  portrait_url: null,
  portrait_asset_id: null,
  portrait_storage_path: null
};

const deleteCandidate = {
  id: deleteCharacterId,
  name: 'Phase 1 Delete Candidate',
  description: 'Temporary Gallery delete coverage.',
  first_mes: 'Delete candidate opening.',
  alternate_greetings: [],
  tags: ['delete'],
  deleted_at: null,
  updated_at: null,
  portrait_url: null
};

function aiMessage(
  id: string,
  sequence: number,
  content: string,
  sourceAction: AlternateSourceAction,
  alternateIndex = 0,
  alternateId = `alt-${id}-${sourceAction}`
): ThreadMessage {
  return {
    id,
    thread_id: threadId,
    message_kind: 'ai_text',
    role: 'assistant',
    sequence,
    content_text: content,
    selected_alternate_id: alternateId,
    alternates: [
      {
        id: alternateId,
        message_id: id,
        alternate_index: alternateIndex,
        content_text: content,
        source_action: sourceAction,
        created_at: null
      }
    ],
    stale_after_edit: false,
    created_at: null,
    updated_at: null
  };
}

function userMessage(id: string, sequence: number, content: string): ThreadMessage {
  return {
    id,
    thread_id: threadId,
    message_kind: 'user_text',
    role: 'user',
    sequence,
    content_text: content,
    selected_alternate_id: null,
    alternates: [],
    stale_after_edit: false,
    created_at: null,
    updated_at: null
  };
}

function threadDetail(messages: ThreadMessage[]) {
  return {
    id: threadId,
    character_id: characterId,
    title: 'Phase 1 Full Path',
    character_name: 'Phase 1 Full Path',
    character_portrait_url: null,
    character_snapshot: {
      name: fullCharacter.name,
      first_mes: fullCharacter.first_mes,
      raw_source_json: fullCharacter.raw_source_json,
      lorebook_json: fullCharacter.lorebook_json
    },
    messages,
    last_message_at: null,
    created_at: null,
    updated_at: null
  };
}

function threadSummary(title = renameDeleteInitialTitle) {
  return {
    id: renameDeleteThreadId,
    character_id: characterId,
    title,
    character_name: 'Phase 1 Full Path',
    character_portrait_url: null,
    last_message_snippet: 'Rename and delete this thread.',
    last_message_at: '2026-04-24T00:00:00Z',
    created_at: '2026-04-24T00:00:00Z',
    updated_at: '2026-04-24T00:00:00Z'
  };
}

async function installFullPathRoutes(page: Page) {
  const messages: ThreadMessage[] = [
    aiMessage(
      'phase1-full-opening',
      0,
      'Phase one selected opening.',
      'first_mes',
      1,
      'phase1-full-opening-alt-1'
    ),
    {
      ...userMessage('phase1-stale-downstream', 1, 'Stale branch remains visible.'),
      stale_after_edit: true
    }
  ];
  const calls = {
    imported: false,
    saved: false,
    createdThread: false,
    exported: false,
    deletedCharacter: false,
    renamedThread: false,
    deletedThread: false,
    regenerated: false,
    swiped: false,
    continued: false,
    sends: 0
  };
  let characterSaved = false;
  let deleteCharacterVisible = true;
  let renameThreadDeleted = false;
  let renameThreadTitle = renameDeleteInitialTitle;

  await page.route('**/api/characters/import', async (route) => {
    expect(route.request().method()).toBe('POST');
    calls.imported = true;
    await fulfillJson(
      route,
      {
        ...fullCharacter,
        character: fullCharacter,
        source_format: 'v3_json',
        warnings: ['Lorebook present - not used in v1']
      },
      201
    );
  });

  await page.route(`**${exportV2Path}`, async (route) => {
    expect(route.request().method()).toBe('GET');
    calls.exported = true;
    await fulfillJson(route, {
      spec: 'chara_card_v2',
      spec_version: '2.0',
      data: {
        name: 'Phase 1 Full Path',
        description: maliciousDescription,
        alternate_greetings: fullCharacter.alternate_greetings
      }
    });
  });

  await page.route(`**/api/characters/${characterId}`, async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, fullCharacter);
      return;
    }

    expect(route.request().method()).toBe('PATCH');
    expect(route.request().postDataJSON()).toMatchObject({
      name: 'Phase 1 Full Path',
      description: 'Edited full path description.',
      alternate_greetings: fullCharacter.alternate_greetings
    });
    characterSaved = true;
    calls.saved = true;
    await fulfillJson(route, {
      ...fullCharacter,
      ...route.request().postDataJSON()
    });
  });

  await page.route(`**/api/characters/${deleteCharacterId}`, async (route) => {
    expect(route.request().method()).toBe('DELETE');
    deleteCharacterVisible = false;
    calls.deletedCharacter = true;
    await fulfillJson(route, {
      character_id: deleteCharacterId,
      deleted_at: '2026-04-24T00:00:00Z',
      preserved_thread_ids: [],
      strategy: 'soft_delete'
    });
  });

  await page.route('**/api/characters', async (route) => {
    expect(route.request().method()).toBe('GET');
    await fulfillJson(route, {
      items: [
        ...(characterSaved ? [fullCharacter] : []),
        ...(deleteCharacterVisible ? [deleteCandidate] : [])
      ]
    });
  });

  await page.route('**/api/threads', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, {
        items: renameThreadDeleted ? [] : [threadSummary(renameThreadTitle)]
      });
      return;
    }

    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toEqual({
      character_id: characterId,
      alternate_greeting_index: 1
    });
    calls.createdThread = true;
    await fulfillJson(route, { thread_id: threadId }, 201);
  });

  await page.route(`**/api/threads/${renameDeleteThreadId}`, async (route) => {
    if (route.request().method() === 'PATCH') {
      const payload = route.request().postDataJSON();
      expect(payload).toEqual({ title: renamedThreadTitle });
      renameThreadTitle = renamedThreadTitle;
      calls.renamedThread = true;
      await fulfillJson(route, {
        id: renameDeleteThreadId,
        title: renamedThreadTitle,
        updated_at: '2026-04-24T00:00:01Z'
      });
      return;
    }

    expect(route.request().method()).toBe('DELETE');
    renameThreadDeleted = true;
    calls.deletedThread = true;
    await fulfillJson(route, {
      thread_id: renameDeleteThreadId,
      deleted_at: '2026-04-24T00:00:02Z'
    });
  });

  await page.route(`**/api/threads/${threadId}`, async (route) => {
    expect(route.request().method()).toBe('GET');
    await fulfillJson(route, threadDetail(messages));
  });

  await page.route(`**/api/chat/${threadId}/send`, async (route) => {
    expect(route.request().method()).toBe('POST');
    const { content } = route.request().postDataJSON() as { content: string };
    calls.sends += 1;
    const nextSequence = messages.length;

    if (calls.sends === 1) {
      const user = userMessage('phase1-user-1', nextSequence, content);
      const ai = aiMessage(
        'phase1-ai-1',
        nextSequence + 1,
        'Phase one streamed answer.',
        'regenerate',
        0,
        'phase1-ai-1-streamed'
      );
      messages.push(user, ai);
      await fulfillSse(route, [
        { type: 'token', text: 'Phase ' },
        { type: 'token', text: 'one ' },
        { type: 'done', message: ai }
      ]);
      return;
    }

    const user = userMessage('phase1-user-2', nextSequence, content);
    const ai = aiMessage(
      'phase1-ai-2',
      nextSequence + 1,
      'Phase one reload follow-up.',
      'regenerate',
      0,
      'phase1-ai-2-streamed'
    );
    messages.push(user, ai);
    await fulfillSse(route, [
      { type: 'token', text: 'Phase ' },
      { type: 'token', text: 'one ' },
      { type: 'done', message: ai }
    ]);
  });

  await page.route('**/api/messages/phase1-ai-1/regenerate', async (route) => {
    expect(route.request().method()).toBe('POST');
    const aiIndex = findMessageIndex(messages, 'phase1-ai-1');
    const regenerated = replaceAiMessage(
      messages[aiIndex],
      'Phase one regenerated replacement.',
      'phase1-regenerated-selected',
      'regenerate'
    );
    messages[aiIndex] = regenerated;
    calls.regenerated = true;
    await fulfillJson(route, regenerated);
  });

  await page.route('**/api/messages/phase1-ai-1/swipes', async (route) => {
    expect(route.request().method()).toBe('POST');
    const aiIndex = findMessageIndex(messages, 'phase1-ai-1');
    const swiped = replaceAiMessage(
      messages[aiIndex],
      'Phase one swipe alternate selected.',
      'phase1-swipe-selected',
      'swipe'
    );
    messages[aiIndex] = swiped;
    calls.swiped = true;
    await fulfillJson(route, swiped);
  });

  await page.route('**/api/messages/phase1-ai-1/continue', async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toEqual({ composer_text: 'extend with a clue' });
    const aiIndex = findMessageIndex(messages, 'phase1-ai-1');
    const continued = replaceAiMessage(
      messages[aiIndex],
      'Phase one continue alternate selected.',
      'phase1-continue-selected',
      'continue'
    );
    messages[aiIndex] = continued;
    calls.continued = true;
    await fulfillJson(route, continued);
  });

  return calls;
}

function findMessageIndex(messages: ThreadMessage[], messageId: string) {
  const index = messages.findIndex((message) => message.id === messageId);
  expect(index).toBeGreaterThanOrEqual(0);
  return index;
}

function replaceAiMessage(
  message: ThreadMessage,
  content: string,
  alternateId: string,
  sourceAction: AlternateSourceAction
): ThreadMessage {
  return {
    ...message,
    content_text: content,
    selected_alternate_id: alternateId,
    alternates: [
      ...message.alternates,
      {
        id: alternateId,
        message_id: message.id,
        alternate_index: message.alternates.length,
        content_text: content,
        source_action: sourceAction,
        created_at: null
      }
    ]
  };
}

async function chooseMessageAction(page: Page, messageId: string, label: string) {
  const row = page.locator(`[data-message-id="${messageId}"]`);
  await row.hover();
  await row.getByRole('button', { name: 'Message actions' }).click();
  await page.getByRole('menuitem', { name: label }).click();
}

test('full Phase 1 browser acceptance path survives reload and continues', async ({ page }) => {
  await page.addInitScript(() => {
    (window as Window & { __raymeXssFired?: boolean }).__raymeXssFired = false;
    window.alert = () => {
      (window as Window & { __raymeXssFired?: boolean }).__raymeXssFired = true;
    };
  });
  const expectNoBrowserErrors = installBrowserErrorGuard(page);
  const calls = await installFullPathRoutes(page);

  await page.goto('/gallery');
  await page.getByRole('button', { name: 'Import Character' }).first().click();
  const importDialog = page.getByRole('dialog', { name: 'Import Character' });
  await importDialog.locator('input[type="file"]').setInputFiles({
    name: 'phase1-full-card.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(fullCharacter.raw_source_json))
  });
  await importDialog.getByRole('button', { name: 'Import Character' }).click();

  await expect(page).toHaveURL(/\/characters\/phase1-full-character\?mode=review$/);
  await expect(page.getByText('Lorebook present - not used in v1')).toBeVisible();
  await expect(page.getByLabel('Description')).toHaveValue(maliciousDescription);
  await page.getByLabel('Description').fill('Edited full path description.');
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
  expect(await page.evaluate(() => (window as Window & { __raymeXssFired?: boolean }).__raymeXssFired)).toBe(false);
  await page.getByRole('button', { name: 'Save Character' }).click();
  await expect(page.getByText('Character saved.')).toBeVisible();

  await page.goto('/');
  await page.getByRole('button', { name: 'Start Chat' }).first().click();
  const homeDialog = page.getByRole('dialog', { name: 'Choose a character' });
  await homeDialog.getByRole('button', { name: /Phase 1 Full Path/ }).click();
  await homeDialog.getByLabel('Phase one selected opening.').check();
  await homeDialog.getByTestId('create-thread-submit').click();

  await expect(page).toHaveURL(/\/chat\/phase1-full-thread$/);
  await expect(page.getByText('Phase one selected opening.').first()).toBeVisible();
  await expect(page.locator('[data-message-id="phase1-full-opening"]')).toHaveAttribute(
    'data-selected-alternate-id',
    'phase1-full-opening-alt-1'
  );

  await page.getByRole('textbox', { name: 'Message' }).fill('Can the full path stream?');
  await page.keyboard.press('Enter');
  await expect(page.locator('[data-message-id="phase1-ai-1"]')).toBeVisible();
  await expect(page.getByText('Phase one streamed answer.')).toBeVisible();
  await expect(page.locator('[data-stale-after-edit="true"]')).toHaveCount(1);

  await chooseMessageAction(page, 'phase1-ai-1', 'Regenerate');
  await expect(page.getByText('Phase one regenerated replacement.')).toBeVisible();
  await expect(page.locator('[data-message-id="phase1-ai-1"]')).toHaveAttribute(
    'data-selected-alternate-id',
    'phase1-regenerated-selected'
  );

  await page.locator('[data-message-id="phase1-ai-1"]').getByRole('button', { name: 'Generate alternate' }).click();
  await expect(page.getByText('Phase one swipe alternate selected.')).toBeVisible();
  await expect(page.locator('[data-message-id="phase1-ai-1"]')).toHaveAttribute(
    'data-selected-alternate-id',
    'phase1-swipe-selected'
  );

  await page.getByRole('textbox', { name: 'Message' }).fill('extend with a clue');
  await chooseMessageAction(page, 'phase1-ai-1', 'Continue');
  await expect(page.getByText('Phase one continue alternate selected.')).toBeVisible();
  await expect(page.locator('[data-message-id="phase1-ai-1"]')).toHaveAttribute(
    'data-selected-alternate-id',
    'phase1-continue-selected'
  );

  await page.reload();
  await expect(page).toHaveURL(/\/chat\/phase1-full-thread$/);
  await expect(page.getByText('Phase one continue alternate selected.')).toBeVisible();
  await page.getByRole('textbox', { name: 'Message' }).fill('Continue after reload.');
  await page.keyboard.press('Enter');
  await expect(page.getByText('Phase one reload follow-up.')).toBeVisible();
  await expect(page).toHaveURL(/\/chat\/phase1-full-thread$/);

  await page.goto('/gallery');
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.waitForRequest(`**${exportV2Path}`),
    page.getByTestId(`character-card-${characterId}`).getByRole('button', { name: 'Export JSON' }).click()
  ]);
  const downloadPath = await download.path();
  expect(downloadPath).not.toBeNull();
  const exported = JSON.parse(await readFile(downloadPath as string, 'utf-8'));
  expect(exported).toMatchObject({
    spec: 'chara_card_v2',
    data: { name: 'Phase 1 Full Path' }
  });

  await page.getByTestId(`character-card-${deleteCharacterId}`).getByRole('button', { name: 'Delete' }).click();
  const deleteCharacterDialog = page.getByRole('dialog', { name: 'Delete character' });
  await deleteCharacterDialog.getByRole('button', { name: 'Delete' }).click();
  expect(calls.deletedCharacter, 'DELETE /api/characters/phase1-delete-character').toBe(true);
  await expect(page.getByText('Phase 1 Delete Candidate')).toHaveCount(0);

  await page.goto('/');
  const renameRow = page.getByTestId(`thread-row-${renameDeleteThreadId}`);
  await renameRow.getByRole('button', { name: `Actions for ${renameDeleteInitialTitle}` }).click();
  await page.getByRole('menuitem', { name: 'Rename' }).click();
  const renameDialog = page.getByRole('dialog', { name: 'Rename thread' });
  await renameDialog.getByLabel('Title').fill(renamedThreadTitle);
  await renameDialog.getByRole('button', { name: 'Save' }).click();
  expect(calls.renamedThread, 'PATCH /api/threads/phase1-thread-rename-delete').toBe(true);
  await expect(page.getByText(renamedThreadTitle)).toBeVisible();

  const renamedRow = page.getByTestId(`thread-row-${renameDeleteThreadId}`);
  await renamedRow.getByRole('button', { name: `Actions for ${renamedThreadTitle}` }).click();
  await page.getByRole('menuitem', { name: 'Delete' }).click();
  const deleteThreadDialog = page.getByRole('dialog', { name: 'Delete thread' });
  await expect(deleteThreadDialog.getByText(deleteThreadConfirmation, { exact: true })).toBeVisible();
  await deleteThreadDialog.getByRole('button', { name: 'Delete' }).click();
  expect(calls.deletedThread, 'DELETE /api/threads/phase1-thread-rename-delete').toBe(true);
  await expect(page.getByText(renamedThreadTitle)).toHaveCount(0);

  expect(calls).toMatchObject({
    imported: true,
    saved: true,
    createdThread: true,
    exported: true,
    deletedCharacter: true,
    renamedThread: true,
    deletedThread: true,
    regenerated: true,
    swiped: true,
    continued: true,
    sends: 2
  });
  await expectNoBrowserErrors();
});
