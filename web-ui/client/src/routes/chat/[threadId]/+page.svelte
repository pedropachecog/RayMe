<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { ArrowLeft, RefreshCw } from 'lucide-svelte';
  import { tick } from 'svelte';

  import {
    appendTokenToStreamingMessage,
    createDraftMessage,
    loadThread,
    markStreamingMessageError,
    replaceStreamingMessage,
    sendChatMessage,
    type ChatMessageView
  } from '$lib/api/chat';
  import type { ThreadDetail } from '$lib/api/types';
  import ChatMessageBubble from '$lib/components/ChatMessageBubble.svelte';
  import Composer from '$lib/components/Composer.svelte';

  let thread = $state<ThreadDetail | null>(null);
  let messages = $state<ChatMessageView[]>([]);
  let loadState = $state<'loading' | 'ready' | 'error'>('loading');
  let sendState = $state<'idle' | 'sending'>('idle');
  let loadedThreadId = $state('');
  let pageError = $state('');
  let messagesViewport = $state<HTMLElement | null>(null);

  const threadId = $derived(page.params.threadId ?? '');
  const characterName = $derived(thread?.character_name ?? 'Character');
  const threadTitle = $derived(thread?.title?.trim() || characterName);
  const portraitUrl = $derived(thread?.character_portrait_url ?? null);
  const hasUserMessage = $derived(
    messages.some((message) => message.role === 'user' && message.message_kind === 'user_text')
  );

  $effect(() => {
    if (!threadId || threadId === loadedThreadId) {
      return;
    }

    loadedThreadId = threadId;
    void refreshThread(threadId);
  });

  async function refreshThread(id = threadId) {
    loadState = 'loading';
    pageError = '';

    try {
      const detail = await loadThread(id);
      thread = detail;
      messages = sortMessages(detail.messages);
      loadState = 'ready';
      await tick();
      scrollToLatest();
    } catch {
      thread = null;
      messages = [];
      loadState = 'error';
      pageError = 'RayMe could not load this thread.';
    }
  }

  async function handleSend(content: string) {
    if (!threadId || sendState === 'sending') {
      return;
    }

    sendState = 'sending';
    const nextSequence = nextMessageSequence(messages);
    const draftKey = `${Date.now()}`;
    const userMessage = createDraftMessage({
      id: `optimistic-user-${draftKey}`,
      thread_id: threadId,
      message_kind: 'user_text',
      role: 'user',
      sequence: nextSequence,
      content_text: content
    });
    const streamingMessage = createDraftMessage({
      id: `streaming-ai-${draftKey}`,
      thread_id: threadId,
      message_kind: 'ai_text',
      role: 'assistant',
      sequence: nextSequence + 1,
      content_text: '',
      streaming: true,
      retryContent: content
    });

    messages = [...messages, userMessage, streamingMessage];
    await tick();
    scrollToLatest();

    try {
      await sendChatMessage(threadId, content, {
        onToken: (token) => {
          messages = appendTokenToStreamingMessage(messages, streamingMessage.id, token);
          void tick().then(scrollToLatest);
        },
        onDone: (message) => {
          messages = sortMessages(replaceStreamingMessage(messages, streamingMessage.id, message));
        },
        onError: () => {
          messages = markStreamingMessageError(messages, streamingMessage.id, content);
        }
      });
    } catch {
      messages = markStreamingMessageError(messages, streamingMessage.id, content);
    } finally {
      sendState = 'idle';
      await tick();
      scrollToLatest();
    }
  }

  async function retryFailedMessage(message: ChatMessageView) {
    const retryContent = message.retryContent?.trim();
    if (!retryContent || sendState === 'sending') {
      return;
    }

    const messageIndex = messages.findIndex((candidate) => candidate.id === message.id);
    messages = messages.filter((candidate, index) => {
      if (candidate.id === message.id) {
        return false;
      }
      return !(index === messageIndex - 1 && candidate.id.startsWith('optimistic-user-'));
    });
    await handleSend(retryContent);
  }

  function sortMessages(nextMessages: ChatMessageView[]): ChatMessageView[] {
    return [...nextMessages].sort((left, right) => left.sequence - right.sequence);
  }

  function nextMessageSequence(currentMessages: ChatMessageView[]): number {
    return currentMessages.reduce((max, message) => Math.max(max, message.sequence), -1) + 1;
  }

  function scrollToLatest() {
    messagesViewport?.scrollTo({
      top: messagesViewport.scrollHeight,
      behavior: 'smooth'
    });
  }

  function isOpeningGreeting(message: ChatMessageView): boolean {
    return (
      !hasUserMessage &&
      message.role === 'assistant' &&
      message.message_kind === 'ai_text' &&
      message.sequence === 0 &&
      message.selected_alternate_id !== null
    );
  }
</script>

<section class="chat-route">
  <header class="chat-header">
    <button class="back-button" type="button" aria-label="Back to Home" onclick={() => goto('/')}>
      <ArrowLeft size={18} strokeWidth={1.8} aria-hidden="true" />
    </button>

    <div class="portrait" aria-hidden="true">
      {#if portraitUrl}
        <img src={portraitUrl} alt="" />
      {:else}
        <span>{characterName.slice(0, 1).toUpperCase()}</span>
      {/if}
    </div>

    <div class="thread-identity">
      <p>{characterName}</p>
      <h1>{threadTitle}</h1>
    </div>

    <button class="refresh-button" type="button" aria-label="Reload thread" onclick={() => refreshThread()}>
      <RefreshCw size={18} strokeWidth={1.8} aria-hidden="true" />
    </button>
  </header>

  {#if loadState === 'loading'}
    <div class="chat-state" aria-label="Loading chat">
      <span></span>
      <span></span>
      <span></span>
    </div>
  {:else if loadState === 'error'}
    <div class="chat-state error" role="status">
      <h2>Thread unavailable</h2>
      <p>{pageError}</p>
      <button type="button" onclick={() => refreshThread()}>
        <RefreshCw size={18} strokeWidth={1.8} aria-hidden="true" />
        <span>Retry</span>
      </button>
    </div>
  {:else}
    <div class="messages" bind:this={messagesViewport} aria-label="Chat messages">
      {#each messages as message (message.id)}
        <ChatMessageBubble
          {message}
          {characterName}
          {portraitUrl}
          openingGreeting={isOpeningGreeting(message)}
          onRetry={retryFailedMessage}
        />
      {/each}
    </div>

    <div class="composer-wrap">
      <Composer disabled={sendState === 'sending'} onSend={handleSend} />
    </div>
  {/if}
</section>

<style>
  .chat-route {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto;
    width: min(100%, 1020px);
    min-height: calc(100vh - 112px);
    margin: 0 auto;
    color: var(--color-text);
  }

  .chat-header {
    position: sticky;
    top: 0;
    z-index: 3;
    display: grid;
    grid-template-columns: 44px 48px minmax(0, 1fr) 44px;
    align-items: center;
    gap: var(--space-sm);
    min-height: 72px;
    padding: var(--space-sm) 0 var(--space-md);
    background: linear-gradient(180deg, var(--color-surface) 78%, rgba(6, 14, 32, 0));
  }

  .back-button,
  .refresh-button,
  .chat-state button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 44px;
    min-height: 44px;
    border: 0;
    border-radius: var(--radius-md);
    background: rgba(20, 31, 56, 0.72);
    color: var(--color-text);
  }

  .portrait {
    display: grid;
    width: 48px;
    height: 48px;
    place-items: center;
    overflow: hidden;
    border-radius: 50%;
    background: rgba(182, 160, 255, 0.16);
    color: var(--color-text);
    font-weight: 600;
  }

  .portrait img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .thread-identity {
    display: grid;
    min-width: 0;
    gap: 2px;
  }

  .thread-identity p {
    margin: 0;
    overflow: hidden;
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .thread-identity h1 {
    margin: 0;
    overflow: hidden;
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .messages {
    display: flex;
    min-height: 420px;
    flex-direction: column;
    gap: var(--space-md);
    overflow-y: auto;
    padding: var(--space-lg) 2px var(--space-xl);
    scroll-behavior: smooth;
  }

  .composer-wrap {
    position: sticky;
    bottom: 0;
    z-index: 2;
    padding: var(--space-md) 0 0;
    background: linear-gradient(180deg, rgba(6, 14, 32, 0), var(--color-surface) 28%);
  }

  .chat-state {
    display: grid;
    align-content: center;
    justify-items: center;
    min-height: 420px;
    gap: var(--space-sm);
    color: var(--color-text-muted);
  }

  .chat-state span {
    width: min(100%, 620px);
    height: 52px;
    border-radius: var(--radius-md);
    background: rgba(20, 31, 56, 0.7);
  }

  .chat-state.error {
    gap: var(--space-md);
    text-align: center;
  }

  .chat-state h2,
  .chat-state p {
    margin: 0;
  }

  .chat-state h2 {
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
  }

  .chat-state button {
    gap: var(--space-xs);
    padding: 0 14px;
    font-size: var(--font-label);
    font-weight: 600;
  }

  @media (max-width: 799px) {
    .chat-route {
      min-height: calc(100vh - 88px);
      padding-bottom: 64px;
    }

    .chat-header {
      grid-template-columns: 44px 44px minmax(0, 1fr) 44px;
    }

    .portrait {
      width: 44px;
      height: 44px;
    }
  }
</style>
