import type { ThreadMessage } from './types';

export interface ChatStreamHandlers {
  onToken?: (text: string) => void;
  onDone?: (message: ThreadMessage) => void;
  onError?: (message: string) => void;
}

type ChatStreamEvent =
  | { type: 'token'; text: string }
  | { type: 'done'; message: ThreadMessage }
  | { type: 'error'; message: string };

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

    dispatchEvent(JSON.parse(dataLines.join('\n')) as ChatStreamEvent, handlers);
  }

  return remainder;
}

function dispatchEvent(event: ChatStreamEvent, handlers: ChatStreamHandlers): void {
  if (event.type === 'token') {
    handlers.onToken?.(event.text);
    return;
  }

  if (event.type === 'done') {
    handlers.onDone?.(event.message);
    return;
  }

  if (event.type === 'error') {
    handlers.onError?.(event.message);
  }
}
