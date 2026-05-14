export type WorkflowStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

export type WorkflowStage =
  | 'queued'
  | 'collecting_raw_items'
  | 'normalizing_evidence'
  | 'structuring_evidence'
  | 'debate'
  | 'round_summary'
  | 'judge'
  | 'completed'
  | 'failed'

export type ReferenceRole = 'supports' | 'counters' | 'cited' | 'refuted'

export interface WorkflowConfigAgent {
  agent_id: string
  role: string
  stance_label: string
  thesis_label: string
  stance_output_key: string
  impact_output_key: string
  limitation: string
}

export interface WorkflowConfig {
  workflow_config_id: string
  name?: string
  description?: string
  collectors?: string[]
  agents: WorkflowConfigAgent[]
  debate_rounds: number
  enabled?: boolean
}

export interface WorkflowRunSummary {
  workflow_run_id: string
  ticker: string
  status: WorkflowStatus
  stage?: WorkflowStage
  analysis_time: string
  workflow_config_id: string
  created_at: string
  completed_at?: string | null
  judgment_id?: string
  final_signal?: string
  confidence?: number
}

export interface WorkflowRunDetail extends WorkflowRunSummary {
  started_at?: string | null
  progress?: {
    raw_items_collected?: number
    evidence_items_normalized?: number
    evidence_items_structured?: number
    agent_arguments_completed?: number
  }
  links?: {
    events?: string
    snapshot?: string
    trace?: string
    evidence?: string
    judgment?: string
  }
}

export interface WorkflowRunCreateRequest {
  ticker: string
  analysis_time: string
  workflow_config_id: string
  query?: {
    lookback_days?: number
    sources?: string[]
  }
  options?: {
    stream?: boolean
    include_raw_payload?: boolean
    auto_run?: boolean
  }
}

export interface WorkflowRunCreateResponse {
  workflow_run_id: string
  status: WorkflowStatus
  ticker: string
  analysis_time: string
  workflow_config_id: string
  created_at: string
  events_url: string
  snapshot_url: string
}

export interface WorkflowEvent {
  event_id: string
  workflow_run_id: string
  sequence: number
  event_type: string
  created_at: string
  payload: Record<string, unknown>
}

export interface EvidenceItem {
  evidence_id: string
  workflow_run_id?: string
  ticker?: string
  source: string
  source_type: string
  evidence_type?: string
  title: string
  objective_summary: string
  publish_time?: string | null
  fetched_at?: string
  source_quality?: number
  relevance?: number
  freshness?: number
  structuring_confidence?: number
  quality_notes?: string[]
  raw_ref?: string
  created_at?: string
  updated_at?: string
}

export interface AgentArgument {
  agent_argument_id: string
  agent_run_id: string
  workflow_run_id: string
  agent_id: string
  role: string
  round: number
  argument: string
  confidence: number
  referenced_evidence_ids: string[]
  counter_evidence_ids: string[]
  limitations: string[]
  role_output?: Record<string, unknown>
  created_at: string
  updated_at?: string
}

export interface RoundSummary {
  round_summary_id: string
  workflow_run_id: string
  round: number
  summary: string
  participants: string[]
  agent_argument_ids: string[]
  referenced_evidence_ids: string[]
  disputed_evidence_ids: string[]
  created_at: string
}

export interface Judgment {
  judgment_id: string
  workflow_run_id: string
  final_signal: string
  confidence: number
  time_horizon?: string
  key_positive_evidence_ids: string[]
  key_negative_evidence_ids: string[]
  reasoning: string
  risk_notes: string[]
  suggested_next_checks: string[]
  referenced_agent_argument_ids: string[]
  tool_call_count: number
  created_at: string
  links?: {
    references?: string
    trace?: string
  }
}

export interface JudgmentReference {
  reference_id: string
  source_type: string
  source_id: string
  evidence_id: string
  reference_role: ReferenceRole
  round: number | null
}

export interface JudgeToolCall {
  tool_call_id?: string
  judgment_id: string
  tool_name: string
  input: Record<string, unknown>
  output_summary: string
  referenced_evidence_ids?: string[]
  affected_fields?: string[]
  created_at: string
}

export interface TraceNode {
  node_type: string
  node_id: string
  title: string
  summary: string
}

export interface TraceEdge {
  from_node_id: string
  to_node_id: string
  edge_type: string
}

export interface WorkflowTrace {
  workflow_run_id: string
  judgment_id?: string
  trace_nodes: TraceNode[]
  trace_edges: TraceEdge[]
}

export interface WorkflowSnapshot {
  workflow_run: WorkflowRunDetail
  evidence_items: EvidenceItem[]
  agent_runs: Array<Record<string, unknown>>
  agent_arguments: AgentArgument[]
  round_summaries: RoundSummary[]
  judgment: Judgment | null
  last_event_sequence: number
}

export interface Entity {
  entity_id: string
  entity_type: string
  name: string
  aliases?: string[]
  description?: string
}
