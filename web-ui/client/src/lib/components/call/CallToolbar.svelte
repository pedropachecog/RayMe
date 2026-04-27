<script lang="ts">
  import {
    ChevronDown,
    Mic,
    MicOff,
    MoreHorizontal,
    PhoneOff,
    RadioTower,
    Volume2,
    Zap
  } from 'lucide-svelte';

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
  export let stateLabel = 'Connecting';
  export let ready = false;
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

  let menuOpen = false;

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

  function handleEnd() {
    menuOpen = false;
    onEnd();
  }

  function handleInterrupt() {
    menuOpen = false;
    onInterrupt();
  }
</script>

<div class="call-toolbar" data-testid="call-toolbar" aria-label="Call controls">
  <div class="state-pill" class:ready data-testid="call-ready-state">
    <span class="state-dot" aria-hidden="true"></span>
    <span>{stateLabel}</span>
  </div>

  <div class="compact-controls">
    <button
      class="icon-control primary"
      type="button"
      disabled={disabled}
      aria-label={muteLabel}
      aria-pressed={muted}
      title={muteLabel}
      on:click={onMuteToggle}
    >
      {#if muted}
        <MicOff size={20} strokeWidth={1.9} aria-hidden="true" />
      {:else}
        <Mic size={20} strokeWidth={1.9} aria-hidden="true" />
      {/if}
    </button>

    <button
      class="icon-control destructive"
      type="button"
      disabled={!endEnabled}
      aria-label="End Call"
      title="End Call"
      on:click={handleEnd}
    >
      <PhoneOff size={20} strokeWidth={1.9} aria-hidden="true" />
    </button>

    <button
      class="icon-control"
      type="button"
      aria-expanded={menuOpen}
      aria-label="More call options"
      title="More call options"
      on:click={() => (menuOpen = !menuOpen)}
    >
      <MoreHorizontal size={21} strokeWidth={1.9} aria-hidden="true" />
    </button>
  </div>

  {#if menuOpen}
    <div class="options-menu" aria-label="More call options panel">
      <button class="menu-action" type="button" disabled={disabled || !interruptEnabled} on:click={handleInterrupt}>
        <Zap size={18} strokeWidth={1.8} aria-hidden="true" />
        <span>Interrupt</span>
      </button>

      <div class="device-controls" aria-label="Audio devices">
        <label>
          <span class="device-label">
            <RadioTower size={16} strokeWidth={1.8} aria-hidden="true" />
            <span>Input</span>
          </span>
          <span class="select-wrap">
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
            <ChevronDown size={16} strokeWidth={1.8} aria-hidden="true" />
          </span>
        </label>
        <p id="input-picker-copy">{inputDescription}</p>

        <label>
          <span class="device-label">
            <Volume2 size={16} strokeWidth={1.8} aria-hidden="true" />
            <span>Output</span>
          </span>
          <span class="select-wrap">
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
            <ChevronDown size={16} strokeWidth={1.8} aria-hidden="true" />
          </span>
        </label>
        <p id="output-picker-copy">{outputDescription}</p>
      </div>
    </div>
  {/if}
</div>

<style>
  .call-toolbar {
    position: relative;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    padding: 8px;
    background: rgba(25, 37, 64, 0.84);
    box-shadow: var(--shadow-float);
    backdrop-filter: blur(20px);
  }

  .state-pill {
    display: inline-flex;
    min-width: 0;
    min-height: 40px;
    align-items: center;
    gap: var(--space-sm);
    border-radius: var(--radius-sm);
    padding: 0 12px;
    background: rgba(9, 19, 40, 0.56);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 700;
    line-height: var(--line-label);
  }

  .state-pill span:last-child {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .state-dot {
    width: 9px;
    height: 9px;
    flex: 0 0 auto;
    border-radius: 999px;
    background: var(--color-text-muted);
    box-shadow: 0 0 0 4px rgba(158, 170, 213, 0.12);
  }

  .state-pill.ready .state-dot {
    background: #00e3fd;
    box-shadow: 0 0 0 4px rgba(0, 227, 253, 0.14);
  }

  .compact-controls {
    display: inline-grid;
    grid-auto-flow: column;
    gap: 6px;
  }

  .icon-control,
  .menu-action {
    display: inline-flex;
    min-width: 44px;
    min-height: 44px;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: var(--radius-sm);
    background: rgba(20, 31, 56, 0.9);
    color: var(--color-text);
  }

  .icon-control.primary {
    background: rgba(0, 227, 253, 0.16);
  }

  .icon-control.destructive {
    background: #ff716c;
    color: var(--color-surface);
  }

  .icon-control:disabled,
  .menu-action:disabled,
  select:disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }

  .options-menu {
    position: absolute;
    top: calc(100% + 8px);
    right: 0;
    z-index: 8;
    display: grid;
    width: min(360px, calc(100vw - 32px));
    gap: var(--space-md);
    border-radius: var(--radius-md);
    padding: var(--space-md);
    background: rgba(25, 37, 64, 0.96);
    box-shadow: var(--shadow-float);
    backdrop-filter: blur(20px);
  }

  .menu-action {
    width: 100%;
    justify-content: flex-start;
    gap: var(--space-sm);
    padding: 0 var(--space-md);
    font-size: var(--font-label);
    font-weight: 700;
    line-height: var(--line-label);
  }

  .device-controls {
    display: grid;
    gap: var(--space-sm);
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

  .select-wrap {
    position: relative;
    display: grid;
    align-items: center;
  }

  .select-wrap :global(svg) {
    position: absolute;
    right: 10px;
    pointer-events: none;
  }

  select {
    width: 100%;
    min-height: 44px;
    appearance: none;
    border: 0;
    border-radius: var(--radius-sm);
    padding: 0 34px 0 12px;
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

  @media (max-width: 520px) {
    .call-toolbar {
      grid-template-columns: minmax(0, 1fr) auto;
      padding: 6px;
    }

    .state-pill {
      min-height: 38px;
      padding: 0 10px;
    }

    .icon-control {
      min-width: 44px;
      min-height: 44px;
    }
  }
</style>
