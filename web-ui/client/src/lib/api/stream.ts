import {
  decodeGenerationFailure,
  decodeRefusalActivity,
  type GenerationFailure,
  type RefusalActivity,
  type ThreadMessage
} from './types';

export interface ChatStreamHandlers {
  onToken?: (text: string) => void;
  onDone?: (message: ThreadMessage) => void;
  /** @deprecated Use onFailure for typed, display-safe handling. */
  onError?: (message: string) => void;
  onFailure?: (failure: GenerationFailure) => void;
  onActivity?: (activity: RefusalActivity) => void;
}

type ChatStreamEvent =
  | { type: 'token'; text: string }
  | { type: 'done'; message: ThreadMessage }
  | { type: 'error'; code?: unknown; message?: unknown }
  | ({ type: 'refusal_activity' } & Record<string, unknown>);

export async function readChatStream(response: Response, handlers: ChatStreamHandlers): Promise<void> {
  if (!response.body) {
    throw new Error('No response stream');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    buffer = dispatchCompleteEvents(buffer, handlers);
  }

  buffer += decoder.decode();
  dispatchCompleteEvents(`${buffer}\n\n`, handlers);
}

function dispatchCompleteEvents(buffer: string, handlers: ChatStreamHandlers): string {
  const parts = buffer.split(/\r?\n\r?\n/);
  const remainder = parts.pop() ?? '';

  for (const part of parts) {
    const dataLines = part
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data: '))
      .map((line) => line.slice('data: '.length));

    if (dataLines.length === 0) {
      continue;
    }

    try {
      dispatchEvent(JSON.parse(dataLines.join('\n')) as ChatStreamEvent, handlers);
    } catch {
      dispatchFailure({ type: 'error' }, handlers);
    }
  }

  return remainder;
}

function dispatchEvent(event: ChatStreamEvent, handlers: ChatStreamHandlers): void {
  if (event.type === 'token') {
    if (typeof event.text === 'string') {
      handlers.onToken?.(event.text);
    }
    return;
  }

  if (event.type === 'done') {
    if (event.message && typeof event.message === 'object') {
      handlers.onDone?.(event.message);
    }
    return;
  }

  if (event.type === 'refusal_activity') {
    const activity = decodeRefusalActivity(event);
    if (activity) {
      handlers.onActivity?.(activity);
    }
    return;
  }

  if (event.type === 'error') {
    dispatchFailure(event, handlers);
  }
}

function dispatchFailure(event: unknown, handlers: ChatStreamHandlers): void {
  const failure = decodeGenerationFailure(event);
  handlers.onFailure?.(failure);
  // Legacy observers receive only the old field when no typed observer exists.
  // Production generation surfaces use onFailure and never consume this field.
  if (!handlers.onFailure && handlers.onError) {
    const record = event && typeof event === 'object' ? (event as Record<string, unknown>) : null;
    handlers.onError(typeof record?.message === 'string' ? record.message : 'LLM stream failed');
  }
}
