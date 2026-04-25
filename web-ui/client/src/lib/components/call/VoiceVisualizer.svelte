<script lang="ts">
  import type { CallStateName } from '$lib/api/types';

  export let state: Extract<CallStateName, 'listening' | 'thinking' | 'speaking'> = 'listening';
  export let listeningRms: number | null | undefined = undefined;
  export let speakingRms: number | null | undefined = undefined;

  $: stateLabel = labelForState(state);
  $: listeningEnergy = normalizeRms(listeningRms);
  $: speakingEnergy = normalizeRms(speakingRms);
  $: activeEnergy = state === 'speaking' ? speakingEnergy : state === 'listening' ? listeningEnergy : 0;
  $: hasListeningMeter = typeof listeningRms === 'number';
  $: hasSpeakingMeter = typeof speakingRms === 'number';
  $: meterAvailable = state === 'speaking' ? hasSpeakingMeter : state === 'listening' ? hasListeningMeter : false;
  $: bars = createBars(state, activeEnergy, meterAvailable);
  $: visualizerStyle = `--call-energy: ${Math.max(activeEnergy, 0.16).toFixed(3)};`;

  function normalizeRms(value: number | null | undefined): number {
    if (typeof value !== 'number' || Number.isNaN(value)) {
      return 0;
    }

    return Math.max(0, Math.min(1, value));
  }

  function labelForState(nextState: typeof state): 'Listening' | 'Thinking' | 'Speaking' {
    if (nextState === 'thinking') {
      return 'Thinking';
    }

    if (nextState === 'speaking') {
      return 'Speaking';
    }

    return 'Listening';
  }

  function createBars(nextState: typeof state, energy: number, hasMeter: boolean): number[] {
    if (nextState === 'thinking') {
      return [0.38, 0.56, 0.74, 0.92, 0.74, 0.56, 0.38];
    }

    const base = hasMeter ? Math.max(0.18, energy) : 0.42;
    return [0.48, 0.72, 0.58, 0.9, 0.64, 0.78, 0.52].map((scale, index) => {
      const deterministicFallback = hasMeter ? 0 : ((index % 3) + 1) * 0.06;
      return Math.min(1, base * scale + deterministicFallback);
    });
  }
</script>

<section
  class:thinking={state === 'thinking'}
  class:metered={meterAvailable}
  class="voice-visualizer"
  data-testid="voice-visualizer"
  data-call-state={state}
  data-listening-rms={(listeningRms ?? 0).toFixed(3)}
  data-speaking-rms={(speakingRms ?? 0).toFixed(3)}
  aria-label={`Voice visualizer ${stateLabel}`}
  style={visualizerStyle}
>
  <div class="pulse-field" aria-hidden="true">
    <span></span>
    <span></span>
    <span></span>
  </div>

  <div class="status-label">
    <p>{stateLabel}</p>
    <span>{state === 'thinking' ? 'Preparing a response' : meterAvailable ? 'Live audio energy' : 'Live audio fallback'}</span>
  </div>

  <div class="waveform" aria-hidden="true">
    {#each bars as bar, index}
      <span style={`--bar-scale: ${bar.toFixed(3)}; --bar-index: ${index};`}></span>
    {/each}
  </div>
</section>

<style>
  .voice-visualizer {
    position: relative;
    display: grid;
    min-height: clamp(220px, 36vh, 360px);
    place-items: center;
    overflow: hidden;
    border-radius: var(--radius-md);
    background:
      radial-gradient(circle at 50% 44%, rgba(0, 227, 253, calc(0.16 + var(--call-energy) * 0.18)), transparent 33%),
      rgba(9, 19, 40, 0.82);
    box-shadow:
      inset 0 0 0 1px rgba(64, 72, 93, 0.14),
      0 24px 72px rgba(0, 0, 0, 0.2);
  }

  .voice-visualizer.thinking {
    background:
      radial-gradient(circle at 50% 44%, rgba(182, 160, 255, 0.22), transparent 34%),
      linear-gradient(135deg, rgba(182, 160, 255, 0.12), rgba(112, 170, 255, 0.08)),
      rgba(9, 19, 40, 0.82);
  }

  .pulse-field,
  .pulse-field span {
    position: absolute;
    inset: 12%;
    border-radius: 999px;
  }

  .pulse-field span {
    background: rgba(0, 227, 253, 0.08);
    box-shadow: 0 0 calc(44px + var(--call-energy) * 80px) rgba(0, 227, 253, 0.3);
    opacity: calc(0.28 + var(--call-energy) * 0.5);
    transform: scale(calc(0.82 + var(--call-energy) * 0.24));
    animation: listening-pulse 1.8s ease-in-out infinite;
  }

  .thinking .pulse-field span {
    background: linear-gradient(135deg, rgba(182, 160, 255, 0.16), rgba(112, 170, 255, 0.1));
    box-shadow: 0 0 68px rgba(182, 160, 255, 0.24);
    animation-name: thinking-shimmer;
  }

  .pulse-field span:nth-child(2) {
    inset: 18%;
    animation-delay: 180ms;
  }

  .pulse-field span:nth-child(3) {
    inset: 26%;
    animation-delay: 360ms;
  }

  .status-label {
    position: relative;
    z-index: 2;
    display: grid;
    place-items: center;
    gap: var(--space-xs);
    text-align: center;
  }

  .status-label p,
  .status-label span {
    margin: 0;
  }

  .status-label p {
    color: var(--color-text);
    font-size: var(--font-display);
    font-weight: 600;
    line-height: var(--line-display);
  }

  .status-label span {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .waveform {
    position: absolute;
    right: var(--space-lg);
    bottom: var(--space-lg);
    left: var(--space-lg);
    z-index: 2;
    display: flex;
    height: 72px;
    align-items: center;
    justify-content: center;
    gap: var(--space-xs);
  }

  .waveform span {
    width: var(--space-xs);
    height: calc(24px + var(--bar-scale) * 48px);
    border-radius: 999px;
    background: #00e3fd;
    box-shadow: 0 0 22px rgba(0, 227, 253, 0.38);
    animation: waveform-fallback 1.2s ease-in-out infinite;
    animation-delay: calc(var(--bar-index) * -92ms);
  }

  .thinking .waveform span {
    background: linear-gradient(135deg, #b6a0ff 0%, #70aaff 100%);
    box-shadow: 0 0 22px rgba(182, 160, 255, 0.32);
  }

  .metered .waveform span {
    animation: none;
  }

  @keyframes listening-pulse {
    0%,
    100% {
      transform: scale(calc(0.82 + var(--call-energy) * 0.2));
    }

    50% {
      transform: scale(calc(0.9 + var(--call-energy) * 0.34));
    }
  }

  @keyframes thinking-shimmer {
    0%,
    100% {
      transform: scale(0.9) rotate(0deg);
      opacity: 0.28;
    }

    50% {
      transform: scale(1.02) rotate(4deg);
      opacity: 0.58;
    }
  }

  @keyframes waveform-fallback {
    0%,
    100% {
      transform: scaleY(0.72);
    }

    50% {
      transform: scaleY(1.08);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .pulse-field span,
    .waveform span {
      animation: none;
    }

    .pulse-field span {
      transform: scale(calc(0.86 + var(--call-energy) * 0.18));
    }
  }
</style>
