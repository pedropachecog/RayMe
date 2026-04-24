<script lang="ts">
  import { Edit3, MessageSquarePlus, MoreHorizontal, RefreshCw, RotateCw } from 'lucide-svelte';

  import {
    messageActionsForRole,
    type MessageActionId
  } from '$lib/api/chat';
  import type { MessageRole } from '$lib/api/types';

  interface Props {
    role: MessageRole;
    disabled?: boolean;
    onAction?: (action: MessageActionId) => void;
  }

  let { role, disabled = false, onAction }: Props = $props();
  let open = $state(false);
  let root = $state<HTMLElement | null>(null);
  const actions = $derived(messageActionsForRole(role));

  function toggle() {
    if (disabled) {
      return;
    }

    open = !open;
  }

  function choose(action: MessageActionId) {
    if (disabled) {
      return;
    }

    open = false;
    onAction?.(action);
  }

  function closeWhenFocusLeaves(event: FocusEvent) {
    const nextTarget = event.relatedTarget;
    if (nextTarget instanceof Node && root?.contains(nextTarget)) {
      return;
    }

    open = false;
  }
</script>

{#if actions.length > 0}
  <div class="action-menu" bind:this={root} onfocusout={closeWhenFocusLeaves}>
    <button
      class="overflow-trigger"
      type="button"
      aria-label="Message actions"
      aria-expanded={open}
      disabled={disabled}
      onclick={toggle}
    >
      <MoreHorizontal size={18} strokeWidth={1.8} aria-hidden="true" />
    </button>

    {#if open}
      <div class="action-list" role="menu" aria-label="Message actions">
        {#each actions as action}
          <button type="button" role="menuitem" disabled={disabled} onclick={() => choose(action.id)}>
            {#if action.id === 'regenerate'}
              <RefreshCw size={16} strokeWidth={1.8} aria-hidden="true" />
            {:else if action.id === 'swipe'}
              <RotateCw size={16} strokeWidth={1.8} aria-hidden="true" />
            {:else if action.id === 'continue'}
              <MessageSquarePlus size={16} strokeWidth={1.8} aria-hidden="true" />
            {:else}
              <Edit3 size={16} strokeWidth={1.8} aria-hidden="true" />
            {/if}
            <span>{action.label}</span>
          </button>
        {/each}
      </div>
    {/if}
  </div>
{/if}

<style>
  .action-menu {
    position: relative;
    display: inline-flex;
    justify-content: flex-end;
  }

  .overflow-trigger {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    border: 0;
    border-radius: var(--radius-sm);
    background: rgba(64, 72, 93, 0.18);
    color: var(--color-text-muted);
  }

  .overflow-trigger:hover,
  .overflow-trigger:focus-visible,
  .overflow-trigger[aria-expanded='true'] {
    color: var(--color-text);
    background: rgba(182, 160, 255, 0.16);
  }

  .overflow-trigger:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .action-list {
    position: absolute;
    right: 0;
    bottom: calc(100% + var(--space-xs));
    z-index: 8;
    display: grid;
    min-width: 164px;
    gap: 2px;
    border-radius: var(--radius-md);
    padding: var(--space-xs);
    background: rgba(25, 37, 64, 0.86);
    box-shadow: 0 20px 56px rgba(0, 0, 0, 0.34);
    backdrop-filter: blur(20px);
  }

  .action-list button {
    display: grid;
    grid-template-columns: 20px minmax(0, 1fr);
    align-items: center;
    min-height: 40px;
    gap: var(--space-sm);
    border: 0;
    border-radius: var(--radius-sm);
    padding: 0 10px;
    background: transparent;
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    text-align: left;
  }

  .action-list button:hover,
  .action-list button:focus-visible {
    background: rgba(182, 160, 255, 0.14);
  }

  .action-list button:disabled {
    cursor: not-allowed;
    color: var(--color-text-muted);
  }
</style>
