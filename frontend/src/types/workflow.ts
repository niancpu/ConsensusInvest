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
  failure_code?: string | null;
  failure_message?: string | null;
};

export type WorkflowRunListItemView = {
  workflow_run_id: string;
  ticker: string;
  status: WorkflowStatus;
  analysis_time: string;
  workflow_config_id: string;
  created_at: string;
  completed_at?: string | null;
  judgment_id?: string | null;
  final_signal?: string | null;
  confidence?: number | null;
};

export type WorkflowEvent = {
  event_id: string;
  workflow_run_id: string;
  sequence: number;
  event_type: string;
  created_at: string;
  payload: Record<string, unknown>;
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

export type WorkflowSnapshot = {
  workflow_run: {
    workflow_run_id: string;
    ticker: string;
    status: WorkflowStatus;
    stage: WorkflowStage;
    failure_code?: string | null;
    failure_message?: string | null;
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
