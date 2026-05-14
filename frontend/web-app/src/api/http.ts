import type { ApiErrorEnvelope } from '../types/api-envelope'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  code: string
  details?: Record<string, unknown>
  status: number

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

function buildUrl(path: string, params?: Record<string, string | number | boolean | undefined>) {
  const url = new URL(path, API_BASE_URL || window.location.origin)

  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === '') {
        continue
      }
      url.searchParams.set(key, String(value))
    }
  }

  return url
}

async function parseJson(response: Response): Promise<unknown> {
  return response.json()
}

async function request<T>(path: string, init?: RequestInit, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const response = await fetch(buildUrl(path, params), {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  const body = (await parseJson(response)) as { data?: T; error?: ApiErrorEnvelope['error'] }

  if (!response.ok || body.error) {
    const error = body.error ?? { code: 'INTERNAL_ERROR', message: 'Request failed.' }
    throw new ApiError(response.status, error.code, error.message, error.details)
  }

  if (body.data === undefined) {
    throw new ApiError(response.status, 'INTERNAL_ERROR', 'Response did not include data.')
  }

  return body.data
}

export function getJson<T>(path: string, params?: Record<string, string | number | boolean | undefined>) {
  return request<T>(path, { method: 'GET' }, params)
}

export function postJson<TResponse, TRequest>(path: string, payload: TRequest) {
  return request<TResponse>(path, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function buildApiUrl(path: string, params?: Record<string, string | number | boolean | undefined>) {
  return buildUrl(path, params).toString()
}
