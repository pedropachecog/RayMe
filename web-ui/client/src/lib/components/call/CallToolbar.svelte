<script lang="ts">
  import { Mic, MicOff, PhoneOff, RadioTower, Volume2, Zap } from 'lucide-svelte';

  import {
    INPUT_PICKER_UNAVAILABLE_COPY,
    OUTPUT_PICKER_UNAVAILABLE_COPY,
    type AudioInputDevice
  } from '$lib/call/audio';

  export interface AudioOutputDevice {
    deviceId: string;
    label: string;
  }

  export let muted = false;
  export let interruptEnabled = true;
  export let endEnabled = true;
  export let disabled = false;
  export let inputDevices: AudioInputDevice[] = [];
  export let outputDevices: AudioOutputDevice[] = [];
  export let selectedInputId = '';
  export let selectedOutputId = '';
  export let inputPickerSupported = false;
  export let outputPickerSupported = false;
  export let onMuteToggle: () => void = () => {};
  export let onInterrupt: () => void = () => {};
  export let onEnd: () => void = () => {};
  export let onInputChange: (deviceId: string) => void = () => {};
  export let onOutputChange: (deviceId: string) => void = () => {};

  $: muteLabel = muted ? 'Unmute' : 'Mute';
  $: inputDescription = inputPickerSupported
    ? 'Microphone input device'
    : INPUT_PICKER_UNAVAILABLE_COPY;
  $: outputDescription = outputPickerSupported
    ? 'Speaker output device'
    : OUTPUT_PICKER_UNAVAILABLE_COPY;

  function handleInputChange(event: Event) {
    onInputChange((event.currentTarget as HTMLSelectElement).value);
  }

  function handleOutputChange(event: Event) {
    onOutputChange((event.currentTarget as HTMLSelectElement).value);
  }
</script>

<div class="call-toolbar" data-testid="call-toolbar" aria-label="Call controls">
  <div class="primary-controls">
    <button class="control primary" type="button" disabled={disabled} aria-pressed={muted} on:click={onMuteToggle}>
      {#if muted}
        <MicOff size={20} strokeWidth={1.8} aria-hidden="true" />
      {:else}
        <Mic size={20} strokeWidth={1.8} aria-hidden="true" />
      {/if}
      <span>{muteLabel}</span>
    </button>

    <button class="control" type="button" disabled={disabled || !interruptEnabled} on:click={onInterrupt}>
      <Zap size={20} strokeWidth={1.8} aria-hidden="true" />
      <span>Interrupt</span>
    </button>

    <button class="control destructive" type="button" disabled={!endEnabled} on:click={onEnd}>
      <PhoneOff size={20} strokeWidth={1.8} aria-hidden="true" />
      <span>End Call</span>
    </button>
  </div>

  <div class="device-controls" aria-label="Audio devices">
    <label>
      <span class="device-label">
        <RadioTower size={16} strokeWidth={1.8} aria-hidden="true" />
        <span>Input</span>
      </span>
      <select
        aria-describedby="input-picker-copy"
        disabled={disabled || !inputPickerSupported}
        value={selectedInputId}
        on:change={handleInputChange}
      >
        {#if inputDevices.length > 0}
          {#each inputDevices as device}
            <option value={device.deviceId}>{device.label || 'Current microphone'}</option>
          {/each}
        {:else}
          <option value="">Current microphone</option>
        {/if}
      </select>
    </label>
    <p id="input-picker-copy">{inputDescription}</p>

    <label>
      <span class="device-label">
        <Volume2 size={16} strokeWidth={1.8} aria-hidden="true" />
        <span>Output</span>
      </span>
      <select
        aria-describedby="output-picker-copy"
        disabled={disabled || !outputPickerSupported}
        value={selectedOutputId}
        on:change={handleOutputChange}
      >
        {#if outputDevices.length > 0}
          {#each outputDevices as device}
            <option value={device.deviceId}>{device.label || 'Browser default output'}</option>
          {/each}
        {:else}
          <option value="">Browser default output</option>
        {/if}
      </select>
    </label>
    <p id="output-picker-copy">{outputDescription}</p>
  </div>
</div>

<style>
  .call-toolbar {
    display: grid;
    gap: var(--space-md);
    border-radius: var(--radius-md);
    padding: var(--space-md);
    background: rgba(25, 37, 64, 0.74);
    box-shadow: var(--shadow-float);
    backdrop-filter: blur(20px);
  }

  .primary-controls {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .control {
    display: inline-flex;
    min-width: 0;
    min-height: 56px;
    align-items: center;
    justify-content: center;
    gap: var(--space-sm);
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(20, 31, 56, 0.86);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .control.primary {
    background: rgba(0, 227, 253, 0.14);
    color: var(--color-text);
  }

  .control.destructive {
    background: #ff716c;
    color: var(--color-surface);
  }

  .control span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .device-controls {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(180px, 1.15fr);
    align-items: start;
    gap: var(--space-sm) var(--space-md);
  }

  label {
    display: grid;
    min-width: 0;
    gap: var(--space-xs);
  }

  .device-label {
    display: inline-flex;
    align-items: center;
    gap: var(--space-xs);
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  select {
    width: 100%;
    min-height: 44px;
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 12px;
    background: rgba(9, 19, 40, 0.72);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  p {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--font-label);
    line-height: var(--line-label);
  }

  @media (max-width: 720px) {
    .primary-controls,
    .device-controls {
      grid-template-columns: 1fr;
    }

    .control {
      min-height: 56px;
    }
  }
</style>
