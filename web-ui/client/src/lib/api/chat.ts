import { toApiPath } from './client';
import { apiFetch } from './client';
import { readChatStream, type ChatStreamHandlers } from './stream';
import type { MessageKind, MessageRole, ThreadDetail, ThreadMessage } from './types';

export const CHAT_STREAM_ERROR_COPY =
  'RayMe cannot reach the LLM endpoint. Check Settings, run Test Connection, and try again.';

export interface ChatMessageView extends ThreadMessage {
  streaming?: boolean;
  error?: string | null;
  retryContent?: string | null;
}

interface DraftMessageOptions {
  id: string;
  thread_id: string;
  message_kind: MessageKind;
  role: MessageRole;
  sequence: number;
  content_text: string;
  streaming?: boolean;
  error?: string | null;
  retryContent?: string | null;
}

export function loadThread(threadId: string): Promise<ThreadDetail> {
  return apiFetch<ThreadDetail>(`/threads/${encodeURIComponent(threadId)}`, { method: 'GET' });
}

export async function sendChatMessage(
  threadId: string,
  content: string,
  handlers: ChatStreamHandlers
): Promise<void> {
  const response = await fetch(toApiPath(`/chat/${encodeURIComponent(threadId)}/send`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content })
  });

  if (!response.ok) {
    throw new Error(`RayMe chat stream failed: ${response.status} ${response.statusText}`.trim());
  }

  await readChatStream(response, handlers);
}

export function selectedMessageContent(message: Pick<ThreadMessage, 'content_text' | 'selected_alternate_id' | 'alternates'>): string {
  const selectedAlternate = message.alternates.find(
    (alternate) => alternate.id === message.selected_alternate_id
  );
  return selectedAlternate?.content_text ?? message.content_text ?? '';
}

export function createDraftMessage(options: DraftMessageOptions): ChatMessageView {
  return {
    id: options.id,
    thread_id: options.thread_id,
    message_kind: options.message_kind,
    role: options.role,
    sequence: options.sequence,
    content_text: options.content_text,
    selected_alternate_id: null,
    alternates: [],
    stale_after_edit: false,
    created_at: null,
    updated_at: null,
    streaming: options.streaming ?? false,
    error: options.error ?? null,
    retryContent: options.retryContent ?? null
  };
}

export function appendTokenToStreamingMessage(
  messages: ChatMessageView[],
  streamingMessageId: string,
  token: string
): ChatMessageView[] {
  return messages.map((message) =>
    message.id === streamingMessageId
      ? { ...message, content_text: `${message.content_text ?? ''}${token}` }
      : message
  );
}

export function replaceStreamingMessage(
  messages: ChatMessageView[],
  streamingMessageId: string,
  doneMessage: ThreadMessage
): ChatMessageView[] {
  return messages.map((message) =>
    message.id === streamingMessageId ? { ...doneMessage, streaming: false, error: null } : message
  );
}

export function markStreamingMessageError(
  messages: ChatMessageView[],
  streamingMessageId: string,
  retryContent: string
): ChatMessageView[] {
  return messages.map((message) =>
    message.id === streamingMessageId
      ? {
          ...message,
          content_text: '',
          streaming: false,
          error: CHAT_STREAM_ERROR_COPY,
          retryContent
        }
      : message
  );
}
