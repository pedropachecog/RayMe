<script lang="ts">
  export let title: string;
  export let description = '';
  export let eyebrow = '';
  export let labelledby: string | undefined = undefined;
</script>

<section class="form-section" aria-labelledby={labelledby}>
  <div class="section-heading">
    {#if eyebrow}
      <p class="eyebrow">{eyebrow}</p>
    {/if}
    <h2 id={labelledby}>{title}</h2>
    {#if description}
      <p>{description}</p>
    {/if}
  </div>

  <div class="section-content">
    <slot />
  </div>
</section>

<style>
  .form-section {
    display: grid;
    gap: var(--space-md);
    border-radius: var(--radius-md);
    background: rgba(20, 31, 56, 0.78);
    padding: var(--space-lg);
    box-shadow: inset 0 0 0 1px rgba(64, 72, 93, 0.14);
  }

  .section-heading,
  .section-content {
    display: grid;
    gap: var(--space-sm);
  }

  .section-content {
    gap: var(--space-md);
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
</style>
