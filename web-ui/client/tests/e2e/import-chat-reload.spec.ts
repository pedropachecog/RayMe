import { expect, test, type Page, type Route } from '@playwright/test';

import { installBrowserErrorGuard } from './helpers/acceptance';

const maliciousDescription = '<img src=x onerror=alert(1)> javascript:alert(1)';
const characterId = 'imported-character';
const threadId = 'imported-thread';

const importedCharacter = {
  id: characterId,
  name: 'Imported Aster',
  description: maliciousDescription,
  personality: 'Precise and calm.',
  scenario: 'A secure relay room.',
  first_mes: 'Default greeting should not be selected.',
  mes_example: '<START>\n{{char}}: Example line.',
  system_prompt: 'Stay concise.',
  creator_notes: 'Imported creator notes.',
  character_notes: 'Imported character notes.',
  tags: ['fixture', 'lorebook', 'phase-one'],
  alternate_greetings: ['Alternate greeting one persisted.', 'Alternate greeting two persisted.'],
  post_history_instructions: 'Keep the selected branch.',
  creator: 'RayMe',
  character_version: '1.0',
  raw_source_json: {
    spec: 'chara_card_v3',
    spec_version: '3.0',
    data: { name: 'Imported Aster', description: maliciousDescription }
  },
  lorebook_status: 'present_not_used_in_v1',
  lorebook_json: { entries: [{ keys: ['secret'], content: 'Stored only.' }] },
  source_format: 'v3_json',
  warnings: ['Lorebook present - not used in v1'],
  deleted_at: null,
  updated_at: null,
  portrait_url: null,
  portrait_asset_id: null,
  portrait_storage_path: null
};

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
    source_action: 'first_mes' | 'regenerate' | 'swipe' | 'continue';
    created_at: string | null;
  }[];
  stale_after_edit: boolean;
  created_at: string | null;
  updated_at: string | null;
};

function aiMessage(
  id: string,
  sequence: number,
  content: string,
  sourceAction: 'first_mes' | 'regenerate' | 'swipe' | 'continue',
  alternateIndex = 0
): ThreadMessage {
  const alternateId = `alt-${id}-${sourceAction}`;
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

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

function threadDetail(messages: ThreadMessage[]) {
  return {
    id: threadId,
    character_id: characterId,
    title: 'Imported Aster',
    character_name: 'Imported Aster',
    character_portrait_url: null,
    character_snapshot: {
      name: importedCharacter.name,
      first_mes: importedCharacter.first_mes,
      raw_source_json: importedCharacter.raw_source_json,
      lorebook_json: importedCharacter.lorebook_json
    },
    messages,
    last_message_at: null,
    created_at: null,
    updated_at: null
  };
}

async function installAcceptanceRoutes(page: Page) {
  const messages: ThreadMessage[] = [
    aiMessage('opening-message', 0, 'Alternate greeting two persisted.', 'first_mes', 1)
  ];
  const calls = {
    imported: false,
    saved: false,
    createdThread: false,
    regenerated: false,
    swiped: false,
    continued: false,
    sends: 0
  };

  await page.route('**/api/characters/import', async (route) => {
    expect(route.request().method()).toBe('POST');
    calls.imported = true;
    await fulfillJson(
      route,
      {
        ...importedCharacter,
        character: importedCharacter,
        source_format: 'v3_json',
        warnings: ['Lorebook present - not used in v1']
      },
      201
    );
  });

  await page.route(`**/api/characters/${characterId}`, async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, importedCharacter);
      return;
    }

    expect(route.request().method()).toBe('PATCH');
    const payload = route.request().postDataJSON();
    expect(payload).toMatchObject({
      name: importedCharacter.name,
      description: maliciousDescription,
      first_mes: importedCharacter.first_mes,
      alternate_greetings: importedCharacter.alternate_greetings
    });
    calls.saved = true;
    await fulfillJson(route, { ...importedCharacter, ...payload });
  });

  await page.route('**/api/characters', async (route) => {
    expect(route.request().method()).toBe('GET');
    await fulfillJson(route, { items: calls.saved ? [importedCharacter] : [] });
  });

  await page.route('**/api/threads', async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toEqual({
      character_id: characterId,
      alternate_greeting_index: 1
    });
    calls.createdThread = true;
    await fulfillJson(route, { thread_id: threadId }, 201);
  });

  await page.route(`**/api/threads/${threadId}`, async (route) => {
    expect(route.request().method()).toBe('GET');
    await fulfillJson(route, threadDetail(messages));
  });

  await page.route(`**/api/chat/${threadId}/send`, async (route) => {
    expect(route.request().method()).toBe('POST');
    const { content } = route.request().postDataJSON() as { content: string };
    calls.sends += 1;
    const userId = calls.sends === 1 ? 'user-send-1' : 'user-send-2';
    const aiId = calls.sends === 1 ? 'ai-send-1' : 'ai-send-2';
    const aiContent =
      calls.sends === 1 ? 'Streamed backend answer.' : 'Reload follow-up backend answer.';
    const nextSequence = messages.length;
    const user = userMessage(userId, nextSequence, content);
    const ai = aiMessage(aiId, nextSequence + 1, aiContent, 'regenerate');
    messages.push(user, ai);
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: [
        'data: {"type":"token","text":"Streamed "}\n\n',
        'data: {"type":"token","text":"backend"}\n\n',
        `data: ${JSON.stringify({ type: 'done', message: ai })}\n\n`
      ].join('')
    });
  });

  await page.route('**/api/messages/ai-send-1/regenerate', async (route) => {
    expect(route.request().method()).toBe('POST');
    const regenerated = {
      ...aiMessage('ai-send-1', 2, 'Backend regenerated replacement.', 'regenerate'),
      alternates: [
        ...messages[2].alternates,
        {
          id: 'alt-regenerated-selected',
          message_id: 'ai-send-1',
          alternate_index: 1,
          content_text: 'Backend regenerated replacement.',
          source_action: 'regenerate',
          created_at: null
        }
      ],
      selected_alternate_id: 'alt-regenerated-selected'
    } satisfies ThreadMessage;
    messages[2] = regenerated;
    calls.regenerated = true;
    await fulfillJson(route, regenerated);
  });

  await page.route('**/api/messages/ai-send-1/swipes', async (route) => {
    expect(route.request().method()).toBe('POST');
    const swiped = {
      ...messages[2],
      selected_alternate_id: 'alt-swipe-selected',
      alternates: [
        ...messages[2].alternates,
        {
          id: 'alt-swipe-selected',
          message_id: 'ai-send-1',
          alternate_index: messages[2].alternates.length,
          content_text: 'Backend swipe alternate selected.',
          source_action: 'swipe',
          created_at: null
        }
      ]
    } satisfies ThreadMessage;
    messages[2] = swiped;
    calls.swiped = true;
    await fulfillJson(route, swiped);
  });

  await page.route('**/api/messages/ai-send-1/continue', async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toEqual({ composer_text: 'extend with a clue' });
    const continued = {
      ...messages[2],
      selected_alternate_id: 'alt-continue-selected',
      alternates: [
        ...messages[2].alternates,
        {
          id: 'alt-continue-selected',
          message_id: 'ai-send-1',
          alternate_index: messages[2].alternates.length,
          content_text: 'Backend continue alternate selected.',
          source_action: 'continue',
          created_at: null
        }
      ]
    } satisfies ThreadMessage;
    messages[2] = continued;
    calls.continued = true;
    await fulfillJson(route, continued);
  });

  return calls;
}

async function chooseMessageAction(page: Page, messageId: string, label: string) {
  const row = page.locator(`[data-message-id="${messageId}"]`);
  await row.hover();
  await row.getByRole('button', { name: 'Message actions' }).click();
  await page.getByRole('menuitem', { name: label }).click();
}

test('imported character chat reloads and continues', async ({ page }) => {
  await page.addInitScript(() => {
    (window as Window & { __raymeXssFired?: boolean }).__raymeXssFired = false;
    window.alert = () => {
      (window as Window & { __raymeXssFired?: boolean }).__raymeXssFired = true;
    };
  });
  const expectNoBrowserErrors = installBrowserErrorGuard(page);
  const calls = await installAcceptanceRoutes(page);

  await page.goto('/gallery');
  await page.getByRole('button', { name: 'Import Character' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Import Character' });
  await dialog.locator('input[type="file"]').setInputFiles({
    name: 'phase-one-card.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(importedCharacter.raw_source_json))
  });
  await dialog.getByRole('button', { name: 'Import Character' }).click();

  await expect(page).toHaveURL(/\/characters\/imported-character\?mode=review$/);
  await expect(page.getByText('Lorebook present - not used in v1')).toBeVisible();
  await expect(page.getByLabel('Description')).toHaveValue(maliciousDescription);
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
  await expect(page.locator('script').filter({ hasText: 'alert(1)' })).toHaveCount(0);
  await expect(page).not.toHaveURL(/javascript:alert/);
  expect(await page.evaluate(() => (window as Window & { __raymeXssFired?: boolean }).__raymeXssFired)).toBe(false);

  await page.getByRole('button', { name: 'Save Character' }).click();
  await expect(page.getByText('Character saved.')).toBeVisible();

  await page.goto('/gallery');
  const card = page.getByTestId(`character-card-${characterId}`);
  await expect(card.getByText('Imported Aster')).toBeVisible();
  await expect(page.getByTestId(`character-snippet-${characterId}`).locator('img')).toHaveCount(0);
  await card.getByRole('button', { name: 'Start Chat' }).click();

  const greetingDialog = page.getByRole('dialog', { name: 'Imported Aster' });
  await expect(greetingDialog.getByText('Choose the first message for this thread')).toBeVisible();
  await greetingDialog.getByLabel('Alternate greeting two persisted.').check();
  await greetingDialog.getByRole('button', { name: 'Start Chat' }).click();

  await expect(page).toHaveURL(/\/chat\/imported-thread$/);
  await expect(page.getByText('Alternate greeting two persisted.').first()).toBeVisible();
  await expect(page.locator('[data-message-id="opening-message"]')).toHaveAttribute(
    'data-selected-alternate-id',
    'alt-opening-message-first_mes'
  );

  await page.getByRole('textbox', { name: 'Message' }).fill('Can you stream from the backend?');
  await page.keyboard.press('Enter');
  await expect(page.locator('[data-message-id="ai-send-1"]')).toBeVisible();
  await expect(page.getByText('Streamed backend answer.')).toBeVisible();

  await chooseMessageAction(page, 'ai-send-1', 'Redo and Replace');
  await expect(page.getByText('Backend regenerated replacement.')).toBeVisible();
  await expect(page.locator('[data-message-id="ai-send-1"]')).toHaveAttribute(
    'data-selected-alternate-id',
    'alt-regenerated-selected'
  );

  await page.locator('[data-message-id="ai-send-1"]').getByRole('button', { name: 'Redo' }).click();
  await expect(page.getByText('Backend swipe alternate selected.')).toBeVisible();
  await expect(page.locator('[data-message-id="ai-send-1"]')).toHaveAttribute(
    'data-selected-alternate-id',
    'alt-swipe-selected'
  );

  await page.getByRole('textbox', { name: 'Message' }).fill('extend with a clue');
  await chooseMessageAction(page, 'ai-send-1', 'Continue');
  await expect(page.getByText('Backend continue alternate selected.')).toBeVisible();
  await expect(page.locator('[data-message-id="ai-send-1"]')).toHaveAttribute(
    'data-selected-alternate-id',
    'alt-continue-selected'
  );

  await page.reload();
  await expect(page.getByText('Backend continue alternate selected.')).toBeVisible();
  await page.getByRole('textbox', { name: 'Message' }).fill('Continue after reload.');
  await page.keyboard.press('Enter');
  await expect(page.getByText('Reload follow-up backend answer.')).toBeVisible();

  expect(calls).toMatchObject({
    imported: true,
    saved: true,
    createdThread: true,
    regenerated: true,
    swiped: true,
    continued: true,
    sends: 2
  });
  await expectNoBrowserErrors();
});
