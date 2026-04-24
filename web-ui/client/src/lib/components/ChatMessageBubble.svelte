<script lang="ts">
  import { RefreshCw } from 'lucide-svelte';

  import {
    selectedAlternateIndex,
    selectedMessageContent,
    sortedMessageAlternates,
    type ChatMessageView,
    type MessageActionId
  } from '$lib/api/chat';
  import { renderTrustedMarkdown } from '$lib/sanitizer/renderMarkdown';
  import MessageActionMenu from './MessageActionMenu.svelte';
  import SwipeStepper from './SwipeStepper.svelte';

  interface Props {
    message: ChatMessageView;
    characterName?: string | null;
    portraitUrl?: string | null;
    openingGreeting?: boolean;
    actionBusy?: boolean;
    busyLabel?: string | null;
    editing?: boolean;
    editDraft?: string;
    onRetry?: (message: ChatMessageView) => void;
    onAction?: (message: ChatMessageView, action: MessageActionId) => void;
    onEditDraftChange?: (content: string) => void;
    onSaveEdit?: (message: ChatMessageView, content: string) => void | Promise<void>;
    onCancelEdit?: () => void;
    onSelectAlternate?: (message: ChatMessageView, alternateId: string) => void | Promise<void>;
    onGenerateAlternate?: (message: ChatMessageView) => void | Promise<void>;
  }

  let {
    message,
    characterName = 'Character',
    portraitUrl = null,
    openingGreeting = false,
    actionBusy = false,
    busyLabel = null,
    editing = false,
    editDraft = '',
    onRetry,
    onAction,
    onEditDraftChange,
    onSaveEdit,
    onCancelEdit,
    onSelectAlternate,
    onGenerateAlternate
  }: Props = $props();

  const isUser = $derived(message.role === 'user');
  const displayName = $derived(isUser ? 'You' : characterName || 'Character');
  const avatarInitial = $derived((characterName || 'R').trim().slice(0, 1).toUpperCase() || 'R');
  const content = $derived(selectedMessageContent(message));
  const renderedContent = $derived(renderTrustedMarkdown(content));
  const orderedAlternates = $derived(sortedMessageAlternates(message));
  const currentAlternateIndex = $derived(selectedAlternateIndex(message));
  const swipeTotal = $derived(Math.max(orderedAlternates.length, 1));
  const canTouchSwipe = $derived(
    !isUser && !actionBusy && !editing && orderedAlternates.length > 1
  );
  const showActions = $derived(
    !message.streaming && !message.error && (message.role === 'assistant' || message.role === 'user')
  );
  const showSwipeStepper = $derived(!isUser && !message.streaming && !message.error);
  let pointerStart = $state<{ x: number; y: number; id: number } | null>(null);
  let swipePreview = $state<'previous' | 'next' | null>(null);

  function retry() {
    onRetry?.(message);
  }

  function chooseAction(action: MessageActionId) {
    onAction?.(message, action);
  }

  function updateEditDraft(event: Event) {
    onEditDraftChange?.((event.currentTarget as HTMLTextAreaElement).value);
  }

  function saveEdit() {
    const nextContent = editDraft.trim();
    if (!nextContent) {
      return;
    }

    void onSaveEdit?.(message, nextContent);
  }

  function selectPreviousAlternate() {
    const alternate = orderedAlternates[currentAlternateIndex - 1];
    if (alternate) {
      void onSelectAlternate?.(message, alternate.id);
    }
  }

  function selectNextAlternate() {
    const alternate = orderedAlternates[currentAlternateIndex + 1];
    if (alternate) {
      void onSelectAlternate?.(message, alternate.id);
    }
  }

  function generateAlternate() {
    void onGenerateAlternate?.(message);
  }

  function handlePointerDown(event: PointerEvent) {
    if (!canTouchSwipe) {
      return;
    }

    pointerStart = { x: event.clientX, y: event.clientY, id: event.pointerId };
    swipePreview = null;
  }

  function handlePointerMove(event: PointerEvent) {
    if (!pointerStart || pointerStart.id !== event.pointerId || !canTouchSwipe) {
      return;
    }

    swipePreview = swipeTarget(event.clientX - pointerStart.x, event.clientY - pointerStart.y, 24);
  }

  function handlePointerUp(event: PointerEvent) {
    if (!pointerStart || pointerStart.id !== event.pointerId || !canTouchSwipe) {
      resetPointerSwipe();
      return;
    }

    const target = swipeTarget(event.clientX - pointerStart.x, event.clientY - pointerStart.y, 56);
    resetPointerSwipe();

    if (target === 'previous') {
      selectPreviousAlternate();
    } else if (target === 'next') {
      selectNextAlternate();
    }
  }

  function resetPointerSwipe() {
    pointerStart = null;
    swipePreview = null;
  }

  function swipeTarget(
    deltaX: number,
    deltaY: number,
    threshold: number
  ): 'previous' | 'next' | null {
    if (Math.abs(deltaX) < threshold || Math.abs(deltaX) < Math.abs(deltaY) * 1.25) {
      return null;
    }

    if (deltaX > 0 && currentAlternateIndex > 0) {
      return 'previous';
    }

    if (deltaX < 0 && currentAlternateIndex < orderedAlternates.length - 1) {
      return 'next';
    }

    return null;
  }
</script>

<article
  class:user={isUser}
  class:assistant={!isUser}
  class:stale={message.stale_after_edit}
  class:swipe-preview-previous={swipePreview === 'previous'}
  class:swipe-preview-next={swipePreview === 'next'}
  class="message-row"
  data-message-id={message.id}
  data-message-kind={message.message_kind}
  data-message-role={message.role}
  data-message-sequence={message.sequence}
  data-selected-alternate-id={message.selected_alternate_id ?? ''}
  data-stale-after-edit={message.stale_after_edit ? 'true' : 'false'}
  data-streaming={message.streaming ? 'true' : 'false'}
  onpointerdown={handlePointerDown}
  onpointermove={handlePointerMove}
  onpointerup={handlePointerUp}
  onpointercancel={resetPointerSwipe}
>
  {#if !isUser}
    <div class="avatar" aria-hidden="true">
      {#if portraitUrl}
        <img src={portraitUrl} alt="" />
      {:else}
        <span>{avatarInitial}</span>
      {/if}
    </div>
  {/if}

  <div class="bubble">
    {#if showActions}
      <div class="message-actions">
        <MessageActionMenu role={message.role} disabled={actionBusy} onAction={chooseAction} />
      </div>
    {/if}

    <div class="message-meta">
      <span>{displayName}</span>
      {#if openingGreeting}
        <span class="chip selected">Selected greeting</span>
      {/if}
      {#if message.stale_after_edit}
        <span class="chip stale-chip">Stale</span>
      {/if}
      {#if message.streaming}
        <span class="chip streaming-chip">Streaming</span>
      {/if}
      {#if actionBusy && busyLabel}
        <span class="chip busy-chip">{busyLabel}</span>
      {/if}
    </div>

    {#if editing}
      <div class="edit-panel">
        <textarea
          value={editDraft}
          aria-label="Edit message"
          disabled={actionBusy}
          rows="4"
          oninput={updateEditDraft}
        ></textarea>
        <div class="edit-actions">
          <button class="secondary" type="button" disabled={actionBusy} onclick={() => onCancelEdit?.()}>
            Cancel
          </button>
          <button type="button" disabled={actionBusy || editDraft.trim().length === 0} onclick={saveEdit}>
            Save
          </button>
        </div>
      </div>
    {:else if message.error}
      <div class="error-state" role="alert">
        <p>{message.error}</p>
        <button type="button" onclick={retry}>
          <RefreshCw size={16} strokeWidth={1.8} aria-hidden="true" />
          <span>Regenerate</span>
        </button>
      </div>
    {:else}
      <div class="message-content">
        {@html renderedContent}
        {#if message.streaming}
          <span class="stream-caret" aria-hidden="true"></span>
        {/if}
      </div>
    {/if}

    {#if showSwipeStepper}
      <SwipeStepper
        currentIndex={currentAlternateIndex}
        total={swipeTotal}
        disabled={actionBusy}
        onPrevious={selectPreviousAlternate}
        onNext={selectNextAlternate}
        onGenerate={generateAlternate}
      />
    {/if}
  </div>
</article>

<style>
  .message-row {
    display: flex;
    align-items: flex-end;
    gap: var(--space-sm);
    width: 100%;
    min-height: 52px;
  }

  .message-row.user {
    justify-content: flex-end;
  }

  .message-row.assistant {
    justify-content: flex-start;
  }

  .message-row.stale {
    border-left: 2px solid rgba(255, 113, 108, 0.7);
    padding-left: var(--space-sm);
  }

  .avatar {
    display: grid;
    width: 36px;
    height: 36px;
    flex: 0 0 auto;
    place-items: center;
    overflow: hidden;
    border-radius: 50%;
    background: rgba(112, 170, 255, 0.16);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
  }

  .avatar img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .bubble {
    position: relative;
    display: grid;
    width: min(76%, 680px);
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    padding: 12px 14px;
    background: rgba(20, 31, 56, 0.72);
    color: var(--color-text);
    box-shadow: 0 18px 48px rgba(0, 0, 0, 0.16);
    touch-action: pan-y;
    transition: transform 120ms ease;
  }

  .message-row.swipe-preview-previous .bubble {
    transform: translateX(10px);
  }

  .message-row.swipe-preview-next .bubble {
    transform: translateX(-10px);
  }

  .user .bubble {
    background: rgba(182, 160, 255, 0.18);
  }

  .message-actions {
    position: absolute;
    top: 6px;
    right: 6px;
    z-index: 3;
    opacity: 0;
    transition: opacity 120ms ease;
  }

  .message-row:hover .message-actions,
  .message-row:focus-within .message-actions {
    opacity: 1;
  }

  @media (hover: none) {
    .message-actions {
      opacity: 1;
    }
  }

  .message-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-xs);
    padding-right: 46px;
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .chip {
    display: inline-flex;
    align-items: center;
    min-height: 20px;
    border-radius: 999px;
    padding: 0 8px;
    background: rgba(64, 72, 93, 0.28);
    color: var(--color-text-muted);
    font-size: var(--font-label);
    line-height: var(--line-label);
  }

  .chip.selected,
  .streaming-chip,
  .busy-chip {
    background: rgba(182, 160, 255, 0.18);
    color: var(--color-text);
  }

  .stale-chip {
    color: var(--color-danger);
  }

  .message-content,
  .error-state p,
  .edit-panel textarea {
    color: var(--color-text);
    font-size: var(--font-body);
    font-weight: 400;
    line-height: var(--line-body);
    overflow-wrap: anywhere;
  }

  .message-content :global(p) {
    margin: 0;
  }

  .message-content :global(p + p) {
    margin-top: var(--space-sm);
  }

  .message-content :global(a) {
    color: #70aaff;
  }

  .stream-caret {
    display: inline-block;
    width: 7px;
    height: 1.1em;
    margin-left: 3px;
    border-radius: 999px;
    background: var(--pulse-gradient);
    vertical-align: -0.16em;
    animation: pulse 0.85s ease-in-out infinite;
  }

  .edit-panel {
    display: grid;
    gap: var(--space-sm);
  }

  .edit-panel textarea {
    width: 100%;
    min-height: 112px;
    resize: vertical;
    border: 0;
    border-radius: var(--radius-sm);
    padding: 10px 12px;
    background: rgba(9, 19, 40, 0.44);
    outline: 1px solid rgba(182, 160, 255, 0.2);
  }

  .edit-panel textarea:focus {
    outline-color: rgba(182, 160, 255, 0.48);
  }

  .edit-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-xs);
  }

  .error-state {
    display: grid;
    gap: var(--space-sm);
  }

  .error-state p {
    margin: 0;
    color: var(--color-danger);
  }

  .error-state button,
  .edit-actions button {
    display: inline-flex;
    align-items: center;
    min-height: 44px;
    gap: var(--space-xs);
    border: 0;
    border-radius: var(--radius-sm);
    padding: 0 12px;
    background: rgba(182, 160, 255, 0.18);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
  }

  .error-state button {
    justify-self: start;
    outline: 1px solid rgba(255, 113, 108, 0.35);
    background: transparent;
  }

  .edit-actions button.secondary {
    background: rgba(64, 72, 93, 0.26);
    color: var(--color-text-muted);
  }

  .edit-actions button:disabled {
    cursor: not-allowed;
    opacity: 0.58;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 0.35;
    }

    50% {
      opacity: 1;
    }
  }

  @media (max-width: 640px) {
    .bubble {
      width: min(86%, 680px);
    }

    .message-actions {
      opacity: 1;
    }
  }

</style>
