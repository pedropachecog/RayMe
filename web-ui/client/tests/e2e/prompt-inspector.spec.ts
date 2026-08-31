import { expect, test, type Page, type Route } from '@playwright/test';

import { fulfillJson, installBrowserErrorGuard } from './helpers/acceptance';

const threadId = 'thread-inspector';

function threadFixture() {
  return {
    id: threadId,
    character_id: 'character-1',
    title: 'Inspector relay',
    character_name: 'Aster',
    character_portrait_url: null,
    messages: [
      {
        id: 'user-1',
        thread_id: threadId,
        message_kind: 'user_text',
        role: 'user',
        sequence: 1,
        content_text: 'What do you see?',
        selected_alternate_id: null,
        alternates: [],
        stale_after_edit: false
      },
      {
        id: 'assistant-2',
        thread_id: threadId,
        message_kind: 'ai_text',
        role: 'assistant',
        sequence: 2,
        content_text: 'Fallback assistant content',
        selected_alternate_id: 'assistant-2-selected',
        alternates: [
          {
            id: 'assistant-2-selected',
            message_id: 'assistant-2',
            alternate_index: 0,
            content_text: 'Selected assistant branch with a complete target.',
            source_action: 'regenerate'
          }
        ],
        stale_after_edit: false
      },
      {
        id: 'assistant-stale',
        thread_id: threadId,
        message_kind: 'ai_text',
        role: 'assistant',
        sequence: 3,
        content_text: 'Stale target must not appear.',
        selected_alternate_id: null,
        alternates: [],
        stale_after_edit: true
      }
    ]
  };
}

function previewFixture(action: string, options: { hostile?: boolean; many?: boolean } = {}) {
  const hostile = options.hostile
    ? '<img src=x onerror="globalThis.INSPECTOR_XSS=1"> {{unknown}}\n  exact whitespace'
    : 'Stay fully in character.\n  Preserve exact spacing.';
  const wireMessages = Array.from({ length: options.many ? 12 : 1 }, (_, index) => ({
    order: index,
    role: index % 2 ? 'user' : 'system',
    content: `${hostile}${index ? `\nrow-${index}` : ''}`,
    section_ids: [`section-${index}`]
  }));
  const activity = options.many
    ? Array.from({ length: 8 }, (_, index) => ({
        action: index % 2 ? 'call_turn' : 'send',
        attempt: (index % 3) + 1,
        reason_code: 'policy_or_safety',
        prefix_characters: 120 + index,
        prefix_estimated_tokens: 30 + index,
        retry_count: Math.min(index % 3, 2),
        release_ms: index * 10,
        decision_ms: index * 11,
        terminal_outcome: index === 7 ? 'accepted' : 'retry',
        timestamp: `2026-08-31T08:00:${String(index).padStart(2, '0')}Z`
      }))
    : [];

  return {
    action,
    variant: action.startsWith('call_') ? 'call' : 'text',
    mode: 'roleplay',
    prompt_contract_version: 'rayme-prompt-contract-v1',
    request_shape_version: 'rayme-generation-request-v1',
    thread_id: threadId,
    configured_model: 'Qwen/Qwen3.5-27B',
    adapter: {
      configured: 'auto',
      effective: 'qwen_llama_server',
      name: 'qwen_llama_server',
      version: 'rayme-generation-request-v1'
    },
    configured_sampler: {
      max_tokens: action === 'call_turn' ? 1024 : 512,
      temperature: 0.8,
      top_p: 0.95,
      min_p: 0.05,
      top_k: 40,
      repetition_penalty: 1.05,
      presence_penalty: 0,
      frequency_penalty: 0
    },
    sections: wireMessages.map((message, index) => ({
      order: index,
      section_id: message.section_ids[0],
      logical_role: message.role,
      content: message.content,
      source: index ? 'selected_history' : 'global_preset',
      override_state: index ? 'selected' : 'inherited',
      mandatory: index === 0,
      estimated_tokens: 12 + index,
      atomic_group_id: null,
      included: true
    })),
    wire_messages: wireMessages,
    effective_request: {
      model: 'Qwen/Qwen3.5-27B',
      messages: wireMessages.map(({ role, content }) => ({ role, content })),
      stream: true,
      max_tokens: action === 'call_turn' ? 1024 : 512,
      temperature: 0.8,
      top_p: 0.95,
      presence_penalty: 0,
      frequency_penalty: 0,
      extra_body: {
        top_k: 40,
        min_p: 0.05,
        repeat_penalty: 1.05,
        chat_template_kwargs: { enable_thinking: false }
      },
      seed_policy: 'generated_at_send_time',
      omitted_fields: []
    },
    budget: {
      context_limit: 32768,
      configured_max_output: action === 'call_turn' ? 1024 : 512,
      safety_margin: 1639,
      input_budget: action === 'call_turn' ? 30105 : 30617,
      estimator_version: 'rayme-token-estimate-v1',
      estimated_input_tokens: 220,
      included_history_count: wireMessages.length - 1,
      dropped_history_count: 2,
      included_example_group_count: 1,
      dropped_example_group_count: 1,
      max_messages: action === 'call_offer' ? 48 : null,
      max_content_length: action === 'call_offer' ? 20000 : null,
      content_truncated: false
    },
    warnings: [],
    refusal_policy: {
      max_attempts: 3,
      max_retries: 2,
      prefix_max_characters: 640,
      prefix_max_estimated_tokens: 192,
      safe_sentence_min_visible_characters: 24,
      estimator_version: 'rayme-refusal-estimate-v1',
      retry_correction_present: true,
      correction_role: 'user',
      seed_policy: 'fresh_at_send_time_per_attempt',
      correction_prose_exposed: false,
      rejected_prose_exposed: false,
      exhausted_error_code: 'llm_refusal_exhausted'
    },
    recent_refusal_activity: activity
  };
}

type RouteOptions = {
  hostile?: boolean;
  many?: boolean;
  delayMs?: number;
  budgetFailure?: boolean;
};

async function installRoutes(page: Page, options: RouteOptions = {}) {
  const previewRequests: Array<Record<string, unknown>> = [];
  const mutationRequests: string[] = [];

  await page.route('**/api/threads/*', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, threadFixture());
      return;
    }
    mutationRequests.push(`${route.request().method()} ${new URL(route.request().url()).pathname}`);
    await route.abort();
  });
  await page.route('**/api/prompt-preview', async (route) => {
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    previewRequests.push(payload);
    if (options.delayMs) {
      await new Promise((resolve) => setTimeout(resolve, options.delayMs));
    }
    if (options.budgetFailure) {
      await fulfillJson(
        route,
        { detail: { code: 'prompt_budget_exceeded', message: 'PRIVATE_EXCEPTION_CANARY' } },
        422
      );
      return;
    }
    await fulfillJson(
      route,
      previewFixture(String(payload.action), { hostile: options.hostile, many: options.many })
    );
  });
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (
      request.method() !== 'GET' &&
      url.pathname.startsWith('/api/') &&
      url.pathname !== '/api/prompt-preview'
    ) {
      mutationRequests.push(`${request.method()} ${url.pathname}`);
    }
  });
  return { previewRequests, mutationRequests };
}

async function openInspector(page: Page) {
  await page.goto(`/chat/${threadId}`);
  await page.getByRole('textbox', { name: 'Message' }).fill('Exact unsent composer draft');
  await page.getByRole('button', { name: 'Inspect Prompt' }).click();
  await expect(page.getByRole('dialog', { name: 'Prompt Inspector' })).toBeVisible();
}

test('all six actions send exact preview-only payloads and keep offer ceilings isolated', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  const { previewRequests, mutationRequests } = await installRoutes(page);
  await openInspector(page);

  const dialog = page.getByRole('dialog', { name: 'Prompt Inspector' });
  await dialog.getByRole('button', { name: 'Preview Request' }).click();
  await expect(dialog.getByText('Preview only', { exact: true }).last()).toBeVisible();

  for (const action of ['Regenerate', 'Swipe', 'Continue']) {
    await dialog.getByLabel('Action').selectOption({ label: action });
    await dialog.getByLabel('Target turn').selectOption('assistant-2');
    await dialog.getByRole('button', { name: 'Preview Request' }).click();
    await expect(dialog.getByText('Preview out of date')).toHaveCount(0);
  }

  await dialog.getByLabel('Call').check();
  await dialog.getByLabel('Action').selectOption({ label: 'Call offer' });
  await dialog.getByRole('button', { name: 'Preview Request' }).click();
  await expect(dialog.getByText('48', { exact: true })).toBeVisible();
  await expect(dialog.getByText('20000', { exact: true })).toBeVisible();

  await dialog.getByLabel('Action').selectOption({ label: 'Call turn' });
  await dialog.getByLabel('Preview user transcript').fill('Local-only spoken turn');
  await dialog.getByRole('button', { name: 'Preview Request' }).click();
  await expect(dialog.getByText('1024', { exact: true }).first()).toBeVisible();
  await expect(dialog.getByText('AI-backend transport messages')).toHaveCount(0);
  await expect(dialog.getByText('AI-backend transport characters')).toHaveCount(0);

  expect(previewRequests).toEqual([
    { action: 'send', thread_id: threadId, composer_text: 'Exact unsent composer draft' },
    { action: 'regenerate', thread_id: threadId, target_message_id: 'assistant-2' },
    { action: 'swipe', thread_id: threadId, target_message_id: 'assistant-2' },
    {
      action: 'continue',
      thread_id: threadId,
      target_message_id: 'assistant-2',
      composer_text: 'Exact unsent composer draft'
    },
    { action: 'call_offer', thread_id: threadId },
    { action: 'call_turn', thread_id: threadId, composer_text: 'Local-only spoken turn' }
  ]);
  expect(mutationRequests).toEqual([]);
  await expect(page.locator('textarea[aria-label="Message"]')).toHaveValue('Exact unsent composer draft');
  assertNoBrowserErrors();
});

test('hostile and long rows stay escaped, complete, contained, stale-aware, and metadata-only', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installRoutes(page, { hostile: true, many: true });
  await openInspector(page);
  const dialog = page.getByRole('dialog', { name: 'Prompt Inspector' });
  await dialog.getByRole('button', { name: 'Preview Request' }).click();

  await expect(dialog.locator('img')).toHaveCount(0);
  await expect(dialog.getByText(/<img src=x onerror=/).first()).toBeVisible();
  await expect(dialog.getByText('{{unknown}}', { exact: false }).first()).toBeVisible();
  await expect(dialog.locator('.message-card')).toHaveCount(12);
  await expect(dialog.locator('.activity-row')).toHaveCount(8);
  await expect(dialog.getByText('No refusal retries recorded for this thread.')).toHaveCount(0);
  await expect(dialog.getByText(/API_KEY_CANARY|BEARER_CANARY|PRIVATE_EXCEPTION_CANARY/)).toHaveCount(0);
  expect(await page.evaluate(() => (globalThis as { INSPECTOR_XSS?: number }).INSPECTOR_XSS)).toBeUndefined();

  await dialog.getByRole('button', { name: 'Close Prompt Inspector' }).click();
  await page.getByRole('textbox', { name: 'Message' }).fill('Changed but still unsent');
  await page.getByRole('button', { name: 'Inspect Prompt' }).click();
  const reopened = page.getByRole('dialog', { name: 'Prompt Inspector' });
  await expect(reopened.getByText('Preview out of date')).toBeVisible();
  await reopened.getByText('Credential-free request JSON').click();
  const json = reopened.locator('.request-json');
  expect(await json.evaluate((element) => element.scrollWidth >= element.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  assertNoBrowserErrors();
});

test('loading remains closable and abortable, and typed budget failure preserves local input', async ({ page }) => {
  const delayed = await installRoutes(page, { delayMs: 1000 });
  await openInspector(page);
  const dialog = page.getByRole('dialog', { name: 'Prompt Inspector' });
  await dialog.getByRole('button', { name: 'Preview Request' }).click();
  await expect(dialog.getByText('Building request preview…')).toBeVisible();
  await expect(dialog.locator('.skeleton-row')).toHaveCount(3);
  await dialog.getByRole('button', { name: 'Close Prompt Inspector' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Inspect Prompt' })).toBeFocused();
  expect(delayed.mutationRequests).toEqual([]);

  await page.unrouteAll({ behavior: 'wait' });
  await installRoutes(page, { budgetFailure: true });
  await page.getByRole('button', { name: 'Inspect Prompt' }).click();
  const reopened = page.getByRole('dialog', { name: 'Prompt Inspector' });
  await reopened.getByRole('button', { name: 'Preview Request' }).click();
  await expect(reopened.getByText('This request does not fit the configured context. Raise the context limit or reduce prompt/history content, then try again.')).toBeVisible();
  await expect(page.locator('textarea[aria-label="Message"]')).toHaveValue('Exact unsent composer draft');
  await expect(reopened.getByText('PRIVATE_EXCEPTION_CANARY')).toHaveCount(0);
});

test('320px sheet traps focus, inerts background, restores trigger, and keeps priority header actions', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await installRoutes(page);
  await page.goto(`/chat/${threadId}`);

  await expect(page.getByRole('button', { name: 'Back to Home' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Inspect Prompt' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start call' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Reload thread' })).toHaveCount(0);
  await page.getByRole('button', { name: 'More thread actions' }).click();
  await expect(page.getByRole('menuitem', { name: 'Reload thread' })).toBeVisible();
  await page.keyboard.press('Escape');

  const trigger = page.getByRole('button', { name: 'Inspect Prompt' });
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: 'Prompt Inspector' });
  const box = await dialog.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.width).toBeLessThanOrEqual(320);
  expect(box!.height).toBeLessThanOrEqual(640);
  await expect(page.locator('.chat-header')).toHaveAttribute('inert', '');

  for (let index = 0; index < 12; index += 1) {
    await page.keyboard.press('Tab');
    expect(await page.evaluate(() => document.activeElement?.closest('[role="dialog"]') !== null)).toBe(true);
  }
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
