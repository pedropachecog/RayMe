import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  appendTokenToStreamingMessage,
  CHAT_STREAM_ERROR_COPY,
  createDraftMessage,
  loadThread,
  markStreamingMessageError,
  replaceStreamingMessage,
  selectedMessageContent,
  sendChatMessage
} from '../../src/lib/api/chat';
import type { ThreadDetail, ThreadMessage } from '../../src/lib/api/types';
import chatApiSource from '../../src/lib/api/chat.ts?raw';
import bubbleSource from '../../src/lib/components/ChatMessageBubble.svelte?raw';
import composerSource from '../../src/lib/components/Composer.svelte?raw';
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

  it('uses thread hydration for selected alternates, alternate lists, and stale flags', async () => {
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
    expect(bubbleSource).toContain('Message alternates');
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
    expect(bubbleSource).toContain('Regenerate');
  });

  it('composer sends on Enter and preserves newline entry on Shift+Enter', () => {
    expect(composerSource).toContain("event.key !== 'Enter' || event.shiftKey");
    expect(composerSource).toContain('onsubmit={handleSubmit}');
    expect(composerSource).toContain('onkeydown={handleKeydown}');
  });
});
