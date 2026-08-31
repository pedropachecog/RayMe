import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  applyEditedBackendMessage,
  appendTokenToStreamingMessage,
  CHAT_STREAM_ERROR_COPY,
  continueMessage,
  createRetryStatusController,
  createDraftMessage,
  editMessage,
  generationFailurePresentation,
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
import { generationFailureFromCallTerminal } from '../../src/lib/api/calls';
import type {
  GenerationFailure,
  ThreadDetail,
  ThreadMessage
} from '../../src/lib/api/types';
import chatApiSource from '../../src/lib/api/chat.ts?raw';
import bubbleSource from '../../src/lib/components/ChatMessageBubble.svelte?raw';
import composerSource from '../../src/lib/components/Composer.svelte?raw';
import messageActionMenuSource from '../../src/lib/components/MessageActionMenu.svelte?raw';
import swipeStepperSource from '../../src/lib/components/SwipeStepper.svelte?raw';
import callRouteSource from '../../src/routes/call/[threadId]/+page.svelte?raw';
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
  vi.useRealTimers();
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
    expect(routeSource).toContain('const composerText = composerDraft;');
  });

  it('user edit marks downstream stale and keeps the truncate-or-keep choice copy in the route', async () => {
    const editedUser: ThreadMessage = {
      ...staleUserMessage,
      stale_after_edit: false,
      content_text: 'Edited user branch'
    };
    const downstream: ThreadMessage = {
      ...selectedOpening,
      id: 'downstream-ai',
      sequence: 2,
      stale_after_edit: false
    };
    const fetchMock = installFetch(mockJsonResponse(editedUser));

    const response = await editMessage(staleUserMessage.id, 'Edited user branch');
    const request = lastRequest(fetchMock);
    const messages = applyEditedBackendMessage([editedUser, downstream], response);

    expect(request.url).toBe('/api/messages/user-stale');
    expect(request.init.method).toBe('PATCH');
    expect(JSON.parse(request.init.body as string)).toEqual({ content: 'Edited user branch' });
    expect(messages[0].content_text).toBe('Edited user branch');
    expect(messages[1].stale_after_edit).toBe(true);
    expect(bubbleSource).toContain('Stale');
    expect(chatApiSource).toContain(TRUNCATE_STALE_CONFIRMATION_COPY);
    expect(routeSource).toContain('TRUNCATE_STALE_CONFIRMATION_COPY');
    expect(routeSource).toContain('truncateStaleMessages');
    expect(routeSource).toContain('keepStaleMessages');
  });

  it('assistant edit keeps later messages fresh in the projected client state', () => {
    const editedAssistant: ThreadMessage = {
      ...selectedOpening,
      content_text: 'Corrected assistant response'
    };
    const downstream: ThreadMessage = {
      ...staleUserMessage,
      id: 'downstream-user',
      sequence: 2,
      stale_after_edit: false
    };

    const messages = applyEditedBackendMessage([selectedOpening, downstream], editedAssistant);

    expect(messages[0].content_text).toBe('Corrected assistant response');
    expect(messages[1].stale_after_edit).toBe(false);
  });

  it('assistant edit preserves a later stale AI message identity, alternate, and content', () => {
    const editedTarget: ThreadMessage = {
      id: 'stale-assistant-target',
      thread_id: 'thread-1',
      message_kind: 'ai_text',
      role: 'assistant',
      sequence: 2,
      content_text: 'Corrected second-to-last assistant response',
      selected_alternate_id: 'target-alternate',
      alternates: [
        {
          id: 'target-alternate',
          message_id: 'stale-assistant-target',
          alternate_index: 0,
          content_text: 'Corrected second-to-last assistant response',
          source_action: 'regenerate',
          created_at: null
        }
      ],
      stale_after_edit: true,
      created_at: null,
      updated_at: null
    };
    const staleUserBetween: ThreadMessage = {
      ...staleUserMessage,
      id: 'stale-user-between',
      sequence: 3
    };
    const finalStaleAssistant: ThreadMessage = {
      id: 'final-stale-assistant',
      thread_id: 'thread-1',
      message_kind: 'ai_text',
      role: 'assistant',
      sequence: 4,
      content_text: 'Final stale assistant response',
      selected_alternate_id: 'final-alternate',
      alternates: [
        {
          id: 'final-alternate',
          message_id: 'final-stale-assistant',
          alternate_index: 0,
          content_text: 'Final stale assistant response',
          source_action: 'regenerate',
          created_at: null
        }
      ],
      stale_after_edit: true,
      created_at: null,
      updated_at: null
    };

    const messages = applyEditedBackendMessage(
      [
        { ...editedTarget, content_text: 'Original second-to-last assistant response' },
        staleUserBetween,
        finalStaleAssistant
      ],
      editedTarget
    );

    expect(messages[0].content_text).toBe('Corrected second-to-last assistant response');
    expect(messages[2]).toEqual(finalStaleAssistant);
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

  it('shows retry metadata at exactly 300ms and never flickers at 299ms', () => {
    vi.useFakeTimers();
    const statuses: Array<string | null> = [];
    const retry = createRetryStatusController((status) => statuses.push(status));

    retry.schedule('Aster', 2);
    vi.advanceTimersByTime(299);
    expect(statuses).toEqual([]);

    vi.advanceTimersByTime(1);
    expect(statuses).toEqual(['Keeping Aster in character — attempt 2 of 3…']);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('clears retry feedback synchronously on accepted content and cannot flicker after dispose', () => {
    vi.useFakeTimers();
    const statuses: Array<string | null> = [];
    const retry = createRetryStatusController((status) => statuses.push(status));

    retry.schedule('Aster', 2);
    vi.advanceTimersByTime(300);
    retry.clear();
    expect(statuses.at(-1)).toBeNull();

    retry.schedule('Aster', 3);
    retry.dispose();
    vi.runAllTimers();
    expect(statuses).toEqual(['Keeping Aster in character — attempt 2 of 3…', null]);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('removes retry status on the first accepted Unicode chunk without rewriting it', () => {
    const accepted = 'Cafe\u0301 — 你好 — 👩🏽‍🚀';
    const streaming = {
      ...createDraftMessage({
        id: 'streaming-ai-typed',
        thread_id: 'thread-1',
        message_kind: 'ai_text',
        role: 'assistant',
        sequence: 2,
        content_text: '',
        streaming: true
      }),
      retryStatus: 'Keeping Aster in character — attempt 2 of 3…'
    };

    const [updated] = appendTokenToStreamingMessage([streaming], streaming.id, accepted);
    expect(updated.content_text).toBe(accepted);
    expect(updated.retryStatus).toBeNull();
  });

  it.each([
    [
      'llm_refusal_exhausted',
      'The model stayed out of character after three attempts. Try again or inspect the prompt.',
      ['try_again', 'inspect_prompt']
    ],
    [
      'prompt_budget_exceeded',
      'This request does not fit the configured context. Raise the context limit or reduce prompt/history content, then try again.',
      ['open_settings', 'inspect_prompt']
    ],
    [
      'provider_evidence_mismatch',
      'The selected model profile could not build this request. Check Prompt & Generation settings.',
      ['open_settings']
    ],
    [
      'invalid_model_profile',
      'The selected model profile could not build this request. Check Prompt & Generation settings.',
      ['open_settings']
    ],
    [
      'invalid_generation_request',
      'The selected model profile could not build this request. Check Prompt & Generation settings.',
      ['open_settings']
    ],
    ['llm_stream_failed', CHAT_STREAM_ERROR_COPY, ['try_again']]
  ] as const)(
    'maps %s to exact fixed copy and typed action intents',
    (code, expectedMessage, expectedActions) => {
      const presentation = generationFailurePresentation({
        type: 'generation_failure',
        code
      });
      expect(presentation).toEqual({
        message: expectedMessage,
        actions: expectedActions
      });
    }
  );

  it('turns a failed placeholder into a non-assistant failure row with no rejected content', () => {
    const prior = { ...selectedOpening };
    const streaming = createDraftMessage({
      id: 'streaming-ai-failure',
      thread_id: 'thread-1',
      message_kind: 'ai_text',
      role: 'assistant',
      sequence: 2,
      content_text: '',
      streaming: true,
      retryContent: 'Original user request'
    });
    const failure: GenerationFailure = {
      type: 'generation_failure',
      code: 'llm_refusal_exhausted'
    };

    const updated = markStreamingMessageError(
      [prior, streaming],
      streaming.id,
      'Original user request',
      failure
    );

    expect(updated[0]).toEqual(prior);
    expect(updated.filter((message) => message.role === 'assistant')).toHaveLength(1);
    expect(updated[1]).toMatchObject({
      role: 'event',
      content_text: '',
      streaming: false,
      error:
        'The model stayed out of character after three attempts. Try again or inspect the prompt.',
      retryContent: 'Original user request',
      failure,
      failureActions: ['try_again', 'inspect_prompt'],
      retryStatus: null
    });
    expect(JSON.stringify(updated)).not.toContain('REJECTED_PROSE_CANARY');
  });

  it('maps call terminal generation codes into the shared failure union only', () => {
    expect(
      generationFailureFromCallTerminal({
        type: 'error',
        turn_id: 'turn-1',
        code: 'prompt_budget_exceeded',
        message: 'REJECTED_PROSE_CANARY'
      })
    ).toEqual({ type: 'generation_failure', code: 'prompt_budget_exceeded' });
    expect(
      generationFailureFromCallTerminal({
        type: 'error',
        turn_id: 'turn-1',
        code: 'private_internal_code',
        message: 'REJECTED_PROSE_CANARY'
      })
    ).toEqual({ type: 'generation_failure', code: 'llm_generation_failed' });
  });

  it('keeps raw call terminal messages out of visible call failure state', () => {
    expect(callRouteSource).toContain(
      'generationFailureFromCallTerminal(errorEvent)'
    );
    expect(callRouteSource).toContain(
      'generationFailurePresentation(generationFailure).message'
    );
    expect(callRouteSource).not.toContain('errorEvent.message');
    expect(callRouteSource).not.toContain(
      'messageForCallFailure(event.code, event.message)'
    );
    expect(callRouteSource).not.toContain('const normalized = message?.trim()');
    expect(callRouteSource).not.toContain('REJECTED_PROSE_CANARY');
  });

  it('owns retry timers and abort cleanup through the route lifecycle', () => {
    expect(routeSource).toContain('onActivity: (activity) =>');
    expect(routeSource).toContain("activity.terminal_outcome === 'retry'");
    expect(routeSource).toContain('retryFeedback.schedule(characterName, activity.retry_count + 1)');
    expect(routeSource).toContain('onFailure: (failure) =>');
    expect(routeSource).toContain('retryFeedback.clear();');
    expect(routeSource).toContain('activeSendAbort?.abort();');
    expect(routeSource).toContain('onDestroy(() =>');
    expect(routeSource).toContain('activeRetryFeedback?.dispose();');
  });

  it('renders keyboard-reachable fixed failure actions and a polite retry announcement', () => {
    expect(routeSource).toContain('aria-live="polite"');
    expect(routeSource).toContain('{message.retryStatus}');
    expect(routeSource).toContain('generation-failure-actions');
    expect(routeSource).toContain('Try Again');
    expect(routeSource).toContain('Open Settings');
    expect(routeSource).toContain('Inspect Prompt');
    expect(routeSource).toContain("goto('/settings')");
    expect(routeSource).toContain('promptInspectorIntent = {');
    expect(routeSource).not.toContain('REJECTED_PROSE_CANARY');
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
