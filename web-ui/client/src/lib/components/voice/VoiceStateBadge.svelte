<script lang="ts">
  import { AlertTriangle } from 'lucide-svelte';

  import type { CharacterDefaultVoice, CharacterDefaultVoiceState } from '$lib/api/types';

  export let state: CharacterDefaultVoiceState | undefined = 'none';
  export let label: string | null | undefined = null;
  export let voice: CharacterDefaultVoice | null | undefined = null;

  $: voiceName = label || voice?.name || voice?.deleted_name || '';
  $: displayState = state ?? 'none';
  $: badgeText =
    displayState === 'assigned' && voiceName
      ? `Voice: ${voiceName}`
      : displayState === 'unavailable'
        ? 'Voice unavailable'
        : 'No voice';
  $: ariaText =
    displayState === 'assigned' && voiceName
      ? `Default voice: ${voiceName}`
      : displayState === 'unavailable' && voiceName && voiceName !== 'Voice unavailable'
        ? `Default voice unavailable: ${voiceName}`
        : badgeText;
</script>

<span class={`voice-state ${displayState}`} aria-label={ariaText} title={ariaText}>
  {#if displayState === 'unavailable'}
    <AlertTriangle size={14} strokeWidth={2} aria-hidden="true" />
  {/if}
  <span>{badgeText}</span>
</span>

<style>
  .voice-state {
    display: inline-flex;
    width: fit-content;
    max-width: 100%;
    min-height: 28px;
    align-items: center;
    gap: var(--space-xs);
    overflow: hidden;
    border-radius: var(--radius-md);
    padding: var(--space-xs) var(--space-sm);
    background: rgba(9, 19, 40, 0.72);
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .voice-state span {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .voice-state.assigned {
    background: rgba(182, 160, 255, 0.18);
    color: var(--color-text);
  }

  .voice-state.unavailable {
    background: rgba(255, 113, 108, 0.12);
    color: var(--color-danger);
  }
</style>
