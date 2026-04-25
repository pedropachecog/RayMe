<script lang="ts">
  import type { TtsEngineMetadata, VoiceSummary, VoiceTestPlayPayload } from '$lib/api/types';
  import VoiceLibraryRow from '$lib/components/voice/VoiceLibraryRow.svelte';

  export let voices: VoiceSummary[] = [];
  export let engines: TtsEngineMetadata[] = [];
  export let loading = false;
  export let errorMessage = '';
  export let testingVoiceId: string | null = null;
  export let testAudioByVoiceId: Record<string, string> = {};
  export let onTestPlay: (voice: VoiceSummary, payload: VoiceTestPlayPayload) => void = () => {};
  export let onRename: (voice: VoiceSummary) => void = () => {};
  export let onDelete: (voice: VoiceSummary) => void = () => {};

  $: engineLabels = new Map(engines.map((engine) => [engine.id, engine.label]));
</script>

<section class="voice-library" aria-labelledby="voice-library-title">
  <div>
    <p class="eyebrow">Saved voices</p>
    <h2 id="voice-library-title">Voice Library</h2>
  </div>

  {#if loading}
    <div class="loading" role="status">Loading Voice Library...</div>
  {:else if errorMessage}
    <p class="error" role="alert">{errorMessage}</p>
  {:else if voices.length === 0}
    <div class="empty-state">
      <h3>No voices yet</h3>
      <p>Upload a 6-15 second WAV, MP3, or FLAC sample to create the first voice.</p>
    </div>
  {:else}
    <ul aria-label="Voice Library voices">
      {#each voices as voice (voice.voice_id)}
        <VoiceLibraryRow
          {voice}
          engineLabel={engineLabels.get(voice.default_engine) ?? voice.default_engine}
          testing={testingVoiceId === voice.voice_id}
          testAudioUrl={testAudioByVoiceId[voice.voice_id] ?? null}
          {onTestPlay}
          {onRename}
          {onDelete}
        />
      {/each}
    </ul>
  {/if}
</section>

<style>
  .voice-library {
    display: grid;
    min-width: 0;
    gap: var(--space-md);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(20, 31, 56, 0.72);
  }

  .eyebrow,
  h2,
  h3,
  p,
  ul {
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

  h3 {
    color: var(--color-text);
    font-size: var(--font-body);
    font-weight: 600;
    line-height: var(--line-body);
  }

  p,
  .loading {
    color: var(--color-text-muted);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  .empty-state,
  .loading,
  .error {
    display: grid;
    min-height: 132px;
    align-content: center;
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    padding: var(--space-md);
    background: rgba(9, 19, 40, 0.74);
  }

  .error {
    min-height: 0;
    color: var(--color-danger);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  ul {
    display: grid;
    min-width: 0;
    gap: var(--space-sm);
    padding: 0;
    list-style: none;
  }

  @media (max-width: 520px) {
    .voice-library {
      padding: var(--space-md);
    }
  }
</style>
