<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { createVirtualizer } from '@tanstack/svelte-virtual';
  import { ArrowDown, ArrowLeft, RefreshCw } from 'lucide-svelte';
  import { tick } from 'svelte';
  import { get } from 'svelte/store';

  import {
    appendTokenToStreamingMessage,
    applyEditedBackendMessage,
    continueMessage,
    createDraftMessage,
    editMessage,
    generateSwipeAlternate,
    keepStaleMessages,
    loadThread,
    markStreamingMessageError,
    regenerateMessage,
    replaceStreamingMessage,
    selectSwipeAlternate,
    selectedMessageContent,
    sendChatMessage,
    truncateStaleMessages,
    TRUNCATE_STALE_CONFIRMATION_COPY,
    upsertBackendMessage,
    type ChatMessageView,
    type MessageActionId
  } from '$lib/api/chat';
  import type { ThreadDetail, ThreadMessage } from '$lib/api/types';
  import ChatMessageBubble from '$lib/components/ChatMessageBubble.svelte';
  import Composer from '$lib/components/Composer.svelte';

  type BusyAction = MessageActionId | 'truncate-stale' | 'keep-stale';

  const VIRTUALIZATION_THRESHOLD = 500;
  const BOTTOM_PROXIMITY_PX = 96;

  interface StaleContinueRequest {
    message: ChatMessageView;
    composerText: string;
  }

  interface ScrollAnchor {
    messageId: string;
    offsetTop: number;
    scrollTop: number;
  }

  let thread = $state<ThreadDetail | null>(null);
  let messages = $state<ChatMessageView[]>([]);
  let loadState = $state<'loading' | 'ready' | 'error'>('loading');
  let sendState = $state<'idle' | 'sending'>('idle');
  let actionState = $state<{ messageId: string; action: BusyAction } | null>(null);
  let loadedThreadId = $state('');
  let pageError = $state('');
  let actionError = $state('');
  let editingMessageId = $state<string | null>(null);
  let editDraft = $state('');
  let composerDraft = $state('');
  let staleConfirmation = $state<StaleContinueRequest | null>(null);
  let messagesViewport = $state<HTMLElement | null>(null);
  let showJumpToLatest = $state(false);

  const threadId = $derived(page.params.threadId ?? '');
  const characterName = $derived(thread?.character_name ?? 'Character');
  const characterInitials = $derived(initialsFor(characterName));
  const threadTitle = $derived(thread?.title?.trim() || characterName);
  const portraitUrl = $derived(thread?.character_portrait_url ?? null);
  const shouldVirtualize = $derived(messages.length >= VIRTUALIZATION_THRESHOLD);
  const hasUserMessage = $derived(
    messages.some((message) => message.role === 'user' && message.message_kind === 'user_text')
  );
  const messageVirtualizer = createVirtualizer<HTMLDivElement, HTMLDivElement>({
    count: 0,
    getScrollElement: () => messagesViewport,
    estimateSize: estimateMessageSize,
    getItemKey: (index) => messages[index]?.id ?? index,
    overscan: 10,
    gap: 16,
    enabled: false
  });

  $effect(() => {
    const virtualizer = get(messageVirtualizer);

    virtualizer.setOptions({
      count: shouldVirtualize ? messages.length : 0,
      getScrollElement: () => messagesViewport,
      estimateSize: estimateMessageSize,
      getItemKey: (index) => messages[index]?.id ?? index,
      overscan: 10,
      gap: 16,
      enabled: shouldVirtualize
    });
    virtualizer.shouldAdjustScrollPositionOnItemSizeChange = () => false;

    if (!shouldVirtualize) {
      showJumpToLatest = false;
    }
  });

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
      await settleMessageLayout(true, 'auto');
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

    const stickToLatest = isNearBottom();
    const scrollAnchor = stickToLatest ? null : captureScrollAnchor();
    let preservedScrollTop = scrollAnchor?.scrollTop ?? null;
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
    await settleSendLayout(stickToLatest, 'smooth');
    if (!stickToLatest && messagesViewport) {
      preservedScrollTop = messagesViewport.scrollTop;
    }

    try {
      await sendChatMessage(threadId, content, {
        onToken: (token) => {
          const shouldStick = stickToLatest && isNearBottom();
          preserveCurrentScrollTop(shouldStick);
          messages = appendTokenToStreamingMessage(messages, streamingMessage.id, token);
          void settleSendLayout(shouldStick);
        },
        onDone: (message) => {
          const shouldStick = stickToLatest && isNearBottom();
          preserveCurrentScrollTop(shouldStick);
          messages = sortMessages(replaceStreamingMessage(messages, streamingMessage.id, message));
          void settleSendLayout(shouldStick);
        },
        onError: () => {
          const shouldStick = stickToLatest && isNearBottom();
          preserveCurrentScrollTop(shouldStick);
          messages = markStreamingMessageError(messages, streamingMessage.id, content);
          void settleSendLayout(shouldStick);
        }
      });
    } catch {
      const shouldStick = stickToLatest && isNearBottom();
      preserveCurrentScrollTop(shouldStick);
      messages = markStreamingMessageError(messages, streamingMessage.id, content);
      await settleSendLayout(shouldStick);
    } finally {
      sendState = 'idle';
      const shouldStick = stickToLatest && isNearBottom();
      await settleSendLayout(shouldStick);
    }

    async function settleSendLayout(
      shouldStick: boolean,
      behavior: ScrollBehavior = 'auto'
    ): Promise<void> {
      await settleMessageLayout(shouldStick, behavior, shouldStick ? null : scrollAnchor);
      if (!shouldStick) {
        restoreScrollTop(preservedScrollTop);
        updateJumpVisibility();
      }
    }

    function preserveCurrentScrollTop(shouldStick: boolean) {
      if (!shouldStick && messagesViewport) {
        preservedScrollTop = messagesViewport.scrollTop;
      }
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

  function handleComposerDraftChange(content: string) {
    composerDraft = content;
  }

  function handleMessageAction(message: ChatMessageView, action: MessageActionId) {
    if (action === 'edit') {
      beginEdit(message);
      return;
    }

    if (action === 'regenerate') {
      void replaceFromBackend(message, action, () => regenerateMessage(message.id));
      return;
    }

    if (action === 'swipe') {
      void replaceFromBackend(message, action, () => generateSwipeAlternate(message.id));
      return;
    }

    void requestContinue(message);
  }

  function beginEdit(message: ChatMessageView) {
    if (actionState || sendState === 'sending') {
      return;
    }

    editingMessageId = message.id;
    editDraft = selectedMessageContent(message);
    actionError = '';
  }

  function cancelEdit() {
    editingMessageId = null;
    editDraft = '';
  }

  function setEditDraft(content: string) {
    editDraft = content;
  }

  async function saveEdit(message: ChatMessageView, content: string) {
    const saved = await replaceFromBackend(
      message,
      'edit',
      () => editMessage(message.id, content),
      applyEditedBackendMessage
    );

    if (saved) {
      cancelEdit();
    }
  }

  async function selectAlternate(message: ChatMessageView, alternateId: string) {
    await replaceFromBackend(message, 'swipe', () => selectSwipeAlternate(message.id, alternateId));
  }

  async function generateAlternate(message: ChatMessageView) {
    await replaceFromBackend(message, 'swipe', () => generateSwipeAlternate(message.id));
  }

  async function requestContinue(message: ChatMessageView) {
    const composerText = composerDraft.trim();

    if (hasStaleDownstream(message)) {
      staleConfirmation = { message, composerText };
      actionError = '';
      return;
    }

    await runContinue(message, composerText);
  }

  async function confirmStaleContinue(strategy: 'truncate' | 'keep') {
    const pending = staleConfirmation;
    if (!pending || actionState || sendState === 'sending') {
      return;
    }

    staleConfirmation = null;
    actionError = '';
    actionState = {
      messageId: pending.message.id,
      action: strategy === 'truncate' ? 'truncate-stale' : 'keep-stale'
    };

    let targetMessage: ChatMessageView = pending.message;

    try {
      if (strategy === 'truncate') {
        messages = sortMessages(await truncateStaleMessages(pending.message.id));
        targetMessage =
          messages.find((message) => message.id === pending.message.id) ?? pending.message;
      } else {
        const keptMessage = await keepStaleMessages(pending.message.id);
        messages = upsertBackendMessage(messages, keptMessage);
        targetMessage = messages.find((message) => message.id === keptMessage.id) ?? keptMessage;
      }
    } catch {
      actionError = 'RayMe could not resolve stale turns for Continue.';
      return;
    } finally {
      actionState = null;
    }

    await runContinue(targetMessage, pending.composerText);
  }

  async function runContinue(message: ChatMessageView, composerText: string) {
    const continued = await replaceFromBackend(message, 'continue', () =>
      continueMessage(message.id, composerText)
    );

    if (continued) {
      composerDraft = '';
    }
  }

  async function replaceFromBackend(
    message: ChatMessageView,
    action: BusyAction,
    operation: () => Promise<ThreadMessage>,
    applyMessage: (
      currentMessages: ChatMessageView[],
      backendMessage: ThreadMessage
    ) => ChatMessageView[] = upsertBackendMessage
  ): Promise<boolean> {
    if (actionState || sendState === 'sending') {
      return false;
    }

    actionState = { messageId: message.id, action };
    actionError = '';

    try {
      const backendMessage = await operation();
      const stickToLatest = isNearBottom();
      const scrollAnchor = stickToLatest ? null : captureScrollAnchor();
      messages = applyMessage(messages, backendMessage);
      await settleMessageLayout(stickToLatest, 'auto', scrollAnchor);
      return true;
    } catch {
      actionError = 'RayMe could not update this message.';
      return false;
    } finally {
      actionState = null;
    }
  }

  function hasStaleDownstream(message: ChatMessageView): boolean {
    return messages.some(
      (candidate) =>
        candidate.thread_id === message.thread_id &&
        candidate.sequence > message.sequence &&
        candidate.stale_after_edit
    );
  }

  function isMessageBusy(message: ChatMessageView): boolean {
    return actionState?.messageId === message.id || sendState === 'sending';
  }

  function busyLabelFor(message: ChatMessageView): string | null {
    if (actionState?.messageId !== message.id) {
      return null;
    }

    switch (actionState.action) {
      case 'regenerate':
        return 'Regenerating';
      case 'swipe':
        return 'Updating alternate';
      case 'continue':
        return 'Continuing';
      case 'edit':
        return 'Saving';
      case 'truncate-stale':
        return 'Removing stale turns';
      case 'keep-stale':
        return 'Keeping stale turns';
      default:
        return null;
    }
  }

  function sortMessages(nextMessages: ChatMessageView[]): ChatMessageView[] {
    return [...nextMessages].sort((left, right) => left.sequence - right.sequence);
  }

  function nextMessageSequence(currentMessages: ChatMessageView[]): number {
    return currentMessages.reduce((max, message) => Math.max(max, message.sequence), -1) + 1;
  }

  function estimateMessageSize(index: number): number {
    const message = messages[index];
    const contentLength = selectedMessageContent(
      message ?? { content_text: '', selected_alternate_id: null, alternates: [] }
    ).length;
    const baseSize = message?.role === 'user' ? 88 : 112;
    const streamingReserve = message?.streaming ? 28 : 0;
    const staleReserve = message?.stale_after_edit ? 12 : 0;
    const editReserve = editingMessageId === message?.id ? 132 : 0;
    const alternateReserve = message && message.role === 'assistant' ? 44 : 0;

    return Math.min(
      260,
      baseSize +
        Math.ceil(contentLength / 90) * 20 +
        streamingReserve +
        staleReserve +
        editReserve +
        alternateReserve
    );
  }

  function measureVirtualRow(node: HTMLDivElement) {
    get(messageVirtualizer).measureElement(node);

    return {
      update() {
        get(messageVirtualizer).measureElement(node);
      },
      destroy() {
        get(messageVirtualizer).measureElement(null);
      }
    };
  }

  async function settleMessageLayout(
    stickToLatest: boolean,
    behavior: ScrollBehavior = 'smooth',
    scrollAnchor: ScrollAnchor | null = null
  ) {
    await tick();
    await nextAnimationFrame();
    get(messageVirtualizer).measure();

    if (stickToLatest) {
      scrollToLatest(behavior);
      await nextAnimationFrame();
      scrollToLatest('auto');
    } else {
      restoreScrollAnchor(scrollAnchor);
      updateJumpVisibility();
    }
  }

  function nextAnimationFrame(): Promise<void> {
    if (typeof requestAnimationFrame !== 'function') {
      return Promise.resolve();
    }

    return new Promise((resolve) => requestAnimationFrame(() => resolve()));
  }

  function scrollToLatest(behavior: ScrollBehavior = 'smooth') {
    if (!messagesViewport) {
      return;
    }

    messagesViewport.scrollTo({
      top: Math.max(messagesViewport.scrollHeight, get(messageVirtualizer).getTotalSize()),
      behavior
    });

    showJumpToLatest = false;
  }

  function isNearBottom(): boolean {
    if (!messagesViewport) {
      return true;
    }

    return (
      messagesViewport.scrollHeight - messagesViewport.scrollTop - messagesViewport.clientHeight <=
      BOTTOM_PROXIMITY_PX
    );
  }

  function updateJumpVisibility() {
    showJumpToLatest = loadState === 'ready' && !isNearBottom();
  }

  function handleMessagesScroll() {
    updateJumpVisibility();
  }

  function captureScrollAnchor(): ScrollAnchor | null {
    if (!messagesViewport) {
      return null;
    }

    const viewportTop = messagesViewport.getBoundingClientRect().top;
    const rows = Array.from(messagesViewport.querySelectorAll<HTMLElement>('[data-message-id]'));
    const anchorRow = rows.find((row) => row.getBoundingClientRect().bottom >= viewportTop);

    if (!anchorRow?.dataset.messageId) {
      return null;
    }

    return {
      messageId: anchorRow.dataset.messageId,
      offsetTop: anchorRow.getBoundingClientRect().top - viewportTop,
      scrollTop: messagesViewport.scrollTop
    };
  }

  function restoreScrollAnchor(scrollAnchor: ScrollAnchor | null) {
    if (!messagesViewport || !scrollAnchor) {
      return;
    }

    const viewportTop = messagesViewport.getBoundingClientRect().top;
    const anchorRow = Array.from(
      messagesViewport.querySelectorAll<HTMLElement>('[data-message-id]')
    ).find((row) => row.dataset.messageId === scrollAnchor.messageId);

    if (!anchorRow) {
      messagesViewport.scrollTop = scrollAnchor.scrollTop;
      return;
    }

    const nextOffsetTop = anchorRow.getBoundingClientRect().top - viewportTop;
    messagesViewport.scrollTop += nextOffsetTop - scrollAnchor.offsetTop;

    if (Math.abs(messagesViewport.scrollTop - scrollAnchor.scrollTop) > 4) {
      messagesViewport.scrollTop = scrollAnchor.scrollTop;
    }
  }

  function restoreScrollTop(scrollTop: number | null) {
    if (!messagesViewport || scrollTop === null) {
      return;
    }

    messagesViewport.scrollTop = scrollTop;
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

  function initialsFor(value: string): string {
    return value
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('');
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
        <span>{characterInitials || 'R'}</span>
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
    <div
      class:virtualized={shouldVirtualize}
      class="messages"
      bind:this={messagesViewport}
      aria-label="Chat messages"
      data-message-count={messages.length}
      data-virtualized={shouldVirtualize ? 'true' : 'false'}
      onscroll={handleMessagesScroll}
    >
      {#if shouldVirtualize}
        <div class="virtual-spacer" style={`height: ${$messageVirtualizer.getTotalSize()}px;`}>
          {#each $messageVirtualizer.getVirtualItems() as virtualRow (virtualRow.key)}
            {@const message = messages[virtualRow.index]}
            {#if message}
              <div
                class="virtual-row"
                data-index={virtualRow.index}
                data-virtual-index={virtualRow.index}
                style={`transform: translateY(${virtualRow.start}px);`}
                use:measureVirtualRow
              >
                <ChatMessageBubble
                  {message}
                  {characterName}
                  {portraitUrl}
                  openingGreeting={isOpeningGreeting(message)}
                  actionBusy={isMessageBusy(message)}
                  busyLabel={busyLabelFor(message)}
                  editing={editingMessageId === message.id}
                  {editDraft}
                  onRetry={retryFailedMessage}
                  onAction={handleMessageAction}
                  onEditDraftChange={setEditDraft}
                  onSaveEdit={saveEdit}
                  onCancelEdit={cancelEdit}
                  onSelectAlternate={selectAlternate}
                  onGenerateAlternate={generateAlternate}
                />
              </div>
            {/if}
          {/each}
        </div>
      {:else}
        {#each messages as message (message.id)}
          <ChatMessageBubble
            {message}
            {characterName}
            {portraitUrl}
            openingGreeting={isOpeningGreeting(message)}
            actionBusy={isMessageBusy(message)}
            busyLabel={busyLabelFor(message)}
            editing={editingMessageId === message.id}
            {editDraft}
            onRetry={retryFailedMessage}
            onAction={handleMessageAction}
            onEditDraftChange={setEditDraft}
            onSaveEdit={saveEdit}
            onCancelEdit={cancelEdit}
            onSelectAlternate={selectAlternate}
            onGenerateAlternate={generateAlternate}
          />
        {/each}
      {/if}
    </div>

    <div class="composer-wrap">
      {#if showJumpToLatest}
        <div class="jump-row">
          <button class="jump-to-latest" type="button" onclick={() => scrollToLatest()}>
            <ArrowDown size={16} strokeWidth={1.8} aria-hidden="true" />
            <span>Jump to latest</span>
          </button>
        </div>
      {/if}
      {#if actionError}
        <p class="action-error" role="status">{actionError}</p>
      {/if}
      <Composer
        disabled={sendState === 'sending'}
        value={composerDraft}
        onDraftChange={handleComposerDraftChange}
        onSend={handleSend}
      />
    </div>
  {/if}

  {#if staleConfirmation}
    <div class="confirmation-backdrop">
      <div class="stale-confirmation" role="dialog" aria-modal="true" aria-labelledby="stale-title">
        <h2 id="stale-title">Continue from edited branch</h2>
        <p>{TRUNCATE_STALE_CONFIRMATION_COPY}</p>
        <div class="confirmation-actions">
          <button class="secondary" type="button" onclick={() => (staleConfirmation = null)}>
            Cancel
          </button>
          <button type="button" onclick={() => confirmStaleContinue('keep')}>Keep stale turns</button>
          <button class="destructive" type="button" onclick={() => confirmStaleContinue('truncate')}>
            Remove stale turns
          </button>
        </div>
      </div>
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

  .messages.virtualized {
    display: block;
    contain: strict;
  }

  .virtual-spacer {
    position: relative;
    width: 100%;
    min-height: 100%;
  }

  .virtual-row {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    min-height: 64px;
  }

  .composer-wrap {
    position: sticky;
    bottom: 0;
    z-index: 2;
    padding: var(--space-md) 0 0;
    background: linear-gradient(180deg, rgba(6, 14, 32, 0), var(--color-surface) 28%);
  }

  .jump-row {
    display: flex;
    justify-content: center;
    margin-bottom: var(--space-sm);
    pointer-events: none;
  }

  .jump-to-latest {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 44px;
    gap: var(--space-xs);
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 14px;
    background: rgba(25, 37, 64, 0.78);
    color: var(--color-text);
    box-shadow: 0 18px 44px rgba(0, 0, 0, 0.28);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
    pointer-events: auto;
    backdrop-filter: blur(20px);
  }

  .jump-to-latest:hover,
  .jump-to-latest:focus-visible {
    background: rgba(182, 160, 255, 0.2);
  }

  .action-error {
    margin: 0 0 var(--space-sm);
    border-radius: var(--radius-sm);
    padding: var(--space-sm) var(--space-md);
    background: rgba(255, 113, 108, 0.1);
    color: var(--color-danger);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .confirmation-backdrop {
    position: fixed;
    inset: 0;
    z-index: 20;
    display: grid;
    place-items: center;
    padding: var(--space-lg);
    background: rgba(6, 14, 32, 0.68);
    backdrop-filter: blur(10px);
  }

  .stale-confirmation {
    display: grid;
    width: min(100%, 460px);
    gap: var(--space-md);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(25, 37, 64, 0.92);
    color: var(--color-text);
    box-shadow: 0 24px 80px rgba(0, 0, 0, 0.42);
  }

  .stale-confirmation h2,
  .stale-confirmation p {
    margin: 0;
  }

  .stale-confirmation h2 {
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
  }

  .stale-confirmation p {
    color: var(--color-text-muted);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  .confirmation-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--space-xs);
  }

  .confirmation-actions button {
    min-height: 44px;
    border: 0;
    border-radius: var(--radius-sm);
    padding: 0 12px;
    background: rgba(182, 160, 255, 0.18);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
  }

  .confirmation-actions button.secondary {
    background: rgba(64, 72, 93, 0.28);
    color: var(--color-text-muted);
  }

  .confirmation-actions button.destructive {
    background: var(--color-danger);
    color: var(--color-surface);
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

    .composer-wrap {
      bottom: 64px;
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
