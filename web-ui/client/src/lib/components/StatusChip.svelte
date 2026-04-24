<script lang="ts">
  export let label: string;
  export let description: string | undefined = undefined;
  export let tone: 'neutral' | 'healthy' | 'warning' | 'danger' = 'neutral';
</script>

<span class:healthy={tone === 'healthy'} class:warning={tone === 'warning'} class:danger={tone === 'danger'} class="status-chip" aria-label={description ?? label}>
  <span class="status-dot" aria-hidden="true"></span>
  <span>{label}</span>
</span>

<style>
  .status-chip {
    display: inline-flex;
    align-items: center;
    min-height: 32px;
    max-width: 100%;
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    padding: 0 10px;
    background: rgba(25, 37, 64, 0.68);
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
    white-space: nowrap;
  }

  .status-dot {
    width: var(--space-sm);
    height: var(--space-sm);
    flex: 0 0 auto;
    border-radius: 999px;
    background: var(--color-text-muted);
  }

  .healthy {
    color: var(--color-text);
  }

  .healthy .status-dot {
    background: var(--color-secondary);
    box-shadow: 0 0 18px rgba(0, 227, 253, 0.3);
  }

  .warning .status-dot {
    background: var(--color-primary);
  }

  .danger {
    color: var(--color-text);
  }

  .danger .status-dot {
    background: var(--color-danger);
  }
</style>
