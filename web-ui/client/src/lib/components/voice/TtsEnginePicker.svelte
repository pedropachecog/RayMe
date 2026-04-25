<script lang="ts">
  import type { TtsEngineMetadata } from '$lib/api/types';

  export let engines: TtsEngineMetadata[] = [];
  export let selectedEngine = 'f5';

  const fallbackCaveats: Record<string, string[]> = {
    f5: ['Default', 'Requires transcript'],
    xtts_v2: ['No transcript required', 'Streaming capable'],
    qwen3_0_6b: ['Opt-in', 'Latency caveat', 'Accent caveat'],
    luxtts: ['Quality caveat', 'Retest references'],
    chatterbox_turbo: ['Experimental', 'Avoid baseline long-form'],
    tada_1b: ['Experimental', 'High VRAM', 'WSL caution']
  };

  function caveatsFor(engine: TtsEngineMetadata) {
    return engine.caveat_chips?.length
      ? engine.caveat_chips
      : engine.caveats?.length
        ? engine.caveats
        : fallbackCaveats[engine.id] ?? [];
  }
</script>

<section class="engine-picker" aria-labelledby="engine-step-title">
  <div>
    <h2 id="engine-step-title">TTS Engine</h2>
    <p>Choose from backend metadata. Unavailable engines stay visible with caveats.</p>
  </div>

  <div class="engine-grid" role="radiogroup" aria-label="TTS engine">
    {#each engines as engine (engine.id)}
      {@const available = engine.availability?.available !== false}
      <label class:selected={selectedEngine === engine.id} class:unavailable={!available}>
        <input
          type="radio"
          name="tts-engine"
          value={engine.id}
          bind:group={selectedEngine}
          disabled={!available}
        />
        <span class="engine-name">{engine.label}</span>
        <span class="engine-meta">
          {#if !available}
            {engine.availability?.unavailable_reason || 'This engine is not available in the current runtime.'}
          {:else if engine.id === 'qwen3_0_6b'}
            Qwen3-TTS 0.6B-Base is experimental and non-default; use it only when you want the Apache-2.0 path despite current latency and accent caveats.
          {:else if engine.requires_transcript}
            Transcript required for this voice clone path.
          {:else}
            Reference transcript not required for this engine.
          {/if}
        </span>
        <span class="chips">
          {#each caveatsFor(engine) as caveat}
            <span>{caveat}</span>
          {/each}
        </span>
      </label>
    {/each}
  </div>
</section>

<style>
  .engine-picker {
    display: grid;
    gap: var(--space-md);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(20, 31, 56, 0.72);
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

  p {
    color: var(--color-text-muted);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  .engine-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: var(--space-sm);
  }

  label {
    display: grid;
    grid-template-columns: 20px minmax(0, 1fr);
    min-width: 0;
    min-height: 132px;
    align-content: start;
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    padding: var(--space-md);
    background: rgba(9, 19, 40, 0.72);
    color: var(--color-text-muted);
    cursor: pointer;
  }

  label.selected {
    box-shadow: inset 0 0 0 2px rgba(182, 160, 255, 0.72);
    color: var(--color-text);
  }

  label.unavailable {
    opacity: 0.62;
  }

  input {
    width: 18px;
    height: 18px;
    margin: 2px 0 0;
  }

  .engine-name,
  .engine-meta,
  .chips {
    grid-column: 2;
  }

  .engine-name {
    color: var(--color-text);
    font-size: var(--font-body);
    font-weight: 600;
    line-height: var(--line-body);
  }

  .engine-meta {
    font-size: var(--font-label);
    line-height: var(--line-label);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-xs);
  }

  .chips span {
    border-radius: var(--radius-sm);
    padding: var(--space-xs) var(--space-sm);
    background: rgba(25, 37, 64, 0.88);
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }
</style>
