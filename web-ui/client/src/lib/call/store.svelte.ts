import type { CallErrorCode, CallStateName, CallTranscriptTurn } from '$lib/api/types';

type StopHandle = { stop?: () => void };
type AbortHandle = { abort?: () => void };

export interface CallStoreOptions {
  callId?: string | null;
  threadId?: string | null;
  generation?: AbortHandle & { promise?: Promise<unknown> };
  playback?: StopHandle;
  media?: StopHandle & { localTrack?: { enabled: boolean } };
}

export interface CallFailure {
  code?: CallErrorCode;
  publicMessage?: string;
}

export interface FinalizedSpeech {
  turnId?: string;
  text: string;
}

export interface AiSpeechStarted {
  turnId?: string;
  text?: string;
}

export interface CallStore {
  readonly state: CallStateName;
  readonly transcript: CallTranscriptTurn[];
  readonly activeAiText: string;
  readonly serverMuted: boolean;
  readonly errorMessage: string | null;
  startConnecting: () => void;
  markListening: () => void;
  markThinking: () => void;
  markSpeaking: (event?: AiSpeechStarted) => void;
  interruptAiTurn: (options?: { source?: 'button' | 'server' }) => void;
  setServerMuted: (muted: boolean) => void;
  appendUserFinal: (event: FinalizedSpeech) => CallTranscriptTurn;
  appendAiToken: (token: string) => CallTranscriptTurn;
  finishAiTurn: () => CallTranscriptTurn | null;
  failCall: (failure?: CallFailure) => void;
  endCall: () => void;
  connected: () => void;
  userSpeechFinalized: (event: FinalizedSpeech) => CallTranscriptTurn;
  aiSpeechStarted: (event?: AiSpeechStarted) => void;
  interrupt: (options?: { source?: 'button' | 'server' }) => void;
  fail: (failure?: CallFailure) => void;
  end: () => void;
  flushTransientState: () => Promise<void>;
}

const CALL_STATES: CallStateName[] = [
  'idle',
  'connecting',
  'listening',
  'thinking',
  'speaking',
  'interrupted',
  'ended',
  'failed'
];

export function createCallStore(options: CallStoreOptions = {}): CallStore {
  let state: CallStateName = options.callId || options.threadId ? 'connecting' : 'idle';
  let transcript: CallTranscriptTurn[] = [];
  let activeAiText = '';
  let activeAiTurn: CallTranscriptTurn | null = null;
  let serverMuted = false;
  let errorMessage: string | null = null;
  let sequence = 0;

  const cleanupActiveWork = () => {
    options.generation?.abort?.();
    options.playback?.stop?.();
  };

  const stopAll = () => {
    cleanupActiveWork();
    options.media?.stop?.();
  };

  const store: CallStore = {
    get state() {
      return state;
    },
    get transcript() {
      return transcript;
    },
    get activeAiText() {
      return activeAiText;
    },
    get serverMuted() {
      return serverMuted;
    },
    get errorMessage() {
      return errorMessage;
    },
    startConnecting() {
      state = 'connecting';
      errorMessage = null;
    },
    markListening() {
      state = 'listening';
      errorMessage = null;
      activeAiText = '';
      activeAiTurn = null;
    },
    markThinking() {
      state = 'thinking';
      errorMessage = null;
    },
    markSpeaking(event?: AiSpeechStarted) {
      state = 'speaking';
      errorMessage = null;
      if (event?.text) {
        store.appendAiToken(event.text);
      }
    },
    interruptAiTurn(options?: { source?: 'button' | 'server' }) {
      if (options?.source === 'button') {
        cleanupActiveWork();
      }
      state = 'interrupted';
    },
    setServerMuted(muted: boolean) {
      serverMuted = muted;
    },
    appendUserFinal(event: FinalizedSpeech) {
      const turn = createTranscriptTurn({
        role: 'user',
        type: 'user_speech',
        text: event.text,
        turnId: event.turnId
      });
      transcript = [...transcript, turn];
      state = 'thinking';
      return turn;
    },
    appendAiToken(token: string) {
      if (!activeAiTurn) {
        activeAiText = '';
        activeAiTurn = createTranscriptTurn({
          role: 'assistant',
          type: 'ai_speech',
          text: '',
          turnId: undefined
        });
        transcript = [...transcript, activeAiTurn];
      }

      activeAiText = `${activeAiText}${token}`;
      activeAiTurn = { ...activeAiTurn, text: activeAiText };
      transcript = transcript.map((turn) => (turn.id === activeAiTurn?.id ? activeAiTurn : turn));
      return activeAiTurn;
    },
    finishAiTurn() {
      const finished = activeAiTurn;
      activeAiText = '';
      activeAiTurn = null;
      state = 'listening';
      return finished;
    },
    failCall(failure?: CallFailure) {
      cleanupActiveWork();
      errorMessage = failure?.publicMessage ?? failure?.code ?? null;
      state = 'failed';
    },
    endCall() {
      stopAll();
      state = 'ended';
    },
    connected() {
      store.markListening();
    },
    userSpeechFinalized(event: FinalizedSpeech) {
      return store.appendUserFinal(event);
    },
    aiSpeechStarted(event?: AiSpeechStarted) {
      store.markSpeaking(event);
    },
    interrupt(options?: { source?: 'button' | 'server' }) {
      store.interruptAiTurn(options);
    },
    fail(failure?: CallFailure) {
      store.failCall(failure);
    },
    end() {
      store.endCall();
    },
    async flushTransientState() {
      if (state === 'interrupted') {
        await Promise.resolve();
        store.markListening();
      }
    }
  };

  function createTranscriptTurn(options: {
    role: CallTranscriptTurn['role'];
    type: NonNullable<CallTranscriptTurn['type']>;
    text: string;
    turnId?: string;
  }): CallTranscriptTurn {
    sequence += 1;
    return {
      id: `local-call-turn-${sequence}`,
      turn_id: options.turnId,
      role: options.role,
      type: options.type,
      text: options.text,
      created_at: null
    };
  }

  void CALL_STATES;
  return store;
}
