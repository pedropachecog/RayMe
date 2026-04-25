import { expect, test, type Page } from '@playwright/test';

import { fulfillJson, installBrowserErrorGuard } from './helpers/acceptance';
import { makeThreadDetail } from './helpers/fixtures';

const threadId = 'call-summary-thread';

test('ending a call returns chronological call_start speech and call_end rows to the thread', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installSummaryRoutes(page);

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();
  await page.getByRole('button', { name: 'End Call' }).click();
  await page.getByRole('button', { name: 'Return to Thread' }).click();

  const rows = page.locator('[data-message-kind]');
  await expect(rows).toHaveCount(6);
  await expect(rows.nth(0)).toHaveAttribute('data-message-kind', 'call_start');
  await expect(rows.nth(1)).toHaveAttribute('data-message-kind', 'user_speech');
  await expect(rows.nth(2)).toHaveAttribute('data-message-kind', 'ai_speech');
  await expect(rows.nth(3)).toHaveAttribute('data-message-kind', 'user_speech');
  await expect(rows.nth(4)).toHaveAttribute('data-message-kind', 'ai_speech');
  await expect(rows.nth(5)).toHaveAttribute('data-message-kind', 'call_end');
  assertNoBrowserErrors();
});

async function installSummaryRoutes(page: Page) {
  let callEnded = false;
  const callRows = [
    callRow('summary-call-start', 'call_start', 0, 'Call started.'),
    callRow('summary-user-1', 'user_speech', 1, 'Can you hear me?'),
    callRow('summary-ai-1', 'ai_speech', 2, 'I can hear you.'),
    callRow('summary-user-2', 'user_speech', 3, 'Tell me one thing.'),
    callRow('summary-ai-2', 'ai_speech', 4, 'The relay is stable.'),
    callRow('summary-call-end', 'call_end', 5, 'Call ended.')
  ];

  await page.route(`**/api/threads/${threadId}`, async (route) => {
    await fulfillJson(route, makeThreadDetail({
      id: threadId,
      title: 'Summary Thread',
      character_name: 'Summary Aster',
      messages: callEnded ? callRows : []
    }));
  });
  await page.route('**/api/calls', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-summary-01',
      thread_id: threadId,
      state: 'listening'
    }, 201);
  });
  await page.route('**/api/calls/*/end', async (route) => {
    callEnded = true;
    await fulfillJson(route, { state: 'ended', duration_ms: 18_000 });
  });
  await page.route('**/webrtc/offer', async (route) => {
    await fulfillJson(route, { type: 'answer', sdp: 'v=0\r\n' });
  });
}

function callRow(id: string, message_kind: string, sequence: number, content_text: string) {
  return {
    id,
    thread_id: threadId,
    message_kind,
    role: message_kind === 'user_speech' ? 'user' : 'assistant',
    sequence,
    content_text,
    selected_alternate_id: null,
    alternates: [],
    stale_after_edit: false,
    created_at: null,
    updated_at: null
  };
}
