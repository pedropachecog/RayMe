<script lang="ts">
  import { MoreHorizontal, Pencil, Trash2 } from 'lucide-svelte';

  import type { ThreadSummary } from '$lib/api/types';

  export let thread: ThreadSummary;
  export let menuOpen = false;
  export let onOpen: (thread: ThreadSummary) => void = () => {};
  export let onToggleMenu: (threadId: string) => void = () => {};
  export let onRename: (thread: ThreadSummary) => void = () => {};
  export let onDelete: (thread: ThreadSummary) => void = () => {};

  $: title = thread.title?.trim() || thread.character_name || 'Untitled thread';
  $: characterName = thread.character_name || 'Unknown character';
  $: snippet = thread.last_message_snippet?.trim() || 'No messages yet';
  $: timestamp = formatRelativeTime(thread.last_message_at || thread.updated_at || thread.created_at);
  $: portraitUrl = thread.character_portrait_url || '';
  $: initials = characterName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');

  function formatRelativeTime(value: string | null | undefined): string {
    if (!value) {
      return 'No activity yet';
    }

    const time = new Date(value).getTime();
    if (Number.isNaN(time)) {
      return 'Recent activity';
    }

    const seconds = Math.max(0, Math.round((Date.now() - time) / 1000));
    if (seconds < 60) {
      return 'Just now';
    }

    const minutes = Math.round(seconds / 60);
    if (minutes < 60) {
      return `${minutes}m ago`;
    }

    const hours = Math.round(minutes / 60);
    if (hours < 24) {
      return `${hours}h ago`;
    }

    const days = Math.round(hours / 24);
    if (days < 30) {
      return `${days}d ago`;
    }

    return new Intl.DateTimeFormat(undefined, {
      month: 'short',
      day: 'numeric'
    }).format(new Date(value));
  }

  function handleOpen() {
    onOpen(thread);
  }

  function handleMenuClick(event: MouseEvent) {
    event.stopPropagation();
    onToggleMenu(thread.id);
  }

  function handleRename(event: MouseEvent) {
    event.stopPropagation();
    onRename(thread);
  }

  function handleDelete(event: MouseEvent) {
    event.stopPropagation();
    onDelete(thread);
  }
</script>

<article class="thread-row" data-testid={`thread-row-${thread.id}`} aria-label={`${title} with ${characterName}`}>
  <button class="thread-open" type="button" on:click={handleOpen}>
    <span class="portrait" aria-hidden="true">
      {#if portraitUrl}
        <img src={portraitUrl} alt="" loading="lazy" />
      {:else}
        <span>{initials || 'R'}</span>
      {/if}
    </span>

    <span class="thread-copy">
      <span class="thread-meta">
        <span class="character-name">{characterName}</span>
        <span class="timestamp">{timestamp}</span>
      </span>
      <span class="thread-title">{title}</span>
      <span class="snippet">{snippet}</span>
    </span>
  </button>

  <div class="menu-anchor">
    <button
      class="icon-button"
      type="button"
      aria-label={`Actions for ${title}`}
      aria-expanded={menuOpen}
      on:click={handleMenuClick}
    >
      <MoreHorizontal size={20} strokeWidth={1.8} />
    </button>

    {#if menuOpen}
      <div class="thread-menu" role="menu">
        <button type="button" role="menuitem" on:click={handleRename}>
          <Pencil size={16} strokeWidth={1.8} />
          <span>Rename</span>
        </button>
        <button class="danger" type="button" role="menuitem" on:click={handleDelete}>
          <Trash2 size={16} strokeWidth={1.8} />
          <span>Delete</span>
        </button>
      </div>
    {/if}
  </div>
</article>

<style>
  .thread-row {
    position: relative;
    display: grid;
    grid-template-columns: minmax(0, 1fr) 44px;
    align-items: center;
    min-height: 96px;
    gap: var(--space-md);
    border-radius: var(--radius-md);
    padding: var(--space-md);
    background: rgba(20, 31, 56, 0.76);
    box-shadow: inset 0 0 0 1px rgba(64, 72, 93, 0.14);
  }

  .thread-open {
    display: grid;
    grid-template-columns: 56px minmax(0, 1fr);
    align-items: center;
    min-width: 0;
    gap: var(--space-md);
    border: 0;
    padding: 0;
    background: transparent;
    color: inherit;
    text-align: left;
  }

  .portrait {
    display: grid;
    width: 56px;
    height: 56px;
    place-items: center;
    overflow: hidden;
    border-radius: 50%;
    background: var(--pulse-gradient);
    color: var(--color-surface);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: 1;
  }

  .portrait img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .thread-copy {
    display: grid;
    min-width: 0;
    gap: var(--space-xs);
  }

  .thread-meta {
    display: flex;
    min-width: 0;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-sm);
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .character-name {
    color: var(--color-text);
  }

  .timestamp {
    color: var(--color-text-muted);
  }

  .thread-title,
  .snippet {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .thread-title {
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
  }

  .snippet {
    color: var(--color-text-muted);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  .menu-anchor {
    position: relative;
    align-self: start;
  }

  .icon-button {
    display: inline-grid;
    width: 44px;
    min-width: 44px;
    height: 44px;
    place-items: center;
    border: 0;
    border-radius: var(--radius-md);
    background: rgba(9, 19, 40, 0.72);
    color: var(--color-text-muted);
  }

  .thread-menu {
    position: absolute;
    top: calc(100% + var(--space-sm));
    right: 0;
    z-index: 5;
    display: grid;
    min-width: 136px;
    gap: var(--space-xs);
    border-radius: var(--radius-md);
    padding: var(--space-sm);
    background: rgba(25, 37, 64, 0.94);
    box-shadow: var(--shadow-float);
    backdrop-filter: blur(20px);
  }

  .thread-menu button {
    display: inline-flex;
    align-items: center;
    justify-content: flex-start;
    min-height: 40px;
    gap: var(--space-sm);
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-sm);
    background: transparent;
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .thread-menu button:hover,
  .thread-menu button:focus-visible {
    background: rgba(20, 31, 56, 0.86);
  }

  .thread-menu .danger {
    color: var(--color-danger);
  }
</style>
