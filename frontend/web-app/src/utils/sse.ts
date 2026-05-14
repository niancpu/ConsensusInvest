import { buildApiUrl } from '../api/http'
import type { WorkflowEvent } from '../types/workflow'

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
