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

function editableThread(threadId: string) {
  return {
    id: threadId,
    character_id: 'character-1',
    title: 'Editable relay',
    character_name: 'Aster',
    character_portrait_url: null,
    messages: [
      {
        id: 'user-persisted',
        thread_id: threadId,
        message_kind: 'user_text',
        role: 'user',
        sequence: 1,
        content_text: 'Original user prompt',
        selected_alternate_id: null,
        alternates: [],
        stale_after_edit: false,
        created_at: null,
        updated_at: null
      },
      {
        id: 'ai-after-user',
        thread_id: threadId,
        message_kind: 'ai_text',
        role: 'assistant',
        sequence: 2,
        content_text: 'Original AI response',
        selected_alternate_id: 'alt-original-ai',
        alternates: [
          {
            id: 'alt-original-ai',
            message_id: 'ai-after-user',
            alternate_index: 0,
            content_text: 'Original AI response',
            source_action: 'regenerate',
            created_at: null
          }
        ],
        stale_after_edit: false,
        created_at: null,
        updated_at: null
      },
      {
        id: 'later-user',
        thread_id: threadId,
        message_kind: 'user_text',
        role: 'user',
        sequence: 3,
        content_text: 'Later user turn stays fresh after an assistant correction',
        selected_alternate_id: null,
        alternates: [],
        stale_after_edit: false,
        created_at: null,
        updated_at: null
      }
    ]
  };
}

function editableCallThread(threadId: string) {
  return {
    id: threadId,
    character_id: 'character-1',
    title: 'Editable call relay',
    character_name: 'Aster',
    character_portrait_url: null,
    messages: [
      {
        id: 'call-user-speech',
        thread_id: threadId,
        message_kind: 'user_speech',
        role: 'user',
        sequence: 1,
        content_text: 'Original spoken user prompt',
        selected_alternate_id: null,
        alternates: [],
        stale_after_edit: false,
        created_at: null,
        updated_at: null
      },
      {
        id: 'call-ai-speech',
        thread_id: threadId,
        message_kind: 'ai_speech',
        role: 'assistant',
        sequence: 2,
        content_text: 'Original spoken AI response',
        selected_alternate_id: null,
        alternates: [],
        stale_after_edit: false,
        created_at: null,
        updated_at: null
      },
      {
        id: 'call-later-user-speech',
        thread_id: threadId,
        message_kind: 'user_speech',
        role: 'user',
        sequence: 3,
        content_text: 'Later spoken user turn stays fresh after assistant correction',
        selected_alternate_id: null,
        alternates: [],
        stale_after_edit: false,
        created_at: null,
        updated_at: null
      }
    ]
  };
}

function staleAssistantIsolationThread(threadId: string) {
  return {
    id: threadId,
    character_id: 'character-1',
    title: 'Stale assistant isolation',
    character_name: 'Aster',
    character_portrait_url: null,
    messages: [
      {
        id: 'user-before-target',
        thread_id: threadId,
        message_kind: 'user_text',
        role: 'user',
        sequence: 1,
        content_text: 'Prompt before the stale assistant pair',
        selected_alternate_id: null,
        alternates: [],
        stale_after_edit: false,
        created_at: null,
        updated_at: null
      },
      {
        id: 'second-to-last-ai',
        thread_id: threadId,
        message_kind: 'ai_text',
        role: 'assistant',
        sequence: 2,
        content_text: 'Original second-to-last assistant response',
        selected_alternate_id: 'target-alternate',
        alternates: [
          {
            id: 'target-alternate',
            message_id: 'second-to-last-ai',
            alternate_index: 0,
            content_text: 'Original second-to-last assistant response',
            source_action: 'regenerate',
            created_at: null
          }
        ],
        stale_after_edit: true,
        created_at: null,
        updated_at: null
      },
      {
        id: 'stale-user-between',
        thread_id: threadId,
        message_kind: 'user_text',
        role: 'user',
        sequence: 3,
        content_text: 'Previously stale user message',
        selected_alternate_id: null,
        alternates: [],
        stale_after_edit: true,
        created_at: null,
        updated_at: null
      },
      {
        id: 'final-stale-ai',
        thread_id: threadId,
        message_kind: 'ai_text',
        role: 'assistant',
        sequence: 4,
        content_text: 'Final stale assistant response',
        selected_alternate_id: 'final-alternate',
        alternates: [
          {
            id: 'final-alternate',
            message_id: 'final-stale-ai',
            alternate_index: 0,
            content_text: 'Final stale assistant response',
            source_action: 'regenerate',
            created_at: null
          }
        ],
        stale_after_edit: true,
        created_at: null,
        updated_at: null
      }
    ]
  };
}

async function mockThread(page: Page, threadId: string, thread = hydratedThread(threadId)) {
  await page.route(`**/api/threads/${threadId}`, async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(thread)
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

test('chat replaces a streamed optimistic user with the persisted user message before it can be edited', async ({
  page
}) => {
  const expectNoBrowserErrors = installBrowserErrorGuard(page);
  const threadId = 'e2e-persisted-send-thread';
  const initial = hydratedThread(threadId);
  const persistedUser = {
    id: 'user-from-server',
    thread_id: threadId,
    message_kind: 'user_text',
    role: 'user',
    sequence: 2,
    content_text: 'Persist this before editing',
    selected_alternate_id: null,
    alternates: [],
    stale_after_edit: false,
    created_at: null,
    updated_at: null
  };
  const persisted = {
    ...initial,
    messages: [...initial.messages, persistedUser, { ...doneMessage(threadId), sequence: 3 }]
  };
  let threadReads = 0;

  await page.route(`**/api/threads/${threadId}`, async (route) => {
    threadReads += 1;
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(threadReads === 1 ? initial : persisted)
    });
  });
  await page.route(`**/api/chat/${threadId}/send`, async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: `data: ${JSON.stringify({ type: 'done', message: { ...doneMessage(threadId), sequence: 3 } })}\n\n`
    });
  });

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('textbox', { name: 'Message' }).fill('Persist this before editing');
  await page.keyboard.press('Enter');

  await expect(page.locator('[data-message-id="user-from-server"]')).toBeVisible();
  await expect(page.locator('[data-message-id^="optimistic-user-"]')).toHaveCount(0);
  expect(threadReads).toBe(2);
  await expectNoBrowserErrors();
});

test('chat persists an assistant edit through its authoritative message ID', async ({ page }) => {
  const expectNoBrowserErrors = installBrowserErrorGuard(page);
  const threadId = 'e2e-assistant-edit-thread';
  const thread = editableThread(threadId);
  let regenerateRequests = 0;
  const editedAssistant = {
    ...thread.messages[1],
    content_text: 'Edited assistant response',
    selected_alternate_id: 'alt-edited-ai',
    alternates: [
      ...thread.messages[1].alternates,
      {
        id: 'alt-edited-ai',
        message_id: 'ai-after-user',
        alternate_index: 1,
        content_text: 'Edited assistant response',
        source_action: 'regenerate',
        created_at: null
      }
    ]
  };

  await mockThread(page, threadId, thread);
  await page.route('**/api/messages/ai-after-user', async (route) => {
    expect(route.request().method()).toBe('PATCH');
    expect(route.request().postDataJSON()).toEqual({ content: 'Edited assistant response' });
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editedAssistant)
    });
  });
  await page.route('**/api/messages/ai-after-user/regenerate', async (route) => {
    regenerateRequests += 1;
    await route.fulfill({ status: 500 });
  });

  await page.goto(`/chat/${threadId}`);
  const assistant = page.locator('[data-message-id="ai-after-user"]');
  await assistant.getByRole('button', { name: 'Message actions' }).click();
  await page.getByRole('menuitem', { name: 'Edit' }).click();
  await assistant.getByRole('textbox', { name: 'Edit message' }).fill('Edited assistant response');
  await assistant.getByRole('button', { name: 'Save' }).click();

  await expect(assistant.getByText('Edited assistant response')).toBeVisible();
  await expect(page.locator('[data-message-id="later-user"]')).toHaveAttribute(
    'data-stale-after-edit',
    'false'
  );
  expect(regenerateRequests).toBe(0);
  await expectNoBrowserErrors();
});

test('chat keeps a later stale AI message isolated when editing the second-to-last assistant', async ({ page }) => {
  const expectNoBrowserErrors = installBrowserErrorGuard(page);
  const threadId = 'e2e-stale-assistant-isolation-thread';
  const thread = staleAssistantIsolationThread(threadId);
  let regenerateRequests = 0;
  const editedTarget = {
    ...thread.messages[1],
    content_text: 'Corrected second-to-last assistant response',
    alternates: [
      {
        ...thread.messages[1].alternates[0],
        content_text: 'Corrected second-to-last assistant response'
      }
    ]
  };

  await mockThread(page, threadId, thread);
  await page.route('**/api/messages/second-to-last-ai', async (route) => {
    expect(route.request().method()).toBe('PATCH');
    expect(route.request().postDataJSON()).toEqual({
      content: 'Corrected second-to-last assistant response'
    });
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editedTarget)
    });
  });
  await page.route('**/api/messages/final-stale-ai/regenerate', async (route) => {
    regenerateRequests += 1;
    await route.fulfill({ status: 500 });
  });

  await page.goto(`/chat/${threadId}`);
  const target = page.locator('[data-message-id="second-to-last-ai"]');
  const final = page.locator('[data-message-id="final-stale-ai"]');
  await target.getByRole('button', { name: 'Message actions' }).click();
  await page.getByRole('menuitem', { name: 'Edit' }).click();
  await target
    .getByRole('textbox', { name: 'Edit message' })
    .fill('Corrected second-to-last assistant response');
  await target.getByRole('button', { name: 'Save' }).click();

  await expect(target).toContainText('Corrected second-to-last assistant response');
  await expect(final).toContainText('Final stale assistant response');
  await expect(final).toHaveAttribute('data-message-id', 'final-stale-ai');
  await expect(final).toHaveAttribute('data-selected-alternate-id', 'final-alternate');
  await expect(final).toHaveAttribute('data-stale-after-edit', 'true');
  expect(regenerateRequests).toBe(0);
  await expectNoBrowserErrors();
});

test('chat persists a user edit then regenerates its immediate downstream AI response', async ({ page }) => {
  const expectNoBrowserErrors = installBrowserErrorGuard(page);
  const threadId = 'e2e-user-edit-thread';
  const thread = editableThread(threadId);
  const editedUser = { ...thread.messages[0], content_text: 'Corrected user prompt' };
  const regeneratedAssistant = {
    ...thread.messages[1],
    content_text: 'AI response to corrected prompt',
    selected_alternate_id: 'alt-regenerated-ai',
    alternates: [
      ...thread.messages[1].alternates,
      {
        id: 'alt-regenerated-ai',
        message_id: 'ai-after-user',
        alternate_index: 1,
        content_text: 'AI response to corrected prompt',
        source_action: 'regenerate',
        created_at: null
      }
    ]
  };
  const requests: string[] = [];

  await mockThread(page, threadId, thread);
  await page.route('**/api/messages/user-persisted', async (route) => {
    requests.push(route.request().method());
    expect(route.request().postDataJSON()).toEqual({ content: 'Corrected user prompt' });
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editedUser)
    });
  });
  await page.route('**/api/messages/ai-after-user/regenerate', async (route) => {
    requests.push(route.request().method());
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(regeneratedAssistant)
    });
  });

  await page.goto(`/chat/${threadId}`);
  const user = page.locator('[data-message-id="user-persisted"]');
  await user.getByRole('button', { name: 'Message actions' }).click();
  await page.getByRole('menuitem', { name: 'Edit' }).click();
  await user.getByRole('textbox', { name: 'Edit message' }).fill('Corrected user prompt');
  await user.getByRole('button', { name: 'Save' }).click();

  await expect(user.getByText('Corrected user prompt')).toBeVisible();
  await expect(page.locator('[data-message-id="ai-after-user"]')).toContainText(
    'AI response to corrected prompt'
  );
  expect(requests).toEqual(['PATCH', 'POST']);
  await expectNoBrowserErrors();
});

test('chat edits call-origin speech rows with the established role-specific semantics', async ({
  page
}) => {
  const expectNoBrowserErrors = installBrowserErrorGuard(page);
  const threadId = 'e2e-call-edit-thread';
  const thread = editableCallThread(threadId);
  const editedUser = { ...thread.messages[0], content_text: 'Corrected spoken user prompt' };
  const regeneratedAssistant = {
    ...thread.messages[1],
    content_text: 'AI response to corrected spoken prompt'
  };
  const editedAssistant = {
    ...thread.messages[1],
    content_text: 'Corrected spoken AI response'
  };
  const requests: string[] = [];

  await mockThread(page, threadId, thread);
  await page.route('**/api/messages/call-user-speech', async (route) => {
    requests.push(`${route.request().method()} user`);
    expect(route.request().postDataJSON()).toEqual({ content: 'Corrected spoken user prompt' });
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editedUser)
    });
  });
  await page.route('**/api/messages/call-ai-speech', async (route) => {
    requests.push(`${route.request().method()} assistant`);
    expect(route.request().postDataJSON()).toEqual({ content: 'Corrected spoken AI response' });
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editedAssistant)
    });
  });
  await page.route('**/api/messages/call-ai-speech/regenerate', async (route) => {
    requests.push(`${route.request().method()} regenerate`);
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(regeneratedAssistant)
    });
  });

  await page.goto(`/chat/${threadId}`);

  const assistant = page.locator('[data-message-id="call-ai-speech"]');
  await assistant.getByRole('button', { name: 'Message actions' }).click();
  await page.getByRole('menuitem', { name: 'Edit' }).click();
  await assistant
    .getByRole('textbox', { name: 'Edit message' })
    .fill('Corrected spoken AI response');
  await assistant.getByRole('button', { name: 'Save' }).click();

  await expect(assistant).toContainText('Corrected spoken AI response');
  await expect(page.locator('[data-message-id="call-later-user-speech"]')).toHaveAttribute(
    'data-stale-after-edit',
    'false'
  );

  const user = page.locator('[data-message-id="call-user-speech"]');
  await user.getByRole('button', { name: 'Message actions' }).click();
  await page.getByRole('menuitem', { name: 'Edit' }).click();
  await user.getByRole('textbox', { name: 'Edit message' }).fill('Corrected spoken user prompt');
  await user.getByRole('button', { name: 'Save' }).click();

  await expect(user).toContainText('Corrected spoken user prompt');
  await expect(assistant).toContainText('AI response to corrected spoken prompt');
  await expect(page.locator('[data-message-id="call-later-user-speech"]')).toHaveAttribute(
    'data-stale-after-edit',
    'true'
  );
  expect(requests).toEqual(['PATCH assistant', 'PATCH user', 'POST regenerate']);
  await expectNoBrowserErrors();
});
