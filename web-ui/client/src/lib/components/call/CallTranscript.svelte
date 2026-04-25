<script lang="ts">
  import type { CallTranscriptTurn } from '$lib/api/types';
  import { renderTrustedMarkdown } from '$lib/sanitizer/renderMarkdown';

  export let turns: CallTranscriptTurn[] = [];
  export let activeAiText = '';
  export let interrupted = false;

  $: visibleTurns = turns.filter((turn) => turn.text.trim().length > 0);
  $: showEmptyState = visibleTurns.length === 0 && activeAiText.trim().length === 0;
  $: streamingHtml = renderTrustedMarkdown(activeAiText);

  function displayName(turn: CallTranscriptTurn): string {
    return turn.role === 'user' ? 'You' : 'RayMe';
  }

  function chipFor(turn: CallTranscriptTurn): 'Final' | 'Streaming' | 'Interrupted' {
    if ((interrupted && turn.role === 'assistant') || turn.interrupted) {
      return 'Interrupted';
    }

    return 'Final';
  }

  function htmlFor(turn: CallTranscriptTurn): string {
    return renderTrustedMarkdown(turn.text);
  }
</script>

<section class="call-transcript" aria-label="Call transcript">
  {#if showEmptyState}
    <div class="empty-state">
      <h2>Ready when you are</h2>
      <p>Start speaking when RayMe is listening. Your call transcript will appear here after the first turn.</p>
    </div>
  {:else}
    <div class="turn-list">
      {#each visibleTurns as turn, index}
        {@const chip = chipFor(turn)}
        <article class:user={turn.role === 'user'} class="turn" data-turn-type={turn.type ?? ''}>
          <div class="turn-meta">
            <span>{displayName(turn)}</span>
            <span class:interrupted-chip={chip === 'Interrupted'} class="state-chip">{chip}</span>
          </div>
          <div class="turn-text">
            {@html htmlFor(turn)}
            {#if index === visibleTurns.length - 1 && activeAiText.trim().length > 0 && turn.role === 'assistant'}
              <span class="stream-caret" aria-hidden="true"></span>
            {/if}
          </div>
        </article>
      {/each}

      {#if activeAiText.trim().length > 0 && visibleTurns.at(-1)?.text !== activeAiText}
        <article class="turn streaming" data-turn-type="ai_speech">
          <div class="turn-meta">
            <span>RayMe</span>
            <span class="state-chip streaming-chip">Streaming</span>
          </div>
          <div class="turn-text">
            {@html streamingHtml}
            <span class="stream-caret" aria-hidden="true"></span>
          </div>
        </article>
      {/if}
    </div>
  {/if}
</section>

<style>
  .call-transcript {
    display: grid;
    min-height: 220px;
    border-radius: var(--radius-md);
    padding: var(--space-md);
    background: rgba(9, 19, 40, 0.72);
    color: var(--color-text);
  }

  .empty-state {
    display: grid;
    align-content: center;
    min-height: 188px;
    gap: var(--space-sm);
    color: var(--color-text-muted);
  }

  h2,
  p {
    margin: 0;
  }

  h2 {
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
  }

  p,
  .turn-text {
    font-size: var(--font-body);
    font-weight: 400;
    line-height: var(--line-body);
  }

  .turn-list {
    display: grid;
    align-content: start;
    gap: var(--space-sm);
  }

  .turn {
    display: grid;
    width: min(82%, 680px);
    gap: var(--space-xs);
    border-radius: var(--radius-md);
    padding: 12px 14px;
    background: rgba(20, 31, 56, 0.78);
    box-shadow: 0 18px 48px rgba(0, 0, 0, 0.14);
  }

  .turn.user {
    justify-self: end;
    background: rgba(182, 160, 255, 0.16);
  }

  .turn.streaming {
    box-shadow: 0 0 36px rgba(182, 160, 255, 0.1);
  }

  .turn-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-xs);
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .state-chip {
    display: inline-flex;
    min-height: 20px;
    align-items: center;
    border-radius: var(--radius-md);
    padding: 0 8px;
    background: rgba(64, 72, 93, 0.28);
    color: var(--color-text-muted);
  }

  .streaming-chip {
    background: rgba(182, 160, 255, 0.18);
    color: var(--color-text);
  }

  .interrupted-chip {
    color: #ff716c;
  }

  .turn-text {
    color: var(--color-text);
    overflow-wrap: anywhere;
  }

  .turn-text :global(p) {
    margin: 0;
  }

  .turn-text :global(p + p) {
    margin-top: var(--space-sm);
  }

  .stream-caret {
    display: inline-block;
    width: 7px;
    height: 1.1em;
    margin-left: 3px;
    border-radius: 999px;
    background: linear-gradient(135deg, #b6a0ff 0%, #70aaff 100%);
    vertical-align: -0.16em;
    animation: caret-pulse 0.85s ease-in-out infinite;
  }

  @keyframes caret-pulse {
    0%,
    100% {
      opacity: 0.35;
    }

    50% {
      opacity: 1;
    }
  }

  @media (max-width: 640px) {
    .turn {
      width: min(92%, 680px);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .stream-caret {
      animation: none;
      opacity: 1;
    }
  }
</style>
