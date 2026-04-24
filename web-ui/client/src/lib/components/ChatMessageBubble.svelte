<script lang="ts">
  import { RefreshCw } from 'lucide-svelte';

  import { selectedMessageContent, type ChatMessageView } from '$lib/api/chat';
  import { renderTrustedMarkdown } from '$lib/sanitizer/renderMarkdown';

  interface Props {
    message: ChatMessageView;
    characterName?: string | null;
    portraitUrl?: string | null;
    openingGreeting?: boolean;
    onRetry?: (message: ChatMessageView) => void;
  }

  let {
    message,
    characterName = 'Character',
    portraitUrl = null,
    openingGreeting = false,
    onRetry
  }: Props = $props();

  const isUser = $derived(message.role === 'user');
  const displayName = $derived(isUser ? 'You' : characterName || 'Character');
  const avatarInitial = $derived((characterName || 'R').trim().slice(0, 1).toUpperCase() || 'R');
  const content = $derived(selectedMessageContent(message));
  const renderedContent = $derived(renderTrustedMarkdown(content));
  const orderedAlternates = $derived(
    [...message.alternates].sort((left, right) => left.alternate_index - right.alternate_index)
  );

  function retry() {
    onRetry?.(message);
  }
</script>

<article
  class:user={isUser}
  class:assistant={!isUser}
  class:stale={message.stale_after_edit}
  class="message-row"
  data-message-id={message.id}
  data-message-kind={message.message_kind}
  data-message-role={message.role}
  data-message-sequence={message.sequence}
  data-selected-alternate-id={message.selected_alternate_id ?? ''}
  data-stale-after-edit={message.stale_after_edit ? 'true' : 'false'}
  data-streaming={message.streaming ? 'true' : 'false'}
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
    </div>

    {#if message.error}
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

    {#if orderedAlternates.length > 0 && !message.error}
      <ol class="alternate-list" aria-label="Message alternates">
        {#each orderedAlternates as alternate}
          <li class:selected={alternate.id === message.selected_alternate_id}>
            <span class="alternate-index">{alternate.alternate_index + 1}</span>
            <div>{@html renderTrustedMarkdown(alternate.content_text)}</div>
          </li>
        {/each}
      </ol>
    {/if}
  </div>
</article>

<style>
  .message-row {
    display: flex;
    align-items: flex-end;
    gap: var(--space-sm);
    width: 100%;
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
    display: grid;
    width: min(76%, 680px);
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    padding: 12px 14px;
    background: rgba(20, 31, 56, 0.72);
    color: var(--color-text);
    box-shadow: 0 18px 48px rgba(0, 0, 0, 0.16);
  }

  .user .bubble {
    background: rgba(182, 160, 255, 0.18);
  }

  .message-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-xs);
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
  .streaming-chip {
    background: rgba(182, 160, 255, 0.18);
    color: var(--color-text);
  }

  .stale-chip {
    color: var(--color-danger);
  }

  .message-content,
  .error-state p,
  .alternate-list {
    color: var(--color-text);
    font-size: var(--font-body);
    font-weight: 400;
    line-height: var(--line-body);
  }

  .message-content :global(p),
  .alternate-list :global(p) {
    margin: 0;
  }

  .message-content :global(p + p) {
    margin-top: var(--space-sm);
  }

  .message-content :global(a),
  .alternate-list :global(a) {
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

  .alternate-list {
    display: grid;
    gap: var(--space-xs);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .alternate-list li {
    display: grid;
    grid-template-columns: 24px minmax(0, 1fr);
    gap: var(--space-sm);
    border-radius: var(--radius-sm);
    padding: var(--space-sm);
    background: rgba(9, 19, 40, 0.44);
    color: var(--color-text-muted);
  }

  .alternate-list li.selected {
    background: rgba(182, 160, 255, 0.14);
    color: var(--color-text);
  }

  .alternate-index {
    display: grid;
    width: 24px;
    height: 24px;
    place-items: center;
    border-radius: 50%;
    background: rgba(64, 72, 93, 0.26);
    color: inherit;
    font-size: var(--font-label);
    font-weight: 600;
  }

  .error-state {
    display: grid;
    gap: var(--space-sm);
  }

  .error-state p {
    margin: 0;
    color: var(--color-danger);
  }

  .error-state button {
    display: inline-flex;
    align-items: center;
    justify-self: start;
    min-height: 36px;
    gap: var(--space-xs);
    border: 1px solid rgba(255, 113, 108, 0.35);
    border-radius: var(--radius-sm);
    padding: 0 12px;
    background: transparent;
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
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
  }
</style>
