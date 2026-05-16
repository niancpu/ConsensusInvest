import { readJsonResponse } from './errors';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

export type SingleResponse<T> = {
  data: T;
  meta?: {
    request_id?: string;
    data_state?: string;
    refresh_task_id?: string | null;
    report_run_id?: string | null;
  };
};

export type ListResponse<T> = {
  data: T[];
  pagination?: {
    limit?: number;
    offset?: number;
    total: number;
    has_more?: boolean;
  };
  meta?: {
    request_id?: string;
    data_state?: string;
    refresh_task_id?: string | null;
    report_run_id?: string | null;
  };
};

export function withBase(path: string): string {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }
  return `${API_BASE}${path}`;
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(withBase(path), {
    headers: { Accept: 'application/json' },
    signal,
  });
  return readJsonResponse<T>(response, path);
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(withBase(path), {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  return readJsonResponse<T>(response, path);
}
