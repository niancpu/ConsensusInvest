export interface ApiMeta {
  request_id: string
}

export interface ApiErrorPayload {
  code: string
  message: string
  details?: Record<string, unknown>
}

export interface Pagination {
  limit: number
  offset: number
  total: number
  has_more: boolean
}

export interface ApiSuccessEnvelope<T> {
  data: T
  meta: ApiMeta
}

export interface ApiListEnvelope<T> {
  data: T[]
  pagination: Pagination
  meta: ApiMeta
}

export interface ApiErrorEnvelope {
  error: ApiErrorPayload
  meta: ApiMeta
}
