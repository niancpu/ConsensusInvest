import { readJsonResponse } from '../../api/errors';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

type SingleResponse<T> = {
  data: T;
};

type ListResponse<T> = {
  data: T[];
  pagination?: {
    limit?: number;
    offset?: number;
    total: number;
    has_more?: boolean;
  };
};

export type WorkflowRunListItemView = {
  workflow_run_id: string;
  ticker: string;
  status: string;
  analysis_time: string;
  workflow_config_id: string;
  created_at: string;
  completed_at?: string | null;
  judgment_id?: string | null;
  final_signal?: string | null;
  confidence?: number | null;
};

export async function listWorkflowRuns(signal?: AbortSignal): Promise<WorkflowRunListItemView[]> {
  return apiGet<ListResponse<WorkflowRunListItemView>>('/api/v1/workflow-runs?limit=20&offset=0', signal).then(
    (response) => response.data,
  );
}

export async function getWorkflowRun(workflowRunId: string, signal?: AbortSignal): Promise<WorkflowRunListItemView> {
  return apiGet<SingleResponse<WorkflowRunListItemView>>(
    `/api/v1/workflow-runs/${encodeURIComponent(workflowRunId)}`,
    signal,
  ).then((response) => response.data);
}

async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(withBase(path), {
    headers: {
      Accept: 'application/json',
    },
    signal,
  });
  return readJsonResponse<T>(response, path);
}

function withBase(path: string): string {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }
  return `${API_BASE}${path}`;
}
