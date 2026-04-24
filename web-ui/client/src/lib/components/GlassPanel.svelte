<script lang="ts">
  export let ariaLabel: string | undefined = undefined;
  export let ariaLabelledby: string | undefined = undefined;
  export let tone: 'low' | 'high' | 'glass' = 'glass';
</script>

<section
  class:low={tone === 'low'}
  class:high={tone === 'high'}
  class="glass-panel"
  aria-label={ariaLabel}
  aria-labelledby={ariaLabelledby}
>
  <slot />
</section>

<style>
  .glass-panel {
    border-radius: var(--radius-md);
    background: rgba(25, 37, 64, 0.6);
    box-shadow: var(--shadow-float);
    backdrop-filter: blur(20px);
  }

  .low {
    background: rgba(9, 19, 40, 0.78);
  }

  .high {
    background: rgba(20, 31, 56, 0.82);
  }
</style>
