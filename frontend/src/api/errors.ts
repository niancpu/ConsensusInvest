export const API_TIMEOUT_REASON = 'timeout';

export type ApiErrorBody = {
  code?: string;
  message?: string;
  details?: Record<string, unknown>;
};

export const API_TIMEOUT_CODE = 'TIMEOUT';

export class ApiRequestError extends Error {
  readonly status: number;
  readonly path: string;
  readonly code?: string;
  readonly details?: Record<string, unknown>;

  constructor({
    status,
    path,
    code,
    message,
    details,
  }: {
    status: number;
    path: string;
    code?: string;
    message: string;
    details?: Record<string, unknown>;
  }) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.path = path;
    this.code = code;
    this.details = details;
  }
}

export async function readJsonResponse<T>(response: Response, path: string): Promise<T> {
  const text = await response.text();
  const payload = parseJson(text);
  if (!response.ok) {
    const error = payload?.error as ApiErrorBody | undefined;
    const message = error?.message || text.trim() || response.statusText || `HTTP ${response.status}`;
    throw new ApiRequestError({
      status: response.status,
      path,
      code: error?.code,
      message,
      details: error?.details,
    });
  }
  return payload as T;
}

export function formatApiError(error: unknown, fallback: string): string {
  if (error instanceof ApiRequestError) {
    if (error.code === API_TIMEOUT_CODE) {
      return `${fallback}：加载 10 秒仍无结果，请稍后重试`;
    }
    const code = error.code ? `，错误码：${error.code}` : '';
    return `${fallback}（${error.path}，HTTP ${error.status}${code}）：${error.message}`;
  }
  if (error instanceof Error) {
    return `${fallback}：${error.message}`;
  }
  return fallback;
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

export function isTimeoutError(error: unknown): boolean {
  return error instanceof ApiRequestError && error.code === API_TIMEOUT_CODE;
}

export function toApiError(error: unknown, path: string, reason?: unknown): unknown {
  if (!isAbortError(error)) {
    return error;
  }

  if (reason !== API_TIMEOUT_REASON) {
    return error;
  }

  return new ApiRequestError({
    status: 408,
    path,
    code: API_TIMEOUT_CODE,
    message: '请求超时',
  });
}

export function mergeAbortSignals(...signals: Array<AbortSignal | undefined>): AbortSignal | undefined {
  const activeSignals = signals.filter((signal): signal is AbortSignal => Boolean(signal));
  if (activeSignals.length === 0) {
    return undefined;
  }
  if (activeSignals.length === 1) {
    return activeSignals[0];
  }

  const controller = new AbortController();
  const cleanup = new Map<AbortSignal, () => void>();

  const abortFrom = (signal: AbortSignal) => {
    for (const [currentSignal, listener] of cleanup) {
      currentSignal.removeEventListener('abort', listener);
    }
    cleanup.clear();
    controller.abort(signal.reason);
  };

  for (const signal of activeSignals) {
    if (signal.aborted) {
      abortFrom(signal);
      return controller.signal;
    }
    const listener = () => abortFrom(signal);
    cleanup.set(signal, listener);
    signal.addEventListener('abort', listener, { once: true });
  }

  return controller.signal;
}

function parseJson(text: string): any {
  if (!text.trim()) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}
