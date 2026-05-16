import { useEffect, useRef } from 'react';
import { eventStreamUrl } from '../api/workflow';
import type { WorkflowEvent } from '../types/workflow';

export type WorkflowStreamHandlers = {
  onMessage: (event: WorkflowEvent) => void;
  onClose?: () => void;
  onOpen?: () => void;
  onReplaying?: () => void;
  onError?: (reason: string) => void;
  onParseError?: () => void;
};

const STREAM_EVENT_TYPES = [
  'snapshot',
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
];

const TERMINAL_EVENT_TYPES = new Set(['workflow_completed', 'workflow_failed']);

export function useWorkflowStream(workflowRunId: string, handlers: WorkflowStreamHandlers): void {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    if (!workflowRunId) {
      return undefined;
    }

    handlersRef.current.onReplaying?.();
    const source = new EventSource(eventStreamUrl(workflowRunId, 0));
    const listener = (message: MessageEvent) => {
      try {
        const parsed = JSON.parse(message.data) as WorkflowEvent;
        handlersRef.current.onMessage(parsed);
        if (TERMINAL_EVENT_TYPES.has(parsed.event_type)) {
          source.close();
          handlersRef.current.onClose?.();
        }
      } catch {
        handlersRef.current.onParseError?.();
      }
    };

    source.onopen = () => handlersRef.current.onOpen?.();
    source.onmessage = listener;
    source.onerror = () => {
      source.close();
      handlersRef.current.onError?.(
        'Workflow 事件流连接失败：页面无法继续接收实时运行日志，请点击“刷新快照”查看最新状态。',
      );
    };

    STREAM_EVENT_TYPES.forEach((eventType) => {
      source.addEventListener(eventType, listener);
    });

    return () => {
      STREAM_EVENT_TYPES.forEach((eventType) => {
        source.removeEventListener(eventType, listener);
      });
      source.close();
    };
  }, [workflowRunId]);
}
