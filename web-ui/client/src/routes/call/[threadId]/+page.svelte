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
    promoteCallPeer,
    recoverCallEvents,
    sendCallOffer as offerCall,
    setCallMuted,
    startCall,
    submitCallTurn
  } from '$lib/api/calls';
  import { loadThread } from '$lib/api/chat';
  import { getVoice, getVoicePreparationStatus } from '$lib/api/voices';
  import type { CallErrorCode, CallEvent, CallOfferResponse, CallStateName, CallTranscriptTurn, CallTurnAssistantMessage, CallTurnStreamEvent, ThreadDetail, VoicePreparationStatus } from '$lib/api/types';
  import {
    keepCallMicrophoneTracksLive,
    normalizeRemoteCallInterruptDrainMs,
    requestCallMicrophone,
    setCallMicrophoneTracksEnabled,
    syncRemoteCallAudioAudibility,
    unlockCallAudioContext
  } from '$lib/call/audio';
  import {
    selectReconnectAudioBackfill as selectReconnectAudioBackfillFromChunks,
    type LocalMicPcmChunk,
    type LocalMicPcmSelection
  } from '$lib/call/reconnectBackfill';
  import { dispatchCallTurnStreamEvent, existingTurnDisposition } from '$lib/call/turnStream';
  import CallToolbar from '$lib/components/call/CallToolbar.svelte';
  import CallTranscript from '$lib/components/call/CallTranscript.svelte';
  import VoiceVisualizer from '$lib/components/call/VoiceVisualizer.svelte';
  import StatusChip from '$lib/components/StatusChip.svelte';

  type ActiveCallState = Extract<CallStateName, 'connecting' | 'listening' | 'understanding' | 'thinking' | 'rehearsing' | 'speaking' | 'interrupted' | 'ended' | 'failed'>;
  type VisualState = Extract<CallStateName, 'listening' | 'understanding' | 'thinking' | 'rehearsing' | 'speaking'>;
  type BlockingAction = 'Retry Microphone' | 'Retry Preparation' | 'Open Voice Lab' | 'Open Character' | 'Choose Voice' | 'Open Settings' | 'Return to Thread';

  interface BlockingPanel {
    heading?: string;
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

  interface ActiveTurnResponseResult {
    delivered: boolean;
    audioDurationMs: number;
  }

  interface ActiveTurnResponseGuard {
    turnId: string;
    startedAt: number;
    delivered: boolean;
    audioDurationMs: number;
    settled: boolean;
    promise: Promise<ActiveTurnResponseResult>;
    resolve: (result: ActiveTurnResponseResult) => void;
  }

  interface InterruptDrainGeneration {
    id: number;
    lifecycle: number;
    sessionId: string;
    turnId: string | null;
    startedAt: number;
    drainMs: number;
    completed: boolean;
    acknowledgements: Set<'data-channel' | 'http'>;
  }

  interface ReconnectAudioBackfillProgress {
    batchIndex: number;
    lastEndMs: number;
    flushPromise: Promise<void> | null;
    finalPromise: Promise<void> | null;
    recoveryDrainTimer: number;
    finalAcknowledged: boolean;
    promotedState: boolean;
    awaitingFinalResponse: boolean;
  }

  interface ReconnectAudioBackfillGeneration {
    readonly generationId: number;
    readonly backfillId: string;
    readonly captureEpoch: number;
    readonly startMs: number;
    readonly reason: MediaReconnectReason;
    readonly abortController: AbortController;
    readonly progress: ReconnectAudioBackfillProgress;
  }

  interface BrowserMediaConnectionOwner {
    readonly generationId: number;
    readonly connection: RTCPeerConnection;
    eventsChannel: RTCDataChannel;
    candidateRemoteStream: MediaStream | null;
    readonly candidateRemoteStreamReady: Promise<MediaStream>;
    readonly resolveCandidateRemoteStream: (stream: MediaStream) => void;
    remoteAudioPromoted: boolean;
  }

  interface MuteRequestOwner {
    readonly requestId: number;
    readonly callId: string;
    readonly sessionId: string;
    readonly previousMuted: boolean;
    readonly targetMuted: boolean;
    readonly abortController: AbortController;
    readonly acknowledgement: {
      muted: boolean | null;
      audioInputEpoch: number | null;
      muteRevision: number | null;
      settled: boolean;
      promise: Promise<AuthoritativeMuteResult>;
      resolve: (result: AuthoritativeMuteResult) => void;
    };
  }

  interface AuthoritativeMuteResult {
    muted: boolean;
    audio_input_epoch: number;
    mute_revision: number;
  }

  class AmbiguousPeerPromotionError extends Error {
    readonly lastError: unknown;

    constructor(lastError: unknown) {
      super('Replacement peer commit acknowledgement remained ambiguous');
      this.name = 'AmbiguousPeerPromotionError';
      this.lastError = lastError;
    }
  }

  class PeerPromotionDecisionDeadlineError extends AmbiguousPeerPromotionError {
    constructor(lastError: unknown) {
      super(lastError);
      this.name = 'PeerPromotionDecisionDeadlineError';
      this.message = 'Replacement peer switch exceeded its backend decision deadline';
    }
  }

  class FailedPeerPromotionError extends Error {
    constructor() {
      super('Replacement peer switch failed');
      this.name = 'FailedPeerPromotionError';
    }
  }

  class RejectedPeerPromotionError extends Error {
    constructor() {
      super('Replacement peer commit was rejected');
      this.name = 'RejectedPeerPromotionError';
    }
  }

  type MediaReconnectReason = 'failed' | 'disconnected';

  let thread = $state<ThreadDetail | null>(null);
  let loadState = $state<'loading' | 'ready' | 'error'>('loading');
  let callState = $state<ActiveCallState>('connecting');
  let callId = $state('');
  let sessionId = $state('');
  let serverMuted = $state(false);
  let muteRequestPending = $state(false);
  let muteSynchronizationFailed = $state(false);
  let muteRequestGeneration = 0;
  let activeMuteRequest: MuteRequestOwner | null = null;
  let localMicAudioEpoch = 0;
  let localMuteRevision = 0;
  let listeningRms = $state<number | null>(null);
  let speakingRms = $state<number | null>(null);
  let transcript = $state<CallTranscriptTurn[]>([]);
  let activeAiText = $state('');
  let blockingPanel = $state<BlockingPanel | null>(null);
  let blockingPanelHeading = $state<HTMLElement | null>(null);
  let selectedCallEngine = $state('');
  let selectedCallVoiceName = $state('selected voice');
  let callPreparation = $state<VoicePreparationStatus>({
    model: { state: 'idle', engine_id: null },
    prompt: { state: 'none' }
  });
  let callPreparationPollToken = 0;
  let ending = $state(false);
  let timers: number[] = [];
  const handledUserFinalTurnIds = new Set<string>();
  let activeTurnAbort: AbortController | null = null;
  let activeTurnReader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  let activeTurnResponseGuard: ActiveTurnResponseGuard | null = null;
  let localMediaStream: MediaStream | null = null;
  let peerConnection: RTCPeerConnection | null = null;
  let eventsChannel: RTCDataChannel | null = null;
  let browserMediaConnectionGeneration = 0;
  let activeBrowserMediaConnection: BrowserMediaConnectionOwner | null = null;
  let mediaReconnectTimer = 0;
  let mediaReconnectStableTimer = 0;
  let mediaReconnecting = false;
  let mediaReconnectAttempts = 0;
  let localAudioContext: AudioContext | null = null;
  let localMicSource: MediaStreamAudioSourceNode | null = null;
  let localMicAnalyser: AnalyserNode | null = null;
  let localMicRecorderProcessor: ScriptProcessorNode | null = null;
  let localMicRecorderGain: GainNode | null = null;
  let localMicPcmBuffer: LocalMicPcmChunk[] = [];
  let reconnectAudioBackfillGeneration = 0;
  let activeReconnectAudioBackfill: ReconnectAudioBackfillGeneration | null = null;
  let terminalReconnectCleanupPromise: Promise<void> | null = null;
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
  let remoteAudioInterruptDrainTimer = 0;
  let remoteAudioInterruptDrainActive = false;
  let interruptedStateTimer = 0;
  let interruptDrainGeneration = 0;
  let callMediaLifecycle = 0;
  let activeInterruptDrain: InterruptDrainGeneration | null = null;
  let latestAiTurnId: string | null = null;
  const handledInterruptedTurnKeys = new Set<string>();

  const MEDIA_RECONNECT_DISCONNECTED_GRACE_MS = 2500;
  const MEDIA_RECONNECT_RETRY_DELAY_MS = 1000;
  const MEDIA_RECONNECT_MAX_ATTEMPTS = 2;
  const MEDIA_RECONNECT_STABLE_RESET_MS = 10000;
  const MEDIA_RECONNECT_MIC_DIAG_MS = 7000;
  const MEDIA_RECONNECT_MIC_DIAG_INTERVAL_MS = 500;
  const PEER_PROMOTION_RECONCILIATION_TIMEOUT_MS = 2500;
  const PEER_PROMOTION_ATTEMPT_TIMEOUT_MS = 750;
  const PEER_PROMOTION_RETRY_DELAY_MS = 100;
  const PEER_PROMOTION_SWITCH_DECISION_FALLBACK_MS = 11000;
  const PEER_PROMOTION_SWITCH_DECISION_MAX_MS = 30000;
  const MIC_BACKFILL_SAMPLE_RATE = 16000;
  const MIC_BACKFILL_ROLLING_MS = 180000;
  const MIC_BACKFILL_RECONNECT_PREROLL_MS = 30000;
  const MIC_BACKFILL_MAX_MS = 30000;
  const MIC_BACKFILL_BATCH_MAX_MS = 10000;
  const MISSED_CALL_EVENTS_RECOVERY_RETRY_MS = 2000;
  const MUTE_ACKNOWLEDGEMENT_TIMEOUT_MS = 1500;
  const MUTE_COMPENSATION_TIMEOUT_MS = 1000;
  const TERMINAL_RECONNECT_BACKFILL_WAIT_MS = 2000;
  const TERMINAL_RECONNECT_ACTIVE_RESPONSE_WAIT_MS = 120000;
  const TERMINAL_RECONNECT_RESPONSE_VISIBLE_GRACE_MS = 1500;
  const TERMINAL_RECONNECT_RESPONSE_PLAYBACK_MAX_MS = 60000;

  const threadId = $derived(page.params.threadId ?? '');
  const characterName = $derived(thread?.character_name ?? 'RayMe');
  const title = $derived(thread?.title?.trim() || characterName);
  const visualState = $derived<VisualState>(
    callState === 'understanding' || callState === 'thinking' || callState === 'rehearsing' || callState === 'speaking'
      ? callState
      : 'listening'
  );
  const statusTone = $derived(callState === 'failed' ? 'danger' : callState === 'connecting' ? 'neutral' : 'healthy');
  const statusLabel = $derived(labelForState(callState));
  const callControlStateLabel = $derived(callState === 'listening' ? 'Ready to speak' : statusLabel);
  const canUseToolbar = $derived(callState !== 'connecting' && callState !== 'ended' && callState !== 'failed');
  const qwenPreparationActive = $derived(selectedCallEngine === 'qwen3_1_7b' && callState === 'connecting');

  onMount(() => {
    void initializeCall();
  });

  onDestroy(() => {
    callPreparationPollToken += 1;
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
    resetBrowserMediaReconnectIncident();
    callState = 'connecting';
    clearEventTimers();
    handledUserFinalTurnIds.clear();
    localMicAudioEpoch = 0;
    localMuteRevision = 0;
    muteRequestPending = false;
    muteSynchronizationFailed = false;
    activeMuteRequest?.abortController.abort();
    activeMuteRequest = null;
    retireReconnectAudioBackfill(activeReconnectAudioBackfill);

    try {
      localMediaStream = await requestCallMicrophone();
      startLocalMicMeter(localMediaStream);
      // Browser audio unlock is best-effort: resume() may remain pending until a
      // user gesture, and must never block signaling or visible call readiness.
      void unlockAudioForCall();
      const started = await startCall({ thread_id: threadId });
      callId = started.call_id;
      sessionId = started.session_id || started.call_id;
      selectedCallEngine = started.engine_id ?? '';
      if (started.voice_id) {
        void getVoice(started.voice_id).then(
          (voice) => {
            selectedCallVoiceName = voice.name || 'selected voice';
          },
          () => undefined
        );
      }
      const preparationToken =
        started.engine_id === 'qwen3_1_7b' ? beginCallPreparationMonitoring() : 0;
      const offerResponse = await connectBrowserMedia(started);
      if (preparationToken) {
        callPreparationPollToken += 1;
        const preparation = offerResponse?.preparation;
        if (!preparation || preparation.model.state !== 'resident' || preparation.prompt.state !== 'ready') {
          throw new CallApiError(
            'RayMe could not prepare this voice for the call.',
            502,
            preparation?.prompt.error_code || 'call_tts_prepare_failed'
          );
        }
        callPreparation = preparation;
      }
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
    options: {
      beforeRemoteDescription?: () => Promise<void>;
      preserveExistingUntilConnected?: boolean;
    } = {}
  ): Promise<CallOfferResponse | null> {
    if (!localMediaStream) {
      return null;
    }

    if (typeof RTCPeerConnection === 'undefined') {
      throw new CallApiError('This browser cannot start a real WebRTC call.', 400, 'webrtc_offer_failed');
    }

    const previousConnection = peerConnection;
    const previousConnectionOwner = activeBrowserMediaConnection;
    const previousEventsChannel = eventsChannel;
    const preserveExisting =
      options.preserveExistingUntilConnected === true && previousConnection !== null;

    const connection = new RTCPeerConnection();
    const candidateEventsChannel = connection.createDataChannel('rayme-events');
    let resolveCandidateRemoteStream = (_stream: MediaStream) => undefined;
    const candidateRemoteStreamReady = new Promise<MediaStream>((resolve) => {
      resolveCandidateRemoteStream = resolve;
    });
    const connectionOwner: BrowserMediaConnectionOwner = {
      generationId: ++browserMediaConnectionGeneration,
      connection,
      eventsChannel: candidateEventsChannel,
      candidateRemoteStream: null,
      candidateRemoteStreamReady,
      resolveCandidateRemoteStream,
      remoteAudioPromoted: false
    };
    let candidateDiscarded = false;
    const ownsCandidateConnection = () =>
      !candidateDiscarded && (
        ownsBrowserMediaConnection(connectionOwner) ||
        (
          preserveExisting &&
          connectionOwner.generationId === browserMediaConnectionGeneration &&
          activeBrowserMediaConnection === previousConnectionOwner
        )
      );
    if (!preserveExisting) {
      peerConnection = connection;
      activeBrowserMediaConnection = connectionOwner;
      eventsChannel = candidateEventsChannel;
    }
    attachPeerConnectionDebug(connectionOwner, started.call_id);
    attachCallEventChannel(
      candidateEventsChannel,
      connectionOwner,
      started.call_id,
      'browser-created'
    );
    if (!preserveExisting) {
      previousConnection?.close();
    }
    connection.ondatachannel = (event) => {
      emitDebugEvent(started.call_id, 'pc.ondatachannel', {
        label: event.channel.label,
        readyState: event.channel.readyState,
        connectionGeneration: connectionOwner.generationId,
        isCurrentPeer: ownsBrowserMediaConnection(connectionOwner)
      });
      if (!ownsCandidateConnection()) {
        event.channel.close();
        return;
      }
      if (event.channel.label === 'rayme-events') {
        connectionOwner.eventsChannel = event.channel;
        if (!preserveExisting || ownsBrowserMediaConnection(connectionOwner)) {
          eventsChannel = event.channel;
        }
        attachCallEventChannel(
          event.channel,
          connectionOwner,
          started.call_id,
          'remote-attached'
        );
      }
    };
    connection.ontrack = (event) => {
      emitDebugEvent(started.call_id, 'pc.ontrack', {
        kind: event.track.kind,
        id: event.track.id,
        readyState: event.track.readyState,
        streams: event.streams.length,
        connectionGeneration: connectionOwner.generationId,
        isCurrentPeer: ownsBrowserMediaConnection(connectionOwner)
      });
      if (!ownsCandidateConnection()) {
        return;
      }
      const stream = event.streams[0] ?? new MediaStream([event.track]);
      if (preserveExisting && !connectionOwner.remoteAudioPromoted) {
        if (!connectionOwner.candidateRemoteStream) {
          connectionOwner.candidateRemoteStream = stream;
          connectionOwner.resolveCandidateRemoteStream(stream);
        }
        emitDebugEvent(started.call_id, 'remote_audio.candidate.staged', {
          stream_id: stream.id,
          connectionGeneration: connectionOwner.generationId
        });
        return;
      }
      connectionOwner.remoteAudioPromoted = true;
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

    let pendingPeerGeneration: number | null = null;
    let backendPeerCommitted = false;
    let promotionSessionId = started.session_id || started.call_id;
    try {
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
      const response = await offerCall(started.call_id, localDescription, started.session_id);
      sessionId = response.session_id || started.session_id || started.call_id;
      promotionSessionId = sessionId;
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
      if (preserveExisting) {
        if (
          !Number.isInteger(response.peer_generation) ||
          (response.peer_generation ?? 0) < 1
        ) {
          throw new Error('Replacement offer did not include a valid peer generation');
        }
        pendingPeerGeneration = response.peer_generation as number;
        await waitForBrowserMediaConnected(connection, started.call_id);
        const candidateRemoteStream =
          connectionOwner.candidateRemoteStream ??
          await waitForBrowserMediaCandidateStream(connectionOwner, started.call_id);
        await commitBrowserPeerPromotion(
          started.call_id,
          promotionSessionId,
          pendingPeerGeneration,
          response.peer_commit_timeout_ms
        );
        backendPeerCommitted = true;
        peerConnection = connection;
        activeBrowserMediaConnection = connectionOwner;
        eventsChannel = connectionOwner.eventsChannel;
        promoteBrowserMediaCandidate(
          connectionOwner,
          candidateRemoteStream,
          started.call_id
        );
      }
      if (preserveExisting && previousConnection && previousConnection !== connection) {
        previousConnection.close();
      }
      return response;
    } catch (error) {
      if (preserveExisting) {
        if (
          error instanceof AmbiguousPeerPromotionError ||
          error instanceof FailedPeerPromotionError
        ) {
          emitDebugEvent(started.call_id, 'remote_audio.candidate.commit_ambiguous', {
            generation: pendingPeerGeneration,
            name:
              error instanceof AmbiguousPeerPromotionError
                ? (error.lastError as DOMException)?.name ?? 'unknown'
                : error.name,
            message:
              error instanceof AmbiguousPeerPromotionError
                ? (error.lastError as Error)?.message ?? ''
                : error.message
          });
          throw error;
        }
        if (pendingPeerGeneration !== null && !backendPeerCommitted) {
          const rejection = await rejectBrowserPeerPromotion(
            started.call_id,
            promotionSessionId,
            pendingPeerGeneration
          );
          if (rejection !== 'rollback_safe') {
            throw new AmbiguousPeerPromotionError(
              new Error(`Replacement peer rejection was ${rejection}`)
            );
          }
        }
        candidateDiscarded = true;
        discardBrowserMediaCandidate(connectionOwner, started.call_id, error);
        if (peerConnection === connection) {
          peerConnection = previousConnection;
        }
        if (activeBrowserMediaConnection === connectionOwner) {
          activeBrowserMediaConnection = previousConnectionOwner;
        }
        if (eventsChannel === candidateEventsChannel) {
          eventsChannel = previousEventsChannel;
        }
        connection.close();
      }
      throw error;
    }
  }

  async function commitBrowserPeerPromotion(
    callId: string,
    promotionSessionId: string,
    generation: number,
    backendDecisionTimeoutMs: number | null | undefined
  ) {
    const deadline = performance.now() + PEER_PROMOTION_RECONCILIATION_TIMEOUT_MS;
    let attempt = 0;
    let lastError: unknown = new Error('Replacement peer commit was not attempted');
    let authoritativeInProgress = false;

    while (performance.now() < deadline) {
      attempt += 1;
      const controller = new AbortController();
      const attemptTimeout = Math.max(
        1,
        Math.min(PEER_PROMOTION_ATTEMPT_TIMEOUT_MS, deadline - performance.now())
      );
      const timeout = window.setTimeout(() => controller.abort(), attemptTimeout);
      try {
        const promotion = await promoteCallPeer(
          callId,
          promotionSessionId,
          generation,
          'commit',
          { signal: controller.signal }
        );
        if (
          promotion.session_id !== promotionSessionId ||
          promotion.generation !== generation
        ) {
          throw new Error('Replacement peer commit returned an invalid acknowledgement');
        }
        if (promotion.status === 'in_progress') {
          authoritativeInProgress = true;
          lastError = new Error('Replacement peer commit is still in progress');
          emitDebugEvent(callId, 'remote_audio.candidate.commit_in_progress', {
            generation,
            attempt,
            decisionTimeoutMs: normalizePeerPromotionDecisionTimeoutMs(
              backendDecisionTimeoutMs
            )
          });
          break;
        }
        if (promotion.status === 'failed') {
          throw new FailedPeerPromotionError();
        }
        if (promotion.status === 'rejected') {
          throw new RejectedPeerPromotionError();
        }
        if (attempt > 1) {
          emitDebugEvent(callId, 'remote_audio.candidate.commit_reconciled', {
            generation,
            attempt,
            result: 'committed'
          });
        }
        return;
      } catch (error) {
        if (
          error instanceof CallApiError &&
          error.code === 'webrtc_peer_already_committed'
        ) {
          emitDebugEvent(callId, 'remote_audio.candidate.commit_reconciled', {
            generation,
            attempt,
            result: 'already_committed'
          });
          return;
        }
        if (error instanceof FailedPeerPromotionError) {
          throw error;
        }
        if (peerPromotionProvesNotCommitted(error)) {
          throw error;
        }
        lastError = error;
        const remainingMs = deadline - performance.now();
        if (remainingMs <= 0) {
          break;
        }
        emitDebugEvent(callId, 'remote_audio.candidate.commit_retry', {
          generation,
          attempt,
          remainingMs: Math.round(remainingMs),
          name: (error as DOMException)?.name ?? 'unknown',
          code: error instanceof CallApiError ? error.code : undefined
        });
        await delay(Math.min(PEER_PROMOTION_RETRY_DELAY_MS, remainingMs));
      } finally {
        window.clearTimeout(timeout);
      }
    }

    if (authoritativeInProgress) {
      return reconcileInProgressBrowserPeerPromotion(
        callId,
        promotionSessionId,
        generation,
        attempt,
        backendDecisionTimeoutMs,
        lastError
      );
    }

    throw new AmbiguousPeerPromotionError(lastError);
  }

  async function reconcileInProgressBrowserPeerPromotion(
    callId: string,
    promotionSessionId: string,
    generation: number,
    initialAttempt: number,
    backendDecisionTimeoutMs: number | null | undefined,
    initialError: unknown
  ) {
    const decisionTimeoutMs = normalizePeerPromotionDecisionTimeoutMs(
      backendDecisionTimeoutMs
    );
    const deadline = performance.now() + decisionTimeoutMs;
    let attempt = initialAttempt;
    let lastError = initialError;

    while (performance.now() < deadline) {
      const remainingBeforeDelay = deadline - performance.now();
      await delay(Math.min(PEER_PROMOTION_RETRY_DELAY_MS, remainingBeforeDelay));
      if (performance.now() >= deadline) {
        break;
      }
      attempt += 1;
      const controller = new AbortController();
      const attemptTimeout = Math.max(
        1,
        Math.min(PEER_PROMOTION_ATTEMPT_TIMEOUT_MS, deadline - performance.now())
      );
      const timeout = window.setTimeout(() => controller.abort(), attemptTimeout);
      try {
        const promotion = await promoteCallPeer(
          callId,
          promotionSessionId,
          generation,
          'commit',
          { signal: controller.signal }
        );
        if (
          promotion.session_id !== promotionSessionId ||
          promotion.generation !== generation
        ) {
          throw new Error('Replacement peer commit returned an invalid acknowledgement');
        }
        if (promotion.status === 'committed') {
          emitDebugEvent(callId, 'remote_audio.candidate.commit_reconciled', {
            generation,
            attempt,
            result: 'committed_after_in_progress'
          });
          return;
        }
        if (promotion.status === 'failed') {
          throw new FailedPeerPromotionError();
        }
        if (promotion.status === 'rejected') {
          throw new RejectedPeerPromotionError();
        }
        lastError = new Error('Replacement peer commit is still in progress');
        emitDebugEvent(callId, 'remote_audio.candidate.commit_status_poll', {
          generation,
          attempt,
          remainingMs: Math.round(deadline - performance.now())
        });
      } catch (error) {
        if (
          error instanceof CallApiError &&
          error.code === 'webrtc_peer_already_committed'
        ) {
          emitDebugEvent(callId, 'remote_audio.candidate.commit_reconciled', {
            generation,
            attempt,
            result: 'already_committed_after_in_progress'
          });
          return;
        }
        if (error instanceof FailedPeerPromotionError) {
          throw error;
        }
        if (peerPromotionProvesNotCommitted(error)) {
          throw error;
        }
        lastError = error;
        emitDebugEvent(callId, 'remote_audio.candidate.commit_status_retry', {
          generation,
          attempt,
          remainingMs: Math.round(deadline - performance.now()),
          name: (error as DOMException)?.name ?? 'unknown',
          code: error instanceof CallApiError ? error.code : undefined
        });
      } finally {
        window.clearTimeout(timeout);
      }
    }

    return resolveExpiredBrowserPeerPromotion(
      callId,
      promotionSessionId,
      generation,
      attempt,
      lastError
    );
  }

  function normalizePeerPromotionDecisionTimeoutMs(value: number | null | undefined) {
    if (!Number.isInteger(value) || (value ?? 0) <= 0) {
      return PEER_PROMOTION_SWITCH_DECISION_FALLBACK_MS;
    }
    return Math.min(
      PEER_PROMOTION_SWITCH_DECISION_MAX_MS,
      Math.max(PEER_PROMOTION_SWITCH_DECISION_FALLBACK_MS, value as number)
    );
  }

  async function resolveExpiredBrowserPeerPromotion(
    callId: string,
    promotionSessionId: string,
    generation: number,
    attempt: number,
    lastError: unknown
  ) {
    emitDebugEvent(callId, 'remote_audio.candidate.commit_decision_deadline', {
      generation,
      attempt
    });

    const controller = new AbortController();
    const timeout = window.setTimeout(
      () => controller.abort(),
      PEER_PROMOTION_ATTEMPT_TIMEOUT_MS
    );
    try {
      const promotion = await promoteCallPeer(
        callId,
        promotionSessionId,
        generation,
        'commit',
        { signal: controller.signal }
      );
      if (
        promotion.session_id !== promotionSessionId ||
        promotion.generation !== generation
      ) {
        throw new Error('Replacement peer commit returned an invalid acknowledgement');
      }
      if (promotion.status === 'committed') {
        emitDebugEvent(callId, 'remote_audio.candidate.commit_reconciled', {
          generation,
          attempt: attempt + 1,
          result: 'committed_at_decision_deadline'
        });
        return;
      }
      if (promotion.status === 'failed') {
        throw new FailedPeerPromotionError();
      }
      if (promotion.status === 'rejected') {
        throw new RejectedPeerPromotionError();
      }
      lastError = new Error('Replacement peer commit remained in progress at its deadline');
    } catch (error) {
      if (
        error instanceof CallApiError &&
        error.code === 'webrtc_peer_already_committed'
      ) {
        return;
      }
      if (error instanceof FailedPeerPromotionError || peerPromotionProvesNotCommitted(error)) {
        throw error;
      }
      lastError = error;
    } finally {
      window.clearTimeout(timeout);
    }

    const rejection = await rejectBrowserPeerPromotion(
      callId,
      promotionSessionId,
      generation
    );
    if (rejection === 'rollback_safe') {
      throw new RejectedPeerPromotionError();
    }
    if (rejection === 'committed') {
      emitDebugEvent(callId, 'remote_audio.candidate.commit_reconciled', {
        generation,
        attempt: attempt + 2,
        result: 'committed_during_deadline_resolution'
      });
      return;
    }
    if (rejection === 'failed') {
      throw new FailedPeerPromotionError();
    }
    throw new PeerPromotionDecisionDeadlineError(lastError);
  }

  function peerPromotionProvesNotCommitted(error: unknown) {
    if (error instanceof RejectedPeerPromotionError) {
      return true;
    }
    if (!(error instanceof CallApiError)) {
      return false;
    }
    return (
      error.code === 'webrtc_peer_generation_stale' ||
      error.code === 'webrtc_peer_not_connected' ||
      error.code === 'call_session_not_found' ||
      error.code === 'call_session_terminal'
    );
  }

  async function rejectBrowserPeerPromotion(
    callId: string,
    promotionSessionId: string,
    generation: number
  ): Promise<'rollback_safe' | 'committed' | 'failed' | 'in_progress' | 'ambiguous'> {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 1000);
    try {
      const promotion = await promoteCallPeer(
        callId,
        promotionSessionId,
        generation,
        'reject',
        { signal: controller.signal }
      );
      if (
        promotion.session_id !== promotionSessionId ||
        promotion.generation !== generation
      ) {
        return 'ambiguous';
      }
      if (promotion.status === 'rejected') {
        return 'rollback_safe';
      }
      if (promotion.status === 'committed') {
        return 'committed';
      }
      return promotion.status;
    } catch (error) {
      emitDebugEvent(callId, 'remote_audio.candidate.reject_failed', {
        generation,
        name: (error as DOMException)?.name ?? 'unknown',
        message: (error as Error)?.message ?? ''
      });
      if (
        error instanceof CallApiError &&
        error.code === 'webrtc_peer_already_committed'
      ) {
        return 'committed';
      }
      return peerPromotionProvesNotCommitted(error) ? 'rollback_safe' : 'ambiguous';
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function beginCallPreparationMonitoring(): number {
    const token = ++callPreparationPollToken;
    callPreparation = {
      model: { state: 'loading', engine_id: 'qwen3_1_7b' },
      prompt: { state: 'prewarming' }
    };
    void monitorCallPreparation(token);
    return token;
  }

  async function monitorCallPreparation(token: number) {
    for (let attempt = 0; attempt < 480 && token === callPreparationPollToken; attempt += 1) {
      try {
        const preparation = await getVoicePreparationStatus();
        if (token !== callPreparationPollToken) return;
        callPreparation = preparation;
        if (preparation.prompt.state === 'ready' || preparation.prompt.state === 'failed') return;
      } catch {
        // The offer response is authoritative; transient polling failure keeps the call visibly preparing.
      }
      await delay(250);
    }
  }

  function ownsBrowserMediaConnection(
    owner: BrowserMediaConnectionOwner | null
  ): owner is BrowserMediaConnectionOwner {
    return Boolean(
      owner &&
      activeBrowserMediaConnection === owner &&
      peerConnection === owner.connection
    );
  }

  function attachPeerConnectionDebug(
    owner: BrowserMediaConnectionOwner,
    debugCallId: string
  ) {
    const { connection } = owner;
    connection.addEventListener('iceconnectionstatechange', () => {
      const iceConnectionState = connection.iceConnectionState;
      emitDebugEvent(debugCallId, 'pc.iceconnectionstatechange', {
        iceConnectionState,
        connectionGeneration: owner.generationId,
        isCurrentPeer: ownsBrowserMediaConnection(owner)
      });
      if (!ownsBrowserMediaConnection(owner)) {
        emitMediaReconnectGuardSkip(owner, debugCallId, 'disconnected', 'recover', ['stale_peer']);
        return;
      }
      if (iceConnectionState === 'failed' || iceConnectionState === 'disconnected') {
        scheduleBrowserMediaReconnect(
          owner,
          debugCallId,
          iceConnectionState === 'failed' ? 'failed' : 'disconnected'
        );
      }
      if ((iceConnectionState === 'connected' || iceConnectionState === 'completed') && isBrowserMediaConnected(connection)) {
        if (mediaReconnecting) {
          emitMediaReconnectGuardSkip(
            owner,
            debugCallId,
            'disconnected',
            'recover',
            ['replacement_pending']
          );
          return;
        }
        handleBrowserMediaRecovered(owner, debugCallId, 'disconnected', 'iceconnectionstatechange');
      }
    });
    connection.addEventListener('connectionstatechange', () => {
      emitDebugEvent(debugCallId, 'pc.connectionstatechange', {
        connectionState: connection.connectionState,
        connectionGeneration: owner.generationId,
        isCurrentPeer: ownsBrowserMediaConnection(owner)
      });
      if (!ownsBrowserMediaConnection(owner)) {
        emitMediaReconnectGuardSkip(owner, debugCallId, 'failed', 'recover', ['stale_peer']);
        return;
      }
      if (connection.connectionState === 'failed' || connection.connectionState === 'disconnected') {
        emitDebugEvent(debugCallId, 'pc.connection.failed', {
          connectionState: connection.connectionState,
          iceConnectionState: connection.iceConnectionState,
          remoteAudioContextState: remoteAudioContext?.state ?? 'none',
          remoteAudioElementPlaying: remoteAudioElement ? !remoteAudioElement.paused : false,
          speakingRms: speakingRms
        });
        scheduleBrowserMediaReconnect(
          owner,
          debugCallId,
          connection.connectionState === 'failed' ? 'failed' : 'disconnected'
        );
      }
      if (connection.connectionState === 'connected' && isBrowserMediaConnected(connection)) {
        if (mediaReconnecting) {
          emitMediaReconnectGuardSkip(
            owner,
            debugCallId,
            'failed',
            'recover',
            ['replacement_pending']
          );
          return;
        }
        handleBrowserMediaRecovered(owner, debugCallId, 'failed', 'connectionstatechange');
        try {
          if (eventsChannel && (eventsChannel.readyState === 'closed' || eventsChannel.readyState === 'closing')) {
            emitDebugEvent(debugCallId, 'datachannel.recreate', {
              previousReadyState: eventsChannel.readyState
            });
            const recreatedEventsChannel = connection.createDataChannel('rayme-events');
            owner.eventsChannel = recreatedEventsChannel;
            eventsChannel = recreatedEventsChannel;
            attachCallEventChannel(
              recreatedEventsChannel,
              owner,
              debugCallId,
              'recreated'
            );
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
    owner: BrowserMediaConnectionOwner,
    debugCallId: string,
    reason: MediaReconnectReason
  ) {
    const { connection } = owner;
    const guardSkips: string[] = [];
    if (mediaReconnecting) {
      guardSkips.push('already_reconnecting');
    }
    if (!ownsBrowserMediaConnection(owner)) {
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
      emitMediaReconnectGuardSkip(owner, debugCallId, reason, 'schedule', guardSkips);
      return;
    }
    clearMediaReconnectStableTimer(owner);
    if (mediaReconnectTimer) {
      if (reason === 'failed') {
        clearMediaReconnectTimer(owner);
        emitDebugEvent(debugCallId, 'pc.media_reconnect.upgrade', {
          reason,
          attempts: mediaReconnectAttempts,
          connectionState: connection.connectionState,
          iceConnectionState: connection.iceConnectionState
        });
      } else {
        emitMediaReconnectGuardSkip(owner, debugCallId, reason, 'schedule', ['timer_pending']);
        return;
      }
    }
    if (mediaReconnectAttempts >= MEDIA_RECONNECT_MAX_ATTEMPTS) {
      emitDebugEvent(debugCallId, 'pc.media_reconnect.give_up', {
        reason,
        attempts: mediaReconnectAttempts
      });
      void failTerminalMediaReconnect(debugCallId, 'media_reconnect_give_up');
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
    const timerId = window.setTimeout(() => {
      if (!ownsBrowserMediaConnection(owner) || mediaReconnectTimer !== timerId) {
        return;
      }
      mediaReconnectTimer = 0;
      if (isBrowserMediaConnected(connection)) {
        handleBrowserMediaRecovered(owner, debugCallId, reason, 'schedule_timer');
        return;
      }
      void reconnectBrowserMedia(owner, debugCallId, reason);
    }, delayMs);
    mediaReconnectTimer = timerId;
  }

  async function reconnectBrowserMedia(
    failedOwner: BrowserMediaConnectionOwner,
    debugCallId: string,
    reason: MediaReconnectReason
  ) {
    const failedConnection = failedOwner.connection;
    const guardSkips: string[] = [];
    if (mediaReconnecting) {
      guardSkips.push('already_reconnecting');
    }
    if (!ownsBrowserMediaConnection(failedOwner)) {
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
    if (callState === 'ended' || callState === 'failed') {
      guardSkips.push(`terminal_state_${callState}`);
    }
    if (guardSkips.length > 0) {
      emitMediaReconnectGuardSkip(failedOwner, debugCallId, reason, 'start', guardSkips);
      return;
    }

    mediaReconnecting = true;
    mediaReconnectAttempts += 1;
    const reconnectAttempt = mediaReconnectAttempts;
    const backfillGeneration = startReconnectAudioBackfill(debugCallId, reason);
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
      await connectBrowserMedia(
        { call_id: callId, session_id: sessionId },
        {
          preserveExistingUntilConnected: true,
          beforeRemoteDescription: () =>
            flushReconnectAudioBackfill(
              debugCallId,
              reason,
              reconnectAttempt,
              {},
              backfillGeneration
            )
        }
      );
      handleBrowserMediaRecovered(
        activeBrowserMediaConnection,
        debugCallId,
        reason,
        'replacement_connected'
      );
      if (
        !ownsReconnectAudioBackfill(backfillGeneration) ||
        !backfillGeneration.progress.promotedState ||
        !backfillGeneration.progress.awaitingFinalResponse ||
        callState !== 'understanding'
      ) {
        applyCallState('listening');
      }
      emitDebugEvent(debugCallId, 'pc.media_reconnect.ok', {
        attempt: reconnectAttempt
      });
      emitLocalMicReconnectDiagnostic(debugCallId, {
        phase: 'ok',
        reason,
        attempt: reconnectAttempt
      });
    } catch (error) {
      if (error instanceof PeerPromotionDecisionDeadlineError) {
        emitDebugEvent(debugCallId, 'pc.media_reconnect.peer_decision_deadline', {
          attempt: reconnectAttempt,
          name: error.name,
          message: error.message
        });
        emitLocalMicReconnectDiagnostic(debugCallId, {
          phase: 'peer_decision_deadline',
          reason,
          attempt: reconnectAttempt
        });
        await failTerminalMediaReconnect(
          debugCallId,
          'media_reconnect_peer_decision_deadline'
        );
        return;
      }
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
        await failTerminalMediaReconnect(debugCallId, 'media_reconnect_failed');
      } else {
        scheduleBrowserMediaReconnectRetry(
          activeBrowserMediaConnection,
          debugCallId,
          reason,
          reconnectAttempt
        );
      }
    } finally {
      mediaReconnecting = false;
    }
  }

  function scheduleBrowserMediaReconnectRetry(
    owner: BrowserMediaConnectionOwner | null,
    debugCallId: string,
    reason: MediaReconnectReason,
    failedAttempt: number
  ) {
    if (!ownsBrowserMediaConnection(owner)) {
      emitDebugEvent(debugCallId, 'pc.media_reconnect.retry_skip', {
        reason,
        failedAttempt,
        causes: ['stale_peer']
      });
      return;
    }
    if (mediaReconnectTimer) {
      emitDebugEvent(debugCallId, 'pc.media_reconnect.retry_skip', {
        reason,
        failedAttempt,
        cause: 'timer_pending'
      });
      return;
    }
    emitDebugEvent(debugCallId, 'pc.media_reconnect.retry_scheduled', {
      reason,
      failedAttempt,
      delayMs: MEDIA_RECONNECT_RETRY_DELAY_MS,
      attempts: mediaReconnectAttempts
    });
    const timerId = window.setTimeout(() => {
      if (!ownsBrowserMediaConnection(owner) || mediaReconnectTimer !== timerId) {
        return;
      }
      mediaReconnectTimer = 0;
      const { connection } = owner;
      const guardSkips: string[] = [];
      if (!localMediaStream) {
        guardSkips.push('missing_local_media');
      }
      if (!callId) {
        guardSkips.push('missing_call_id');
      }
      if (!sessionId) {
        guardSkips.push('missing_session_id');
      }
      if (callState === 'ended' || callState === 'failed') {
        guardSkips.push(`terminal_state_${callState}`);
      }
      if (guardSkips.length > 0) {
        emitDebugEvent(debugCallId, 'pc.media_reconnect.retry_skip', {
          reason,
          failedAttempt,
          causes: guardSkips
        });
        return;
      }
      if (isBrowserMediaConnected(connection)) {
        handleBrowserMediaRecovered(owner, debugCallId, reason, 'retry_timer');
        return;
      }
      void reconnectBrowserMedia(owner, debugCallId, reason);
    }, MEDIA_RECONNECT_RETRY_DELAY_MS);
    mediaReconnectTimer = timerId;
  }

  async function failTerminalMediaReconnect(debugCallId: string, reason: string) {
    await cleanupTerminalFailedCall(debugCallId, reason);
    applyCallState('failed');
    blockingPanel = {
      body: 'The call ended because the connection dropped. Your transcript so far was saved.',
      action: 'Return to Thread',
      tone: 'danger'
    };
  }

  async function cleanupTerminalFailedCall(debugCallId: string, reason: string) {
    if (!callId || !sessionId) {
      return;
    }
    if (terminalReconnectCleanupPromise) {
      await terminalReconnectCleanupPromise;
      return;
    }
    const requestCallId = callId;
    const requestSessionId = sessionId;
    terminalReconnectCleanupPromise = (async () => {
      try {
        await waitForTerminalReconnectAudioBackfill(
          debugCallId,
          activeReconnectAudioBackfill?.reason ?? 'failed',
          Math.max(mediaReconnectAttempts, 1),
          'connection_failed'
        );
      } catch {
        // Recovery below still has a chance to drain already-queued events.
      }
      await waitForActiveTurnResponseBeforeTerminalCleanup(
        debugCallId,
        reason,
        'before_recover'
      );
      await recoverMissedCallEvents(debugCallId, reason);
      await waitForActiveTurnResponseBeforeTerminalCleanup(
        debugCallId,
        reason,
        'after_recover'
      );
      try {
        await endCall(requestCallId, requestSessionId, 'connection_failed');
      } catch {
        // The failed panel remains visible; cleanup failures are diagnostic-only here.
      }
    })().finally(() => {
      terminalReconnectCleanupPromise = null;
    });
    await terminalReconnectCleanupPromise;
  }

  async function waitForTerminalReconnectAudioBackfill(
    debugCallId: string,
    reason: MediaReconnectReason,
    attempt: number,
    phase: string
  ) {
    const generation = activeReconnectAudioBackfill;
    if (!generation) {
      return;
    }
    const flushResult = flushReconnectAudioBackfill(
      debugCallId,
      reason,
      attempt,
      { awaitFinal: true },
      generation
    ).then(
      () => ({ status: 'done' as const }),
      (error) => ({ status: 'failed' as const, error })
    );
    let timeoutId = 0;
    const timeoutResult = new Promise<{ status: 'timeout' }>((resolve) => {
      timeoutId = window.setTimeout(
        () => resolve({ status: 'timeout' }),
        TERMINAL_RECONNECT_BACKFILL_WAIT_MS
      );
    });

    const result = await Promise.race([flushResult, timeoutResult]);
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
    if (!ownsReconnectAudioBackfill(generation)) {
      return;
    }
    if (result.status === 'timeout') {
      emitDebugEvent(debugCallId, 'mic.reconnect_backfill.terminal_timeout', {
        reason,
        attempt,
        phase,
        timeoutMs: TERMINAL_RECONNECT_BACKFILL_WAIT_MS,
        backfillId: generation.backfillId
      });
      return;
    }
    if (result.status === 'failed') {
      emitDebugEvent(debugCallId, 'mic.reconnect_backfill.terminal_failed', {
        reason,
        attempt,
        phase,
        name: (result.error as Error)?.name ?? 'unknown',
        message: (result.error as Error)?.message ?? ''
      });
      throw result.error;
    }
  }

  function clearMediaReconnectTimer(owner: BrowserMediaConnectionOwner | null = null) {
    if (owner && !ownsBrowserMediaConnection(owner)) {
      return;
    }
    if (mediaReconnectTimer) {
      window.clearTimeout(mediaReconnectTimer);
      mediaReconnectTimer = 0;
    }
  }

  function clearMediaReconnectStableTimer(
    owner: BrowserMediaConnectionOwner | null = null
  ) {
    if (owner && !ownsBrowserMediaConnection(owner)) {
      return;
    }
    if (mediaReconnectStableTimer) {
      window.clearTimeout(mediaReconnectStableTimer);
      mediaReconnectStableTimer = 0;
    }
  }

  function resetBrowserMediaReconnectIncident() {
    clearMediaReconnectTimer();
    clearMediaReconnectStableTimer();
    mediaReconnectAttempts = 0;
  }

  function scheduleBrowserMediaReconnectStableBoundary(
    owner: BrowserMediaConnectionOwner,
    debugCallId: string,
    source: string
  ) {
    clearMediaReconnectStableTimer(owner);
    if (mediaReconnectAttempts === 0) {
      return;
    }
    const attemptBudget = mediaReconnectAttempts;
    const timerId = window.setTimeout(() => {
      if (
        !ownsBrowserMediaConnection(owner) ||
        mediaReconnectStableTimer !== timerId ||
        mediaReconnecting ||
        mediaReconnectTimer ||
        !isBrowserMediaConnected(owner.connection) ||
        callState === 'ended' ||
        callState === 'failed'
      ) {
        return;
      }
      mediaReconnectStableTimer = 0;
      mediaReconnectAttempts = 0;
      emitDebugEvent(debugCallId, 'pc.media_reconnect.stable', {
        source,
        stableMs: MEDIA_RECONNECT_STABLE_RESET_MS,
        attempts: attemptBudget,
        connectionGeneration: owner.generationId
      });
    }, MEDIA_RECONNECT_STABLE_RESET_MS);
    mediaReconnectStableTimer = timerId;
  }

  function handleBrowserMediaRecovered(
    owner: BrowserMediaConnectionOwner | null,
    debugCallId: string,
    reason: MediaReconnectReason,
    source: string
  ) {
    if (!ownsBrowserMediaConnection(owner)) {
      return;
    }
    clearMediaReconnectTimer(owner);
    scheduleBrowserMediaReconnectStableBoundary(owner, debugCallId, source);
    const generation = activeReconnectAudioBackfill;
    if (generation) {
      beginReconnectAudioBackfillRecoveryDrain(
        generation,
        debugCallId,
        reason,
        source
      );
    }
    emitLocalMicReconnectDiagnostic(debugCallId, {
      phase: 'recovered',
      reason,
      source,
      backfillGeneration: generation?.generationId ?? null,
      awaitingFinalResponse: generation?.progress.awaitingFinalResponse ?? false
    });
  }

  function isBrowserMediaConnected(connection: RTCPeerConnection) {
    return (
      connection.connectionState === 'connected' &&
      (connection.iceConnectionState === 'connected' || connection.iceConnectionState === 'completed')
    );
  }

  function emitMediaReconnectGuardSkip(
    owner: BrowserMediaConnectionOwner,
    debugCallId: string,
    reason: MediaReconnectReason,
    phase: 'schedule' | 'start' | 'recover',
    guardSkips: string[]
  ) {
    const { connection } = owner;
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
      connectionGeneration: owner.generationId,
      isCurrentPeer: ownsBrowserMediaConnection(owner),
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

  function startReconnectAudioBackfill(
    debugCallId: string,
    reason: MediaReconnectReason
  ): ReconnectAudioBackfillGeneration | null {
    if (muteRequestPending || muteSynchronizationFailed || serverMuted) {
      return null;
    }
    if (activeReconnectAudioBackfill) {
      return activeReconnectAudioBackfill;
    }
    const nowMs = performance.now();
    const startMs = Math.max(0, nowMs - MIC_BACKFILL_RECONNECT_PREROLL_MS);
    const generation = Object.freeze<ReconnectAudioBackfillGeneration>({
      generationId: ++reconnectAudioBackfillGeneration,
      backfillId: `${debugCallId || 'call'}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
      captureEpoch: localMicAudioEpoch,
      startMs,
      reason,
      abortController: new AbortController(),
      progress: {
        batchIndex: 0,
        lastEndMs: 0,
        flushPromise: null,
        finalPromise: null,
        recoveryDrainTimer: 0,
        finalAcknowledged: false,
        promotedState: false,
        awaitingFinalResponse: false
      }
    });
    activeReconnectAudioBackfill = generation;
    if (callState === 'listening') {
      applyCallState('understanding');
      generation.progress.promotedState = true;
    }
    emitDebugEvent(debugCallId, 'mic.reconnect_backfill.start', {
      reason,
      generation: generation.generationId,
      backfillId: generation.backfillId,
      audioInputEpoch: generation.captureEpoch,
      startOffsetMs: Math.round(nowMs - generation.startMs),
      bufferedChunks: localMicPcmBuffer.length
    });
    return generation;
  }

  function ownsReconnectAudioBackfill(
    generation: ReconnectAudioBackfillGeneration | null
  ): generation is ReconnectAudioBackfillGeneration {
    return Boolean(
      generation &&
      activeReconnectAudioBackfill === generation &&
      !generation.abortController.signal.aborted
    );
  }

  function canSendReconnectAudioBackfill(
    generation: ReconnectAudioBackfillGeneration | null
  ): generation is ReconnectAudioBackfillGeneration {
    return Boolean(
      ownsReconnectAudioBackfill(generation) &&
      !muteRequestPending &&
      !muteSynchronizationFailed &&
      !serverMuted &&
      generation.captureEpoch === localMicAudioEpoch
    );
  }

  function retireReconnectAudioBackfill(
    generation: ReconnectAudioBackfillGeneration | null
  ): boolean {
    if (!ownsReconnectAudioBackfill(generation)) {
      return false;
    }
    if (generation.progress.recoveryDrainTimer) {
      window.clearTimeout(generation.progress.recoveryDrainTimer);
      generation.progress.recoveryDrainTimer = 0;
    }
    generation.abortController.abort();
    activeReconnectAudioBackfill = null;
    if (generation.progress.promotedState && callState === 'understanding') {
      applyCallState('listening');
    }
    generation.progress.promotedState = false;
    generation.progress.awaitingFinalResponse = false;
    return true;
  }

  function beginReconnectAudioBackfillRecoveryDrain(
    generation: ReconnectAudioBackfillGeneration,
    debugCallId: string,
    reason: MediaReconnectReason,
    source: string
  ) {
    if (!ownsReconnectAudioBackfill(generation)) {
      return;
    }
    if (generation.progress.finalAcknowledged) {
      retireReconnectAudioBackfill(generation);
      return;
    }
    if (!generation.progress.finalPromise && !generation.progress.flushPromise) {
      void flushReconnectAudioBackfill(
        debugCallId,
        reason,
        Math.max(mediaReconnectAttempts, 1),
        {},
        generation
      );
    }
    if (generation.progress.recoveryDrainTimer) {
      return;
    }
    emitDebugEvent(debugCallId, 'mic.reconnect_backfill.recovery_drain', {
      reason,
      source,
      generation: generation.generationId,
      backfillId: generation.backfillId,
      timeoutMs: TERMINAL_RECONNECT_BACKFILL_WAIT_MS
    });
    generation.progress.recoveryDrainTimer = window.setTimeout(() => {
      generation.progress.recoveryDrainTimer = 0;
      if (!ownsReconnectAudioBackfill(generation)) {
        return;
      }
      emitDebugEvent(debugCallId, 'mic.reconnect_backfill.recovery_drain_timeout', {
        reason,
        source,
        generation: generation.generationId,
        backfillId: generation.backfillId,
        timeoutMs: TERMINAL_RECONNECT_BACKFILL_WAIT_MS
      });
      retireReconnectAudioBackfill(generation);
    }, TERMINAL_RECONNECT_BACKFILL_WAIT_MS);
  }

  function finishReconnectBackfillFinalResponse(
    generation: ReconnectAudioBackfillGeneration,
    hasEvent: boolean
  ) {
    if (!ownsReconnectAudioBackfill(generation)) {
      return;
    }
    generation.progress.awaitingFinalResponse = false;
    generation.progress.promotedState = false;
    if (!hasEvent && callState === 'understanding') {
      applyCallState('listening');
    }
  }

  async function flushReconnectAudioBackfill(
    debugCallId: string,
    reason: MediaReconnectReason,
    attempt: number,
    options: { awaitFinal?: boolean } = {},
    generation = activeReconnectAudioBackfill
  ) {
    if (!canSendReconnectAudioBackfill(generation)) {
      return;
    }
    if (generation.progress.flushPromise) {
      const flushPromise = generation.progress.flushPromise;
      await flushPromise;
      if (!canSendReconnectAudioBackfill(generation)) {
        return;
      }
      if (options.awaitFinal && generation.progress.finalPromise) {
        const finalPromise = generation.progress.finalPromise;
        await finalPromise;
        if (!ownsReconnectAudioBackfill(generation)) {
          return;
        }
      }
      return;
    }
    if (options.awaitFinal && generation.progress.finalPromise) {
      const finalPromise = generation.progress.finalPromise;
      await finalPromise;
      if (!ownsReconnectAudioBackfill(generation)) {
        return;
      }
      return;
    }
    const flushPromise = flushReconnectAudioBackfillOnce(
      generation,
      debugCallId,
      reason,
      attempt,
      options
    );
    const trackedFlushPromise = flushPromise.finally(() => {
      if (
        ownsReconnectAudioBackfill(generation) &&
        generation.progress.flushPromise === trackedFlushPromise
      ) {
        generation.progress.flushPromise = null;
      }
    });
    generation.progress.flushPromise = trackedFlushPromise;
    await trackedFlushPromise;
    if (!ownsReconnectAudioBackfill(generation)) {
      return;
    }
  }

  async function flushReconnectAudioBackfillOnce(
    generation: ReconnectAudioBackfillGeneration,
    debugCallId: string,
    reason: MediaReconnectReason,
    attempt: number,
    options: { awaitFinal?: boolean } = {}
  ) {
    if (!callId || !sessionId || !canSendReconnectAudioBackfill(generation)) {
      return;
    }
    const requestCallId = callId;
    const requestSessionId = sessionId;
    const selection = selectReconnectAudioBackfill(generation, performance.now());
    if (!selection) {
      emitDebugEvent(debugCallId, 'mic.reconnect_backfill.skip', {
        reason,
        attempt,
        generation: generation.generationId,
        backfillId: generation.backfillId,
        cause: 'empty',
        bufferedChunks: localMicPcmBuffer.length
      });
      if (!canSendReconnectAudioBackfill(generation)) {
        return;
      }
      generation.progress.batchIndex += 1;
      generation.progress.awaitingFinalResponse = true;
      const finalPromise = trackReconnectAudioBackfillFinalPromise(generation, sendReconnectAudioBackfillBatch({
        generation,
        debugCallId,
        requestCallId,
        requestSessionId,
        reason: generation.reason,
        attempt,
        batchIndex: generation.progress.batchIndex,
        final: true,
        selection: null
      }));
      if (options.awaitFinal) {
        await finalPromise;
        if (!ownsReconnectAudioBackfill(generation)) {
          return;
        }
      } else {
        void finalPromise;
      }
      return;
    }

    for (const chunk of splitReconnectAudioBackfillSelection(selection)) {
      if (!canSendReconnectAudioBackfill(generation)) {
        return;
      }
      generation.progress.batchIndex += 1;
      await sendReconnectAudioBackfillBatch({
        generation,
        debugCallId,
        requestCallId,
        requestSessionId,
        reason: generation.reason,
        attempt,
        batchIndex: generation.progress.batchIndex,
        final: false,
        selection: chunk
      });
      if (!canSendReconnectAudioBackfill(generation)) {
        return;
      }
      generation.progress.lastEndMs = chunk.endMs;
    }

    const tailSelection = selectReconnectAudioBackfill(
      generation,
      performance.now(),
      generation.progress.lastEndMs,
      { limitToMaxWindow: false }
    );
    const tailChunks = tailSelection ? splitReconnectAudioBackfillSelection(tailSelection) : [];
    if (!canSendReconnectAudioBackfill(generation)) {
      return;
    }
    generation.progress.awaitingFinalResponse = true;
    const finalPromise = trackReconnectAudioBackfillFinalPromise(generation, (async () => {
      if (tailChunks.length === 0) {
        if (!canSendReconnectAudioBackfill(generation)) {
          return;
        }
        generation.progress.batchIndex += 1;
        await sendReconnectAudioBackfillBatch({
          generation,
          debugCallId,
          requestCallId,
          requestSessionId,
          reason: generation.reason,
          attempt,
          batchIndex: generation.progress.batchIndex,
          final: true,
          selection: null
        });
        if (!ownsReconnectAudioBackfill(generation)) {
          return;
        }
        return;
      }

      for (let index = 0; index < tailChunks.length; index += 1) {
        if (!canSendReconnectAudioBackfill(generation)) {
          return;
        }
        const chunk = tailChunks[index];
        generation.progress.batchIndex += 1;
        await sendReconnectAudioBackfillBatch({
          generation,
          debugCallId,
          requestCallId,
          requestSessionId,
          reason: generation.reason,
          attempt,
          batchIndex: generation.progress.batchIndex,
          final: index === tailChunks.length - 1,
          selection: chunk
        });
        if (!canSendReconnectAudioBackfill(generation)) {
          return;
        }
        generation.progress.lastEndMs = chunk.endMs;
      }
    })());
    if (options.awaitFinal) {
      await finalPromise;
      if (!ownsReconnectAudioBackfill(generation)) {
        return;
      }
    } else {
      void finalPromise;
    }
  }

  function trackReconnectAudioBackfillFinalPromise(
    generation: ReconnectAudioBackfillGeneration,
    promise: Promise<void>
  ) {
    const trackedPromise = promise.finally(() => {
      if (
        ownsReconnectAudioBackfill(generation) &&
        generation.progress.finalPromise === trackedPromise
      ) {
        generation.progress.finalPromise = null;
      }
    });
    if (ownsReconnectAudioBackfill(generation)) {
      generation.progress.finalPromise = trackedPromise;
    }
    return trackedPromise;
  }

  async function sendReconnectAudioBackfillBatch({
    generation,
    debugCallId,
    requestCallId,
    requestSessionId,
    reason,
    attempt,
    batchIndex,
    final,
    selection
  }: {
    generation: ReconnectAudioBackfillGeneration;
    debugCallId: string;
    requestCallId: string;
    requestSessionId: string;
    reason: MediaReconnectReason;
    attempt: number;
    batchIndex: number;
    final: boolean;
    selection: LocalMicPcmSelection | null;
  }) {
    if (!canSendReconnectAudioBackfill(generation)) {
      return;
    }
    const batchBackfillId = `${generation.backfillId}-batch-${batchIndex}`;
    const selectedStartOffsetMs =
      selection ? Math.round(selection.startMs - generation.startMs) : null;
    const selectedEndOffsetMs =
      selection ? Math.round(selection.endMs - generation.startMs) : null;
    emitDebugEvent(debugCallId, 'mic.reconnect_backfill.sending', {
      reason,
      attempt,
      generation: generation.generationId,
      backfillId: batchBackfillId,
      baseBackfillId: generation.backfillId,
      audioInputEpoch: generation.captureEpoch,
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
        audio_input_epoch: generation.captureEpoch,
        reason,
        attempt,
        duration_ms: selection?.durationMs ?? 0,
        batch_index: batchIndex,
        final
      }, { signal: generation.abortController.signal });
      if (!ownsReconnectAudioBackfill(generation)) {
        return;
      }
      emitDebugEvent(debugCallId, 'mic.reconnect_backfill.sent', {
        reason,
        attempt,
        generation: generation.generationId,
        backfillId: batchBackfillId,
        baseBackfillId: generation.backfillId,
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
      if (final && (response.status === 'accepted' || response.status === 'duplicate')) {
        generation.progress.finalAcknowledged = true;
      }
      if (response.event) {
        await handleCallDataEvent(response.event);
        if (!ownsReconnectAudioBackfill(generation)) {
          return;
        }
      }
      if (final) {
        finishReconnectBackfillFinalResponse(generation, Boolean(response.event));
        if (generation.progress.finalAcknowledged) {
          retireReconnectAudioBackfill(generation);
        }
      }
    } catch (error) {
      if (
        !ownsReconnectAudioBackfill(generation) ||
        (error as DOMException)?.name === 'AbortError'
      ) {
        return;
      }
      emitDebugEvent(debugCallId, 'mic.reconnect_backfill.failed', {
        reason,
        attempt,
        generation: generation.generationId,
        backfillId: batchBackfillId,
        baseBackfillId: generation.backfillId,
        batchIndex,
        final,
        selectedStartOffsetMs,
        selectedEndOffsetMs,
        durationMs: selection?.durationMs ?? 0,
        samples: selection?.samples.length ?? 0,
        name: (error as Error)?.name ?? 'unknown',
        message: (error as Error)?.message ?? ''
      });
      await recoverMissedCallEvents(
        debugCallId,
        'reconnect_backfill_failed',
        generation
      );
      if (!ownsReconnectAudioBackfill(generation)) {
        return;
      }
      queueMissedCallEventsRecovery(
        debugCallId,
        'reconnect_backfill_failed_retry',
        generation
      );
      if (final) {
        finishReconnectBackfillFinalResponse(generation, false);
      }
    }
  }

  async function recoverMissedCallEvents(
    debugCallId: string,
    reason: string,
    generation: ReconnectAudioBackfillGeneration | null = null
  ) {
    if (generation && !ownsReconnectAudioBackfill(generation)) {
      return;
    }
    if (!callId || !sessionId) {
      return;
    }
    try {
      const response = await recoverCallEvents(callId, sessionId);
      emitDebugEvent(debugCallId, 'call.events_recover.done', {
        reason,
        events: response.events.length
      });
      for (const event of response.events) {
        if (generation && !ownsReconnectAudioBackfill(generation)) {
          return;
        }
        await handleCallDataEvent(event);
      }
    } catch (error) {
      emitDebugEvent(debugCallId, 'call.events_recover.failed', {
        reason,
        name: (error as Error)?.name ?? 'unknown',
        message: (error as Error)?.message ?? ''
      });
    }
  }

  function queueMissedCallEventsRecovery(
    debugCallId: string,
    reason: string,
    generation: ReconnectAudioBackfillGeneration | null = null
  ) {
    const timer = window.setTimeout(() => {
      if (generation && !ownsReconnectAudioBackfill(generation)) {
        return;
      }
      void recoverMissedCallEvents(debugCallId, reason, generation);
    }, MISSED_CALL_EVENTS_RECOVERY_RETRY_MS);
    timers = [...timers, timer];
  }

  function selectReconnectAudioBackfill(
    generation: ReconnectAudioBackfillGeneration,
    endMs: number,
    startMsOverride = generation.startMs,
    options: { limitToMaxWindow?: boolean } = {}
  ): LocalMicPcmSelection | null {
    const selection = selectReconnectAudioBackfillFromChunks(localMicPcmBuffer, {
      endMs,
      startMs: startMsOverride,
      maxDurationMs: MIC_BACKFILL_MAX_MS,
      sampleRate: MIC_BACKFILL_SAMPLE_RATE,
      audioInputEpoch: generation.captureEpoch,
      limitToMaxWindow: options.limitToMaxWindow ?? true
    });
    if (!selection || startMsOverride <= 0 || selection.startMs <= startMsOverride) {
      return selection;
    }
    return padReconnectAudioSelectionStart(selection, startMsOverride);
  }

  function splitReconnectAudioBackfillSelection(
    selection: LocalMicPcmSelection
  ): LocalMicPcmSelection[] {
    if (selection.durationMs <= MIC_BACKFILL_BATCH_MAX_MS) {
      return [selection];
    }

    const maxSamples = Math.max(
      1,
      Math.floor(MIC_BACKFILL_SAMPLE_RATE * MIC_BACKFILL_BATCH_MAX_MS / 1000)
    );
    const chunks: LocalMicPcmSelection[] = [];
    for (let offset = 0; offset < selection.samples.length; offset += maxSamples) {
      const samples = selection.samples.slice(offset, offset + maxSamples);
      const startMs = selection.startMs + offset * 1000 / MIC_BACKFILL_SAMPLE_RATE;
      chunks.push(makeReconnectAudioSelection(samples, startMs));
    }
    return chunks;
  }

  function padReconnectAudioSelectionStart(
    selection: LocalMicPcmSelection,
    startMs: number
  ): LocalMicPcmSelection {
    const paddingSamples = Math.max(
      0,
      Math.round((selection.startMs - startMs) * MIC_BACKFILL_SAMPLE_RATE / 1000)
    );
    if (paddingSamples === 0) {
      return { ...selection, startMs };
    }

    const samples = new Int16Array(paddingSamples + selection.samples.length);
    samples.set(selection.samples, paddingSamples);
    return makeReconnectAudioSelection(samples, startMs);
  }

  function makeReconnectAudioSelection(samples: Int16Array, startMs: number): LocalMicPcmSelection {
    let sumSquares = 0;
    let peak = 0;
    for (const sample of samples) {
      const abs = Math.abs(sample);
      peak = Math.max(peak, abs);
      sumSquares += sample * sample;
    }
    const durationMs = Math.round(samples.length * 1000 / MIC_BACKFILL_SAMPLE_RATE);
    return {
      startMs,
      endMs: startMs + durationMs,
      samples,
      durationMs,
      rms: Math.sqrt(sumSquares / Math.max(samples.length, 1)),
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

  function attachCallEventChannel(
    channel: RTCDataChannel,
    owner: BrowserMediaConnectionOwner,
    debugCallId = '',
    source = 'unknown'
  ) {
    emitDebugEvent(debugCallId, 'datachannel.attach', {
      label: channel.label,
      readyState: channel.readyState,
      source
    });
    channel.onopen = () => {
      if (!ownsBrowserMediaConnection(owner) || owner.eventsChannel !== channel) {
        return;
      }
      emitDebugEvent(debugCallId, 'datachannel.open', {
        label: channel.label,
        source
      });
    };
    channel.onclose = () => {
      if (!ownsBrowserMediaConnection(owner) || owner.eventsChannel !== channel) {
        return;
      }
      emitDebugEvent(debugCallId, 'datachannel.close', {
        label: channel.label,
        source
      });
    };
    channel.onerror = (event) => {
      if (!ownsBrowserMediaConnection(owner) || owner.eventsChannel !== channel) {
        return;
      }
      const error = (event as RTCErrorEvent).error;
      emitDebugEvent(debugCallId, 'datachannel.error', {
        label: channel.label,
        source,
        errorName: error?.name ?? 'unknown',
        errorMessage: error?.message ?? ''
      });
    };
    channel.onmessage = (message) => {
      if (!ownsBrowserMediaConnection(owner) || owner.eventsChannel !== channel) {
        return;
      }
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
          samples,
          audioInputEpoch: localMicAudioEpoch
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
    if (
      muteRequestPending ||
      muteSynchronizationFailed ||
      serverMuted ||
      chunk.audioInputEpoch !== localMicAudioEpoch ||
      !chunk.samples.length
    ) {
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
    retireReconnectAudioBackfill(activeReconnectAudioBackfill);
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

  function waitForBrowserMediaConnected(
    connection: RTCPeerConnection,
    debugCallId: string,
    timeoutMs = 7000
  ): Promise<void> {
    if (isBrowserMediaConnected(connection)) {
      return Promise.resolve();
    }

    return new Promise((resolve, reject) => {
      const cleanup = () => {
        window.clearTimeout(timeout);
        connection.removeEventListener('connectionstatechange', handleStateChange);
        connection.removeEventListener('iceconnectionstatechange', handleStateChange);
      };
      const handleStateChange = () => {
        if (isBrowserMediaConnected(connection)) {
          cleanup();
          resolve();
          return;
        }
        if (
          connection.connectionState === 'failed' ||
          connection.connectionState === 'closed' ||
          connection.iceConnectionState === 'failed' ||
          connection.iceConnectionState === 'closed'
        ) {
          cleanup();
          reject(new Error('Replacement media did not connect'));
        }
      };
      const timeout = window.setTimeout(() => {
        cleanup();
        emitDebugEvent(debugCallId, 'pc.media_connect.timeout', {
          connectionState: connection.connectionState,
          iceConnectionState: connection.iceConnectionState,
          timeoutMs
        });
        reject(new Error('Replacement media timed out before connecting'));
      }, timeoutMs);

      connection.addEventListener('connectionstatechange', handleStateChange);
      connection.addEventListener('iceconnectionstatechange', handleStateChange);
      handleStateChange();
    });
  }

  function waitForBrowserMediaCandidateStream(
    owner: BrowserMediaConnectionOwner,
    debugCallId: string,
    timeoutMs = 7000
  ): Promise<MediaStream> {
    if (owner.candidateRemoteStream) {
      return Promise.resolve(owner.candidateRemoteStream);
    }

    return new Promise((resolve, reject) => {
      let settled = false;
      const cleanup = () => {
        window.clearTimeout(timeout);
        owner.connection.removeEventListener('connectionstatechange', handleStateChange);
        owner.connection.removeEventListener('iceconnectionstatechange', handleStateChange);
      };
      const rejectOnce = (error: Error) => {
        if (settled) return;
        settled = true;
        cleanup();
        reject(error);
      };
      const handleStateChange = () => {
        if (
          owner.connection.connectionState === 'failed' ||
          owner.connection.connectionState === 'closed' ||
          owner.connection.iceConnectionState === 'failed' ||
          owner.connection.iceConnectionState === 'closed'
        ) {
          rejectOnce(new Error('Replacement media stream failed before promotion'));
        }
      };
      const timeout = window.setTimeout(() => {
        emitDebugEvent(debugCallId, 'remote_audio.candidate.timeout', {
          connectionGeneration: owner.generationId,
          connectionState: owner.connection.connectionState,
          iceConnectionState: owner.connection.iceConnectionState,
          timeoutMs
        });
        rejectOnce(new Error('Replacement media stream timed out before promotion'));
      }, timeoutMs);

      owner.connection.addEventListener('connectionstatechange', handleStateChange);
      owner.connection.addEventListener('iceconnectionstatechange', handleStateChange);
      owner.candidateRemoteStreamReady.then((stream) => {
        if (settled) return;
        settled = true;
        cleanup();
        resolve(stream);
      });
      handleStateChange();
    });
  }

  function promoteBrowserMediaCandidate(
    owner: BrowserMediaConnectionOwner,
    stream: MediaStream,
    debugCallId: string
  ) {
    if (!ownsBrowserMediaConnection(owner)) {
      throw new Error('Replacement media ownership changed before audio promotion');
    }
    attachRemoteAudio(stream, debugCallId);
    owner.remoteAudioPromoted = true;
    owner.candidateRemoteStream = null;
    emitDebugEvent(debugCallId, 'remote_audio.candidate.promoted', {
      stream_id: stream.id,
      connectionGeneration: owner.generationId
    });
  }

  function discardBrowserMediaCandidate(
    owner: BrowserMediaConnectionOwner,
    debugCallId: string,
    error: unknown
  ) {
    const stream = owner.candidateRemoteStream;
    owner.candidateRemoteStream = null;
    if (!stream || owner.remoteAudioPromoted) {
      return;
    }
    emitDebugEvent(debugCallId, 'remote_audio.candidate.discarded', {
      stream_id: stream.id,
      connectionGeneration: owner.generationId,
      name: (error as DOMException)?.name ?? 'unknown',
      message: (error as Error)?.message ?? ''
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
      normalized === 'rehearsing' ||
      normalized === 'speaking' ||
      normalized === 'interrupted' ||
      normalized === 'ended' ||
      normalized === 'failed' ||
      normalized === 'connecting'
    ) {
      const nextIsTerminal = normalized === 'ended' || normalized === 'failed';
      const currentIsTerminal = callState === 'ended' || callState === 'failed' || ending;
      if (currentIsTerminal && !nextIsTerminal) {
        return;
      }
      const prevState = callState;
      callState = normalized;
      keepMicrophoneSenderLive(prevState, normalized);
      syncRemoteAudioAudibility();
    } else {
      if (callState === 'ended' || callState === 'failed' || ending) {
        return;
      }
      callState = 'listening';
      keepMicrophoneSenderLive(undefined, 'listening');
      syncRemoteAudioAudibility();
    }
  }

  function keepMicrophoneSenderLive(prevState: string | undefined, nextState: string) {
    if (!localMediaStream) {
      return;
    }
    const transmissionAllowed =
      !muteRequestPending && !muteSynchronizationFailed && !serverMuted;
    const changed = transmissionAllowed
      ? keepCallMicrophoneTracksLive(localMediaStream)
      : setCallMicrophoneTracksEnabled(localMediaStream, false);
    if (changed > 0 || prevState !== nextState) {
      emitDebugEvent(callId, 'mic.keep_live', {
        changed,
        prevState: prevState ?? null,
        nextState,
        transmissionAllowed,
        policy: transmissionAllowed ? 'authoritative-unmute' : 'mute-fail-safe'
      });
    }
  }

  function setOwnedMicrophoneTransmission(enabled: boolean, reason: string) {
    if (!localMediaStream) {
      return;
    }
    const changed = setCallMicrophoneTracksEnabled(localMediaStream, enabled);
    emitDebugEvent(callId, 'mic.transmission_policy', {
      enabled,
      reason,
      changed,
      tracks: summarizeLocalAudioTracks()
    });
  }

  function syncRemoteAudioAudibility() {
    if (!remoteAudioElement) {
      return;
    }
    if (
      syncRemoteCallAudioAudibility(
        remoteAudioElement,
        remoteAudioInterruptDrainActive
      )
    ) {
      emitDebugEvent(callId, 'remote_audio.audibility', {
        muted: remoteAudioElement.muted,
        callState,
        policy: remoteAudioInterruptDrainActive ? 'interrupt-drain' : 'audible'
      });
    }
  }

  function interruptedTurnKey(eventSessionId: string, turnId: string | null): string | null {
    return turnId ? `${eventSessionId}:${turnId}` : null;
  }

  function interruptGenerationIsCurrent(generation: InterruptDrainGeneration): boolean {
    return (
      activeInterruptDrain === generation &&
      generation.lifecycle === callMediaLifecycle &&
      generation.sessionId === sessionId
    );
  }

  function interruptAcknowledgementMatches(
    generation: InterruptDrainGeneration,
    eventSessionId: string,
    turnId: string | null
  ): boolean {
    return (
      interruptGenerationIsCurrent(generation) &&
      eventSessionId === generation.sessionId &&
      (!generation.turnId || !turnId || generation.turnId === turnId)
    );
  }

  function beginRemoteAudioInterruptDrain(
    turnId: string | null,
    requestedDrainMs?: number | null
  ): InterruptDrainGeneration {
    const drainMs = normalizeRemoteCallInterruptDrainMs(requestedDrainMs);
    if (remoteAudioInterruptDrainTimer) {
      window.clearTimeout(remoteAudioInterruptDrainTimer);
    }
    if (interruptedStateTimer) {
      window.clearTimeout(interruptedStateTimer);
    }
    const generation: InterruptDrainGeneration = {
      id: ++interruptDrainGeneration,
      lifecycle: callMediaLifecycle,
      sessionId,
      turnId,
      startedAt: performance.now(),
      drainMs,
      completed: false,
      acknowledgements: new Set()
    };
    activeInterruptDrain = generation;
    remoteAudioInterruptDrainActive = true;
    syncRemoteAudioAudibility();
    emitDebugEvent(callId, 'remote_audio.interrupt_drain.started', {
      drainMs,
      generation: generation.id,
      turn_id: turnId
    });
    remoteAudioInterruptDrainTimer = window.setTimeout(() => {
      if (!interruptGenerationIsCurrent(generation)) {
        return;
      }
      remoteAudioInterruptDrainTimer = 0;
      remoteAudioInterruptDrainActive = false;
      generation.completed = true;
      syncRemoteAudioAudibility();
      emitDebugEvent(callId, 'remote_audio.interrupt_drain.completed', {
        drainMs,
        generation: generation.id,
        turn_id: generation.turnId
      });
    }, drainMs);
    applyCallState('interrupted');
    interruptedStateTimer = window.setTimeout(() => {
      if (!interruptGenerationIsCurrent(generation)) {
        return;
      }
      interruptedStateTimer = 0;
      if (callState === 'interrupted') {
        applyCallState('listening');
      }
    }, drainMs);
    return generation;
  }

  function acknowledgeInterruptDrain(
    generation: InterruptDrainGeneration,
    source: 'data-channel' | 'http',
    eventSessionId: string,
    turnId: string | null,
    requestedDrainMs?: number | null
  ): boolean {
    if (!interruptAcknowledgementMatches(generation, eventSessionId, turnId)) {
      return false;
    }
    if (!generation.turnId && turnId) {
      generation.turnId = turnId;
    }
    generation.acknowledgements.add(source);
    const key = interruptedTurnKey(eventSessionId, generation.turnId);
    if (key) {
      handledInterruptedTurnKeys.add(key);
    }
    emitDebugEvent(callId, 'remote_audio.interrupt_drain.acknowledged', {
      source,
      generation: generation.id,
      turn_id: generation.turnId,
      drainMs: normalizeRemoteCallInterruptDrainMs(requestedDrainMs),
      completed: generation.completed
    });
    return true;
  }

  function supersedeInterruptDrain(reason: 'new-turn' | 'teardown') {
    const generation = activeInterruptDrain;
    if (remoteAudioInterruptDrainTimer) {
      window.clearTimeout(remoteAudioInterruptDrainTimer);
      remoteAudioInterruptDrainTimer = 0;
    }
    if (interruptedStateTimer) {
      window.clearTimeout(interruptedStateTimer);
      interruptedStateTimer = 0;
    }
    remoteAudioInterruptDrainActive = false;
    activeInterruptDrain = null;
    syncRemoteAudioAudibility();
    if (generation) {
      emitDebugEvent(callId, 'remote_audio.interrupt_drain.superseded', {
        generation: generation.id,
        turn_id: generation.turnId,
        reason
      });
    }
  }

  function clearInterruptDrainState() {
    callMediaLifecycle += 1;
    supersedeInterruptDrain('teardown');
    latestAiTurnId = null;
    handledInterruptedTurnKeys.clear();
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
      const nextTurnId = event.turn_id ?? null;
      if (
        nextTurnId &&
        activeInterruptDrain &&
        activeInterruptDrain.turnId !== nextTurnId
      ) {
        supersedeInterruptDrain('new-turn');
      }
      latestAiTurnId = nextTurnId;
      markActiveTurnResponseDelivered(
        event.turn_id ?? undefined,
        event.audio?.duration_ms ?? undefined
      );
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

    if (event.type === 'muted') {
      if (event.session_id !== sessionId) {
        return;
      }
      const owner = activeMuteRequest;
      if (owner && event.muted !== owner.targetMuted) {
        return;
      }
      applyAuthoritativeMuteState(
        event.muted,
        event.audio_input_epoch,
        event.mute_revision,
        owner,
        'data-channel'
      );
      return;
    }

    if (event.type === 'interrupted') {
      if (event.session_id !== sessionId) {
        return;
      }
      const interruptedTurnId = event.cancelled_turn_id ?? event.turn_id ?? null;
      const key = interruptedTurnKey(event.session_id, interruptedTurnId);
      if (key && handledInterruptedTurnKeys.has(key)) {
        return;
      }
      if (
        activeInterruptDrain &&
        interruptAcknowledgementMatches(
          activeInterruptDrain,
          event.session_id,
          interruptedTurnId
        )
      ) {
        acknowledgeInterruptDrain(
          activeInterruptDrain,
          'data-channel',
          event.session_id,
          interruptedTurnId,
          event.receiver_drain_ms
        );
        return;
      }
      if (!interruptedTurnId && latestAiTurnId) {
        return;
      }
      if (interruptedTurnId && latestAiTurnId && interruptedTurnId !== latestAiTurnId) {
        handledInterruptedTurnKeys.add(key!);
        return;
      }
      cancelActiveTurnStream();
      markLastAiTurnInterrupted();
      const generation = beginRemoteAudioInterruptDrain(
        interruptedTurnId,
        event.receiver_drain_ms
      );
      acknowledgeInterruptDrain(
        generation,
        'data-channel',
        event.session_id,
        interruptedTurnId,
        event.receiver_drain_ms
      );
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
    const safeQwenMessage = safeQwenCallFailureMessage(code);
    if (safeQwenMessage) {
      return safeQwenMessage;
    }

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

  function safeQwenCallFailureMessage(code: CallErrorCode): string | null {
    if (code === 'qwen3_transcript_required') {
      return 'Add the matching reference transcript before using Qwen3-TTS 1.7B.';
    }
    if (code === 'qwen3_transcript_mismatch' || code === 'qwen3_alignment_failed') {
      return 'This transcript does not appear to match the voice sample. Review the transcript or choose a different sample, then try again.';
    }
    if (code === 'qwen3_generation_ceiling') {
      return 'RayMe stopped this voice because the generated audio exceeded its safe limit. Check the transcript and try again.';
    }
    if (
      code === 'qwen3_worker_protocol' ||
      code === 'qwen3_worker_timeout' ||
      code === 'qwen3_worker_stopped' ||
      code === 'call_tts_prepare_unavailable'
    ) {
      return 'Qwen3-TTS 1.7B is unavailable right now. Choose another voice or check AI backend status in Settings.';
    }
    if (code.startsWith('qwen3_') || code.startsWith('call_tts_prepare_')) {
      return 'RayMe could not prepare this voice for the call. Retry preparation, choose another voice, or check Settings.';
    }
    return null;
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
    if (activeReconnectAudioBackfill) {
      activeReconnectAudioBackfill.progress.promotedState = false;
      activeReconnectAudioBackfill.progress.awaitingFinalResponse = false;
    }
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
    const responseGuard = startActiveTurnResponseGuard(event.turn_id);

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
      finishActiveTurnResponseGuard(responseGuard);
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
    dispatchCallTurnStreamEvent(event, {
      ai_token: (tokenEvent) => {
        if (!tokenEvent.text) {
          return;
        }
        markActiveTurnResponseDelivered(tokenEvent.turn_id);
        appendAiText(tokenEvent.text, tokenEvent.turn_id);
      },
      state: (stateEvent) => applyCallState(stateEvent.state),
      ai_audio_started: (audioEvent) => {
        markActiveTurnResponseDelivered(audioEvent.turn_id, audioEvent.audio?.duration_ms);
        emitDebugEvent(callId, 'call.ai_audio_started', {
          turn_id: audioEvent.turn_id ?? null,
          audio: audioEvent.audio ?? null,
          remoteAudioContextState: remoteAudioContext?.state ?? 'none',
          speakingRms,
          source: 'turn-stream'
        });
        applyCallState('speaking');
      },
      ai_done: (doneEvent) => {
        markActiveTurnResponseDelivered(doneEvent.turn_id);
        if (doneEvent.message) {
          restoreCompletedAiMessage(doneEvent.message, doneEvent.turn_id);
        }
        finishAiTurn();
      },
      turn_existing: (existingEvent) => {
        markActiveTurnResponseDelivered(existingEvent.turn_id);
        const disposition = existingTurnDisposition(existingEvent.state);
        if (disposition.notice) {
          appendCallNotice(disposition.notice, existingEvent.turn_id);
        }
        applyCallState(disposition.state);
      },
      error: (errorEvent) => {
        const message = messageForCallFailure(
          (errorEvent.code ?? 'call_generation_failed') as CallErrorCode,
          errorEvent.message
        );
        appendCallNotice(message, errorEvent.turn_id);
        applyCallState('listening');
      }
    });
  }

  function restoreCompletedAiMessage(message: CallTurnAssistantMessage, turnId?: string) {
    const text = message.content_text?.trim() ?? '';
    if (!text) {
      return;
    }
    const canonical: CallTranscriptTurn = {
      id: message.id,
      turn_id: turnId,
      role: 'assistant',
      type: 'ai_speech',
      text,
      created_at: message.created_at ?? null
    };
    const existingIndex = transcript.findIndex(
      (turn) =>
        turn.role === 'assistant' &&
        (turn.id === message.id || (turnId !== undefined && turn.turn_id === turnId))
    );
    if (existingIndex < 0) {
      transcript = [...transcript, canonical];
      return;
    }
    transcript = transcript.map((turn, index) =>
      index === existingIndex ? canonical : turn
    );
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

  function ownsMuteRequest(owner: MuteRequestOwner | null): owner is MuteRequestOwner {
    return Boolean(owner && activeMuteRequest === owner);
  }

  function isAuthoritativeAudioInputEpoch(value: unknown): value is number {
    return Number.isInteger(value) && Number(value) >= 0;
  }

  function isAuthoritativeMuteRevision(value: unknown): value is number {
    return Number.isInteger(value) && Number(value) >= 1;
  }

  function applyAuthoritativeMuteState(
    muted: boolean,
    audioInputEpoch: unknown,
    muteRevision: unknown,
    owner: MuteRequestOwner | null = null,
    source: 'http' | 'data-channel' = 'http'
  ): boolean {
    if (
      typeof muted !== 'boolean' ||
      !isAuthoritativeAudioInputEpoch(audioInputEpoch) ||
      audioInputEpoch < localMicAudioEpoch ||
      !isAuthoritativeMuteRevision(muteRevision) ||
      muteRevision < localMuteRevision ||
      (muteRevision === localMuteRevision && muted !== serverMuted)
    ) {
      return false;
    }
    if (owner && !ownsMuteRequest(owner)) {
      return false;
    }
    if (owner) {
      owner.acknowledgement.muted = muted;
      owner.acknowledgement.audioInputEpoch = audioInputEpoch;
      owner.acknowledgement.muteRevision = muteRevision;
    }
    const epochChanged = audioInputEpoch !== localMicAudioEpoch;
    localMicAudioEpoch = audioInputEpoch;
    localMuteRevision = muteRevision;
    serverMuted = muted;
    muteSynchronizationFailed = false;
    setOwnedMicrophoneTransmission(!muted, muted ? 'authoritative-mute' : 'authoritative-unmute');
    if (muted || epochChanged) {
      localMicPcmBuffer = [];
    }
    if (muted) {
      retireReconnectAudioBackfill(activeReconnectAudioBackfill);
    }
    if (owner && source === 'data-channel' && !owner.acknowledgement.settled) {
      const result = {
        muted,
        audio_input_epoch: audioInputEpoch,
        mute_revision: muteRevision
      };
      owner.acknowledgement.settled = true;
      owner.acknowledgement.resolve(result);
      owner.abortController.abort();
      emitDebugEvent(owner.callId, 'call.mute.acknowledged', {
        requestId: owner.requestId,
        source,
        muted,
        muteRevision
      });
    }
    return true;
  }

  function validAuthoritativeMuteResult(
    result: Partial<AuthoritativeMuteResult>
  ): result is AuthoritativeMuteResult {
    return (
      typeof result.muted === 'boolean' &&
      isAuthoritativeAudioInputEpoch(result.audio_input_epoch) &&
      isAuthoritativeMuteRevision(result.mute_revision)
    );
  }

  async function requestAuthoritativeMute(owner: MuteRequestOwner) {
    let lastError: unknown = new Error('Mute request failed');
    const httpResult = (async (): Promise<AuthoritativeMuteResult> => {
      for (let attempt = 1; attempt <= 2; attempt += 1) {
        try {
          const result = await setCallMuted(
            owner.callId,
            owner.sessionId,
            owner.targetMuted,
            { signal: owner.abortController.signal }
          );
          if (!ownsMuteRequest(owner)) {
            throw new DOMException('Mute request owner was superseded', 'AbortError');
          }
          if (
            validAuthoritativeMuteResult(result) &&
            result.muted === owner.targetMuted
          ) {
            emitDebugEvent(owner.callId, 'call.mute.acknowledged', {
              requestId: owner.requestId,
              source: 'http',
              muted: result.muted,
              muteRevision: result.mute_revision
            });
            return result;
          }
          lastError = new Error('Mute response did not include authoritative state');
        } catch (error) {
          if (!ownsMuteRequest(owner) || owner.abortController.signal.aborted) {
            throw error;
          }
          lastError = error;
        }
        if (attempt === 1) {
          emitDebugEvent(owner.callId, 'call.mute.retry', {
            requestId: owner.requestId,
            muted: owner.targetMuted
          });
        }
      }
      throw lastError;
    })();
    let timeoutId = 0;
    const timeout = new Promise<never>((_resolve, reject) => {
      timeoutId = window.setTimeout(() => {
        owner.abortController.abort();
        reject(new DOMException('Mute acknowledgement timed out', 'TimeoutError'));
      }, MUTE_ACKNOWLEDGEMENT_TIMEOUT_MS);
    });
    try {
      return await Promise.race([
        httpResult,
        owner.acknowledgement.promise,
        timeout
      ]);
    } finally {
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
    }
  }

  async function requestCompensatingMute(
    owner: MuteRequestOwner
  ): Promise<AuthoritativeMuteResult | null> {
    const controller = new AbortController();
    let timeoutId = 0;
    const timeout = new Promise<null>((resolve) => {
      timeoutId = window.setTimeout(() => {
        controller.abort();
        resolve(null);
      }, MUTE_COMPENSATION_TIMEOUT_MS);
    });
    try {
      const result = await Promise.race([
        setCallMuted(owner.callId, owner.sessionId, true, { signal: controller.signal })
          .then((response) =>
            validAuthoritativeMuteResult(response) && response.muted === true
              ? response
              : null
          )
          .catch(() => null),
        timeout
      ]);
      emitDebugEvent(owner.callId, 'call.mute.compensation', {
        requestId: owner.requestId,
        confirmed: Boolean(result),
        muteRevision: result?.mute_revision ?? null
      });
      return result;
    } finally {
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
    }
  }

  function createMuteRequestOwner(targetMuted: boolean): MuteRequestOwner {
    let resolveAcknowledgement!: (result: AuthoritativeMuteResult) => void;
    const acknowledgementPromise = new Promise<AuthoritativeMuteResult>((resolve) => {
      resolveAcknowledgement = resolve;
    });
    return Object.freeze<MuteRequestOwner>({
      requestId: ++muteRequestGeneration,
      callId,
      sessionId,
      previousMuted: serverMuted,
      targetMuted,
      abortController: new AbortController(),
      acknowledgement: {
        muted: null,
        audioInputEpoch: null,
        muteRevision: null,
        settled: false,
        promise: acknowledgementPromise,
        resolve: resolveAcknowledgement
      }
    });
  }

  async function applyMuteTarget(targetMuted: boolean) {
    if (muteRequestPending || !callId || !sessionId) {
      return;
    }

    const owner = createMuteRequestOwner(targetMuted);
    activeMuteRequest = owner;
    muteRequestPending = true;
    serverMuted = owner.targetMuted;
    setOwnedMicrophoneTransmission(false, 'mute-control-pending');

    try {
      const result = await requestAuthoritativeMute(owner);
      if (!ownsMuteRequest(owner) || !result) {
        return;
      }
      if (!applyAuthoritativeMuteState(
        result.muted,
        result.audio_input_epoch,
        result.mute_revision,
        owner
      )) {
        throw new Error('Mute response carried stale authoritative state');
      }
    } catch (error) {
      if (!ownsMuteRequest(owner)) {
        return;
      }
      serverMuted = true;
      muteSynchronizationFailed = true;
      setOwnedMicrophoneTransmission(false, 'mute-control-ambiguous');
      localMicPcmBuffer = [];
      retireReconnectAudioBackfill(activeReconnectAudioBackfill);
      emitDebugEvent(owner.callId, 'call.mute.sync_failed', {
        requestId: owner.requestId,
        targetMuted: owner.targetMuted,
        previousMuted: owner.previousMuted,
        name: (error as Error)?.name ?? 'unknown'
      });
      const compensated = await requestCompensatingMute(owner);
      if (
        ownsMuteRequest(owner) &&
        compensated &&
        compensated.muted === true
      ) {
        applyAuthoritativeMuteState(
          compensated.muted,
          compensated.audio_input_epoch,
          compensated.mute_revision
        );
      }
    } finally {
      if (ownsMuteRequest(owner)) {
        activeMuteRequest = null;
        muteRequestPending = false;
        setOwnedMicrophoneTransmission(
          !serverMuted && !muteSynchronizationFailed,
          'mute-control-settled'
        );
      }
    }
  }

  async function toggleMute() {
    if (muteSynchronizationFailed) {
      return;
    }
    await applyMuteTarget(!serverMuted);
  }

  async function retryMuteSynchronization() {
    if (!muteSynchronizationFailed || muteRequestPending) {
      return;
    }
    await applyMuteTarget(true);
  }

  async function interrupt() {
    const interruptedTurnId = latestAiTurnId ?? activeTurnResponseGuard?.turnId ?? null;
    cancelActiveTurnStream();
    markLastAiTurnInterrupted();
    const generation = beginRemoteAudioInterruptDrain(interruptedTurnId);
    if (callId && sessionId) {
      try {
        const result = await interruptCall(callId, sessionId);
        acknowledgeInterruptDrain(
          generation,
          'http',
          result.session_id,
          result.cancelled_turn_id ?? null,
          result.receiver_drain_ms
        );
      } catch {
        // The visual state still returns to listening; raw control failures stay out of UI copy.
      }
    }
  }

  function cancelActiveTurnStream() {
    if (activeTurnResponseGuard) {
      finishActiveTurnResponseGuard(activeTurnResponseGuard);
    }
    activeTurnAbort?.abort();
    activeTurnReader?.cancel().catch(() => undefined);
    activeTurnAbort = null;
    activeTurnReader = null;
  }

  function startActiveTurnResponseGuard(turnId: string): ActiveTurnResponseGuard {
    let resolveGuard: (result: ActiveTurnResponseResult) => void = () => undefined;
    const guard: ActiveTurnResponseGuard = {
      turnId,
      startedAt: performance.now(),
      delivered: false,
      audioDurationMs: 0,
      settled: false,
      promise: new Promise<ActiveTurnResponseResult>((resolve) => {
        resolveGuard = resolve;
      }),
      resolve: (result: ActiveTurnResponseResult) => resolveGuard(result)
    };
    activeTurnResponseGuard = guard;
    return guard;
  }

  function finishActiveTurnResponseGuard(guard: ActiveTurnResponseGuard) {
    if (guard.settled) {
      return;
    }
    guard.settled = true;
    guard.resolve({
      delivered: guard.delivered,
      audioDurationMs: guard.audioDurationMs
    });
    if (activeTurnResponseGuard === guard) {
      activeTurnResponseGuard = null;
    }
  }

  function markActiveTurnResponseDelivered(turnId?: string, audioDurationMs?: number) {
    const guard = activeTurnResponseGuard;
    if (!guard) {
      return;
    }
    if (turnId && guard.turnId && turnId !== guard.turnId) {
      return;
    }
    guard.delivered = true;
    if (typeof audioDurationMs === 'number' && Number.isFinite(audioDurationMs)) {
      guard.audioDurationMs = Math.max(guard.audioDurationMs, Math.max(0, audioDurationMs));
    }
  }

  async function waitForActiveTurnResponseBeforeTerminalCleanup(
    debugCallId: string,
    reason: string,
    phase: string
  ) {
    const guard = activeTurnResponseGuard;
    if (!guard) {
      return;
    }
    emitDebugEvent(debugCallId, 'call.turn_response.terminal_wait.start', {
      reason,
      phase,
      turnId: guard.turnId,
      elapsedMs: Math.round(performance.now() - guard.startedAt)
    });

    let timeoutId = 0;
    const timeoutResult = new Promise<{ status: 'timeout' }>((resolve) => {
      timeoutId = window.setTimeout(
        () => resolve({ status: 'timeout' }),
        TERMINAL_RECONNECT_ACTIVE_RESPONSE_WAIT_MS
      );
    });
    const result = await Promise.race([
      guard.promise.then((value) => ({ status: 'done' as const, value })),
      timeoutResult
    ]);
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }

    if (result.status === 'timeout') {
      emitDebugEvent(debugCallId, 'call.turn_response.terminal_wait.timeout', {
        reason,
        phase,
        turnId: guard.turnId,
        timeoutMs: TERMINAL_RECONNECT_ACTIVE_RESPONSE_WAIT_MS
      });
      return;
    }

    const playbackGraceMs = result.value.delivered
      ? Math.min(
          Math.max(
            result.value.audioDurationMs,
            TERMINAL_RECONNECT_RESPONSE_VISIBLE_GRACE_MS
          ),
          TERMINAL_RECONNECT_RESPONSE_PLAYBACK_MAX_MS
        )
      : 0;
    emitDebugEvent(debugCallId, 'call.turn_response.terminal_wait.done', {
      reason,
      phase,
      turnId: guard.turnId,
      delivered: result.value.delivered,
      audioDurationMs: result.value.audioDurationMs,
      playbackGraceMs
    });
    if (playbackGraceMs > 0) {
      await delay(playbackGraceMs);
    }
  }

  function delay(ms: number) {
    return new Promise<void>((resolve) => {
      window.setTimeout(resolve, ms);
    });
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
        await recoverMissedCallEvents(callId, 'hangup');
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
    const generation = activeReconnectAudioBackfill;
    if (!callId || !sessionId || !generation) {
      return;
    }
    const reason = generation.reason;
    const attempt = Math.max(mediaReconnectAttempts, 1);
    emitDebugEvent(callId, 'mic.reconnect_backfill.hangup_flush', {
      reason,
      attempt,
      backfillId: generation.backfillId,
      bufferedChunks: localMicPcmBuffer.length
    });
    try {
      await waitForTerminalReconnectAudioBackfill(callId, reason, attempt, 'hangup');
    } catch {
      // Hangup must still recover/end when reconnect backfill itself fails.
    }
    await recoverMissedCallEvents(callId, 'hangup_flush');
  }

  async function returnToThread() {
    await goto(`/chat/${encodeURIComponent(threadId)}`);
  }

  function showBlockingPanel(error: unknown) {
    callState = 'failed';

    if (error instanceof CallApiError) {
      if (error.code === 'qwen3_transcript_required') {
        showFocusedBlockingPanel({
          heading: 'Voice preparation failed',
          body: 'Add the matching reference transcript before using Qwen3-TTS 1.7B.',
          action: 'Open Voice Lab',
          tone: 'warning'
        });
        return;
      }

      if (error.code === 'qwen3_transcript_mismatch' || error.code === 'qwen3_alignment_failed') {
        showFocusedBlockingPanel({
          heading: 'Voice preparation failed',
          body: 'This transcript does not appear to match the voice sample. Review the transcript or choose a different sample, then try again.',
          action: 'Open Voice Lab',
          tone: 'warning'
        });
        return;
      }

      if (
        error.code === 'qwen3_prompt_failed' ||
        error.code === 'qwen3_prompt_not_ready' ||
        error.code === 'call_tts_prepare_failed' ||
        error.code === 'call_tts_prepare_mismatch'
      ) {
        showFocusedBlockingPanel({
          heading: 'Voice preparation failed',
          body: 'RayMe could not prepare this voice for the call. Retry preparation, choose another voice, or check Settings.',
          action: 'Retry Preparation',
          tone: 'warning'
        });
        return;
      }

      if (
        error.code === 'qwen3_worker_protocol' ||
        error.code === 'qwen3_worker_timeout' ||
        error.code === 'qwen3_worker_stopped' ||
        error.code === 'call_tts_prepare_unavailable'
      ) {
        showFocusedBlockingPanel({
          heading: 'Qwen3-TTS 1.7B unavailable',
          body: 'Qwen3-TTS 1.7B is unavailable right now. Choose another voice or check AI backend status in Settings.',
          action: 'Open Settings',
          tone: 'danger'
        });
        return;
      }

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

  function showFocusedBlockingPanel(panel: BlockingPanel) {
    blockingPanel = panel;
    queueMicrotask(() => blockingPanelHeading?.focus());
  }

  function handleBlockingAction(action: BlockingAction) {
    if (action === 'Retry Microphone' || action === 'Retry Preparation') {
      void beginCall();
      return;
    }

    if (action === 'Open Voice Lab') {
      void goto('/voice-lab');
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
    resetBrowserMediaReconnectIncident();
    clearInterruptDrainState();
    stopLocalMicReconnectDiagnostics();
    mediaReconnecting = false;
    activeMuteRequest?.abortController.abort();
    activeMuteRequest = null;
    muteRequestPending = false;
    stopLocalMicMeter();
    detachRemoteAudio();
    remoteAudioContext?.close().catch(() => undefined);
    remoteAudioContext = null;
    const closingEventsChannel = eventsChannel;
    const closingPeerConnection = peerConnection;
    activeBrowserMediaConnection = null;
    eventsChannel = null;
    peerConnection = null;
    closingEventsChannel?.close?.();
    closingPeerConnection?.close?.();
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
    element.muted = remoteAudioInterruptDrainActive;
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
    if (state === 'rehearsing') {
      return 'Rehearsing';
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
      <h2 bind:this={blockingPanelHeading} tabindex="-1">{blockingPanel.heading ?? blockingPanel.action}</h2>
      <p>{blockingPanel.body}</p>
      <button type="button" onclick={() => handleBlockingAction(blockingPanel!.action)}>
        {blockingPanel.action}
      </button>
    </div>
  {:else if callState === 'connecting'}
    <div class="blocking-panel" role="status">
      <RefreshCw class="preparation-progress" size={22} strokeWidth={1.8} aria-hidden="true" />
      {#if qwenPreparationActive}
        <h2>Preparing voice</h2>
        <div class="preparation-rows" aria-label="Call voice preparation">
          <p>
            {callPreparation.model.state === 'resident'
              ? 'Qwen3-TTS 1.7B loaded'
              : 'Loading Qwen3-TTS 1.7B…'}
          </p>
          <p>
            {callPreparation.prompt.state === 'ready'
              ? 'Saved voice ready'
              : `Preparing ${selectedCallVoiceName}…`}
          </p>
        </div>
      {:else}
        <h2>Connecting</h2>
      {/if}
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
        muteDisabled={muteRequestPending || muteSynchronizationFailed}
        interruptEnabled={callState === 'understanding' || callState === 'thinking' || callState === 'rehearsing' || callState === 'speaking'}
        endEnabled={!ending}
        inputPickerSupported={false}
        outputPickerSupported={false}
        onMuteToggle={toggleMute}
        onInterrupt={interrupt}
        onEnd={hangup}
      />
      {#if muteSynchronizationFailed}
        <div class="mute-recovery" role="alert">
          <p>RayMe could not confirm the microphone state. Your microphone is physically off.</p>
          <div class="mute-recovery-actions">
            <button
              type="button"
              disabled={muteRequestPending}
              onclick={retryMuteSynchronization}
            >
              Retry microphone sync
            </button>
            <button type="button" disabled={ending} onclick={hangup}>End call now</button>
          </div>
        </div>
      {/if}
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

  .mute-recovery {
    display: grid;
    gap: var(--space-sm);
    border: 1px solid rgba(255, 191, 105, 0.56);
    border-radius: var(--radius-md);
    padding: var(--space-md);
    background: rgba(70, 42, 12, 0.94);
    color: var(--color-text);
    box-shadow: var(--shadow-float);
  }

  .mute-recovery p {
    line-height: var(--line-body);
  }

  .mute-recovery-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-sm);
  }

  .mute-recovery-actions button {
    min-height: 44px;
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(20, 31, 56, 0.9);
    color: var(--color-text);
    font: inherit;
    font-weight: 600;
  }

  .mute-recovery-actions button:disabled {
    cursor: not-allowed;
    opacity: 0.55;
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

  .preparation-rows {
    display: grid;
    width: min(100%, 520px);
    gap: var(--space-sm);
  }

  .preparation-rows p {
    border-radius: var(--radius-md);
    padding: var(--space-sm) var(--space-md);
    background: rgba(9, 19, 40, 0.56);
    color: var(--color-text);
    overflow-wrap: anywhere;
  }

  :global(.preparation-progress) {
    animation: preparation-spin 1s linear infinite;
  }

  @keyframes preparation-spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    :global(.preparation-progress) {
      animation: none;
    }
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
