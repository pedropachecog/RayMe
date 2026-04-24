<script lang="ts">
  import { tick } from 'svelte';

  export let open = false;
  export let title: string;
  export let body: string;
  export let confirmLabel = 'Delete';
  export let cancelLabel = 'Cancel';
  export let submitting = false;
  export let onConfirm: () => void = () => {};
  export let onCancel: () => void = () => {};

  let dialogElement: HTMLDivElement;
  let cancelButton: HTMLButtonElement;

  $: if (open) {
    focusInitialControl();
  }

  async function focusInitialControl() {
    await tick();
    cancelButton?.focus();
  }

  function closeFromBackdrop(event: MouseEvent) {
    if (event.target === event.currentTarget && !submitting) {
      onCancel();
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape' && !submitting) {
      event.preventDefault();
      onCancel();
      return;
    }

    if (event.key !== 'Tab' || !dialogElement) {
      return;
    }

    const controls = Array.from(
      dialogElement.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')
    );
    const first = controls[0];
    const last = controls[controls.length - 1];

    if (!first || !last) {
      return;
    }

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
</script>

{#if open}
  <div class="dialog-backdrop" role="presentation" on:click={closeFromBackdrop}>
    <div
      bind:this={dialogElement}
      class="dialog-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      aria-describedby="confirm-dialog-body"
      tabindex="-1"
      on:keydown={handleKeydown}
    >
      <div>
        <p class="eyebrow">Confirmation required</p>
        <h2 id="confirm-dialog-title">{title}</h2>
      </div>
      <p id="confirm-dialog-body">{body}</p>
      <div class="dialog-actions">
        <button bind:this={cancelButton} class="secondary" type="button" disabled={submitting} on:click={onCancel}>
          {cancelLabel}
        </button>
        <button class="danger" type="button" disabled={submitting} on:click={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .dialog-backdrop {
    position: fixed;
    inset: 0;
    z-index: 80;
    display: grid;
    place-items: center;
    padding: var(--space-lg);
    background: rgba(6, 14, 32, 0.72);
    backdrop-filter: blur(16px);
  }

  .dialog-panel {
    display: grid;
    width: min(100%, 440px);
    gap: var(--space-lg);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(25, 37, 64, 0.92);
    box-shadow: var(--shadow-float);
  }

  .eyebrow,
  h2,
  p {
    margin: 0;
  }

  .eyebrow {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  h2 {
    margin-top: var(--space-xs);
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
  }

  p {
    color: var(--color-text-muted);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  .dialog-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--space-sm);
  }

  button {
    min-height: 44px;
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .secondary {
    background: rgba(20, 31, 56, 0.82);
  }

  .danger {
    background: var(--color-danger);
    color: var(--color-surface);
  }
</style>
