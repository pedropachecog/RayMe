<script lang="ts">
  import { Upload } from 'lucide-svelte';

  import type { VoiceAsset } from '$lib/api/types';

  export let asset: VoiceAsset | null = null;
  export let sampleUrl: string | null = null;
  export let busy = false;
  export let errorMessage = '';
  export let onFileSelected: (file: File) => void = () => {};

  const acceptedExtensions = ['wav', 'mp3', 'flac'];

  function handleFileChange(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];

    if (file) {
      onFileSelected(file);
    }
  }

  $: durationLabel =
    typeof asset?.duration_seconds === 'number' ? `${asset.duration_seconds.toFixed(1)} sec` : null;
  $: durationWarning =
    typeof asset?.duration_seconds !== 'number'
      ? ''
      : asset.duration_seconds < 6
        ? 'This sample may be too short for a stable clone. Use 6-15 seconds when possible.'
        : asset.duration_seconds > 15
          ? 'This sample is longer than recommended and may take longer to process. Use 6-15 seconds when possible.'
          : '';
</script>

<section class="dropzone" aria-label="Sample upload">
  <div class="dropzone-copy">
    <Upload size={22} strokeWidth={1.8} aria-hidden="true" />
    <div>
      <h2 id="upload-step-title">Upload Sample</h2>
      <p>Use a 6-15 second WAV, MP3, or FLAC sample. Mono is preferred when available.</p>
    </div>
  </div>

  <label class="file-control">
    <span>{busy ? 'Uploading sample...' : asset ? 'Replace sample' : 'Upload Sample'}</span>
    <input
      aria-label="Upload Sample"
      accept=".wav,.mp3,.flac,audio/wav,audio/mpeg,audio/flac"
      disabled={busy}
      type="file"
      on:change={handleFileChange}
    />
  </label>

  <div class="sample-status" aria-live="polite">
    {#if asset}
      <span>{asset.content_type ?? 'audio sample'}</span>
      {#if durationLabel}
        <span>{durationLabel}</span>
      {/if}
      {#if asset.channel_count}
        <span>{asset.channel_count === 1 ? 'mono' : `${asset.channel_count} channels`}</span>
      {/if}
    {:else}
      <span>Accepted: {acceptedExtensions.join(', ')}</span>
    {/if}
  </div>

  {#if durationWarning}
    <p class="warning" role="status">{durationWarning}</p>
  {/if}
  {#if sampleUrl}
    <div class="sample-player" aria-label="Uploaded sample playback">
      <span>Uploaded sample</span>
      <audio aria-label="Play uploaded sample" controls preload="metadata" src={sampleUrl}></audio>
    </div>
  {/if}
  {#if errorMessage}
    <p class="error" role="alert">{errorMessage}</p>
  {/if}
</section>

<style>
  .dropzone {
    display: grid;
    min-height: 176px;
    align-content: space-between;
    gap: var(--space-md);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(20, 31, 56, 0.76);
    box-shadow: inset 0 0 0 1px rgba(64, 72, 93, 0.18);
  }

  .dropzone-copy {
    display: flex;
    min-width: 0;
    gap: var(--space-md);
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

  p,
  .sample-status {
    color: var(--color-text-muted);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  .file-control {
    display: inline-flex;
    width: fit-content;
    min-height: 44px;
    align-items: center;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: var(--color-primary);
    color: var(--color-surface);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
    cursor: pointer;
  }

  .file-control input {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
  }

  .sample-status {
    display: flex;
    min-height: 32px;
    flex-wrap: wrap;
    gap: var(--space-sm);
  }

  .sample-player {
    display: grid;
    gap: var(--space-xs);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  audio {
    width: 100%;
    max-width: 520px;
  }

  .sample-status span,
  .warning,
  .error {
    border-radius: var(--radius-md);
    padding: var(--space-xs) var(--space-sm);
    background: rgba(9, 19, 40, 0.72);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .warning {
    color: var(--color-primary);
  }

  .error {
    color: var(--color-danger);
  }

  @media (max-width: 520px) {
    .dropzone {
      min-height: 148px;
      padding: var(--space-md);
    }
  }
</style>
