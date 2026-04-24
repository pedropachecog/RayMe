import { expect, test, type Locator, type Page } from '@playwright/test';

const LONG_THREAD_SIZE = 520;
const SCROLL_STABILITY_TOLERANCE_PX = 192;

function longThread(threadId: string, count = LONG_THREAD_SIZE) {
  return {
    id: threadId,
    character_id: 'character-virtual',
    title: 'Virtual relay',
    character_name: 'Aster',
    character_portrait_url: null,
    messages: Array.from({ length: count }, (_, index) => ({
      id: `long-message-${index}`,
      thread_id: threadId,
      message_kind: index % 2 === 0 ? 'ai_text' : 'user_text',
      role: index % 2 === 0 ? 'assistant' : 'user',
      sequence: index,
      content_text:
        index % 17 === 0
          ? `Long thread message ${index}. This row has enough detail to force a measured height and keep virtual scrolling honest while content changes.`
          : `Long thread message ${index}`,
      selected_alternate_id: null,
      alternates: [],
      stale_after_edit: index === 14,
      created_at: null,
      updated_at: null
    }))
  };
}

function streamedDoneMessage(threadId: string) {
  return {
    id: 'streamed-done-message',
    thread_id: threadId,
    message_kind: 'ai_text',
    role: 'assistant',
    sequence: LONG_THREAD_SIZE + 1,
    content_text: 'Streaming token response fallback',
    selected_alternate_id: 'streamed-selected',
    alternates: [
      {
        id: 'streamed-selected',
        message_id: 'streamed-done-message',
        alternate_index: 0,
        content_text: 'Streaming token response complete',
        source_action: 'regenerate',
        created_at: null
      }
    ],
    stale_after_edit: false,
    created_at: null,
    updated_at: null
  };
}

async function mockLongThread(page: Page, threadId: string) {
  await page.route(`**/api/threads/${threadId}`, async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(longThread(threadId))
    });
  });
}

function messagesViewport(page: Page) {
  return page.getByLabel('Chat messages');
}

async function scrollViewportToTop(viewport: Locator) {
  await viewport.evaluate((element) => {
    element.scrollTop = 0;
    element.dispatchEvent(new Event('scroll', { bubbles: true }));
  });
}

async function scrollMetrics(viewport: Locator) {
  return viewport.evaluate((element) => ({
    scrollTop: element.scrollTop,
    distanceFromBottom: element.scrollHeight - element.scrollTop - element.clientHeight
  }));
}

test('long chat threads virtualize at 520 messages and jump back to latest', async ({ page }) => {
  const threadId = 'virtual-thread';
  await mockLongThread(page, threadId);

  await page.goto(`/chat/${threadId}`);

  const viewport = messagesViewport(page);
  await expect(viewport).toHaveAttribute('data-virtualized', 'true');
  await expect(viewport).toHaveAttribute('data-message-count', `${LONG_THREAD_SIZE}`);
  await expect(page.getByText(`Long thread message ${LONG_THREAD_SIZE - 1}`)).toBeVisible();
  const renderedRows = await page.locator('[data-virtual-index]').count();
  expect(renderedRows).toBeGreaterThan(0);
  expect(renderedRows).toBeLessThan(100);

  await scrollViewportToTop(viewport);

  const jump = page.getByRole('button', { name: 'Jump to latest' });
  await expect(jump).toBeVisible();

  await jump.click();

  await expect(page.getByText(`Long thread message ${LONG_THREAD_SIZE - 1}`)).toBeVisible();
  await expect(jump).toBeHidden();
});

test('streaming tokens keep scroll position stable when scrolled away in a virtualized thread', async ({
  page
}) => {
  const threadId = 'virtual-stream-thread';
  let releaseStream: () => void = () => undefined;
  const streamCanFinish = new Promise<void>((resolve) => {
    releaseStream = resolve;
  });

  await mockLongThread(page, threadId);
  await page.route(`**/api/chat/${threadId}/send`, async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toEqual({ content: 'Stream from bottom' });
    await streamCanFinish;
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: [
        'data: {"type":"token","text":"Streaming "}\n\n',
        'data: {"type":"token","text":"token response"}\n\n',
        `data: ${JSON.stringify({ type: 'done', message: streamedDoneMessage(threadId) })}\n\n`
      ].join('')
    });
  });

  await page.goto(`/chat/${threadId}`);
  await expect(page.getByText(`Long thread message ${LONG_THREAD_SIZE - 1}`)).toBeVisible();

  await scrollViewportToTop(messagesViewport(page));
  await expect(page.getByRole('button', { name: 'Jump to latest' })).toBeVisible();
  await page.getByRole('textbox', { name: 'Message' }).fill('Stream from bottom');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('textbox', { name: 'Message' })).toBeDisabled();

  const before = await scrollMetrics(messagesViewport(page));
  releaseStream();

  await expect(page.getByRole('textbox', { name: 'Message' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Jump to latest' })).toBeVisible();
  const after = await scrollMetrics(messagesViewport(page));

  expect(after.scrollTop).toBeGreaterThanOrEqual(before.scrollTop - SCROLL_STABILITY_TOLERANCE_PX);
  expect(after.scrollTop).toBeLessThanOrEqual(before.scrollTop + SCROLL_STABILITY_TOLERANCE_PX);
  expect(after.distanceFromBottom).toBeGreaterThanOrEqual(0);

  await page.getByRole('button', { name: 'Jump to latest' }).click();
  await expect(page.getByText('Streaming token response complete')).toBeVisible();
});

test.describe('mobile virtualized chat layout', () => {
  test.use({ viewport: { width: 393, height: 851 }, isMobile: true });

  test('jump control sits above the sticky composer and mobile bottom navigation', async ({ page }) => {
    const threadId = 'virtual-mobile-thread';
    await mockLongThread(page, threadId);

    await page.goto(`/chat/${threadId}`);

    const viewport = messagesViewport(page);
    await expect(viewport).toHaveAttribute('data-message-count', `${LONG_THREAD_SIZE}`);
    await scrollViewportToTop(viewport);

    const jump = page.getByRole('button', { name: 'Jump to latest' });
    await expect(jump).toBeVisible();

    const jumpBox = await jump.boundingBox();
    const composerBox = await page.locator('.composer').boundingBox();
    const bottomNavBox = await page.getByRole('navigation', { name: 'Primary mobile' }).boundingBox();

    expect(jumpBox).not.toBeNull();
    expect(composerBox).not.toBeNull();
    expect(bottomNavBox).not.toBeNull();
    expect(jumpBox!.y + jumpBox!.height).toBeLessThanOrEqual(composerBox!.y + 1);
    expect(composerBox!.y + composerBox!.height).toBeLessThanOrEqual(bottomNavBox!.y + 1);
    expect(jumpBox!.y + jumpBox!.height).toBeLessThanOrEqual(bottomNavBox!.y + 1);
  });
});
