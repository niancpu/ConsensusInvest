import { getJson } from './http'
import type { Entity, EvidenceItem } from '../types/workflow'

export function fetchEntity(entityId: string) {
  return getJson<Entity>(`/api/v1/entities/${entityId}`)
}

export function fetchEntityEvidence(entityId: string) {
  return getJson<EvidenceItem[]>(`/api/v1/entities/${entityId}/evidence`)
}
