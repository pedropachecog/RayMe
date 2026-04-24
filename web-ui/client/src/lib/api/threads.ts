import { apiFetch } from './client';
import type { CreateThreadRequest, CreateThreadResponse, ThreadDetail, ThreadSummary } from './types';

export function listThreads(): Promise<ThreadSummary[]> {
  return apiFetch<ThreadSummary[]>('/threads', { method: 'GET' });
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
