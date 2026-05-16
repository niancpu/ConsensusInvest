import { apiGet, apiPost, withBase, type ListResponse, type SingleResponse } from './http';
import type {
  WorkflowConfig,
  WorkflowRunCreateView,
  WorkflowRunListItemView,
  WorkflowSnapshot,
} from '../types/workflow';
import type { WorkflowTrace } from '../types/trace';

export type CreateWorkflowRequest = {
  ticker: string;
  workflow_config_id: string;
  analysis_time?: string;
  sources?: string[];
  evidence_types?: string[];
};

export async function listWorkflowConfigs(signal?: AbortSignal): Promise<WorkflowConfig[]> {
  return apiGet<ListResponse<WorkflowConfig>>('/api/v1/workflow-configs', signal).then(
    (response) => response.data,
  );
}

export async function createWorkflowRun(request: CreateWorkflowRequest): Promise<WorkflowRunCreateView> {
  const body = {
    ticker: request.ticker.trim(),
    stock_code: request.ticker.trim(),
    analysis_time: request.analysis_time ?? new Date().toISOString(),
    workflow_config_id: request.workflow_config_id,
    query: {
      lookback_days: 30,
      sources: request.sources ?? ['tavily', 'exa', 'akshare'],
      evidence_types: request.evidence_types ?? ['financial_report', 'company_news', 'industry_news'],
      max_results: 50,
    },
    options: {
      stream: true,
      include_raw_payload: false,
      auto_run: true,
    },
  };
  return apiPost<SingleResponse<WorkflowRunCreateView>>('/api/v1/workflow-runs', body).then(
    (response) => response.data,
  );
}

export async function listWorkflowRuns(signal?: AbortSignal): Promise<WorkflowRunListItemView[]> {
  return apiGet<ListResponse<WorkflowRunListItemView>>(
    '/api/v1/workflow-runs?limit=20&offset=0',
    signal,
  ).then((response) => response.data);
}

export async function getWorkflowRun(workflowRunId: string, signal?: AbortSignal): Promise<WorkflowRunListItemView> {
  return apiGet<SingleResponse<WorkflowRunListItemView>>(
    `/api/v1/workflow-runs/${encodeURIComponent(workflowRunId)}`,
    signal,
  ).then((response) => response.data);
}

export async function getWorkflowSnapshot(
  workflowRunId: string,
  signal?: AbortSignal,
): Promise<WorkflowSnapshot> {
  return apiGet<SingleResponse<WorkflowSnapshot>>(
    `/api/v1/workflow-runs/${encodeURIComponent(workflowRunId)}/snapshot?include_events=true`,
    signal,
  ).then((response) => response.data);
}

export async function getWorkflowTrace(workflowRunId: string, signal?: AbortSignal): Promise<WorkflowTrace> {
  return apiGet<SingleResponse<WorkflowTrace>>(
    `/api/v1/workflow-runs/${encodeURIComponent(workflowRunId)}/trace`,
    signal,
  ).then((response) => response.data);
}

export function eventStreamUrl(workflowRunId: string, afterSequence = 0): string {
  const params = new URLSearchParams({ follow: 'true' });
  if (afterSequence > 0) {
    params.set('after_sequence', String(afterSequence));
  }
  return withBase(`/api/v1/workflow-runs/${encodeURIComponent(workflowRunId)}/events?${params.toString()}`);
}
