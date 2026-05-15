import { readJsonResponse } from '../../api/errors';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

export type SingleResponse<T> = {
  data: T;
  meta?: {
    request_id?: string;
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
  };
};

export type WorkflowConfig = {
  workflow_config_id: string;
  debate_rounds: number;
  agents: Array<{
    agent_id: string;
    role: string;
    stance_label?: string | null;
    thesis_label?: string | null;
  }>;
};

export type WorkflowRunCreateView = {
  workflow_run_id: string;
  status: WorkflowStatus;
  ticker: string;
  analysis_time: string;
  workflow_config_id: string;
  created_at: string;
  events_url: string;
  snapshot_url: string;
};

export type WorkflowStatus =
  | 'queued'
  | 'running'
  | 'waiting'
  | 'partial_completed'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | string;

export type WorkflowStage =
  | 'queued'
  | 'collecting_raw_items'
  | 'normalizing_evidence'
  | 'structuring_evidence'
  | 'evidence_selection'
  | 'debate'
  | 'round_summary'
  | 'judge'
  | 'completed'
  | 'failed'
  | string;

export type WorkflowSnapshot = {
  workflow_run: {
    workflow_run_id: string;
    ticker: string;
    status: WorkflowStatus;
    stage: WorkflowStage;
  };
  evidence_items: EvidenceSnapshot[];
  agent_runs: AgentRun[];
  agent_arguments: AgentArgument[];
  round_summaries: RoundSummary[];
  judgment: Judgment | null;
  judge_tool_calls: JudgeToolCall[];
  last_event_sequence: number;
  events?: WorkflowEvent[];
};

export type WorkflowEvent = {
  event_id: string;
  workflow_run_id: string;
  sequence: number;
  event_type: string;
  created_at: string;
  payload: Record<string, unknown>;
};

export type TraceNodeType = 'judgment' | 'agent_argument' | 'evidence' | 'raw_item' | 'round_summary';

export type WorkflowTrace = {
  workflow_run_id: string;
  judgment_id?: string | null;
  trace_nodes: Array<{
    node_type: TraceNodeType;
    node_id: string;
    title: string;
    summary: string;
  }>;
  trace_edges: Array<{
    from_node_id: string;
    to_node_id: string;
    edge_type: string;
  }>;
};

export type EvidenceSnapshot = {
  evidence_id: string;
  raw_ref: string;
  ticker?: string | null;
  source?: string | null;
  source_type?: string | null;
  evidence_type?: string | null;
  title?: string | null;
  content?: string | null;
  url?: string | null;
  publish_time?: string | null;
  fetched_at?: string | null;
  source_quality?: number | null;
  relevance?: number | null;
  freshness?: number | null;
};

export type EvidenceDetail = EvidenceSnapshot & {
  workflow_run_id?: string | null;
  objective_summary?: string | null;
  entities: string[];
  tags: string[];
  key_facts: Array<Record<string, unknown>>;
  claims: Array<Record<string, unknown>>;
  structuring_confidence?: number | null;
  quality_notes: string[];
  links: {
    structure: string;
    raw: string;
    references: string;
  };
};

export type RawItemDetail = {
  raw_ref: string;
  workflow_run_id?: string | null;
  source?: string | null;
  source_type?: string | null;
  ticker?: string | null;
  title?: string | null;
  content?: string | null;
  url?: string | null;
  publish_time?: string | null;
  fetched_at?: string | null;
  raw_payload: Record<string, unknown>;
  derived_evidence_ids: string[];
};

export type AgentRun = {
  agent_run_id: string;
  workflow_run_id: string;
  agent_id: string;
  role: string;
  status: string;
  started_at: string;
  completed_at?: string | null;
  rounds: number[];
};

export type AgentArgument = {
  agent_argument_id: string;
  agent_run_id: string;
  workflow_run_id: string;
  agent_id: string;
  role: string;
  round: number;
  argument: string;
  confidence: number;
  referenced_evidence_ids: string[];
  counter_evidence_ids: string[];
  limitations: string[];
  role_output: Record<string, unknown>;
  created_at?: string | null;
};

export type RoundSummary = {
  round_summary_id: string;
  workflow_run_id: string;
  round: number;
  summary: string;
  participants: string[];
  agent_argument_ids: string[];
  referenced_evidence_ids: string[];
  disputed_evidence_ids: string[];
  created_at?: string | null;
};

export type Judgment = {
  judgment_id: string;
  workflow_run_id: string;
  final_signal: string;
  confidence: number;
  time_horizon: string;
  key_positive_evidence_ids: string[];
  key_negative_evidence_ids: string[];
  reasoning: string;
  risk_notes: string[];
  suggested_next_checks: string[];
  referenced_agent_argument_ids: string[];
  limitations?: string[];
  tool_call_count?: number;
  created_at?: string | null;
};

export type JudgeToolCall = {
  tool_call_id: string;
  judgment_id: string;
  tool_name: string;
  input: Record<string, unknown>;
  output_summary: string;
  referenced_evidence_ids: string[];
  created_at?: string | null;
};

export type CreateWorkflowRequest = {
  ticker: string;
  workflow_config_id: string;
  analysis_time?: string;
  sources?: string[];
  evidence_types?: string[];
};

export async function listWorkflowConfigs(signal?: AbortSignal): Promise<WorkflowConfig[]> {
  return apiGet<ListResponse<WorkflowConfig>>('/api/v1/workflow-configs', signal).then((response) => response.data);
}

export async function createWorkflowRun(request: CreateWorkflowRequest): Promise<WorkflowRunCreateView> {
  const body = {
    ticker: request.ticker.trim(),
    stock_code: request.ticker.trim(),
    analysis_time: request.analysis_time ?? new Date().toISOString(),
    workflow_config_id: request.workflow_config_id,
    query: {
      lookback_days: 30,
      sources: request.sources ?? ['akshare', 'tushare', 'tavily', 'exa'],
      evidence_types: request.evidence_types ?? ['financial_report', 'company_news', 'industry_news'],
      max_results: 50,
    },
    options: {
      stream: true,
      include_raw_payload: false,
      auto_run: true,
    },
  };

  return apiPost<SingleResponse<WorkflowRunCreateView>>('/api/v1/workflow-runs', body).then((response) => response.data);
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

export function eventStreamUrl(workflowRunId: string, afterSequence = 0): string {
  const params = new URLSearchParams({
    follow: 'true',
  });
  if (afterSequence > 0) {
    params.set('after_sequence', String(afterSequence));
  }
  return withBase(`/api/v1/workflow-runs/${encodeURIComponent(workflowRunId)}/events?${params.toString()}`);
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

async function apiPost<T>(path: string, body: unknown): Promise<T> {
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

function withBase(path: string): string {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }
  return `${API_BASE}${path}`;
}
