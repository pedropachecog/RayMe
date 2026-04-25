<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { ArrowLeft, RefreshCw, Settings, UserRound } from 'lucide-svelte';
  import { onDestroy, onMount } from 'svelte';

  import { CallApiError, endCall, interruptCall, setCallMuted, startCall } from '$lib/api/calls';
  import { loadThread } from '$lib/api/chat';
  import type { CallStateName, CallTranscriptTurn, ThreadDetail } from '$lib/api/types';
  import { unlockCallAudioContext } from '$lib/call/audio';
  import CallToolbar from '$lib/components/call/CallToolbar.svelte';
  import CallTranscript from '$lib/components/call/CallTranscript.svelte';
  import VoiceVisualizer from '$lib/components/call/VoiceVisualizer.svelte';
  import StatusChip from '$lib/components/StatusChip.svelte';

  type ActiveCallState = Extract<CallStateName, 'connecting' | 'listening' | 'thinking' | 'speaking' | 'interrupted' | 'ended' | 'failed'>;
  type VisualState = Extract<CallStateName, 'listening' | 'thinking' | 'speaking'>;
  type BlockingAction = 'Retry Microphone' | 'Open Character' | 'Choose Voice' | 'Open Settings' | 'Return to Thread';

  interface BlockingPanel {
    body: string;
    action: BlockingAction;
    tone?: 'danger' | 'warning';
  }

  interface StartEvent {
    type?: string;
    state?: string;
    listeningRms?: number;
    speakingRms?: number;
    text?: string;
  }

  let thread = $state<ThreadDetail | null>(null);
  let loadState = $state<'loading' | 'ready' | 'error'>('loading');
  let callState = $state<ActiveCallState>('connecting');
  let callId = $state('');
  let sessionId = $state('');
  let serverMuted = $state(false);
  let listeningRms = $state<number | null>(null);
  let speakingRms = $state<number | null>(null);
  let transcript = $state<CallTranscriptTurn[]>([]);
  let activeAiText = $state('');
  let blockingPanel = $state<BlockingPanel | null>(null);
  let ending = $state(false);
  let timers: number[] = [];

  const threadId = $derived(page.params.threadId ?? '');
  const characterName = $derived(thread?.character_name ?? 'RayMe');
  const title = $derived(thread?.title?.trim() || characterName);
  const visualState = $derived<VisualState>(
    callState === 'thinking' || callState === 'speaking' ? callState : 'listening'
  );
  const statusTone = $derived(callState === 'failed' ? 'danger' : callState === 'connecting' ? 'neutral' : 'healthy');
  const statusLabel = $derived(labelForState(callState));
  const canUseToolbar = $derived(callState !== 'connecting' && callState !== 'ended' && callState !== 'failed');

  onMount(() => {
    void initializeCall();
  });

  onDestroy(() => {
    clearEventTimers();
  });

  async function initializeCall() {
    loadState = 'loading';
    blockingPanel = null;

    try {
      thread = await loadThread(threadId);
      loadState = 'ready';
    } catch {
      loadState = 'error';
      blockingPanel = {
        body: 'The call ended because the connection dropped. Your transcript so far was saved.',
        action: 'Return to Thread',
        tone: 'danger'
      };
      return;
    }

    const queryCallId = page.url.searchParams.get('call_id');
    const querySessionId = page.url.searchParams.get('session_id');

    if (queryCallId) {
      callId = queryCallId;
      sessionId = querySessionId && querySessionId !== 'undefined' ? querySessionId : queryCallId;
      applyCallState(page.url.searchParams.get('state') ?? 'listening');
      listeningRms = callState === 'listening' ? 0.24 : listeningRms;
      speakingRms = callState === 'speaking' ? 0.36 : speakingRms;
      return;
    }

    await beginCall();
  }

  async function beginCall() {
    callState = 'connecting';
    clearEventTimers();

    try {
      await unlockAudioForCall();
      const started = await startCall({ thread_id: threadId });
      callId = started.call_id;
      sessionId = started.session_id || started.call_id;
      applyCallState(started.state ?? 'listening');
      applyStartEvents((started as typeof started & { events?: StartEvent[] }).events ?? []);

      if (callState === 'listening' && listeningRms === null) {
        listeningRms = 0.22;
      }

      if (callState === 'speaking' && speakingRms === null) {
        speakingRms = 0.34;
      }
    } catch (error) {
      showBlockingPanel(error);
    }
  }

  async function unlockAudioForCall() {
    try {
      await unlockCallAudioContext();
    } catch {
      // Fixed recovery panels below handle public UI copy; raw browser errors stay hidden.
    }
  }

  function applyStartEvents(events: StartEvent[]) {
    clearEventTimers();

    events.forEach((event, index) => {
      const timer = window.setTimeout(() => {
        if (event.state) {
          applyCallState(event.state);
        }
        if (typeof event.listeningRms === 'number') {
          listeningRms = event.listeningRms;
        }
        if (typeof event.speakingRms === 'number') {
          speakingRms = event.speakingRms;
        }
        if (event.type === 'ai_audio_started' && event.text) {
          appendAiText(event.text);
        }
      }, index * 800);
      timers = [...timers, timer];
    });
  }

  function clearEventTimers() {
    timers.forEach((timer) => window.clearTimeout(timer));
    timers = [];
  }

  function applyCallState(nextState: string) {
    const normalized = nextState.toLowerCase();
    if (
      normalized === 'listening' ||
      normalized === 'thinking' ||
      normalized === 'speaking' ||
      normalized === 'interrupted' ||
      normalized === 'ended' ||
      normalized === 'failed' ||
      normalized === 'connecting'
    ) {
      callState = normalized;
    } else {
      callState = 'listening';
    }
  }

  function appendAiText(text: string) {
    activeAiText = `${activeAiText}${text}`;
    const existing = transcript.at(-1);
    if (existing?.role === 'assistant' && existing.type === 'ai_speech') {
      transcript = transcript.map((turn, index) =>
        index === transcript.length - 1 ? { ...turn, text: activeAiText } : turn
      );
      return;
    }

    transcript = [
      ...transcript,
      {
        id: `active-ai-${Date.now()}`,
        role: 'assistant',
        type: 'ai_speech',
        text: activeAiText,
        created_at: null
      }
    ];
  }

  async function toggleMute() {
    if (!callId || !sessionId) {
      serverMuted = !serverMuted;
      return;
    }

    const nextMuted = !serverMuted;
    serverMuted = nextMuted;

    try {
      const result = await setCallMuted(callId, sessionId, nextMuted);
      serverMuted = Boolean((result as typeof result & { serverMuted?: boolean }).serverMuted ?? result.muted ?? nextMuted);
    } catch {
      serverMuted = !nextMuted;
    }
  }

  async function interrupt() {
    if (callId && sessionId) {
      try {
        await interruptCall(callId, sessionId);
      } catch {
        // The visual state still returns to listening; raw control failures stay out of UI copy.
      }
    }

    callState = 'interrupted';
    window.setTimeout(() => {
      if (callState === 'interrupted') {
        callState = 'listening';
      }
    }, 250);
  }

  async function hangup() {
    ending = true;
    clearEventTimers();

    try {
      if (callId && sessionId) {
        await endCall(callId, sessionId);
      }
      callState = 'ended';
    } catch {
      callState = 'failed';
      blockingPanel = {
        body: 'The call ended because the connection dropped. Your transcript so far was saved.',
        action: 'Return to Thread',
        tone: 'danger'
      };
    } finally {
      ending = false;
    }
  }

  async function returnToThread() {
    await goto(`/chat/${encodeURIComponent(threadId)}`);
  }

  function showBlockingPanel(error: unknown) {
    callState = 'failed';

    if (error instanceof CallApiError) {
      if (error.code === 'call_voice_required') {
        blockingPanel = {
          body: 'Assign a voice before calling this character.',
          action: 'Open Character',
          tone: 'warning'
        };
        return;
      }

      if (error.code === 'call_voice_unavailable') {
        blockingPanel = {
          body: "This character's assigned voice is unavailable.",
          action: 'Choose Voice',
          tone: 'warning'
        };
        return;
      }

      if (error.code === 'call_backend_not_ready') {
        blockingPanel = {
          body: 'RayMe voice backend is not ready. Check Settings, then try again.',
          action: 'Open Settings',
          tone: 'warning'
        };
        return;
      }

      if (error.status === 403 || error.code === 'microphone_blocked') {
        blockingPanel = {
          body: 'Microphone access is blocked. Allow microphone access in Chrome, then retry.',
          action: 'Retry Microphone',
          tone: 'danger'
        };
        return;
      }
    }

    blockingPanel = {
      body: 'The call ended because the connection dropped. Your transcript so far was saved.',
      action: 'Return to Thread',
      tone: 'danger'
    };
  }

  function handleBlockingAction(action: BlockingAction) {
    if (action === 'Retry Microphone') {
      void beginCall();
      return;
    }

    if (action === 'Open Settings') {
      void goto('/settings');
      return;
    }

    if (action === 'Open Character' || action === 'Choose Voice') {
      const characterId = thread?.character_id;
      void goto(characterId ? `/characters/${encodeURIComponent(characterId)}` : '/gallery');
      return;
    }

    void returnToThread();
  }

  function labelForState(state: ActiveCallState): string {
    if (state === 'connecting') {
      return 'Connecting';
    }
    if (state === 'thinking') {
      return 'Thinking';
    }
    if (state === 'speaking') {
      return 'Speaking';
    }
    if (state === 'interrupted') {
      return 'Interrupted';
    }
    if (state === 'ended') {
      return 'Ended';
    }
    if (state === 'failed') {
      return 'Failed';
    }
    return 'Listening';
  }
</script>

<section class="call-route" aria-labelledby="call-title">
  <header class="call-header">
    <button class="icon-button" type="button" aria-label="Return to Thread" on:click={returnToThread}>
      <ArrowLeft size={18} strokeWidth={1.8} aria-hidden="true" />
    </button>
    <div>
      <p>{characterName}</p>
      <h1 id="call-title">{title}</h1>
    </div>
    <StatusChip label={statusLabel} tone={statusTone} />
  </header>

  {#if loadState === 'loading'}
    <div class="blocking-panel" role="status">
      <RefreshCw size={22} strokeWidth={1.8} aria-hidden="true" />
      <h2>Connecting</h2>
    </div>
  {:else if blockingPanel}
    <div class:danger={blockingPanel.tone === 'danger'} class="blocking-panel" role="alert">
      {#if blockingPanel.action === 'Open Settings'}
        <Settings size={24} strokeWidth={1.8} aria-hidden="true" />
      {:else}
        <UserRound size={24} strokeWidth={1.8} aria-hidden="true" />
      {/if}
      <h2>{blockingPanel.action}</h2>
      <p>{blockingPanel.body}</p>
      <button type="button" on:click={() => handleBlockingAction(blockingPanel!.action)}>
        {blockingPanel.action}
      </button>
    </div>
  {:else if callState === 'ended'}
    <div class="ended-panel" role="status">
      <h2>Call ended</h2>
      <p>Your transcript so far was saved to the thread.</p>
      <button type="button" on:click={returnToThread}>Return to Thread</button>
    </div>
  {:else}
    <div class="call-canvas">
      <VoiceVisualizer state={visualState} {listeningRms} {speakingRms} />
      <CallTranscript {transcript} {activeAiText} interrupted={callState === 'interrupted'} />
    </div>

    <div class="toolbar-wrap">
      <CallToolbar
        muted={serverMuted}
        disabled={!canUseToolbar}
        interruptEnabled={callState === 'thinking' || callState === 'speaking'}
        endEnabled={!ending}
        inputPickerSupported={false}
        outputPickerSupported={false}
        onMuteToggle={toggleMute}
        onInterrupt={interrupt}
        onEnd={hangup}
      />
    </div>
  {/if}
</section>

<style>
  .call-route {
    display: grid;
    min-height: calc(100vh - 112px);
    gap: var(--space-lg);
    padding-bottom: var(--call-mobile-control-reserve);
    color: var(--color-text);
  }

  .call-header {
    display: grid;
    grid-template-columns: 44px minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-md);
  }

  .call-header p,
  .call-header h1,
  .blocking-panel h2,
  .blocking-panel p,
  .ended-panel h2,
  .ended-panel p {
    margin: 0;
  }

  .call-header p {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .call-header h1 {
    overflow: hidden;
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .icon-button,
  .blocking-panel button,
  .ended-panel button {
    display: inline-flex;
    min-width: 44px;
    min-height: 44px;
    align-items: center;
    justify-content: center;
    gap: var(--space-sm);
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(20, 31, 56, 0.82);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
  }

  .call-canvas {
    display: grid;
    grid-template-columns: minmax(280px, 1fr) minmax(320px, 0.86fr);
    align-items: stretch;
    gap: var(--space-lg);
    min-height: 0;
  }

  .toolbar-wrap {
    position: sticky;
    z-index: 6;
    bottom: calc(64px + env(safe-area-inset-bottom));
    display: grid;
    gap: var(--space-sm);
  }

  .blocking-panel,
  .ended-panel {
    display: grid;
    align-content: center;
    justify-items: start;
    min-height: 360px;
    gap: var(--space-md);
    border-radius: var(--radius-md);
    padding: var(--space-xl);
    background: rgba(20, 31, 56, 0.78);
    box-shadow: var(--shadow-float);
  }

  .blocking-panel.danger {
    background: rgba(255, 113, 108, 0.12);
  }

  .blocking-panel h2,
  .ended-panel h2 {
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
  }

  .blocking-panel p,
  .ended-panel p {
    color: var(--color-text-muted);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  .blocking-panel button,
  .ended-panel button {
    background: var(--pulse-gradient);
    color: var(--color-surface);
  }

  @media (max-width: 799px) {
    .call-route {
      min-height: calc(100vh - 88px);
      padding-bottom: calc(144px + env(safe-area-inset-bottom));
    }

    .call-header {
      grid-template-columns: 44px minmax(0, 1fr);
    }

    .call-header :global(.status-chip) {
      grid-column: 1 / -1;
      justify-self: start;
    }

    .call-canvas {
      grid-template-columns: 1fr;
    }

    .toolbar-wrap {
      bottom: calc(64px + env(safe-area-inset-bottom));
    }
  }
</style>
