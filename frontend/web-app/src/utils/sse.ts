import { buildApiUrl } from '../api/http'
import type { WorkflowEvent } from '../types/workflow'

export const workflowSseEventTypes = [
  'workflow_queued',
  'workflow_started',
  'connector_started',
  'connector_progress',
  'raw_item_collected',
  'evidence_normalized',
  'evidence_structuring_started',
  'evidence_structured',
  'agent_run_started',
  'agent_argument_delta',
  'agent_argument_completed',
  'round_summary_delta',
  'round_summary_completed',
  'judge_started',
  'judge_tool_call_started',
  'judge_tool_call_completed',
  'judgment_delta',
  'judgment_completed',
  'workflow_completed',
  'workflow_failed',
  'snapshot',
] as const

export function createWorkflowEventSource(workflowRunId: string, afterSequence?: number) {
  return new EventSource(
    buildApiUrl(`/api/v1/workflow-runs/${workflowRunId}/events`, {
      include_snapshot: false,
      after_sequence: afterSequence,
    }),
  )
}

export function parseWorkflowEvent(event: MessageEvent<string>): WorkflowEvent {
  return JSON.parse(event.data) as WorkflowEvent
}
