import { getJson, postJson } from './http'
import type {
  AgentArgument,
  Judgment,
  JudgmentReference,
  JudgeToolCall,
  RoundSummary,
  WorkflowConfig,
  WorkflowRunCreateRequest,
  WorkflowRunCreateResponse,
  WorkflowRunDetail,
  WorkflowRunListResponse,
  WorkflowSnapshot,
  WorkflowTrace,
  EvidenceItem,
} from '../types/workflow'

export function fetchWorkflowConfigs() {
  return getJson<WorkflowConfig[]>('/api/v1/workflow-configs')
}

export function createWorkflowRun(payload: WorkflowRunCreateRequest) {
  return postJson<WorkflowRunCreateResponse, WorkflowRunCreateRequest>('/api/v1/workflow-runs', payload)
}

export function fetchWorkflowRuns(cursor?: string) {
  return getJson<WorkflowRunListResponse>('/api/v1/workflow-runs', { cursor })
}

export function fetchWorkflowRun(workflowRunId: string) {
  return getJson<WorkflowRunDetail>(`/api/v1/workflow-runs/${workflowRunId}`)
}

export function fetchWorkflowSnapshot(workflowRunId: string) {
  return getJson<WorkflowSnapshot>(`/api/v1/workflow-runs/${workflowRunId}/snapshot`)
}

export function fetchWorkflowTrace(workflowRunId: string) {
  return getJson<WorkflowTrace>(`/api/v1/workflow-runs/${workflowRunId}/trace`)
}

export function fetchWorkflowJudgment(workflowRunId: string) {
  return getJson<Judgment>(`/api/v1/workflow-runs/${workflowRunId}/judgment`)
}

export function fetchWorkflowEvidence(workflowRunId: string) {
  return getJson<EvidenceItem[]>(`/api/v1/workflow-runs/${workflowRunId}/evidence`)
}

export function fetchEvidence(evidenceId: string) {
  return getJson<EvidenceItem>(`/api/v1/evidence/${evidenceId}`)
}

export function fetchWorkflowAgentArguments(workflowRunId: string) {
  return getJson<AgentArgument[]>(`/api/v1/workflow-runs/${workflowRunId}/agent-arguments`)
}

export function fetchAgentArgument(agentArgumentId: string) {
  return getJson<AgentArgument>(`/api/v1/agent-arguments/${agentArgumentId}`)
}

export function fetchWorkflowRoundSummaries(workflowRunId: string) {
  return getJson<RoundSummary[]>(`/api/v1/workflow-runs/${workflowRunId}/round-summaries`)
}

export function fetchJudgmentReferences(judgmentId: string) {
  return getJson<JudgmentReference[]>(`/api/v1/judgments/${judgmentId}/references`)
}

export function fetchJudgmentToolCalls(judgmentId: string) {
  return getJson<JudgeToolCall[]>(`/api/v1/judgments/${judgmentId}/tool-calls`)
}
