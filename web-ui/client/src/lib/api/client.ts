export interface ApiFetchOptions extends RequestInit {
  apiPrefix?: string;
}

const ABSOLUTE_HTTP_URL = /^https?:\/\//i;

export function toApiPath(path: string, apiPrefix = '/api'): string {
  if (ABSOLUTE_HTTP_URL.test(path)) {
    throw new Error('Client API requests must use RayMe backend routes, not absolute provider URLs.');
  }

  if (path.startsWith('/api/')) {
    return path;
  }

  if (path === '/api') {
    return path;
  }

  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const normalizedPrefix = apiPrefix.endsWith('/') ? apiPrefix.slice(0, -1) : apiPrefix;
  return `${normalizedPrefix}${normalizedPath}`;
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { apiPrefix, headers, body, ...requestOptions } = options;
  const initHeaders = new Headers(headers);
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;

  if (body !== undefined && !isFormData && !initHeaders.has('Content-Type')) {
    initHeaders.set('Content-Type', 'application/json');
  }

  const response = await fetch(toApiPath(path, apiPrefix), {
    ...requestOptions,
    headers: initHeaders,
    body
  });

  if (!response.ok) {
    throw new Error(`RayMe API request failed: ${response.status} ${response.statusText}`.trim());
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
