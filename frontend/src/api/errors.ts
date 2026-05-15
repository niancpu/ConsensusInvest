export type ApiErrorBody = {
  code?: string;
  message?: string;
  details?: Record<string, unknown>;
};

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
    const code = error.code ? `，错误码：${error.code}` : '';
    return `${fallback}（${error.path}，HTTP ${error.status}${code}）：${error.message}`;
  }
  if (error instanceof Error) {
    return `${fallback}：${error.message}`;
  }
  return fallback;
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
