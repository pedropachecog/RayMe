<script lang="ts">
  import { ChevronLeft, ChevronRight, Sparkles } from 'lucide-svelte';

  interface Props {
    currentIndex: number;
    total: number;
    disabled?: boolean;
    onPrevious?: () => void;
    onNext?: () => void;
    onGenerate?: () => void;
  }

  let {
    currentIndex,
    total,
    disabled = false,
    onPrevious,
    onNext,
    onGenerate
  }: Props = $props();

  const safeTotal = $derived(Math.max(total, 1));
  const safeIndex = $derived(Math.min(Math.max(currentIndex, 0), safeTotal - 1));
  const canPrevious = $derived(!disabled && safeIndex > 0);
  const canNext = $derived(!disabled && safeIndex < safeTotal - 1);
</script>

<div class="swipe-stepper" aria-label="Swipe alternates">
  <button type="button" aria-label="Previous swipe" disabled={!canPrevious} onclick={() => onPrevious?.()}>
    <ChevronLeft size={17} strokeWidth={1.8} aria-hidden="true" />
  </button>

  <span class="step-count" aria-label="Selected swipe">{safeIndex + 1} / {safeTotal}</span>

  <button type="button" aria-label="Next swipe" disabled={!canNext} onclick={() => onNext?.()}>
    <ChevronRight size={17} strokeWidth={1.8} aria-hidden="true" />
  </button>

  <button
    class="generate"
    type="button"
    aria-label="Generate alternate"
    disabled={disabled}
    onclick={() => onGenerate?.()}
  >
    <Sparkles size={16} strokeWidth={1.8} aria-hidden="true" />
    <span>Generate alternate</span>
  </button>
</div>

<style>
  .swipe-stepper {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-xs);
  }

  button,
  .step-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 44px;
    min-height: 36px;
    border: 0;
    border-radius: var(--radius-sm);
    background: rgba(9, 19, 40, 0.54);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  button {
    cursor: pointer;
  }

  button:hover:not(:disabled),
  button:focus-visible {
    background: rgba(182, 160, 255, 0.16);
  }

  button:disabled {
    cursor: not-allowed;
    color: var(--color-text-muted);
    opacity: 0.58;
  }

  .step-count {
    min-width: 58px;
    padding: 0 10px;
    color: var(--color-text);
  }

  .generate {
    gap: var(--space-xs);
    padding: 0 10px;
  }

  @media (max-width: 520px) {
    .generate span {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
    }
  }
</style>
