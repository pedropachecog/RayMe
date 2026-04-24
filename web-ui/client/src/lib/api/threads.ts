import { apiFetch } from './client';
import type {
  CreateThreadRequest,
  CreateThreadResponse,
  DeleteThreadResponse,
  ListResponse,
  RenameThreadRequest,
  RenameThreadResponse,
  ThreadDetail,
  ThreadSummary
} from './types';

export async function listThreads(): Promise<ThreadSummary[]> {
  const response = await apiFetch<ListResponse<ThreadSummary> | ThreadSummary[]>('/threads', {
    method: 'GET'
  });
  return Array.isArray(response) ? response : response.items;
}

export function getThread(threadId: string): Promise<ThreadDetail> {
  return apiFetch<ThreadDetail>(`/threads/${encodeURIComponent(threadId)}`, { method: 'GET' });
}

export function createThread(payload: CreateThreadRequest): Promise<CreateThreadResponse> {
  return apiFetch<CreateThreadResponse>('/threads', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function renameThread(
  threadId: string,
  payload: RenameThreadRequest
): Promise<RenameThreadResponse> {
  return apiFetch<RenameThreadResponse>(`/threads/${encodeURIComponent(threadId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  });
}

export function deleteThread(threadId: string): Promise<DeleteThreadResponse> {
  return apiFetch<DeleteThreadResponse>(`/threads/${encodeURIComponent(threadId)}`, {
    method: 'DELETE'
  });
}
