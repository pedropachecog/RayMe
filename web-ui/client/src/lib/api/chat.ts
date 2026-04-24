import { apiFetch, toApiPath } from './client';
import { readChatStream, type ChatStreamHandlers } from './stream';
import type {
  MessageAlternate,
  MessageKind,
  MessageRole,
  ThreadDetail,
  ThreadMessage
} from './types';

export const CHAT_STREAM_ERROR_COPY =
  'RayMe cannot reach the LLM endpoint. Check Settings, run Test Connection, and try again.';

export const TRUNCATE_STALE_CONFIRMATION_COPY =
  'Remove stale turns after this edit? The selected message stays and later turns are removed from this branch.';

export type MessageActionId = 'regenerate' | 'swipe' | 'edit' | 'continue';

export interface MessageActionDescriptor {
  id: MessageActionId;
  label: string;
}

export const AI_MESSAGE_ACTIONS: MessageActionDescriptor[] = [
  { id: 'regenerate', label: 'Regenerate' },
  { id: 'swipe', label: 'Generate alternate' },
  { id: 'edit', label: 'Edit' },
  { id: 'continue', label: 'Continue' }
];

export const USER_MESSAGE_ACTIONS: MessageActionDescriptor[] = [{ id: 'edit', label: 'Edit' }];

export interface ChatMessageView extends ThreadMessage {
  streaming?: boolean;
  error?: string | null;
  retryContent?: string | null;
}

interface TruncateStaleResponse {
  messages: ThreadMessage[];
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

export function regenerateMessage(messageId: string): Promise<ThreadMessage> {
  return apiFetch<ThreadMessage>(`/messages/${encodeURIComponent(messageId)}/regenerate`, {
    method: 'POST'
  });
}

export function generateSwipeAlternate(messageId: string): Promise<ThreadMessage> {
  return apiFetch<ThreadMessage>(`/messages/${encodeURIComponent(messageId)}/swipes`, {
    method: 'POST'
  });
}

export function selectSwipeAlternate(
  messageId: string,
  alternateId: string
): Promise<ThreadMessage> {
  return apiFetch<ThreadMessage>(`/messages/${encodeURIComponent(messageId)}/swipes`, {
    method: 'POST',
    body: JSON.stringify({ alternate_id: alternateId })
  });
}

export function editMessage(messageId: string, content: string): Promise<ThreadMessage> {
  return apiFetch<ThreadMessage>(`/messages/${encodeURIComponent(messageId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ content })
  });
}

export async function truncateStaleMessages(messageId: string): Promise<ThreadMessage[]> {
  const response = await apiFetch<TruncateStaleResponse>(
    `/messages/${encodeURIComponent(messageId)}/truncate-stale`,
    { method: 'POST' }
  );
  return response.messages;
}

export function keepStaleMessages(messageId: string): Promise<ThreadMessage> {
  return apiFetch<ThreadMessage>(`/messages/${encodeURIComponent(messageId)}/keep-stale`, {
    method: 'POST'
  });
}

export function continueMessage(messageId: string, composerText: string): Promise<ThreadMessage> {
  return apiFetch<ThreadMessage>(`/messages/${encodeURIComponent(messageId)}/continue`, {
    method: 'POST',
    body: JSON.stringify({ composer_text: composerText })
  });
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

export function messageActionsForRole(role: MessageRole): MessageActionDescriptor[] {
  if (role === 'assistant') {
    return AI_MESSAGE_ACTIONS;
  }

  if (role === 'user') {
    return USER_MESSAGE_ACTIONS;
  }

  return [];
}

export function sortedMessageAlternates(
  message: Pick<ThreadMessage, 'alternates'>
): MessageAlternate[] {
  return [...message.alternates].sort((left, right) => left.alternate_index - right.alternate_index);
}

export function selectedAlternateIndex(
  message: Pick<ThreadMessage, 'selected_alternate_id' | 'alternates'>
): number {
  const alternates = sortedMessageAlternates(message);
  const selectedIndex = alternates.findIndex(
    (alternate) => alternate.id === message.selected_alternate_id
  );
  return selectedIndex >= 0 ? selectedIndex : 0;
}

export function upsertBackendMessage(
  messages: ChatMessageView[],
  backendMessage: ThreadMessage
): ChatMessageView[] {
  let replaced = false;
  const nextMessages = messages.map((message) => {
    if (message.id !== backendMessage.id) {
      return message;
    }

    replaced = true;
    return { ...backendMessage, streaming: false, error: null, retryContent: null };
  });

  if (!replaced) {
    nextMessages.push({ ...backendMessage, streaming: false, error: null, retryContent: null });
  }

  return nextMessages.sort((left, right) => left.sequence - right.sequence);
}

export function applyEditedBackendMessage(
  messages: ChatMessageView[],
  editedMessage: ThreadMessage
): ChatMessageView[] {
  return upsertBackendMessage(messages, editedMessage).map((message) =>
    message.thread_id === editedMessage.thread_id && message.sequence > editedMessage.sequence
      ? { ...message, stale_after_edit: true }
      : message
  );
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
