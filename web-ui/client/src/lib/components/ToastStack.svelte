<script lang="ts">
  export type ToastItem = {
    id: string;
    message: string;
    tone?: 'success' | 'error' | 'info';
  };

  export let toasts: ToastItem[] = [];
  export let onDismiss: (id: string) => void = () => {};
</script>

{#if toasts.length > 0}
  <section class="toast-stack" aria-label="Notifications" aria-live="polite" aria-relevant="additions removals">
    {#each toasts as toast (toast.id)}
      <div class:error={toast.tone === 'error'} class:success={toast.tone === 'success'} class="toast">
        <span class="toast-dot" aria-hidden="true"></span>
        <p>{toast.message}</p>
        <button type="button" aria-label={`Dismiss ${toast.message}`} on:click={() => onDismiss(toast.id)}>
          Dismiss
        </button>
      </div>
    {/each}
  </section>
{/if}

<style>
  .toast-stack {
    position: fixed;
    right: var(--space-md);
    bottom: calc(64px + var(--space-md));
    z-index: 70;
    display: grid;
    width: min(360px, calc(100vw - 32px));
    gap: var(--space-sm);
  }

  .toast {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    padding: var(--space-sm);
    background: rgba(25, 37, 64, 0.92);
    box-shadow: var(--shadow-float);
    backdrop-filter: blur(20px);
  }

  .toast-dot {
    width: var(--space-sm);
    height: var(--space-sm);
    border-radius: 999px;
    background: var(--color-secondary);
  }

  .error .toast-dot {
    background: var(--color-danger);
  }

  .success .toast-dot {
    background: var(--color-primary);
  }

  p {
    min-width: 0;
    margin: 0;
    color: var(--color-text);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  button {
    min-height: 36px;
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 10px;
    background: rgba(20, 31, 56, 0.82);
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  @media (min-width: 800px) {
    .toast-stack {
      bottom: var(--space-lg);
    }
  }
</style>
