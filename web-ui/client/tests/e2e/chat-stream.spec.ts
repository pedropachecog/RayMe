import { expect, test, type Page } from '@playwright/test';

import { installBrowserErrorGuard } from './helpers/acceptance';

const errorCopy =
  'RayMe cannot reach the LLM endpoint. Check Settings, run Test Connection, and try again.';

function hydratedThread(threadId: string) {
  return {
    id: threadId,
    character_id: 'character-1',
    title: 'Night relay',
    character_name: 'Aster',
    character_portrait_url: null,
    messages: [
      {
        id: 'opening',
        thread_id: threadId,
        message_kind: 'ai_text',
        role: 'assistant',
        sequence: 0,
        content_text: 'Fallback opening',
        selected_alternate_id: 'alt-open-2',
        alternates: [
          {
            id: 'alt-open-1',
            message_id: 'opening',
            alternate_index: 0,
            content_text: 'Fallback opening',
            source_action: 'first_mes',
            created_at: null
          },
          {
            id: 'alt-open-2',
            message_id: 'opening',
            alternate_index: 1,
            content_text: 'Selected opening from hydration',
            source_action: 'first_mes',
            created_at: null
          }
        ],
        stale_after_edit: false,
        created_at: null,
        updated_at: null
      },
      {
        id: 'stale-user',
        thread_id: threadId,
        message_kind: 'user_text',
        role: 'user',
        sequence: 1,
        content_text: 'Edited old branch',
        selected_alternate_id: null,
        alternates: [],
        stale_after_edit: true,
        created_at: null,
        updated_at: null
      }
    ]
  };
}

function doneMessage(threadId: string) {
  return {
    id: 'ai-done',
    thread_id: threadId,
    message_kind: 'ai_text',
    role: 'assistant',
    sequence: 3,
    content_text: 'Generated fallback',
    selected_alternate_id: 'alt-done-2',
    alternates: [
      {
        id: 'alt-done-1',
        message_id: 'ai-done',
        alternate_index: 0,
        content_text: 'Generated fallback',
        source_action: 'regenerate',
        created_at: null
      },
      {
        id: 'alt-done-2',
        message_id: 'ai-done',
        alternate_index: 1,
        content_text: 'Generated final selected branch',
        source_action: 'regenerate',
        created_at: null
      }
    ],
    stale_after_edit: true,
    created_at: null,
    updated_at: null
  };
}

async function mockThread(page: Page, threadId: string) {
  await page.route(`**/api/threads/${threadId}`, async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(hydratedThread(threadId))
    });
  });
}

test('chat hydrates selected alternates, streams send, and preserves done message fields', async ({
  page
}) => {
  const expectNoBrowserErrors = installBrowserErrorGuard(page);
  const threadId = 'e2e-thread';
  await mockThread(page, threadId);
  await page.route(`**/api/chat/${threadId}/send`, async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toEqual({ content: 'Can you hear me?' });

    const message = doneMessage(threadId);
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: [
        'data: {"type":"token","text":"Gen"}\n\n',
        'data: {"type":"token","text":"erated"}\n\n',
        `data: ${JSON.stringify({ type: 'done', message })}\n\n`
      ].join('')
    });
  });

  await page.goto(`/chat/${threadId}`);

  await expect(page.getByRole('heading', { name: 'Night relay' })).toBeVisible();
  await expect(page.getByText('Selected opening from hydration').first()).toBeVisible();
  await expect(page.locator('[data-selected-alternate-id="alt-open-2"]')).toHaveCount(1);
  await expect(page.locator('[data-stale-after-edit="true"]')).toHaveCount(1);
  await expect(page.getByRole('button', { name: /call/i })).toHaveCount(0);

  await page.getByRole('textbox', { name: 'Message' }).fill('Can you hear me?');
  await page.keyboard.press('Enter');

  const doneBubble = page.locator('[data-message-id="ai-done"]');
  await expect(doneBubble).toBeVisible();
  await expect(doneBubble).toHaveAttribute('data-message-kind', 'ai_text');
  await expect(doneBubble).toHaveAttribute('data-message-role', 'assistant');
  await expect(doneBubble).toHaveAttribute('data-message-sequence', '3');
  await expect(doneBubble).toHaveAttribute('data-selected-alternate-id', 'alt-done-2');
  await expect(doneBubble).toHaveAttribute('data-stale-after-edit', 'true');
  await expect(doneBubble.getByText('Generated final selected branch').first()).toBeVisible();
  await expect(page.locator('[data-message-id^="streaming-ai-"]')).toHaveCount(0);
  await expectNoBrowserErrors();
});

test('chat stream error keeps the user message and renders exact recovery copy', async ({ page }) => {
  const expectNoBrowserErrors = installBrowserErrorGuard(page);
  const threadId = 'e2e-error-thread';
  await mockThread(page, threadId);
  await page.route(`**/api/chat/${threadId}/send`, async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: 'data: {"type":"error","message":"LLM stream failed"}\n\n'
    });
  });

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('textbox', { name: 'Message' }).fill('Try the endpoint');
  await page.keyboard.press('Enter');

  await expect(page.getByText('Try the endpoint')).toBeVisible();
  await expect(page.getByText(errorCopy)).toBeVisible();
  await expect(page.getByRole('alert').getByRole('button', { name: 'Redo' })).toBeVisible();
  await expectNoBrowserErrors();
});
