import type {
  CallStateName,
  CallTurnExistingState,
  CallTurnStreamEvent
} from '$lib/api/types';

export interface ExistingTurnDisposition {
  state: Extract<CallStateName, 'thinking' | 'rehearsing' | 'listening'>;
  notice: string | null;
}

export type CallTurnStreamHandlers = {
  [EventType in CallTurnStreamEvent['type']]?: (
    event: Extract<CallTurnStreamEvent, { type: EventType }>
  ) => void;
};

export function existingTurnDisposition(
  state: CallTurnExistingState
): ExistingTurnDisposition {
  if (state === 'reserved') {
    return { state: 'thinking', notice: null };
  }
  if (state === 'running') {
    return { state: 'rehearsing', notice: null };
  }
  if (state === 'cancelled') {
    return {
      state: 'listening',
      notice: 'That turn was cancelled. RayMe is listening for you to try again.'
    };
  }
  return {
    state: 'listening',
    notice: 'That turn did not finish. Please try again.'
  };
}

export function dispatchCallTurnStreamEvent(
  event: CallTurnStreamEvent,
  handlers: CallTurnStreamHandlers
): void {
  switch (event.type) {
    case 'ai_token':
      handlers.ai_token?.(event);
      return;
    case 'state':
      handlers.state?.(event);
      return;
    case 'ai_audio_started':
      handlers.ai_audio_started?.(event);
      return;
    case 'ai_done':
      handlers.ai_done?.(event);
      return;
    case 'turn_existing':
      handlers.turn_existing?.(event);
      return;
    case 'error':
      handlers.error?.(event);
      return;
  }
}
