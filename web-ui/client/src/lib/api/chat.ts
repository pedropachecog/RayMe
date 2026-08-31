import { apiFetch, responseGenerationError, toApiPath } from './client';
import { readChatStream, type ChatStreamHandlers } from './stream';
import type {
  GenerationFailure,
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

export const REFUSAL_EXHAUSTED_COPY =
  'The model stayed out of character after three attempts. Try again or inspect the prompt.';

export const PROMPT_BUDGET_EXCEEDED_COPY =
  'This request does not fit the configured context. Raise the context limit or reduce prompt/history content, then try again.';

export const INVALID_MODEL_PROFILE_COPY =
  'The selected model profile could not build this request. Check Prompt & Generation settings.';

export type GenerationFailureActionIntent =
  | 'try_again'
  | 'open_settings'
  | 'inspect_prompt';

export interface GenerationFailurePresentation {
  message: string;
  actions: GenerationFailureActionIntent[];
}

export interface RetryStatusController {
  schedule(characterName: string, attempt: number): void;
  clear(): void;
  dispose(): void;
}

export type MessageActionId = 'regenerate' | 'swipe' | 'edit' | 'continue';

export interface MessageActionDescriptor {
  id: MessageActionId;
  label: string;
}

export const AI_MESSAGE_ACTIONS: MessageActionDescriptor[] = [
  { id: 'regenerate', label: 'Redo and Replace' },
  { id: 'swipe', label: 'Redo' },
  { id: 'edit', label: 'Edit' },
  { id: 'continue', label: 'Continue' }
];

export const USER_MESSAGE_ACTIONS: MessageActionDescriptor[] = [{ id: 'edit', label: 'Edit' }];

export interface ChatMessageView extends ThreadMessage {
  streaming?: boolean;
  error?: string | null;
  retryContent?: string | null;
  retryStatus?: string | null;
  failure?: GenerationFailure | null;
  failureActions?: GenerationFailureActionIntent[];
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
  retryStatus?: string | null;
  failure?: GenerationFailure | null;
  failureActions?: GenerationFailureActionIntent[];
}

export function generationFailurePresentation(
  failure: GenerationFailure
): GenerationFailurePresentation {
  if (failure.code === 'llm_refusal_exhausted') {
    return {
      message: REFUSAL_EXHAUSTED_COPY,
      actions: ['try_again', 'inspect_prompt']
    };
  }

  if (failure.code === 'prompt_budget_exceeded') {
    return {
      message: PROMPT_BUDGET_EXCEEDED_COPY,
      actions: ['open_settings', 'inspect_prompt']
    };
  }

  if (
    failure.code === 'provider_evidence_mismatch' ||
    failure.code === 'invalid_model_profile' ||
    failure.code === 'invalid_generation_request'
  ) {
    return {
      message: INVALID_MODEL_PROFILE_COPY,
      actions: ['open_settings']
    };
  }

  return { message: CHAT_STREAM_ERROR_COPY, actions: ['try_again'] };
}

export function createRetryStatusController(
  onStatus: (status: string | null) => void
): RetryStatusController {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let visible = false;
  let disposed = false;

  function clear() {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    if (visible) {
      visible = false;
      onStatus(null);
    }
  }

  return {
    schedule(characterName, attempt) {
      if (disposed) {
        return;
      }
      clear();
      timer = setTimeout(() => {
        timer = null;
        if (disposed) {
          return;
        }
        visible = true;
        onStatus(`Keeping ${characterName} in character — attempt ${attempt} of 3…`);
      }, 300);
    },
    clear,
    dispose() {
      clear();
      disposed = true;
    }
  };
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
  handlers: ChatStreamHandlers,
  options: { signal?: AbortSignal } = {}
): Promise<void> {
  const response = await fetch(toApiPath(`/chat/${encodeURIComponent(threadId)}/send`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal: options.signal,
    body: JSON.stringify({ content })
  });

  if (!response.ok) {
    throw await responseGenerationError(response);
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
    return {
      ...backendMessage,
      streaming: false,
      error: null,
      retryContent: null,
      retryStatus: null,
      failure: null,
      failureActions: []
    };
  });

  if (!replaced) {
    nextMessages.push({
      ...backendMessage,
      streaming: false,
      error: null,
      retryContent: null,
      retryStatus: null,
      failure: null,
      failureActions: []
    });
  }

  return nextMessages.sort((left, right) => left.sequence - right.sequence);
}

export function applyEditedBackendMessage(
  messages: ChatMessageView[],
  editedMessage: ThreadMessage
): ChatMessageView[] {
  const updatedMessages = upsertBackendMessage(messages, editedMessage);

  if (editedMessage.role !== 'user') {
    return updatedMessages;
  }

  return updatedMessages.map((message) =>
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
    retryContent: options.retryContent ?? null,
    retryStatus: options.retryStatus ?? null,
    failure: options.failure ?? null,
    failureActions: options.failureActions ?? []
  };
}

export function appendTokenToStreamingMessage(
  messages: ChatMessageView[],
  streamingMessageId: string,
  token: string
): ChatMessageView[] {
  return messages.map((message) =>
    message.id === streamingMessageId
      ? {
          ...message,
          content_text: `${message.content_text ?? ''}${token}`,
          retryStatus: null
        }
      : message
  );
}

export function replaceStreamingMessage(
  messages: ChatMessageView[],
  streamingMessageId: string,
  doneMessage: ThreadMessage
): ChatMessageView[] {
  return messages.map((message) =>
    message.id === streamingMessageId
      ? {
          ...doneMessage,
          streaming: false,
          error: null,
          retryStatus: null,
          failure: null,
          failureActions: []
        }
      : message
  );
}

export function markStreamingMessageError(
  messages: ChatMessageView[],
  streamingMessageId: string,
  retryContent: string,
  failure: GenerationFailure = {
    type: 'generation_failure',
    code: 'llm_generation_failed'
  }
): ChatMessageView[] {
  const presentation = generationFailurePresentation(failure);
  return messages.map((message) =>
    message.id === streamingMessageId
      ? {
          ...message,
          role: message.content_text ? message.role : 'event',
          content_text: message.content_text ?? '',
          streaming: false,
          error: presentation.message,
          retryContent,
          retryStatus: null,
          failure,
          failureActions: presentation.actions
        }
      : message
  );
}
