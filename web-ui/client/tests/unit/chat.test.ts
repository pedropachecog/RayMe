import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  applyEditedBackendMessage,
  appendTokenToStreamingMessage,
  CHAT_STREAM_ERROR_COPY,
  continueMessage,
  createDraftMessage,
  editMessage,
  generateSwipeAlternate,
  loadThread,
  markStreamingMessageError,
  messageActionsForRole,
  regenerateMessage,
  replaceStreamingMessage,
  selectSwipeAlternate,
  selectedAlternateIndex,
  selectedMessageContent,
  sendChatMessage,
  TRUNCATE_STALE_CONFIRMATION_COPY,
  upsertBackendMessage
} from '../../src/lib/api/chat';
import type { ThreadDetail, ThreadMessage } from '../../src/lib/api/types';
import chatApiSource from '../../src/lib/api/chat.ts?raw';
import bubbleSource from '../../src/lib/components/ChatMessageBubble.svelte?raw';
import composerSource from '../../src/lib/components/Composer.svelte?raw';
import messageActionMenuSource from '../../src/lib/components/MessageActionMenu.svelte?raw';
import swipeStepperSource from '../../src/lib/components/SwipeStepper.svelte?raw';
import routeSource from '../../src/routes/chat/[threadId]/+page.svelte?raw';

const selectedOpening: ThreadMessage = {
  id: 'opening',
  thread_id: 'thread-1',
  message_kind: 'ai_text',
  role: 'assistant',
  sequence: 0,
  content_text: 'Fallback greeting',
  selected_alternate_id: 'alt-2',
  alternates: [
    {
      id: 'alt-1',
      message_id: 'opening',
      alternate_index: 0,
      content_text: 'Fallback greeting',
      source_action: 'first_mes',
      created_at: null
    },
    {
      id: 'alt-2',
      message_id: 'opening',
      alternate_index: 1,
      content_text: 'Persisted alternate greeting',
      source_action: 'first_mes',
      created_at: null
    }
  ],
  stale_after_edit: false,
  created_at: null,
  updated_at: null
};

const staleUserMessage: ThreadMessage = {
  id: 'user-stale',
  thread_id: 'thread-1',
  message_kind: 'user_text',
  role: 'user',
  sequence: 1,
  content_text: 'Edited branch',
  selected_alternate_id: null,
  alternates: [],
  stale_after_edit: true,
  created_at: null,
  updated_at: null
};

const threadDetail: ThreadDetail = {
  id: 'thread-1',
  character_id: 'character-1',
  character_name: 'Aster',
  character_portrait_url: '/api/characters/character-1/portrait',
  title: 'Night relay',
  messages: [selectedOpening, staleUserMessage]
};

afterEach(() => {
  vi.restoreAllMocks();
});

function mockJsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init
  });
}

function installFetch(response: Response) {
  const fetchMock = vi.fn(async () => response);
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function lastRequest(fetchMock: ReturnType<typeof installFetch>) {
  const [url, init] = fetchMock.mock.calls.at(-1) ?? [];
  return { url: url as string, init: init as RequestInit };
}

describe('chat route contract', () => {
  it('does not render a Phase 1 call action', () => {
    expect(routeSource).not.toMatch(/>\s*Call\s*</);
    expect(routeSource).not.toContain('PhoneCall');
    expect(routeSource).not.toContain('phone-call');
  });

  it('exposes AI message actions and user edit-only menu contract', () => {
    expect(messageActionsForRole('assistant').map((action) => action.label)).toEqual([
      'Redo and Replace',
      'Redo',
      'Edit',
      'Continue'
    ]);
    expect(messageActionsForRole('user').map((action) => action.label)).toEqual(['Edit']);
    expect(messageActionMenuSource).toContain('messageActionsForRole(role)');
    expect(messageActionMenuSource).toContain('Message actions');
    expect(bubbleSource).toContain('MessageActionMenu');
    expect(bubbleSource).toContain('onAction');
    expect(bubbleSource).toContain('busyLabel');
    expect(routeSource).toContain('Regenerating');
    expect(routeSource).toContain('Updating alternate');
  });

  it('uses thread hydration for selected alternates, swipe controls, and stale flags', async () => {
    const fetchMock = installFetch(mockJsonResponse(threadDetail));

    const result = await loadThread('thread 1');
    const request = lastRequest(fetchMock);

    expect(request.url).toBe('/api/threads/thread%201');
    expect(request.init.method).toBe('GET');
    expect(selectedMessageContent(result.messages[0])).toBe('Persisted alternate greeting');
    expect(result.messages[0].selected_alternate_id).toBe('alt-2');
    expect(result.messages[0].alternates).toHaveLength(2);
    expect(result.messages[1].stale_after_edit).toBe(true);
    expect(routeSource).toContain('loadThread');
    expect(routeSource).toContain('selected_alternate_id');
    expect(bubbleSource).toContain('stale_after_edit');
    expect(bubbleSource).toContain('SwipeStepper');
    expect(swipeStepperSource).toContain('{safeIndex + 1} / {safeTotal}');
  });

  it('keeps alternate greeting selection as pre-create state instead of switching in Chat', () => {
    expect(chatApiSource).not.toContain('alternate_greeting_index');
    expect(routeSource).not.toContain('alternate_greeting_index');
    expect(routeSource).not.toMatch(/switch.*greeting|greeting.*switch/i);
    expect(bubbleSource).toContain('Selected greeting');
  });

  it('appends token chunks into one streaming AI bubble and replaces it with done.message', async () => {
    const doneMessage: ThreadMessage = {
      id: 'ai-done',
      thread_id: 'thread-1',
      message_kind: 'ai_text',
      role: 'assistant',
      sequence: 3,
      content_text: 'Done fallback',
      selected_alternate_id: 'alt-done',
      alternates: [
        {
          id: 'alt-done',
          message_id: 'ai-done',
          alternate_index: 0,
          content_text: 'Done selected branch',
          source_action: 'regenerate',
          created_at: null
        }
      ],
      stale_after_edit: true,
      created_at: null,
      updated_at: null
    };
    const stream = [
      'data: {"type":"token","text":"Hel"}\n\n',
      'data: {"type":"token","text":"lo"}\n\n',
      `data: ${JSON.stringify({ type: 'done', message: doneMessage })}\n\n`
    ].join('');
    const fetchMock = installFetch(
      new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    );
    const tokens: string[] = [];
    let done: ThreadMessage | null = null;
    const streaming = createDraftMessage({
      id: 'streaming-ai-1',
      thread_id: 'thread-1',
      message_kind: 'ai_text',
      role: 'assistant',
      sequence: 2,
      content_text: '',
      streaming: true
    });

    let messages = [streaming];
    await sendChatMessage('thread-1', 'Hello?', {
      onToken: (token) => {
        tokens.push(token);
        messages = appendTokenToStreamingMessage(messages, streaming.id, token);
      },
      onDone: (message) => {
        done = message;
        messages = replaceStreamingMessage(messages, streaming.id, message);
      }
    });

    const request = lastRequest(fetchMock);
    expect(request.url).toBe('/api/chat/thread-1/send');
    expect(request.init.method).toBe('POST');
    expect(JSON.parse(request.init.body as string)).toEqual({ content: 'Hello?' });
    expect(tokens).toEqual(['Hel', 'lo']);
    expect(done).toEqual(doneMessage);
    expect(messages).toHaveLength(1);
    expect(messages.filter((message) => message.streaming)).toHaveLength(0);
    expect(messages[0]).toMatchObject({
      id: 'ai-done',
      message_kind: 'ai_text',
      role: 'assistant',
      sequence: 3,
      selected_alternate_id: 'alt-done',
      stale_after_edit: true
    });
    expect(messages[0].alternates[0]).toMatchObject({
      id: 'alt-done',
      source_action: 'regenerate'
    });
  });

  it('regenerate consumes a backend response and does not append a second canonical bubble', async () => {
    const regenerated: ThreadMessage = {
      ...selectedOpening,
      content_text: 'Regenerated backend response',
      selected_alternate_id: 'regen-alt',
      alternates: [
        ...selectedOpening.alternates,
        {
          id: 'regen-alt',
          message_id: selectedOpening.id,
          alternate_index: 2,
          content_text: 'Regenerated backend response',
          source_action: 'regenerate',
          created_at: null
        }
      ]
    };
    const fetchMock = installFetch(mockJsonResponse(regenerated));

    const response = await regenerateMessage(selectedOpening.id);
    const request = lastRequest(fetchMock);
    const messages = upsertBackendMessage([selectedOpening, staleUserMessage], response);

    expect(request.url).toBe('/api/messages/opening/regenerate');
    expect(request.init.method).toBe('POST');
    expect(messages).toHaveLength(2);
    expect(messages.filter((message) => message.id === selectedOpening.id)).toHaveLength(1);
    expect(selectedMessageContent(messages[0])).toBe('Regenerated backend response');
    expect(messages[0].selected_alternate_id).toBe('regen-alt');
  });

  it('swipe generated alternate consumes backend returned alternate and selected branch becomes canonical', async () => {
    const generatedSwipe: ThreadMessage = {
      ...selectedOpening,
      content_text: 'Second generated swipe',
      selected_alternate_id: 'swipe-alt-2',
      alternates: [
        {
          id: 'swipe-alt-1',
          message_id: selectedOpening.id,
          alternate_index: 0,
          content_text: 'First generated swipe',
          source_action: 'swipe',
          created_at: null
        },
        {
          id: 'swipe-alt-2',
          message_id: selectedOpening.id,
          alternate_index: 1,
          content_text: 'Second generated swipe',
          source_action: 'swipe',
          created_at: null
        }
      ]
    };
    const fetchMock = installFetch(mockJsonResponse(generatedSwipe));

    const response = await generateSwipeAlternate(selectedOpening.id);
    let messages = upsertBackendMessage([selectedOpening], response);

    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/messages/opening/swipes',
      init: { method: 'POST' }
    });
    expect(selectedMessageContent(messages[0])).toBe('Second generated swipe');
    expect(selectedAlternateIndex(messages[0])).toBe(1);

    const selectedFirstSwipe: ThreadMessage = {
      ...generatedSwipe,
      content_text: 'First generated swipe',
      selected_alternate_id: 'swipe-alt-1'
    };
    const selectFetchMock = installFetch(mockJsonResponse(selectedFirstSwipe));

    const selected = await selectSwipeAlternate(selectedOpening.id, 'swipe-alt-1');
    messages = upsertBackendMessage(messages, selected);

    expect(lastRequest(selectFetchMock).url).toBe('/api/messages/opening/swipes');
    expect(JSON.parse(lastRequest(selectFetchMock).init.body as string)).toEqual({
      alternate_id: 'swipe-alt-1'
    });
    expect(selectedMessageContent(messages[0])).toBe('First generated swipe');
    expect(messages[0].selected_alternate_id).toBe('swipe-alt-1');
    expect(swipeStepperSource).toContain('aria-label="Redo"');
    expect(bubbleSource).toContain('onpointerdown={handlePointerDown}');
    expect(bubbleSource).toContain('swipe-preview-next');
  });

  it('continue sends composer text and consumes backend returned continue alternate/message', async () => {
    const continued: ThreadMessage = {
      ...selectedOpening,
      content_text: 'Generated continue from backend',
      selected_alternate_id: 'continue-alt',
      alternates: [
        {
          id: 'continue-alt',
          message_id: selectedOpening.id,
          alternate_index: 2,
          content_text: 'Generated continue from backend',
          source_action: 'continue',
          created_at: null
        }
      ]
    };
    const fetchMock = installFetch(mockJsonResponse(continued));

    const response = await continueMessage(selectedOpening.id, 'extend this thought');
    const request = lastRequest(fetchMock);
    const messages = upsertBackendMessage([selectedOpening], response);

    expect(request.url).toBe('/api/messages/opening/continue');
    expect(request.init.method).toBe('POST');
    expect(JSON.parse(request.init.body as string)).toEqual({
      composer_text: 'extend this thought'
    });
    expect(selectedMessageContent(messages[0])).toBe('Generated continue from backend');
    expect(messages[0].alternates[0].source_action).toBe('continue');
    expect(routeSource).toContain('composerDraft.trim()');
  });

  it('edit marks downstream stale and keeps the truncate-or-keep choice copy in the route', async () => {
    const editedOpening: ThreadMessage = {
      ...selectedOpening,
      content_text: 'Edited opening branch'
    };
    const downstream: ThreadMessage = {
      ...staleUserMessage,
      stale_after_edit: false
    };
    const fetchMock = installFetch(mockJsonResponse(editedOpening));

    const response = await editMessage(selectedOpening.id, 'Edited opening branch');
    const request = lastRequest(fetchMock);
    const messages = applyEditedBackendMessage([selectedOpening, downstream], response);

    expect(request.url).toBe('/api/messages/opening');
    expect(request.init.method).toBe('PATCH');
    expect(JSON.parse(request.init.body as string)).toEqual({ content: 'Edited opening branch' });
    expect(messages[0].content_text).toBe('Edited opening branch');
    expect(messages[1].stale_after_edit).toBe(true);
    expect(bubbleSource).toContain('Stale');
    expect(chatApiSource).toContain(TRUNCATE_STALE_CONFIRMATION_COPY);
    expect(routeSource).toContain('TRUNCATE_STALE_CONFIRMATION_COPY');
    expect(routeSource).toContain('truncateStaleMessages');
    expect(routeSource).toContain('keepStaleMessages');
  });

  it('renders exact LLM endpoint failure copy with retry/regenerate affordance', () => {
    const streaming = createDraftMessage({
      id: 'streaming-ai-1',
      thread_id: 'thread-1',
      message_kind: 'ai_text',
      role: 'assistant',
      sequence: 2,
      content_text: '',
      streaming: true
    });

    const [errored] = markStreamingMessageError([streaming], streaming.id, 'Retry me');

    expect(errored.error).toBe(CHAT_STREAM_ERROR_COPY);
    expect(errored.retryContent).toBe('Retry me');
    expect(chatApiSource).toContain(CHAT_STREAM_ERROR_COPY);
    expect(bubbleSource).toContain('{message.error}');
    expect(bubbleSource).toContain('Redo');
  });

  it('composer sends on Enter and preserves newline entry on Shift+Enter', () => {
    expect(composerSource).toContain("event.key !== 'Enter' || event.shiftKey");
    expect(composerSource).toContain('onsubmit={handleSubmit}');
    expect(composerSource).toContain('onkeydown={handleKeydown}');
  });

  it('virtualizes long chat threads and exposes jump-to-latest controls', () => {
    expect(routeSource).toContain("import { createVirtualizer } from '@tanstack/svelte-virtual'");
    expect(routeSource).toContain('const VIRTUALIZATION_THRESHOLD = 500');
    expect(routeSource).toContain('messages.length >= VIRTUALIZATION_THRESHOLD');
    expect(routeSource).toContain('$messageVirtualizer.getVirtualItems()');
    expect(routeSource).toContain('get(messageVirtualizer).measureElement(node)');
    expect(routeSource).toContain('shouldAdjustScrollPositionOnItemSizeChange');
    expect(routeSource).toContain("data-virtualized={shouldVirtualize ? 'true' : 'false'}");
    expect(routeSource).toContain('Jump to latest');
    expect(routeSource).toContain('showJumpToLatest = loadState ===');
  });

  it('keeps streaming scroll anchored only when already near the latest message', () => {
    expect(routeSource).toContain('const stickToLatest = isNearBottom();');
    expect(routeSource).toContain('const scrollAnchor = stickToLatest ? null : captureScrollAnchor();');
    expect(routeSource).toContain('scrollTop: messagesViewport.scrollTop');
    expect(routeSource).toContain('messagesViewport.scrollTop = scrollAnchor.scrollTop');
    expect(routeSource).toContain('appendTokenToStreamingMessage(messages, streamingMessage.id, token)');
    expect(routeSource).toContain('const shouldStick = stickToLatest && isNearBottom();');
    expect(routeSource).toContain('preserveCurrentScrollTop(shouldStick);');
    expect(routeSource).toContain('void settleSendLayout(shouldStick)');
    expect(routeSource).toContain('BOTTOM_PROXIMITY_PX');
  });

  it('keeps mobile chat controls and composer affordances at the required minimum size', () => {
    expect(routeSource).toContain('min-height: 44px');
    expect(bubbleSource).toContain('min-height: 44px');
    expect(bubbleSource).toContain('overflow-wrap: anywhere');
    expect(bubbleSource).toContain('@media (hover: none)');
    expect(composerSource).toContain('overflow-y: auto');
  });
});
