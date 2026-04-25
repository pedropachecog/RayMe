import { expect, test, type Page, type Route } from '@playwright/test';

import { installBrowserErrorGuard, installEmptyVoiceLibraryRoute } from './helpers/acceptance';

test.use({ viewport: { width: 393, height: 851 }, isMobile: true });

const character = {
  id: 'mobile-imported-character',
  name: 'Mobile Aster',
  description: '<script>alert(1)</script> Mobile safe text.',
  personality: 'Mobile focused.',
  scenario: 'Android Chrome acceptance.',
  first_mes: 'Mobile default greeting.',
  mes_example: '<START>',
  system_prompt: 'Stay concise.',
  creator_notes: 'Mobile notes.',
  character_notes: 'Mobile character notes.',
  tags: ['mobile'],
  alternate_greetings: ['Mobile alternate zero.', 'Mobile alternate selected.'],
  post_history_instructions: 'Continue on mobile.',
  creator: 'RayMe',
  character_version: '1.0',
  raw_source_json: { spec: 'chara_card_v3', spec_version: '3.0', data: { name: 'Mobile Aster' } },
  lorebook_status: 'present_not_used_in_v1',
  lorebook_json: { entries: [{ keys: ['mobile'], content: 'Stored only.' }] },
  warnings: ['Lorebook present - not used in v1'],
  deleted_at: null,
  updated_at: null,
  portrait_url: null
};

const threadId = 'mobile-thread';

type Message = {
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

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

function ai(id: string, sequence: number, content: string, source: Message['alternates'][number]['source_action']): Message {
  const alternateId = `${id}-${source}`;
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
        alternate_index: source === 'first_mes' ? 1 : 0,
        content_text: content,
        source_action: source,
        created_at: null
      }
    ],
    stale_after_edit: false,
    created_at: null,
    updated_at: null
  };
}

function user(id: string, sequence: number, content: string): Message {
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

function detail(messages: Message[]) {
  return {
    id: threadId,
    character_id: character.id,
    title: character.name,
    character_name: character.name,
    character_portrait_url: null,
    character_snapshot: { name: character.name, first_mes: character.first_mes },
    messages,
    last_message_at: null,
    created_at: null,
    updated_at: null
  };
}

async function installMobileRoutes(page: Page) {
  await installEmptyVoiceLibraryRoute(page);

  const messages: Message[] = [ai('mobile-opening', 0, 'Mobile alternate selected.', 'first_mes')];
  let saved = false;

  await page.route('**/api/characters/import', async (route) => {
    await fulfillJson(route, { ...character, character, source_format: 'v3_json' }, 201);
  });
  await page.route(`**/api/characters/${character.id}`, async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, character);
      return;
    }
    expect(route.request().method()).toBe('PATCH');
    saved = true;
    await fulfillJson(route, { ...character, ...route.request().postDataJSON() });
  });
  await page.route('**/api/characters', async (route) => {
    await fulfillJson(route, { items: saved ? [character] : [] });
  });
  await page.route('**/api/threads', async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toEqual({
      character_id: character.id,
      alternate_greeting_index: 1
    });
    await fulfillJson(route, { thread_id: threadId }, 201);
  });
  await page.route(`**/api/threads/${threadId}`, async (route) => {
    await fulfillJson(route, detail(messages));
  });
  await page.route(`**/api/chat/${threadId}/send`, async (route) => {
    const content = (route.request().postDataJSON() as { content: string }).content;
    const nextSequence = messages.length;
    const aiId = messages.some((message) => message.id === 'mobile-ai-1') ? 'mobile-ai-2' : 'mobile-ai-1';
    const aiContent = aiId === 'mobile-ai-1' ? 'Mobile streamed answer.' : 'Mobile reload follow-up.';
    const userId = aiId === 'mobile-ai-1' ? 'mobile-user-1' : 'mobile-user-2';
    const backendMessage = ai(aiId, nextSequence + 1, aiContent, 'regenerate');
    messages.push(user(userId, nextSequence, content), backendMessage);
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: [
        'data: {"type":"token","text":"Mobile "}\n\n',
        'data: {"type":"token","text":"stream"}\n\n',
        `data: ${JSON.stringify({ type: 'done', message: backendMessage })}\n\n`
      ].join('')
    });
  });
  await page.route('**/api/messages/mobile-ai-1/regenerate', async (route) => {
    const next = {
      ...messages[2],
      content_text: 'Mobile regenerated backend answer.',
      selected_alternate_id: 'mobile-regenerated',
      alternates: [
        ...messages[2].alternates,
        {
          id: 'mobile-regenerated',
          message_id: 'mobile-ai-1',
          alternate_index: 1,
          content_text: 'Mobile regenerated backend answer.',
          source_action: 'regenerate',
          created_at: null
        }
      ]
    } satisfies Message;
    messages[2] = next;
    await fulfillJson(route, next);
  });
  await page.route('**/api/messages/mobile-ai-1/swipes', async (route) => {
    const payload = route.request().postData()
      ? (route.request().postDataJSON() as { alternate_id?: string })
      : null;
    if (payload?.alternate_id) {
      const selected = messages[2].alternates.find((alternate) => alternate.id === payload.alternate_id);
      expect(selected).toBeTruthy();
      const next = {
        ...messages[2],
        content_text: selected?.content_text ?? messages[2].content_text,
        selected_alternate_id: payload.alternate_id
      } satisfies Message;
      messages[2] = next;
      await fulfillJson(route, next);
      return;
    }

    const next = {
      ...messages[2],
      selected_alternate_id: 'mobile-swipe',
      alternates: [
        ...messages[2].alternates,
        {
          id: 'mobile-swipe',
          message_id: 'mobile-ai-1',
          alternate_index: 2,
          content_text: 'Mobile swipe backend alternate.',
          source_action: 'swipe',
          created_at: null
        }
      ]
    } satisfies Message;
    messages[2] = next;
    await fulfillJson(route, next);
  });
  await page.route('**/api/messages/mobile-ai-1/continue', async (route) => {
    expect(route.request().postDataJSON()).toEqual({ composer_text: 'mobile continue text' });
    const next = {
      ...messages[2],
      selected_alternate_id: 'mobile-continue',
      alternates: [
        ...messages[2].alternates,
        {
          id: 'mobile-continue',
          message_id: 'mobile-ai-1',
          alternate_index: 3,
          content_text: 'Mobile continue backend alternate.',
          source_action: 'continue',
          created_at: null
        }
      ]
    } satisfies Message;
    messages[2] = next;
    await fulfillJson(route, next);
  });
}

async function chooseAction(page: Page, messageId: string, label: string) {
  const row = page.locator(`[data-message-id="${messageId}"]`);
  await row.getByRole('button', { name: 'Message actions' }).click();
  await page.getByRole('menuitem', { name: label }).click();
}

test('mobile viewport can import chat reload and continue', async ({ page }) => {
  const expectNoBrowserErrors = installBrowserErrorGuard(page);
  await installMobileRoutes(page);

  await page.goto('/gallery');
  await page.getByRole('button', { name: 'Import Character' }).first().click();
  const importDialog = page.getByRole('dialog', { name: 'Import Character' });
  await importDialog.locator('input[type="file"]').setInputFiles({
    name: 'mobile-card.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(character.raw_source_json))
  });
  await importDialog.getByRole('button', { name: 'Import Character' }).click();

  await expect(page).toHaveURL(/\/characters\/mobile-imported-character\?mode=review$/);
  await expect(page.getByText('Lorebook present - not used in v1')).toBeVisible();
  await expect(page.locator('script').filter({ hasText: 'alert(1)' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Save Character' }).click();
  await expect(page.getByText('Character saved.')).toBeVisible();

  await page.goto('/gallery');
  await page.getByTestId('character-card-mobile-imported-character').getByRole('button', { name: 'Start Chat' }).click();
  const greetingDialog = page.getByRole('dialog', { name: 'Mobile Aster' });
  await greetingDialog.getByLabel('Mobile alternate selected.').check();
  await greetingDialog.getByRole('button', { name: 'Start Chat' }).click();

  await expect(page).toHaveURL(/\/chat\/mobile-thread$/);
  await expect(page.getByText('Mobile alternate selected.')).toBeVisible();
  await page.getByRole('textbox', { name: 'Message' }).fill('Mobile send.');
  await page.keyboard.press('Enter');
  await expect(page.getByText('Mobile streamed answer.')).toBeVisible();

  await chooseAction(page, 'mobile-ai-1', 'Redo and Replace');
  await expect(page.getByText('Mobile regenerated backend answer.')).toBeVisible();
  await page.locator('[data-message-id="mobile-ai-1"]').getByRole('button', { name: 'Redo' }).click();
  await expect(page.getByText('Mobile swipe backend alternate.')).toBeVisible();
  await swipeMessage(page, 'mobile-ai-1', 'right');
  await expect(page.getByText('Mobile regenerated backend answer.')).toBeVisible();
  await page.getByRole('textbox', { name: 'Message' }).fill('mobile continue text');
  await chooseAction(page, 'mobile-ai-1', 'Continue');
  await expect(page.getByText('Mobile continue backend alternate.')).toBeVisible();

  await page.reload();
  await expect(page.getByText('Mobile continue backend alternate.')).toBeVisible();
  await page.getByRole('textbox', { name: 'Message' }).fill('Mobile after reload.');
  await page.keyboard.press('Enter');
  await expect(page.getByText('Mobile reload follow-up.')).toBeVisible();

  const composerBox = await page.getByRole('form', { name: 'Chat composer' }).boundingBox();
  const mobileNavBox = await page.getByRole('navigation', { name: 'Primary mobile' }).boundingBox();
  expect(composerBox).not.toBeNull();
  expect(mobileNavBox).not.toBeNull();
  expect((composerBox?.y ?? 0) + (composerBox?.height ?? 0)).toBeLessThanOrEqual(mobileNavBox?.y ?? 0);
  await expectNoBrowserErrors();
});

async function swipeMessage(page: Page, messageId: string, direction: 'left' | 'right') {
  const row = page.locator(`[data-message-id="${messageId}"]`);
  const box = await row.boundingBox();
  expect(box).not.toBeNull();

  const startX = direction === 'left' ? (box?.x ?? 0) + (box?.width ?? 0) - 24 : (box?.x ?? 0) + 24;
  const endX = direction === 'left' ? startX - 96 : startX + 96;
  const y = (box?.y ?? 0) + (box?.height ?? 0) / 2;

  await row.dispatchEvent('pointerdown', {
    pointerId: 1,
    pointerType: 'touch',
    clientX: startX,
    clientY: y
  });
  await row.dispatchEvent('pointermove', {
    pointerId: 1,
    pointerType: 'touch',
    clientX: endX,
    clientY: y
  });
  await row.dispatchEvent('pointerup', {
    pointerId: 1,
    pointerType: 'touch',
    clientX: endX,
    clientY: y
  });
}
