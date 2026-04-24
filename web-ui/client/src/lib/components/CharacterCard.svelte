<script lang="ts">
  import { Download, MessageSquarePlus, Pencil, Trash2 } from 'lucide-svelte';

  import type { CharacterSummary } from '$lib/api/types';
  import { renderTrustedMarkdown } from '$lib/sanitizer/renderMarkdown';

  export let character: CharacterSummary;
  export let busy = false;
  export let onStartChat: (character: CharacterSummary) => void = () => {};
  export let onEdit: (character: CharacterSummary) => void = () => {};
  export let onExportJson: (character: CharacterSummary) => void = () => {};
  export let onDelete: (character: CharacterSummary) => void = () => {};

  $: portraitUrl = character.portrait_url || '';
  $: initials = character.name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');
  $: snippetSource =
    character.description?.trim() ||
    character.personality?.trim() ||
    character.scenario?.trim() ||
    character.first_mes?.trim() ||
    'No description yet.';
  $: renderedSnippet = renderTrustedMarkdown(snippetSource);
  $: visibleTags = (character.tags ?? []).filter(Boolean).slice(0, 2);
  $: remainingTagCount = Math.max(0, (character.tags?.length ?? 0) - visibleTags.length);
</script>

<article class="character-card" data-testid={`character-card-${character.id}`}>
  <div class="portrait-frame" aria-hidden="true">
    {#if portraitUrl}
      <img src={portraitUrl} alt="" loading="lazy" />
    {:else}
      <span>{initials || 'R'}</span>
    {/if}
  </div>

  <div class="card-body">
    <div class="identity">
      <h2>{character.name}</h2>
      <div class="snippet" data-testid={`character-snippet-${character.id}`}>
        {@html renderedSnippet}
      </div>
    </div>

    {#if visibleTags.length > 0}
      <div class="tags" aria-label={`${character.name} tags`}>
        {#each visibleTags as tag}
          <span>{tag}</span>
        {/each}
        {#if remainingTagCount > 0}
          <span>{remainingTagCount} more</span>
        {/if}
      </div>
    {:else}
      <p class="tag-summary">0 tags</p>
    {/if}

    <div class="actions" aria-label={`Actions for ${character.name}`}>
      <button class="primary" type="button" disabled={busy} on:click={() => onStartChat(character)}>
        <MessageSquarePlus size={16} strokeWidth={1.8} />
        <span>Start Chat</span>
      </button>
      <button type="button" disabled={busy} on:click={() => onEdit(character)}>
        <Pencil size={16} strokeWidth={1.8} />
        <span>Edit</span>
      </button>
      <button type="button" disabled={busy} on:click={() => onExportJson(character)}>
        <Download size={16} strokeWidth={1.8} />
        <span>Export JSON</span>
      </button>
      <button class="danger" type="button" disabled={busy} on:click={() => onDelete(character)}>
        <Trash2 size={16} strokeWidth={1.8} />
        <span>Delete</span>
      </button>
    </div>
  </div>
</article>

<style>
  .character-card {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    min-height: 460px;
    overflow: hidden;
    border-radius: var(--radius-md);
    background: rgba(20, 31, 56, 0.78);
    box-shadow: inset 0 0 0 1px rgba(64, 72, 93, 0.14);
  }

  .portrait-frame {
    display: grid;
    aspect-ratio: 4 / 5;
    max-height: 280px;
    place-items: center;
    overflow: hidden;
    background: var(--pulse-gradient);
    color: var(--color-surface);
    font-size: var(--font-display);
    font-weight: 600;
    line-height: 1;
  }

  .portrait-frame img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .card-body {
    display: grid;
    min-height: 0;
    gap: var(--space-md);
    padding: var(--space-md);
  }

  .identity {
    display: grid;
    min-width: 0;
    gap: var(--space-sm);
  }

  h2,
  p {
    margin: 0;
  }

  h2 {
    overflow: hidden;
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .snippet {
    display: -webkit-box;
    min-height: calc(var(--font-body) * var(--line-body) * 2);
    overflow: hidden;
    color: var(--color-text-muted);
    font-size: var(--font-body);
    line-height: var(--line-body);
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
  }

  .snippet :global(*) {
    margin: 0;
    color: inherit;
    font: inherit;
    letter-spacing: 0;
  }

  .snippet :global(a) {
    color: var(--color-primary);
  }

  .tags {
    display: flex;
    min-height: 28px;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-xs);
  }

  .tags span,
  .tag-summary {
    width: fit-content;
    border-radius: var(--radius-md);
    padding: var(--space-xs) var(--space-sm);
    background: rgba(9, 19, 40, 0.72);
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  button {
    display: inline-flex;
    min-height: 44px;
    align-items: center;
    justify-content: center;
    gap: var(--space-xs);
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-sm);
    background: rgba(9, 19, 40, 0.72);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  button.primary {
    background: var(--color-primary);
    color: var(--color-surface);
  }

  button.danger {
    color: var(--color-danger);
  }

  @media (max-width: 520px) {
    .actions {
      grid-template-columns: 1fr;
    }
  }
</style>
