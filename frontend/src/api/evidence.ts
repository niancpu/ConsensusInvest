import { apiGet, type SingleResponse } from './http';
import type { AgentArgument, RoundSummary } from '../types/workflow';
import type { EvidenceDetail, RawItemDetail } from '../types/evidence';

export async function getEvidence(evidenceId: string, signal?: AbortSignal): Promise<EvidenceDetail> {
  return apiGet<SingleResponse<EvidenceDetail>>(
    `/api/v1/evidence/${encodeURIComponent(evidenceId)}`,
    signal,
  ).then((response) => response.data);
}

export async function getRawItem(rawRef: string, signal?: AbortSignal): Promise<RawItemDetail> {
  return apiGet<SingleResponse<RawItemDetail>>(
    `/api/v1/raw-items/${encodeURIComponent(rawRef)}`,
    signal,
  ).then((response) => response.data);
}

export async function getAgentArgument(agentArgumentId: string, signal?: AbortSignal): Promise<AgentArgument> {
  return apiGet<SingleResponse<AgentArgument>>(
    `/api/v1/agent-arguments/${encodeURIComponent(agentArgumentId)}`,
    signal,
  ).then((response) => response.data);
}

export async function getRoundSummary(roundSummaryId: string, signal?: AbortSignal): Promise<RoundSummary> {
  return apiGet<SingleResponse<RoundSummary>>(
    `/api/v1/round-summaries/${encodeURIComponent(roundSummaryId)}`,
    signal,
  ).then((response) => response.data);
}
