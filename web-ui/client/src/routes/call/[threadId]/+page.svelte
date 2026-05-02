<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { ArrowLeft, RefreshCw, Settings, UserRound } from 'lucide-svelte';
  import { onDestroy, onMount } from 'svelte';

  import {
    CallApiError,
    backfillCallReconnectAudio,
    endCall,
    interruptCall,
    sendCallOffer,
    setCallMuted,
    startCall,
    submitCallTurn
  } from '$lib/api/calls';
  import { loadThread } from '$lib/api/chat';
  import type { CallErrorCode, CallEvent, CallStateName, CallTranscriptTurn, ThreadDetail } from '$lib/api/types';
  import {
    ensureRemoteCallAudioAudible,
    keepCallMicrophoneTracksLive,
    requestCallMicrophone,
    unlockCallAudioContext
  } from '$lib/call/audio';
  import CallToolbar from '$lib/components/call/CallToolbar.svelte';
  import CallTranscript from '$lib/components/call/CallTranscript.svelte';
  import VoiceVisualizer from '$lib/components/call/VoiceVisualizer.svelte';
  import StatusChip from '$lib/components/StatusChip.svelte';

  type ActiveCallState = Extract<CallStateName, 'connecting' | 'listening' | 'understanding' | 'thinking' | 'speaking' | 'interrupted' | 'ended' | 'failed'>;
  type VisualState = Extract<CallStateName, 'listening' | 'understanding' | 'thinking' | 'speaking'>;
  type BlockingAction = 'Retry Microphone' | 'Open Character' | 'Choose Voice' | 'Open Settings' | 'Return to Thread';

  interface BlockingPanel {
    body: string;
    action: BlockingAction;
    tone?: 'danger' | 'warning';
  }

  interface StartEvent {
    type?: string;
    session_id?: string;
    turn_id?: string;
    state?: string;
    listeningRms?: number;
    speakingRms?: number;
    text?: string;
  }

  interface CallAudioStats {
    duration_ms?: number;
    samples?: number;
    rms?: number;
    peak?: number;
  }

  interface LocalMicPcmChunk {
    startMs: number;
    endMs: number;
    samples: Int16Array;
  }

  interface LocalMicPcmSelection {
    startMs: number;
    endMs: number;
    samples: Int16Array;
    durationMs: number;
    rms: number;
    peak: number;
  }

  type CallTurnStreamEvent =
    | { type: 'ai_token'; turn_id?: string; text?: string }
    | { type: 'ai_audio_started'; turn_id?: string; session_id?: string; audio?: CallAudioStats | null }
    | { type: 'ai_done'; turn_id?: string }
    | { type: 'error'; turn_id?: string; code?: string; message?: string };

  type MediaReconnectReason = 'failed' | 'disconnected';

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
  const handledUserFinalTurnIds = new Set<string>();
  let activeTurnAbort: AbortController | null = null;
  let activeTurnReader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  let localMediaStream: MediaStream | null = null;
  let peerConnection: RTCPeerConnection | null = null;
  let eventsChannel: RTCDataChannel | null = null;
  let mediaReconnectTimer = 0;
  let mediaReconnecting = false;
  let mediaReconnectAttempts = 0;
  let localAudioContext: AudioContext | null = null;
  let localMicSource: MediaStreamAudioSourceNode | null = null;
  let localMicAnalyser: AnalyserNode | null = null;
  let localMicRecorderProcessor: ScriptProcessorNode | null = null;
  let localMicRecorderGain: GainNode | null = null;
  let localMicPcmBuffer: LocalMicPcmChunk[] = [];
  let reconnectAudioBackfillStartMs = -1;
  let reconnectAudioBackfillLastEndMs = 0;
  let reconnectAudioBackfillBatchIndex = 0;
  let reconnectAudioBackfillId = '';
  let reconnectAudioBackfillReason: MediaReconnectReason | null = null;
  let reconnectAudioBackfillFlushPromise: Promise<void> | null = null;
  let reconnectAudioBackfillFinalPromise: Promise<void> | null = null;
  let localMicMeterFrame = 0;
  let localMicRawRms: number | null = null;
  let localMicRawPeak: number | null = null;
  let localMicReconnectDiagTimer = 0;
  let localMicReconnectDiagStartedAt = 0;
  let localMicReconnectDiagTick = 0;
  let remoteAudioElement: HTMLAudioElement | null = null;
  let remoteAudioContext: AudioContext | null = null;
  let remoteAudioSource: MediaStreamAudioSourceNode | null = null;
  let remoteAudioAnalyser: AnalyserNode | null = null;
  let remoteAudioMeterSink: GainNode | null = null;
  let remoteAudioMeterFrame = 0;
  let remoteAudioMeterTicks = 0;
  let remoteAudioNonZeroLogged = false;

  const MEDIA_RECONNECT_DISCONNECTED_GRACE_MS = 2500;
  const MEDIA_RECONNECT_MAX_ATTEMPTS = 2;
  const MEDIA_RECONNECT_MIC_DIAG_MS = 7000;
  const MEDIA_RECONNECT_MIC_DIAG_INTERVAL_MS = 500;
  const MIC_BACKFILL_SAMPLE_RATE = 16000;
  const MIC_BACKFILL_ROLLING_MS = 35000;
  const MIC_BACKFILL_RECONNECT_PREROLL_MS = 30000;
  const MIC_BACKFILL_MAX_MS = 30000;

  const threadId = $derived(page.params.threadId ?? '');
  const characterName = $derived(thread?.character_name ?? 'RayMe');
  const title = $derived(thread?.title?.trim() || characterName);
  const visualState = $derived<VisualState>(
    callState === 'understanding' || callState === 'thinking' || callState === 'speaking'
      ? callState
      : 'listening'
  );
  const statusTone = $derived(callState === 'failed' ? 'danger' : callState === 'connecting' ? 'neutral' : 'healthy');
  const statusLabel = $derived(labelForState(callState));
  const callControlStateLabel = $derived(callState === 'listening' ? 'Ready to speak' : statusLabel);
  const canUseToolbar = $derived(callState !== 'connecting' && callState !== 'ended' && callState !== 'failed');

  onMount(() => {
    void initializeCall();
  });

  onDestroy(() => {
    clearEventTimers();
    cancelActiveTurnStream();
    stopBrowserMedia();
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
      return;
    }

    await beginCall();
  }

  async function beginCall() {
    callState = 'connecting';
    clearEventTimers();
    handledUserFinalTurnIds.clear();

    try {
      localMediaStream = await requestCallMicrophone();
      startLocalMicMeter(localMediaStream);
      await unlockAudioForCall();
      const started = await startCall({ thread_id: threadId });
      callId = started.call_id;
      sessionId = started.session_id || started.call_id;
      await connectBrowserMedia(started);
      applyCallState(started.state ?? 'listening');
      applyStartEvents((started as typeof started & { events?: StartEvent[] }).events ?? []);

      if (callState === 'listening' && listeningRms === null) {
        listeningRms = 0.22;
      }

    } catch (error) {
      await failCallStartup(error);
    }
  }

  async function connectBrowserMedia(
    started: { call_id: string; session_id?: string | null },
    options: { beforeRemoteDescription?: () => Promise<void> } = {}
  ) {
    if (!localMediaStream) {
      return;
    }

    if (typeof RTCPeerConnection === 'undefined') {
      throw new CallApiError('This browser cannot start a real WebRTC call.', 400, 'webrtc_offer_failed');
    }

    peerConnection?.close();
    const connection = new RTCPeerConnection();
    peerConnection = connection;
    attachPeerConnectionDebug(connection, started.call_id);
    eventsChannel = connection.createDataChannel('rayme-events');
    attachCallEventChannel(eventsChannel, started.call_id, 'browser-created');
    connection.ondatachannel = (event) => {
      emitDebugEvent(started.call_id, 'pc.ondatachannel', {
        label: event.channel.label,
        readyState: event.channel.readyState
      });
      if (event.channel.label === 'rayme-events') {
        eventsChannel = event.channel;
        attachCallEventChannel(event.channel, started.call_id, 'remote-attached');
      }
    };
    connection.ontrack = (event) => {
      emitDebugEvent(started.call_id, 'pc.ontrack', {
        kind: event.track.kind,
        id: event.track.id,
        readyState: event.track.readyState,
        streams: event.streams.length
      });
      const stream = event.streams[0] ?? new MediaStream([event.track]);
      attachRemoteAudio(stream, started.call_id);
    };
    for (const track of localMediaStream.getAudioTracks()) {
      emitDebugEvent(started.call_id, 'pc.addTrack', {
        kind: track.kind,
        id: track.id,
        readyState: track.readyState,
        muted: track.muted,
        enabled: track.enabled,
        settings: summarizeLocalAudioTrackSettings(track)
      });
      connection.addTrack(track, localMediaStream);
    }

    const offer = await connection.createOffer();
    await connection.setLocalDescription(offer);
    emitDebugEvent(started.call_id, 'pc.setLocalDescription', {
      type: offer.type,
      sdp_len: offer.sdp?.length ?? 0
    });
    await waitForIceGathering(connection);
    const localDescription = connection.localDescription ?? offer;
    emitDebugEvent(started.call_id, 'pc.offer.sending', {
      iceGatheringState: connection.iceGatheringState,
      sdp_len: localDescription.sdp?.length ?? 0
    });
    const response = await sendCallOffer(started.call_id, localDescription, started.session_id);
    sessionId = response.session_id || started.session_id || started.call_id;
    emitDebugEvent(started.call_id, 'pc.answer.received', {
      session_id: sessionId,
      has_answer: Boolean(response.answer),
      answer_sdp_len: response.answer?.sdp?.length ?? 0
    });
    if (options.beforeRemoteDescription) {
      await options.beforeRemoteDescription();
    }
    if (response.answer) {
      await connection.setRemoteDescription(response.answer);
      emitDebugEvent(started.call_id, 'pc.setRemoteDescription.done', {
        signalingState: connection.signalingState,
        iceConnectionState: connection.iceConnectionState,
        connectionState: connection.connectionState
      });
    }
  }

  function attachPeerConnectionDebug(connection: RTCPeerConnection, debugCallId: string) {
    connection.addEventListener('iceconnectionstatechange', () => {
      const iceConnectionState = connection.iceConnectionState;
      emitDebugEvent(debugCallId, 'pc.iceconnectionstatechange', {
        iceConnectionState
      });
      if (iceConnectionState === 'failed' || iceConnectionState === 'disconnected') {
        scheduleBrowserMediaReconnect(
          connection,
          debugCallId,
          iceConnectionState === 'failed' ? 'failed' : 'disconnected'
        );
      }
      if ((iceConnectionState === 'connected' || iceConnectionState === 'completed') && isBrowserMediaConnected(connection)) {
        clearMediaReconnectTimer();
        mediaReconnectAttempts = 0;
        clearReconnectAudioBackfill();
        emitLocalMicReconnectDiagnostic(debugCallId, {
          phase: 'recovered',
          reason: 'disconnected',
          source: 'iceconnectionstatechange'
        });
      }
    });
    connection.addEventListener('connectionstatechange', () => {
      emitDebugEvent(debugCallId, 'pc.connectionstatechange', {
        connectionState: connection.connectionState
      });
      if (connection.connectionState === 'failed' || connection.connectionState === 'disconnected') {
        emitDebugEvent(debugCallId, 'pc.connection.failed', {
          connectionState: connection.connectionState,
          iceConnectionState: connection.iceConnectionState,
          remoteAudioContextState: remoteAudioContext?.state ?? 'none',
          remoteAudioElementPlaying: remoteAudioElement ? !remoteAudioElement.paused : false,
          speakingRms: speakingRms
        });
        scheduleBrowserMediaReconnect(
          connection,
          debugCallId,
          connection.connectionState === 'failed' ? 'failed' : 'disconnected'
        );
      }
      if (connection.connectionState === 'connected' && isBrowserMediaConnected(connection)) {
        clearMediaReconnectTimer();
        mediaReconnectAttempts = 0;
        clearReconnectAudioBackfill();
        emitLocalMicReconnectDiagnostic(debugCallId, {
          phase: 'recovered',
          reason: 'failed',
          source: 'connectionstatechange'
        });
        try {
          if (eventsChannel && (eventsChannel.readyState === 'closed' || eventsChannel.readyState === 'closing')) {
            emitDebugEvent(debugCallId, 'datachannel.recreate', {
              previousReadyState: eventsChannel.readyState
            });
            eventsChannel = connection.createDataChannel('rayme-events');
            attachCallEventChannel(eventsChannel, debugCallId, 'recreated');
          }
        } catch {
          // Ignore errors during recovery attempt
        }
      }
    });
    connection.addEventListener('signalingstatechange', () => {
      emitDebugEvent(debugCallId, 'pc.signalingstatechange', {
        signalingState: connection.signalingState
      });
    });
    connection.addEventListener('icegatheringstatechange', () => {
      emitDebugEvent(debugCallId, 'pc.icegatheringstatechange', {
        iceGatheringState: connection.iceGatheringState
      });
    });
    connection.addEventListener('icecandidateerror', (event) => {
      const error = event as RTCPeerConnectionIceErrorEvent;
      emitDebugEvent(debugCallId, 'pc.icecandidateerror', {
        errorCode: error.errorCode,
        errorText: error.errorText,
        url: error.url
      });
    });
  }

  function scheduleBrowserMediaReconnect(
    connection: RTCPeerConnection,
    debugCallId: string,
    reason: MediaReconnectReason
  ) {
    const guardSkips: string[] = [];
    if (mediaReconnecting) {
      guardSkips.push('already_reconnecting');
    }
    if (connection !== peerConnection) {
      guardSkips.push('stale_peer');
    }
    if (!callId) {
      guardSkips.push('missing_call_id');
    }
    if (!sessionId) {
      guardSkips.push('missing_session_id');
    }
    if (!localMediaStream) {
      guardSkips.push('missing_local_media');
    }
    if (callState === 'ended' || callState === 'failed') {
      guardSkips.push(`terminal_state_${callState}`);
    }

    if (guardSkips.length > 0) {
      emitMediaReconnectGuardSkip(connection, debugCallId, reason, 'schedule', guardSkips);
      return;
    }
    if (mediaReconnectTimer) {
      if (reason === 'failed') {
        clearMediaReconnectTimer();
        emitDebugEvent(debugCallId, 'pc.media_reconnect.upgrade', {
          reason,
          attempts: mediaReconnectAttempts,
          connectionState: connection.connectionState,
          iceConnectionState: connection.iceConnectionState
        });
      } else {
        emitMediaReconnectGuardSkip(connection, debugCallId, reason, 'schedule', ['timer_pending']);
        return;
      }
    }
    if (mediaReconnectAttempts >= MEDIA_RECONNECT_MAX_ATTEMPTS) {
      emitDebugEvent(debugCallId, 'pc.media_reconnect.give_up', {
        reason,
        attempts: mediaReconnectAttempts
      });
      applyCallState('failed');
      blockingPanel = {
        body: 'The call ended because the connection dropped. Your transcript so far was saved.',
        action: 'Return to Thread',
        tone: 'danger'
      };
      return;
    }

    const delayMs = reason === 'failed' ? 0 : MEDIA_RECONNECT_DISCONNECTED_GRACE_MS;
    emitDebugEvent(debugCallId, 'pc.media_reconnect.scheduled', {
      reason,
      delayMs,
      attempts: mediaReconnectAttempts
    });
    startReconnectAudioBackfill(debugCallId, reason);
    emitLocalMicReconnectDiagnostic(debugCallId, {
      phase: 'scheduled',
      reason,
      delayMs,
      attempts: mediaReconnectAttempts
    });
    startLocalMicReconnectDiagnostics(debugCallId, reason);
    mediaReconnectTimer = window.setTimeout(() => {
      mediaReconnectTimer = 0;
      if (isBrowserMediaConnected(connection)) {
        clearReconnectAudioBackfill();
        emitLocalMicReconnectDiagnostic(debugCallId, {
          phase: 'schedule_cancelled_connected',
          reason,
          attempts: mediaReconnectAttempts
        });
        return;
      }
      void reconnectBrowserMedia(connection, debugCallId, reason);
    }, delayMs);
  }

  async function reconnectBrowserMedia(
    failedConnection: RTCPeerConnection,
    debugCallId: string,
    reason: MediaReconnectReason
  ) {
    const guardSkips: string[] = [];
    if (mediaReconnecting) {
      guardSkips.push('already_reconnecting');
    }
    if (failedConnection !== peerConnection) {
      guardSkips.push('stale_peer');
    }
    if (!localMediaStream) {
      guardSkips.push('missing_local_media');
    }
    if (!callId) {
      guardSkips.push('missing_call_id');
    }
    if (!sessionId) {
      guardSkips.push('missing_session_id');
    }
    if (guardSkips.length > 0) {
      emitMediaReconnectGuardSkip(failedConnection, debugCallId, reason, 'start', guardSkips);
      return;
    }

    mediaReconnecting = true;
    mediaReconnectAttempts += 1;
    const reconnectAttempt = mediaReconnectAttempts;
    startReconnectAudioBackfill(debugCallId, reason);
    emitDebugEvent(debugCallId, 'pc.media_reconnect.start', {
      reason,
      attempt: reconnectAttempt
    });
    emitLocalMicReconnectDiagnostic(debugCallId, {
      phase: 'start',
      reason,
      attempt: reconnectAttempt
    });

    try {
      detachRemoteAudio();
      eventsChannel?.close?.();
      eventsChannel = null;
      failedConnection.close();
      if (peerConnection === failedConnection) {
        peerConnection = null;
      }

      await connectBrowserMedia(
        { call_id: callId, session_id: sessionId },
        {
          beforeRemoteDescription: () =>
            flushReconnectAudioBackfill(debugCallId, reason, reconnectAttempt)
        }
      );
      applyCallState('listening');
      emitDebugEvent(debugCallId, 'pc.media_reconnect.ok', {
        attempt: reconnectAttempt
      });
      emitLocalMicReconnectDiagnostic(debugCallId, {
        phase: 'ok',
        reason,
        attempt: reconnectAttempt
      });
    } catch (error) {
      emitDebugEvent(debugCallId, 'pc.media_reconnect.failed', {
        attempt: reconnectAttempt,
        name: (error as DOMException)?.name ?? 'unknown',
        message: (error as Error)?.message ?? ''
      });
      emitLocalMicReconnectDiagnostic(debugCallId, {
        phase: 'failed',
        reason,
        attempt: reconnectAttempt,
        name: (error as DOMException)?.name ?? 'unknown'
      });
      if (mediaReconnectAttempts >= MEDIA_RECONNECT_MAX_ATTEMPTS) {
        applyCallState('failed');
        blockingPanel = {
          body: 'The call ended because the connection dropped. Your transcript so far was saved.',
          action: 'Return to Thread',
          tone: 'danger'
        };
      }
    } finally {
      mediaReconnecting = false;
    }
  }

  function clearMediaReconnectTimer() {
    if (mediaReconnectTimer) {
      window.clearTimeout(mediaReconnectTimer);
      mediaReconnectTimer = 0;
    }
  }

  function isBrowserMediaConnected(connection: RTCPeerConnection) {
    return (
      connection.connectionState === 'connected' &&
      (connection.iceConnectionState === 'connected' || connection.iceConnectionState === 'completed')
    );
  }

  function emitMediaReconnectGuardSkip(
    connection: RTCPeerConnection,
    debugCallId: string,
    reason: MediaReconnectReason,
    phase: 'schedule' | 'start',
    guardSkips: string[]
  ) {
    emitDebugEvent(debugCallId, 'pc.media_reconnect.guard_skip', {
      reason,
      phase,
      guardSkips,
      attempts: mediaReconnectAttempts,
      hasTimer: Boolean(mediaReconnectTimer),
      mediaReconnecting,
      callState,
      connectionState: connection.connectionState,
      iceConnectionState: connection.iceConnectionState,
      isCurrentPeer: connection === peerConnection,
      hasCallId: Boolean(callId),
      hasSessionId: Boolean(sessionId),
      hasLocalMedia: Boolean(localMediaStream)
    });
  }

  function startLocalMicReconnectDiagnostics(debugCallId: string, reason: MediaReconnectReason) {
    stopLocalMicReconnectDiagnostics();
    localMicReconnectDiagStartedAt = Date.now();
    localMicReconnectDiagTick = 0;

    const emitNext = () => {
      const elapsedMs = Date.now() - localMicReconnectDiagStartedAt;
      localMicReconnectDiagTick += 1;
      emitLocalMicReconnectDiagnostic(debugCallId, {
        phase: 'interval',
        reason,
        elapsedMs,
        tick: localMicReconnectDiagTick,
        attempts: mediaReconnectAttempts,
        mediaReconnecting
      });

      if (elapsedMs >= MEDIA_RECONNECT_MIC_DIAG_MS || !localMediaStream) {
        stopLocalMicReconnectDiagnostics();
        return;
      }

      localMicReconnectDiagTimer = window.setTimeout(
        emitNext,
        MEDIA_RECONNECT_MIC_DIAG_INTERVAL_MS
      );
    };

    emitNext();
  }

  function stopLocalMicReconnectDiagnostics() {
    if (localMicReconnectDiagTimer) {
      window.clearTimeout(localMicReconnectDiagTimer);
      localMicReconnectDiagTimer = 0;
    }
    localMicReconnectDiagStartedAt = 0;
    localMicReconnectDiagTick = 0;
  }

  function startReconnectAudioBackfill(debugCallId: string, reason: MediaReconnectReason) {
    if (reconnectAudioBackfillStartMs >= 0) {
      return;
    }
    const nowMs = performance.now();
    reconnectAudioBackfillStartMs = Math.max(0, nowMs - MIC_BACKFILL_RECONNECT_PREROLL_MS);
    reconnectAudioBackfillLastEndMs = 0;
    reconnectAudioBackfillBatchIndex = 0;
    reconnectAudioBackfillId = `${debugCallId || 'call'}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    reconnectAudioBackfillReason = reason;
    emitDebugEvent(debugCallId, 'mic.reconnect_backfill.start', {
      reason,
      backfillId: reconnectAudioBackfillId,
      startOffsetMs: Math.round(nowMs - reconnectAudioBackfillStartMs),
      bufferedChunks: localMicPcmBuffer.length
    });
  }

  function clearReconnectAudioBackfill(backfillId?: string) {
    if (backfillId && reconnectAudioBackfillId && reconnectAudioBackfillId !== backfillId) {
      return;
    }
    reconnectAudioBackfillStartMs = -1;
    reconnectAudioBackfillLastEndMs = 0;
    reconnectAudioBackfillBatchIndex = 0;
    reconnectAudioBackfillId = '';
    reconnectAudioBackfillReason = null;
    reconnectAudioBackfillFlushPromise = null;
    reconnectAudioBackfillFinalPromise = null;
  }

  async function flushReconnectAudioBackfill(
    debugCallId: string,
    reason: MediaReconnectReason,
    attempt: number,
    options: { awaitFinal?: boolean } = {}
  ) {
    if (reconnectAudioBackfillFlushPromise) {
      await reconnectAudioBackfillFlushPromise;
      if (options.awaitFinal && reconnectAudioBackfillFinalPromise) {
        await reconnectAudioBackfillFinalPromise;
      }
      return;
    }
    const flushPromise = flushReconnectAudioBackfillOnce(debugCallId, reason, attempt, options);
    const trackedFlushPromise = flushPromise.finally(() => {
      if (reconnectAudioBackfillFlushPromise === trackedFlushPromise) {
        reconnectAudioBackfillFlushPromise = null;
      }
    });
    reconnectAudioBackfillFlushPromise = trackedFlushPromise;
    await trackedFlushPromise;
  }

  async function flushReconnectAudioBackfillOnce(
    debugCallId: string,
    reason: MediaReconnectReason,
    attempt: number,
    options: { awaitFinal?: boolean } = {}
  ) {
    if (!callId || !sessionId || reconnectAudioBackfillStartMs < 0) {
      return;
    }
    const requestCallId = callId;
    const requestSessionId = sessionId;
    const reconnectStartMs = reconnectAudioBackfillStartMs;
    const baseBackfillId = reconnectAudioBackfillId;
    const backfillReason = reconnectAudioBackfillReason ?? reason;
    const selection = selectReconnectAudioBackfill(performance.now());
    if (!selection) {
      emitDebugEvent(debugCallId, 'mic.reconnect_backfill.skip', {
        reason,
        attempt,
        backfillId: baseBackfillId,
        cause: 'empty',
        bufferedChunks: localMicPcmBuffer.length
      });
      reconnectAudioBackfillBatchIndex += 1;
      const finalPromise = trackReconnectAudioBackfillFinalPromise(sendReconnectAudioBackfillBatch({
        debugCallId,
        requestCallId,
        requestSessionId,
        baseBackfillId,
        reconnectStartMs,
        reason: backfillReason,
        attempt,
        batchIndex: reconnectAudioBackfillBatchIndex,
        final: true,
        selection: null
      }).finally(() => clearReconnectAudioBackfill(baseBackfillId)));
      if (options.awaitFinal) {
        await finalPromise;
      } else {
        void finalPromise;
      }
      return;
    }

    reconnectAudioBackfillBatchIndex += 1;
    const initialBatchIndex = reconnectAudioBackfillBatchIndex;
    await sendReconnectAudioBackfillBatch({
      debugCallId,
      requestCallId,
      requestSessionId,
      baseBackfillId,
      reconnectStartMs,
      reason: backfillReason,
      attempt,
      batchIndex: initialBatchIndex,
      final: false,
      selection
    });
    reconnectAudioBackfillLastEndMs = selection.endMs;

    const tailSelection = selectReconnectAudioBackfill(
      performance.now(),
      reconnectAudioBackfillLastEndMs
    );
    reconnectAudioBackfillBatchIndex += 1;
    const finalBatchIndex = reconnectAudioBackfillBatchIndex;
    const finalPromise = trackReconnectAudioBackfillFinalPromise(sendReconnectAudioBackfillBatch({
      debugCallId,
      requestCallId,
      requestSessionId,
      baseBackfillId,
      reconnectStartMs,
      reason: backfillReason,
      attempt,
      batchIndex: finalBatchIndex,
      final: true,
      selection: tailSelection
    }).finally(() => clearReconnectAudioBackfill(baseBackfillId)));
    if (options.awaitFinal) {
      await finalPromise;
    } else {
      void finalPromise;
    }
  }

  function trackReconnectAudioBackfillFinalPromise(promise: Promise<void>) {
    const trackedPromise = promise.finally(() => {
      if (reconnectAudioBackfillFinalPromise === trackedPromise) {
        reconnectAudioBackfillFinalPromise = null;
      }
    });
    reconnectAudioBackfillFinalPromise = trackedPromise;
    return trackedPromise;
  }

  async function sendReconnectAudioBackfillBatch({
    debugCallId,
    requestCallId,
    requestSessionId,
    baseBackfillId,
    reconnectStartMs,
    reason,
    attempt,
    batchIndex,
    final,
    selection
  }: {
    debugCallId: string;
    requestCallId: string;
    requestSessionId: string;
    baseBackfillId: string;
    reconnectStartMs: number;
    reason: MediaReconnectReason;
    attempt: number;
    batchIndex: number;
    final: boolean;
    selection: LocalMicPcmSelection | null;
  }) {
    const batchBackfillId = `${baseBackfillId}-batch-${batchIndex}`;
    const selectedStartOffsetMs =
      selection ? Math.round(selection.startMs - reconnectStartMs) : null;
    const selectedEndOffsetMs =
      selection ? Math.round(selection.endMs - reconnectStartMs) : null;
    emitDebugEvent(debugCallId, 'mic.reconnect_backfill.sending', {
      reason,
      attempt,
      backfillId: batchBackfillId,
      baseBackfillId,
      batchIndex,
      final,
      selectedStartOffsetMs,
      selectedEndOffsetMs,
      durationMs: selection?.durationMs ?? 0,
      samples: selection?.samples.length ?? 0,
      rms: selection?.rms ?? 0,
      peak: selection?.peak ?? 0
    });
    try {
      const response = await backfillCallReconnectAudio(requestCallId, {
        session_id: requestSessionId,
        pcm_b64: selection ? int16SamplesToBase64(selection.samples) : '',
        sample_rate: MIC_BACKFILL_SAMPLE_RATE,
        channels: 1,
        backfill_id: batchBackfillId,
        reason,
        attempt,
        duration_ms: selection?.durationMs ?? 0,
        batch_index: batchIndex,
        final
      });
      emitDebugEvent(debugCallId, 'mic.reconnect_backfill.sent', {
        reason,
        attempt,
        backfillId: batchBackfillId,
        baseBackfillId,
        batchIndex,
        final,
        selectedStartOffsetMs,
        selectedEndOffsetMs,
        durationMs: selection?.durationMs ?? 0,
        samples: selection?.samples.length ?? 0,
        rms: selection?.rms ?? 0,
        peak: selection?.peak ?? 0,
        status: response.status,
        frames: response.frames ?? null,
        responseDurationMs: response.duration_ms ?? null
      });
      if (response.event) {
        await handleCallDataEvent(response.event);
      }
    } catch (error) {
      emitDebugEvent(debugCallId, 'mic.reconnect_backfill.failed', {
        reason,
        attempt,
        backfillId: batchBackfillId,
        baseBackfillId,
        batchIndex,
        final,
        selectedStartOffsetMs,
        selectedEndOffsetMs,
        durationMs: selection?.durationMs ?? 0,
        samples: selection?.samples.length ?? 0,
        name: (error as Error)?.name ?? 'unknown',
        message: (error as Error)?.message ?? ''
      });
    }
  }

  function selectReconnectAudioBackfill(
    endMs: number,
    startMsOverride = reconnectAudioBackfillStartMs
  ): LocalMicPcmSelection | null {
    const startMs = Math.max(
      startMsOverride,
      endMs - MIC_BACKFILL_MAX_MS
    );
    const chunks = localMicPcmBuffer.filter((chunk) => chunk.endMs > startMs && chunk.startMs < endMs);
    const sampleCount = chunks.reduce((total, chunk) => total + chunk.samples.length, 0);
    if (sampleCount <= 0) {
      return null;
    }
    const samples = new Int16Array(sampleCount);
    let offset = 0;
    let sumSquares = 0;
    let peak = 0;
    for (const chunk of chunks) {
      samples.set(chunk.samples, offset);
      offset += chunk.samples.length;
      for (const sample of chunk.samples) {
        const abs = Math.abs(sample);
        peak = Math.max(peak, abs);
        sumSquares += sample * sample;
      }
    }
    const durationMs = Math.round(samples.length * 1000 / MIC_BACKFILL_SAMPLE_RATE);
    return {
      startMs: chunks[0]?.startMs ?? startMs,
      endMs: chunks[chunks.length - 1]?.endMs ?? endMs,
      samples,
      durationMs,
      rms: Math.sqrt(sumSquares / samples.length),
      peak
    };
  }

  function emitLocalMicReconnectDiagnostic(
    debugCallId: string,
    detail: Record<string, unknown>
  ) {
    emitDebugEvent(debugCallId, 'mic.reconnect_diag', {
      ...detail,
      callState,
      hasLocalMedia: Boolean(localMediaStream),
      trackCount: localMediaStream?.getAudioTracks().length ?? 0,
      tracks: summarizeLocalAudioTracks(),
      localAudioContextState: localAudioContext?.state ?? 'none',
      listeningRms,
      localMicRawRms,
      localMicRawPeak
    });
  }

  function summarizeLocalAudioTracks() {
    return (localMediaStream?.getAudioTracks() ?? []).map((track) => ({
      id: track.id,
      kind: track.kind,
      readyState: track.readyState,
      muted: track.muted,
      enabled: track.enabled,
      settings: summarizeLocalAudioTrackSettings(track)
    }));
  }

  function summarizeLocalAudioTrackSettings(track: MediaStreamTrack) {
    const settings =
      typeof track.getSettings === 'function'
        ? track.getSettings()
        : ({} as MediaTrackSettings);
    return {
      sampleRate: settings.sampleRate ?? null,
      sampleSize: settings.sampleSize ?? null,
      channelCount: settings.channelCount ?? null,
      echoCancellation: settings.echoCancellation ?? null,
      noiseSuppression: settings.noiseSuppression ?? null,
      autoGainControl: settings.autoGainControl ?? null,
      deviceIdPresent: Boolean(settings.deviceId),
      groupIdPresent: Boolean(settings.groupId)
    };
  }

  function emitDebugEvent(debugCallId: string, name: string, detail: Record<string, unknown>): void {
    try {
      // eslint-disable-next-line no-console
      console.log(`[rayme-call] ${name}`, detail);
    } catch {
      // Console logging cannot block diagnostics.
    }

    if (!debugCallId) {
      return;
    }

    try {
      void fetch(`/api/calls/${encodeURIComponent(debugCallId)}/_debug/event`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event: name, detail, session_id: sessionId || undefined }),
        keepalive: true
      }).catch(() => undefined);
    } catch {
      // Diagnostic delivery failures must not affect the call.
    }
  }

  async function failCallStartup(error: unknown) {
    clearEventTimers();
    cancelActiveTurnStream();
    stopBrowserMedia();
    showBlockingPanel(error);

    if (!callId || !sessionId) {
      return;
    }

    try {
      await endCall(callId, sessionId, 'setup_failed');
    } catch {
      // Startup failure is already visible; teardown failures are not actionable here.
    }
  }

  function attachCallEventChannel(channel: RTCDataChannel, debugCallId = '', source = 'unknown') {
    emitDebugEvent(debugCallId, 'datachannel.attach', {
      label: channel.label,
      readyState: channel.readyState,
      source
    });
    channel.onopen = () => {
      emitDebugEvent(debugCallId, 'datachannel.open', {
        label: channel.label,
        source
      });
    };
    channel.onclose = () => {
      emitDebugEvent(debugCallId, 'datachannel.close', {
        label: channel.label,
        source
      });
    };
    channel.onerror = (event) => {
      const error = (event as RTCErrorEvent).error;
      emitDebugEvent(debugCallId, 'datachannel.error', {
        label: channel.label,
        source,
        errorName: error?.name ?? 'unknown',
        errorMessage: error?.message ?? ''
      });
    };
    channel.onmessage = (message) => {
      const event = parseCallDataEvent(message.data);
      emitDebugEvent(debugCallId, 'datachannel.message', {
        label: channel.label,
        source,
        bytes: typeof message.data === 'string' ? message.data.length : -1,
        event_type: event?.type ?? 'unparseable'
      });
      // Respond to backend keepalive pings to maintain bidirectional
      // packet flow and prevent ICE timeout during processing gaps.
      if (event?.type === 'ping') {
        try {
          channel.send(JSON.stringify({ type: 'pong' }));
        } catch {
          // Ping response failure is non-actionable.
        }
        return;
      }
      // Backend may send ai_audio_started / ai_done via data channel
      // when the WebRTC connection is still alive even if the /turns SSE
      // stream has not yet delivered them. Handle them here as a fallback.
      if (event?.type === 'ai_audio_started' || event?.type === 'ai_done') {
        void handleCallDataEvent(event);
        return;
      }
      if (event) {
        void handleCallDataEvent(event);
      }
    };
  }

  function parseCallDataEvent(data: unknown): CallEvent | null {
    if (typeof data !== 'string') {
      return null;
    }

    try {
      const parsed = JSON.parse(data) as Partial<CallEvent>;
      return parsed && typeof parsed.type === 'string' ? (parsed as CallEvent) : null;
    } catch {
      return null;
    }
  }

  function startLocalMicMeter(stream: MediaStream) {
    stopLocalMicMeter();
    const AudioContextCtor =
      typeof AudioContext !== 'undefined'
        ? AudioContext
        : (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext })
            .webkitAudioContext;
    if (!AudioContextCtor || typeof requestAnimationFrame === 'undefined') {
      listeningRms = 0.18;
      return;
    }

    try {
      const context = new AudioContextCtor();
      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      attachLocalMicPcmRecorder(context, source);
      if (context.state === 'suspended') {
        void context.resume().catch(() => undefined);
      }
      localAudioContext = context;
      localMicSource = source;
      localMicAnalyser = analyser;
      const samples = new Float32Array(analyser.fftSize);

      const updateMeter = () => {
        if (localMicAnalyser !== analyser) {
          return;
        }
        analyser.getFloatTimeDomainData(samples);
        let sumSquares = 0;
        let peak = 0;
        for (const sample of samples) {
          sumSquares += sample * sample;
          peak = Math.max(peak, Math.abs(sample));
        }
        const rms = Math.sqrt(sumSquares / samples.length);
        localMicRawRms = rms;
        localMicRawPeak = peak;
        listeningRms = Math.max(0.04, Math.min(1, rms * 3.2));
        localMicMeterFrame = requestAnimationFrame(updateMeter);
      };

      localMicMeterFrame = requestAnimationFrame(updateMeter);
    } catch {
      listeningRms = 0.18;
    }
  }

  function attachLocalMicPcmRecorder(
    context: AudioContext,
    source: MediaStreamAudioSourceNode
  ) {
    if (typeof context.createScriptProcessor !== 'function') {
      return;
    }
    try {
      const processor = context.createScriptProcessor(4096, 1, 1);
      const silentSink = context.createGain();
      silentSink.gain.value = 0;
      processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0);
        const sourceRate = event.inputBuffer.sampleRate || context.sampleRate;
        const sourceDurationMs = input.length * 1000 / Math.max(sourceRate, 1);
        const endMs = performance.now();
        const samples = downsampleFloatToInt16(
          input,
          sourceRate,
          MIC_BACKFILL_SAMPLE_RATE
        );
        appendLocalMicPcmChunk({
          startMs: endMs - sourceDurationMs,
          endMs,
          samples
        });
      };
      source.connect(processor);
      processor.connect(silentSink);
      silentSink.connect(context.destination);
      localMicRecorderProcessor = processor;
      localMicRecorderGain = silentSink;
    } catch {
      localMicRecorderProcessor = null;
      localMicRecorderGain = null;
    }
  }

  function appendLocalMicPcmChunk(chunk: LocalMicPcmChunk) {
    if (!chunk.samples.length) {
      return;
    }
    localMicPcmBuffer.push(chunk);
    trimLocalMicPcmBuffer(performance.now() - MIC_BACKFILL_ROLLING_MS);
  }

  function trimLocalMicPcmBuffer(minEndMs: number) {
    while (localMicPcmBuffer.length > 0 && localMicPcmBuffer[0].endMs < minEndMs) {
      localMicPcmBuffer.shift();
    }
  }

  function downsampleFloatToInt16(
    input: Float32Array,
    sourceRate: number,
    targetRate: number
  ) {
    if (!input.length || sourceRate <= 0 || targetRate <= 0) {
      return new Int16Array();
    }
    if (sourceRate === targetRate) {
      const output = new Int16Array(input.length);
      for (let index = 0; index < input.length; index += 1) {
        output[index] = floatSampleToInt16(input[index]);
      }
      return output;
    }

    const ratio = sourceRate / targetRate;
    const outputLength = Math.max(1, Math.floor(input.length / ratio));
    const output = new Int16Array(outputLength);
    for (let index = 0; index < outputLength; index += 1) {
      const position = index * ratio;
      const leftIndex = Math.floor(position);
      const rightIndex = Math.min(leftIndex + 1, input.length - 1);
      const fraction = position - leftIndex;
      const sample = input[leftIndex] * (1 - fraction) + input[rightIndex] * fraction;
      output[index] = floatSampleToInt16(sample);
    }
    return output;
  }

  function floatSampleToInt16(sample: number) {
    const clamped = Math.max(-1, Math.min(1, sample));
    return clamped < 0
      ? Math.round(clamped * 32768)
      : Math.round(clamped * 32767);
  }

  function int16SamplesToBase64(samples: Int16Array) {
    const bytes = new Uint8Array(samples.buffer, samples.byteOffset, samples.byteLength);
    let binary = '';
    const chunkSize = 0x8000;
    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
      const chunk = bytes.subarray(offset, offset + chunkSize);
      binary += String.fromCharCode(...chunk);
    }
    return btoa(binary);
  }

  function stopLocalMicMeter() {
    if (localMicMeterFrame) {
      cancelAnimationFrame(localMicMeterFrame);
      localMicMeterFrame = 0;
    }
    localMicRecorderProcessor?.disconnect();
    localMicRecorderGain?.disconnect();
    if (localMicRecorderProcessor) {
      localMicRecorderProcessor.onaudioprocess = null;
    }
    localMicSource?.disconnect();
    localMicAnalyser?.disconnect();
    localAudioContext?.close().catch(() => undefined);
    localMicSource = null;
    localMicAnalyser = null;
    localMicRecorderProcessor = null;
    localMicRecorderGain = null;
    localAudioContext = null;
    localMicRawRms = null;
    localMicRawPeak = null;
    localMicPcmBuffer = [];
    clearReconnectAudioBackfill();
  }

  function waitForIceGathering(connection: RTCPeerConnection): Promise<void> {
    if (connection.iceGatheringState === 'complete') {
      return Promise.resolve();
    }

    return new Promise((resolve) => {
      const timeout = window.setTimeout(resolve, 1500);
      connection.addEventListener(
        'icegatheringstatechange',
        () => {
          if (connection.iceGatheringState === 'complete') {
            window.clearTimeout(timeout);
            resolve();
          }
        },
        { once: false }
      );
    });
  }

  async function unlockAudioForCall() {
    try {
      const AudioContextCtor =
        typeof AudioContext !== 'undefined'
          ? AudioContext
          : (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext })
              .webkitAudioContext;
      if (AudioContextCtor && !remoteAudioContext) {
        remoteAudioContext = new AudioContextCtor();
      }
      await unlockCallAudioContext(remoteAudioContext ?? undefined);
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
        if (event.type === 'user_final' && event.text) {
          void handleCallDataEvent({
            type: 'user_final',
            session_id: event.session_id ?? sessionId,
            turn_id: event.turn_id ?? `user-final-${Date.now()}`,
            text: event.text
          });
        }
        if (event.type === 'ai_audio_started') {
          void handleCallDataEvent({
            type: 'ai_audio_started',
            session_id: event.session_id ?? sessionId,
            turn_id: event.turn_id ?? null,
            text: event.text ?? null
          });
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
      normalized === 'understanding' ||
      normalized === 'thinking' ||
      normalized === 'speaking' ||
      normalized === 'interrupted' ||
      normalized === 'ended' ||
      normalized === 'failed' ||
      normalized === 'connecting'
    ) {
      const prevState = callState;
      callState = normalized;
      keepMicrophoneSenderLive(prevState, normalized);
      syncRemoteAudioAudibility();
    } else {
      callState = 'listening';
      keepMicrophoneSenderLive(undefined, 'listening');
      syncRemoteAudioAudibility();
    }
  }

  function keepMicrophoneSenderLive(prevState: string | undefined, nextState: string) {
    if (!localMediaStream) {
      return;
    }
    const changed = keepCallMicrophoneTracksLive(localMediaStream);
    if (changed > 0 || prevState !== nextState) {
      emitDebugEvent(callId, 'mic.keep_live', {
        changed,
        prevState: prevState ?? null,
        nextState
      });
    }
  }

  function syncRemoteAudioAudibility() {
    if (!remoteAudioElement) {
      return;
    }
    if (ensureRemoteCallAudioAudible(remoteAudioElement)) {
      emitDebugEvent(callId, 'remote_audio.audibility', {
        muted: remoteAudioElement.muted,
        callState,
        policy: 'always-audible'
      });
    }
  }

  async function handleCallDataEvent(event: CallEvent) {
    if (event.type === 'user_final') {
      if (handledUserFinalTurnIds.has(event.turn_id)) {
        return;
      }
      handledUserFinalTurnIds.add(event.turn_id);
      appendUserFinal(event.text, event.turn_id);
      await submitUserTurn(event);
      return;
    }

    if (event.type === 'state') {
      applyCallState(event.state);
      return;
    }

    if (event.type === 'ai_audio_started') {
      emitDebugEvent(callId, 'call.ai_audio_started', {
        turn_id: event.turn_id ?? null,
        audio: event.audio ?? null,
        remoteAudioContextState: remoteAudioContext?.state ?? 'none',
        speakingRms
      });
      applyCallState('speaking');
      if (event.text) {
        appendAiText(event.text, event.turn_id ?? undefined);
      }
      return;
    }

    if (event.type === 'ai_done') {
      finishAiTurn();
      return;
    }

    if (event.type === 'failed') {
      const message = messageForCallFailure(event.code, event.message);
      activeAiText = '';

      if (event.retry_allowed) {
        blockingPanel = null;
        appendCallNotice(message, event.turn_id ?? undefined);
        applyCallState('listening');
        return;
      }

      applyCallState('failed');
      blockingPanel = {
        body: message,
        action: 'Return to Thread',
        tone: 'danger'
      };
    }
  }

  function messageForCallFailure(code: CallErrorCode, message?: string | null) {
    const normalized = message?.trim();
    if (normalized) {
      return normalized;
    }

    if (code === 'call_stt_failed') {
      return 'Speech transcription failed. Please try speaking again.';
    }

    if (code === 'call_tts_failed') {
      return 'Speech playback failed. Please try again.';
    }

    return 'The call ended because the connection dropped. Your transcript so far was saved.';
  }

  function appendUserFinal(text: string, turnId?: string) {
    transcript = [
      ...transcript,
      {
        id: `user-${turnId ?? Date.now()}`,
        turn_id: turnId,
        role: 'user',
        type: 'user_speech',
        text,
        created_at: null
      }
    ];
    activeAiText = '';
    applyCallState('thinking');
  }

  function appendCallNotice(text: string, turnId?: string) {
    transcript = [
      ...transcript,
      {
        id: `event-${turnId ?? Date.now()}`,
        turn_id: turnId,
        role: 'event',
        type: 'call_notice',
        text,
        created_at: null
      }
    ];
  }

  async function submitUserTurn(event: Extract<CallEvent, { type: 'user_final' }>) {
    if (!callId || !sessionId) {
      return;
    }

    cancelActiveTurnStream();
    activeTurnAbort = new AbortController();

    try {
      const response = await submitCallTurn(
        callId,
        {
          session_id: sessionId,
          turn_id: event.turn_id,
          text: event.text,
          source: 'user_final'
        },
        { signal: activeTurnAbort.signal }
      );
      await readTurnStream(response);
    } catch (error) {
      if ((error as DOMException)?.name !== 'AbortError') {
        callState = 'failed';
      }
    } finally {
      activeTurnAbort = null;
      activeTurnReader = null;
    }
  }

  async function readTurnStream(response: Response) {
    if (!response.body) {
      throw new Error('No call turn stream');
    }

    activeTurnReader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (activeTurnReader) {
      const { value, done } = await activeTurnReader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      buffer = dispatchTurnEvents(buffer);
    }

    buffer += decoder.decode();
    dispatchTurnEvents(`${buffer}\n\n`);
  }

  function dispatchTurnEvents(buffer: string): string {
    const parts = buffer.split(/\r?\n\r?\n/);
    const remainder = parts.pop() ?? '';

    for (const part of parts) {
      const data = part
        .split(/\r?\n/)
        .filter((line) => line.startsWith('data: '))
        .map((line) => line.slice('data: '.length))
        .join('\n');
      if (!data) {
        continue;
      }
      try {
        handleTurnStreamEvent(JSON.parse(data) as CallTurnStreamEvent);
      } catch {
        // Malformed stream events are ignored; the server emits fixed public errors.
      }
    }

    return remainder;
  }

  function handleTurnStreamEvent(event: CallTurnStreamEvent) {
    if (event.type === 'ai_token' && event.text) {
      appendAiText(event.text, event.turn_id);
      return;
    }

    if (event.type === 'ai_audio_started') {
      emitDebugEvent(callId, 'call.ai_audio_started', {
        turn_id: event.turn_id ?? null,
        audio: event.audio ?? null,
        remoteAudioContextState: remoteAudioContext?.state ?? 'none',
        speakingRms,
        source: 'turn-stream'
      });
      applyCallState('speaking');
      return;
    }

    if (event.type === 'ai_done') {
      finishAiTurn();
      return;
    }

    if (event.type === 'error') {
      const message = messageForCallFailure(
        (event.code ?? 'call_generation_failed') as CallErrorCode,
        event.message
      );
      appendCallNotice(message, event.turn_id);
      applyCallState('listening');
    }
  }

  function appendAiText(text: string, turnId?: string) {
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
        turn_id: turnId,
        role: 'assistant',
        type: 'ai_speech',
        text: activeAiText,
        created_at: null
      }
    ];
  }

  function finishAiTurn() {
    activeAiText = '';
    applyCallState('listening');
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
    cancelActiveTurnStream();
    markLastAiTurnInterrupted();
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

  function cancelActiveTurnStream() {
    activeTurnAbort?.abort();
    activeTurnReader?.cancel().catch(() => undefined);
    activeTurnAbort = null;
    activeTurnReader = null;
  }

  function markLastAiTurnInterrupted() {
    for (let index = transcript.length - 1; index >= 0; index -= 1) {
      const turn = transcript[index];
      if (turn.role === 'assistant' && turn.type === 'ai_speech') {
        transcript = transcript.map((current, currentIndex) =>
          currentIndex === index ? { ...current, interrupted: true } : current
        );
        break;
      }
    }
  }

  async function hangup() {
    ending = true;
    clearEventTimers();
    cancelActiveTurnStream();

    try {
      if (callId && sessionId) {
        await drainReconnectAudioBackfillBeforeHangup();
        await endCall(callId, sessionId);
      }
      stopBrowserMedia();
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

  async function drainReconnectAudioBackfillBeforeHangup() {
    if (!callId || !sessionId || reconnectAudioBackfillStartMs < 0) {
      return;
    }
    const reason = reconnectAudioBackfillReason ?? 'disconnected';
    const attempt = Math.max(mediaReconnectAttempts, 1);
    emitDebugEvent(callId, 'mic.reconnect_backfill.hangup_flush', {
      reason,
      attempt,
      backfillId: reconnectAudioBackfillId,
      bufferedChunks: localMicPcmBuffer.length
    });
    await flushReconnectAudioBackfill(callId, reason, attempt, { awaitFinal: true });
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

      if (error.code === 'webrtc_offer_failed' || error.code === 'unreachable' || error.status >= 500) {
        blockingPanel = {
          body: error.message || 'RayMe could not connect this call.',
          action: 'Return to Thread',
          tone: 'danger'
        };
        return;
      }
    }

    if (
      error instanceof DOMException &&
      (error.name === 'NotAllowedError' ||
        error.name === 'PermissionDeniedError' ||
        error.name === 'NotFoundError')
    ) {
      blockingPanel = {
        body: 'Microphone access is blocked. Allow microphone access in Chrome, then retry.',
        action: 'Retry Microphone',
        tone: 'danger'
      };
      return;
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

  function stopBrowserMedia() {
    clearMediaReconnectTimer();
    stopLocalMicReconnectDiagnostics();
    mediaReconnecting = false;
    stopLocalMicMeter();
    detachRemoteAudio();
    remoteAudioContext?.close().catch(() => undefined);
    remoteAudioContext = null;
    eventsChannel?.close?.();
    eventsChannel = null;
    peerConnection?.close?.();
    peerConnection = null;
    localMediaStream?.getTracks().forEach((track) => track.stop());
    localMediaStream = null;
  }

  function attachRemoteAudio(stream: MediaStream, debugCallId = '') {
    detachRemoteAudio();
    emitDebugEvent(debugCallId, 'remote_audio.attach', {
      tracks: stream.getAudioTracks().length,
      stream_id: stream.id
    });
  
    // Log track events for debugging
    for (const track of stream.getAudioTracks()) {
      emitDebugEvent(debugCallId, 'remote_audio.track', {
        kind: track.kind,
        id: track.id,
        readyState: track.readyState,
        muted: track.muted,
        enabled: track.enabled
      });
      track.addEventListener('ended', () => {
        emitDebugEvent(debugCallId, 'remote_audio.track.ended', { id: track.id });
      });
      track.addEventListener('mute', () => {
        emitDebugEvent(debugCallId, 'remote_audio.track.mute', { id: track.id, muted: track.muted });
      });
      track.addEventListener('unmute', () => {
        emitDebugEvent(debugCallId, 'remote_audio.track.unmute', { id: track.id, muted: track.muted });
      });
    }
  
    // Let the browser media element own audible WebRTC playback. Android
    // Chrome is more reliable with a real media element as the sink; the
    // AudioContext graph below is only for diagnostics/meters.
    const element = new Audio();
    element.autoplay = true;
    element.playsInline = true;
    element.controls = false;
    element.muted = false;
    element.srcObject = stream;
    remoteAudioElement = element;
    element.addEventListener('playing', () => {
      emitDebugEvent(debugCallId, 'remote_audio.element.playing', {
        paused: element.paused,
        muted: element.muted,
        volume: element.volume,
        readyState: element.readyState
      });
    });
    element.addEventListener('volumechange', () => {
      emitDebugEvent(debugCallId, 'remote_audio.element.volumechange', {
        muted: element.muted,
        volume: element.volume
      });
    });
    void element.play().then(
      () => {
        emitDebugEvent(debugCallId, 'remote_audio.element.play.ok', {
          paused: element.paused,
          muted: element.muted,
          volume: element.volume,
          readyState: element.readyState
        });
      },
      (error: unknown) => {
        emitDebugEvent(debugCallId, 'remote_audio.element.play.failed', {
          name: (error as DOMException)?.name ?? 'unknown',
          message: (error as Error)?.message ?? ''
        });
      }
    );

    const AudioContextCtor =
      typeof AudioContext !== 'undefined'
        ? AudioContext
        : (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext })
            .webkitAudioContext;
    if (!AudioContextCtor) {
      emitDebugEvent(debugCallId, 'remote_audio.meter.failed', {
        name: 'NotSupportedError',
        message: 'AudioContext is not available'
      });
      return;
    }
  
    try {
      const reusedContext = Boolean(remoteAudioContext);
      const context = remoteAudioContext ?? new AudioContextCtor();
      if (context.state === 'suspended') {
        context.resume().catch(() => undefined);
      }
      remoteAudioContext = context;
  
      const source = context.createMediaStreamSource(stream);
      remoteAudioSource = source;
  
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      const meterSink = context.createGain();
      meterSink.gain.value = 0;
      remoteAudioAnalyser = analyser;
      remoteAudioMeterSink = meterSink;
  
      source.connect(analyser);
      analyser.connect(meterSink);
      meterSink.connect(context.destination);
  
      // Start remote audio metering (speakingRms)
      const samples = new Float32Array(analyser.fftSize);
      remoteAudioMeterTicks = 0;
      remoteAudioNonZeroLogged = false;
      const updateMeter = () => {
        if (remoteAudioAnalyser !== analyser) {
          return;
        }
        analyser.getFloatTimeDomainData(samples);
        let sumSquares = 0;
        for (let i = 0; i < samples.length; i++) {
          sumSquares += samples[i] * samples[i];
        }
        const rms = Math.sqrt(sumSquares / samples.length);
        speakingRms = Math.min(1, rms * 3.2);
        remoteAudioMeterTicks += 1;
        if (!remoteAudioNonZeroLogged && rms > 0.002) {
          remoteAudioNonZeroLogged = true;
          emitDebugEvent(debugCallId, 'remote_audio.rms.nonzero', {
            rms,
            speakingRms,
            contextState: context.state
          });
        } else if (callState === 'speaking' && remoteAudioMeterTicks % 30 === 0) {
          emitDebugEvent(debugCallId, 'remote_audio.rms.sample', {
            rms,
            speakingRms,
            contextState: context.state
          });
        }
        remoteAudioMeterFrame = requestAnimationFrame(updateMeter);
      };
      remoteAudioMeterFrame = requestAnimationFrame(updateMeter);
  
      emitDebugEvent(debugCallId, 'remote_audio.meter.ok', {
        method: 'AudioContext',
        sampleRate: context.sampleRate,
        state: context.state,
        reusedContext
      });
    } catch (error: unknown) {
      emitDebugEvent(debugCallId, 'remote_audio.meter.failed', {
        name: (error as DOMException)?.name ?? 'unknown',
        message: (error as Error)?.message ?? ''
      });
    }
  }
  
  function detachRemoteAudio() {
    // Stop remote audio metering
    if (remoteAudioMeterFrame) {
      cancelAnimationFrame(remoteAudioMeterFrame);
      remoteAudioMeterFrame = 0;
    }
    remoteAudioSource?.disconnect();
    remoteAudioAnalyser?.disconnect();
    remoteAudioMeterSink?.disconnect();
    remoteAudioSource = null;
    remoteAudioAnalyser = null;
    remoteAudioMeterSink = null;
    remoteAudioMeterTicks = 0;
    remoteAudioNonZeroLogged = false;
  
    if (remoteAudioElement) {
      remoteAudioElement.pause();
      remoteAudioElement.srcObject = null;
      remoteAudioElement = null;
    }
  }
  
  
  function labelForState(state: ActiveCallState): string {
    if (state === 'connecting') {
      return 'Connecting';
    }
    if (state === 'understanding') {
      return 'Understanding';
    }
    if (state === 'thinking') {
      return 'Composing';
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
    <button class="icon-button" type="button" aria-label="Return to Thread" onclick={returnToThread}>
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
      <button type="button" onclick={() => handleBlockingAction(blockingPanel!.action)}>
        {blockingPanel.action}
      </button>
    </div>
  {:else if callState === 'ended'}
    <div class="ended-panel" role="status">
      <h2>Call ended</h2>
      <p>Your transcript so far was saved to the thread.</p>
      <button type="button" onclick={returnToThread}>Return to Thread</button>
    </div>
  {:else}
    <div class="toolbar-wrap">
      <CallToolbar
        muted={serverMuted}
        stateLabel={callControlStateLabel}
        ready={callState === 'listening' && canUseToolbar}
        disabled={!canUseToolbar}
        interruptEnabled={callState === 'understanding' || callState === 'thinking' || callState === 'speaking'}
        endEnabled={!ending}
        inputPickerSupported={false}
        outputPickerSupported={false}
        onMuteToggle={toggleMute}
        onInterrupt={interrupt}
        onEnd={hangup}
      />
    </div>

    <div class="call-canvas">
      <VoiceVisualizer state={visualState} {listeningRms} {speakingRms} />
      <CallTranscript turns={transcript} {activeAiText} interrupted={callState === 'interrupted'} />
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
    top: calc(8px + env(safe-area-inset-top));
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
      padding-bottom: calc(72px + env(safe-area-inset-bottom));
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
      top: calc(6px + env(safe-area-inset-top));
    }
  }
</style>
