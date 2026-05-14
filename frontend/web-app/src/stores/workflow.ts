import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchWorkflowRun, fetchWorkflowSnapshot } from '../api/workflow'
import { createWorkflowEventSource, parseWorkflowEvent } from '../utils/sse'
import type { WorkflowEvent, WorkflowRunDetail, WorkflowSnapshot } from '../types/workflow'

export const useWorkflowStore = defineStore('workflow', () => {
  const workflowRun = ref<WorkflowRunDetail | null>(null)
  const snapshot = ref<WorkflowSnapshot | null>(null)
  const events = ref<WorkflowEvent[]>([])
  const isStreaming = ref(false)
  const streamError = ref<string | null>(null)
  const lastSequence = ref<number | undefined>(undefined)
  let eventSource: EventSource | null = null

  function mergeEvent(nextEvent: WorkflowEvent) {
    if (events.value.some((item) => item.sequence === nextEvent.sequence)) {
      return
    }

    events.value = [...events.value, nextEvent].sort((a, b) => a.sequence - b.sequence)
    lastSequence.value = Math.max(lastSequence.value ?? 0, nextEvent.sequence)

    if (nextEvent.event_type === 'workflow_started' || nextEvent.event_type === 'workflow_completed' || nextEvent.event_type === 'workflow_failed') {
      void loadWorkflowRun(nextEvent.workflow_run_id)
    }
  }

  async function loadWorkflowRun(workflowRunId: string) {
    workflowRun.value = await fetchWorkflowRun(workflowRunId)
    return workflowRun.value
  }

  async function loadSnapshot(workflowRunId: string) {
    const nextSnapshot = await fetchWorkflowSnapshot(workflowRunId)
    snapshot.value = nextSnapshot
    if ((lastSequence.value ?? 0) <= nextSnapshot.last_event_sequence) {
      lastSequence.value = nextSnapshot.last_event_sequence
    }
    workflowRun.value = nextSnapshot.workflow_run
    return nextSnapshot
  }

  function disconnect() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    isStreaming.value = false
  }

  function connect(workflowRunId: string) {
    disconnect()
    streamError.value = null
    eventSource = createWorkflowEventSource(workflowRunId, lastSequence.value)
    isStreaming.value = true

    eventSource.onmessage = (event) => {
      mergeEvent(parseWorkflowEvent(event))
    }

    eventSource.onerror = () => {
      streamError.value = 'Live event stream disconnected. Reload snapshot to recover state.'
      isStreaming.value = false
    }
  }

  function reset() {
    disconnect()
    workflowRun.value = null
    snapshot.value = null
    events.value = []
    streamError.value = null
    lastSequence.value = undefined
  }

  return {
    workflowRun,
    snapshot,
    events,
    isStreaming,
    streamError,
    lastSequence,
    connect,
    disconnect,
    loadWorkflowRun,
    loadSnapshot,
    reset,
  }
})
