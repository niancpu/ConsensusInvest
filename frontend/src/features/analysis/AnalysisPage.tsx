import { FormEvent, useEffect, useMemo, useState } from 'react';
import GlobalNav from '../../components/GlobalNav';
import { formatApiError } from '../../api/errors';
import {
  createWorkflowRun,
  getWorkflowSnapshot,
  getWorkflowTrace,
  listWorkflowConfigs,
} from '../../api/workflow';
import { getAgentArgument, getEvidence, getRawItem, getRoundSummary } from '../../api/evidence';
import { useWorkflowStream } from '../../hooks/useWorkflowStream';
import type {
  WorkflowConfig,
  WorkflowEvent,
  WorkflowSnapshot,
} from '../../types/workflow';
import type { WorkflowTrace } from '../../types/trace';
import AnalysisConsole from './console/AnalysisConsole';
import TraceGraph from './graph/TraceGraph';
import TraceGraphEmptyState from './graph/TraceGraphEmptyState';
import JudgmentInspector from './inspector/JudgmentInspector';
import NodeInspector from './inspector/NodeInspector';
import TraceInspectorEmptyState from './inspector/TraceInspectorEmptyState';
import type { SelectedNode } from './inspector/types';
import { layoutTraceGraph } from './layout/traceGraph';
import { summarizeFailurePayload } from './utils/failure';
import { formatTime } from './utils/format';
import './AnalysisPage.css';

type ConnectionState = 'idle' | 'creating' | 'replaying' | 'open' | 'closed' | 'error';

type AnalysisPageProps = {
  routeTicker?: string | null;
};

function AnalysisPage({ routeTicker }: AnalysisPageProps) {
  const initialTicker = routeTicker ?? '002594';
  const [ticker, setTicker] = useState(initialTicker);
  const [configs, setConfigs] = useState<WorkflowConfig[]>([]);
  const [selectedConfigId, setSelectedConfigId] = useState('');
  const [workflowRunId, setWorkflowRunId] = useState('');
  const [snapshot, setSnapshot] = useState<WorkflowSnapshot | null>(null);
  const [trace, setTrace] = useState<WorkflowTrace | null>(null);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [connection, setConnection] = useState<ConnectionState>('idle');
  const [selectedNode, setSelectedNode] = useState<SelectedNode | null>(null);
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    listWorkflowConfigs(controller.signal)
      .then((rows) => {
        setConfigs(rows);
        setSelectedConfigId((current) => current || rows[0]?.workflow_config_id || 'mvp_bull_judge_v1');
      })
      .catch((error) => setErrorMessage(error.message));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const nextTicker = routeTicker?.trim();
    if (nextTicker) {
      setTicker(nextTicker);
    }
  }, [routeTicker]);

  useWorkflowStream(workflowRunId, {
    onReplaying: () => setConnection('replaying'),
    onOpen: () => setConnection('open'),
    onError: (message) => {
      setConnection('error');
      setErrorMessage(message);
    },
    onParseError: () => setConnection('error'),
    onMessage: (parsed) => handleStreamMessage(parsed),
  });

  const latestStatus = snapshot?.workflow_run.status ?? 'idle';
  const latestStage = snapshot?.workflow_run.stage ?? 'idle';
  const isWorkflowFailed = latestStatus === 'failed' || latestStage === 'failed';
  const hasWorkflow = Boolean(workflowRunId);
  const hasTraceNodes = !isWorkflowFailed && (trace?.trace_nodes.length ?? 0) > 0;
  const graph = useMemo(
    () => {
      if (isWorkflowFailed || !trace?.trace_nodes.length) {
        return { nodes: [], edges: [], width: 780, height: 620 };
      }
      return layoutTraceGraph(trace.trace_nodes, trace.trace_edges ?? []);
    },
    [isWorkflowFailed, trace],
  );
  const traceNodeIds = useMemo(
    () => new Set(isWorkflowFailed ? [] : (trace?.trace_nodes ?? []).map((node) => node.node_id)),
    [isWorkflowFailed, trace],
  );

  const judgment = snapshot?.judgment ?? null;
  const failureSummary = useMemo(() => {
    const snapshotFailure = snapshot?.workflow_run.failure_message;
    if (snapshotFailure) {
      return snapshotFailure;
    }
    const failedEvent = [...events].reverse().find((event) => event.event_type === 'workflow_failed');
    return failedEvent ? summarizeFailurePayload(failedEvent.payload) : '';
  }, [events, snapshot]);
  const visibleFailureMessage = isWorkflowFailed ? failureSummary || errorMessage : errorMessage;

  async function handleCreateWorkflow(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ticker.trim() || !selectedConfigId) {
      return;
    }

    setConnection('creating');
    setErrorMessage('');
    setWorkflowRunId('');
    setSnapshot(null);
    setTrace(null);
    setEvents([]);
    setSelectedNode(null);

    try {
      const created = await createWorkflowRun({
        ticker,
        workflow_config_id: selectedConfigId,
      });
      if (created.status === 'failed' && created.failure_message) {
        setErrorMessage(created.failure_message);
      }
      setWorkflowRunId(created.workflow_run_id);
      await loadWorkflowState(created.workflow_run_id, 'replace_events');
    } catch (error) {
      setConnection('error');
      setErrorMessage(formatApiError(error, '分析任务创建失败'));
    }
  }

  async function handleRefresh() {
    if (!workflowRunId) {
      return;
    }
    setErrorMessage('');
    try {
      await loadWorkflowState(workflowRunId, 'merge_events');
    } catch (error) {
      setErrorMessage(formatApiError(error, '刷新失败'));
    }
  }

  async function loadWorkflowState(runId: string, eventMode: 'replace_events' | 'merge_events') {
    let nextSnapshot: WorkflowSnapshot;
    try {
      nextSnapshot = await getWorkflowSnapshot(runId);
    } catch (error) {
      throw new Error(formatApiError(error, 'Workflow 快照加载失败'));
    }

    setSnapshot(nextSnapshot);
    if (nextSnapshot.workflow_run.status === 'failed' || nextSnapshot.workflow_run.stage === 'failed') {
      setTrace(null);
      setSelectedNode(null);
      if (nextSnapshot.workflow_run.failure_message) {
        setErrorMessage(nextSnapshot.workflow_run.failure_message);
      }
    }
    setEvents((current) => {
      const snapshotEvents = nextSnapshot.events ?? [];
      if (eventMode === 'replace_events') {
        return snapshotEvents;
      }
      const byId = new Map(current.map((item) => [item.event_id, item]));
      snapshotEvents.forEach((item) => byId.set(item.event_id, item));
      return [...byId.values()].sort((left, right) => left.sequence - right.sequence);
    });

    if (nextSnapshot.workflow_run.status === 'failed' || nextSnapshot.workflow_run.stage === 'failed') {
      return;
    }

    try {
      const nextTrace = await getWorkflowTrace(runId);
      setTrace(nextTrace);
    } catch (error) {
      setTrace(null);
      setErrorMessage(formatApiError(error, '判断溯源图加载失败'));
    }
  }

  async function handleSelectNode(nodeId: string) {
    const node = trace?.trace_nodes.find((item) => item.node_id === nodeId);
    if (!node) {
      return;
    }

    setErrorMessage('');
    const baseNode = {
      node_id: node.node_id,
      node_type: node.node_type,
      title: node.title,
      summary: node.summary,
    };

    if (node.node_type === 'evidence') {
      setSelectedNode(baseNode);
      try {
        const detail = await getEvidence(node.node_id);
        try {
          const rawDetail = await getRawItem(detail.raw_ref);
          setSelectedNode({ ...baseNode, node_type: 'evidence', detail, rawDetail });
        } catch (rawError) {
          setSelectedNode({
            ...baseNode,
            node_type: 'evidence',
            detail,
            rawDetailError: formatApiError(rawError, '原始数据来源加载失败'),
          });
        }
      } catch (error) {
        setErrorMessage(formatApiError(error, 'Evidence 加载失败'));
      }
      return;
    }

    if (node.node_type === 'raw_item') {
      setSelectedNode(baseNode);
      try {
        const detail = await getRawItem(node.node_id);
        setSelectedNode({ ...baseNode, node_type: 'raw_item', detail });
      } catch (error) {
        setErrorMessage(formatApiError(error, 'Raw Item 加载失败'));
      }
      return;
    }

    if (node.node_type === 'agent_argument') {
      setSelectedNode(baseNode);
      try {
        const detail = await getAgentArgument(node.node_id);
        setSelectedNode({ ...baseNode, node_type: 'agent_argument', detail });
      } catch (error) {
        setErrorMessage(formatApiError(error, 'Agent Argument 加载失败'));
      }
      return;
    }

    if (node.node_type === 'round_summary') {
      setSelectedNode(baseNode);
      try {
        const detail = await getRoundSummary(node.node_id);
        setSelectedNode({ ...baseNode, node_type: 'round_summary', detail });
      } catch (error) {
        setErrorMessage(formatApiError(error, '本轮辩论摘要加载失败'));
      }
      return;
    }

    setSelectedNode(baseNode as SelectedNode);
  }

  function handleStreamMessage(parsed: WorkflowEvent) {
    if (parsed.event_type === 'snapshot') {
      const payloadSnapshot = parsed.payload as unknown as WorkflowSnapshot;
      if (payloadSnapshot.workflow_run) {
        setSnapshot(payloadSnapshot);
      }
    }
    if (
      parsed.event_type === 'workflow_failed' ||
      parsed.event_type === 'agent_argument_completed' ||
      parsed.event_type === 'round_summary_completed' ||
      parsed.event_type === 'judgment_completed' ||
      parsed.event_type === 'workflow_completed'
    ) {
      void loadWorkflowState(parsed.workflow_run_id, 'merge_events').catch((error) => {
        setErrorMessage(formatApiError(error, 'Trace 刷新失败'));
      });
    }
    setEvents((current) => {
      if (current.some((item) => item.event_id === parsed.event_id)) {
        return current;
      }
      return [...current, parsed].sort((left, right) => left.sequence - right.sequence);
    });
  }

  return (
    <main className="analysis-page" aria-label="ConsensusInvest analysis terminal">
      <GlobalNav active="analysis" className="analysis-nav" />

      <AnalysisConsole
        ticker={ticker}
        onTickerChange={setTicker}
        configs={configs}
        selectedConfigId={selectedConfigId}
        onSelectConfig={setSelectedConfigId}
        onCreateWorkflow={handleCreateWorkflow}
        onRefresh={handleRefresh}
        workflowRunId={workflowRunId}
        snapshot={snapshot}
        connection={connection}
        eventCount={events.length}
        latestStatus={latestStatus}
        latestStage={latestStage}
        errorMessage={errorMessage}
      />

      <section className="analysis-workspace" aria-label="Trace graph workspace">
        <header className="graph-title">
          <span>判断溯源图</span>
          <span>|</span>
          <strong>{snapshot?.workflow_run.ticker ?? (ticker || '未选择')}</strong>
        </header>

        <div className="graph-board">
          {hasTraceNodes ? (
            <TraceGraph
              graph={graph}
              traceNodeIds={traceNodeIds}
              selectedNodeId={selectedNode?.node_id ?? null}
              onSelectNode={handleSelectNode}
            />
          ) : (
            <TraceGraphEmptyState
              errorMessage={visibleFailureMessage}
              failureSummary={failureSummary}
              hasWorkflow={hasWorkflow}
              isWorkflowFailed={isWorkflowFailed}
              latestStage={latestStage}
              latestStatus={latestStatus}
            />
          )}
        </div>

        <section className="timeline-panel" aria-label="Workflow events">
          <h2>运行事件</h2>
          <div className="timeline-list">
            {events.slice(-8).map((event) => (
              <div className="timeline-row" key={event.event_id}>
                <span>{event.sequence}</span>
                <strong>{event.event_type}</strong>
                <span>{formatTime(event.created_at)}</span>
              </div>
            ))}
            {events.length === 0 ? <p>尚未创建分析任务。</p> : null}
          </div>
        </section>
      </section>

      <aside className="analysis-inspector" aria-label="Node explanation">
        <section className="inspector-panel">
          <h2>节点说明</h2>
          <div className="inspector-body">
            {selectedNode ? (
              <NodeInspector node={selectedNode} />
            ) : judgment ? (
              <JudgmentInspector judgment={judgment} />
            ) : (
              <TraceInspectorEmptyState
                failureSummary={failureSummary}
                hasWorkflow={hasWorkflow}
                hasTraceNodes={hasTraceNodes}
                isWorkflowFailed={isWorkflowFailed}
                visibleFailureMessage={visibleFailureMessage}
              />
            )}
          </div>
        </section>

        <section className="legend-panel">
          <h2>图例</h2>
          <div className="legend-row">
            <span className="legend-line" />
            <span>推理边</span>
          </div>
          <div className="legend-row">
            <span className="legend-node" />
            <span>Trace 节点</span>
          </div>
        </section>
      </aside>
    </main>
  );
}

export default AnalysisPage;
