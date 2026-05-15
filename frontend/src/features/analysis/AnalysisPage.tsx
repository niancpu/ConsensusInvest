import { FormEvent, useEffect, useMemo, useState } from 'react';
import {
  AgentArgument,
  EvidenceDetail,
  RawItemDetail,
  WorkflowConfig,
  WorkflowEvent,
  WorkflowSnapshot,
  WorkflowTrace,
  createWorkflowRun,
  eventStreamUrl,
  getAgentArgument,
  getEvidence,
  getRawItem,
  getWorkflowSnapshot,
  getWorkflowTrace,
  listWorkflowConfigs,
} from './api';
import GlobalNav from '../../components/GlobalNav';
import { formatApiError } from '../../api/errors';
import './AnalysisPage.css';
import { agentModes, layoutTraceGraph, sourceStatuses } from './analysisData';

type ConnectionState = 'idle' | 'creating' | 'replaying' | 'open' | 'closed' | 'error';

type SelectedNode =
  | { node_id: string; node_type: 'judgment' | 'round_summary'; title: string; summary: string }
  | { node_id: string; node_type: 'agent_argument'; title: string; summary: string; detail?: AgentArgument }
  | { node_id: string; node_type: 'evidence'; title: string; summary: string; detail?: EvidenceDetail }
  | { node_id: string; node_type: 'raw_item'; title: string; summary: string; detail?: RawItemDetail };

function AnalysisPage() {
  const initialTicker = new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('ticker') ?? '002594';
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
    if (!workflowRunId) {
      return undefined;
    }

    setConnection('replaying');
    const source = new EventSource(eventStreamUrl(workflowRunId, 0));

    source.onopen = () => setConnection('open');
    source.onmessage = (message) => appendEventFromMessage(message);
    source.onerror = () => {
      source.close();
      setConnection('error');
      setErrorMessage('Workflow 事件流连接失败：页面无法继续接收实时运行日志，请点击“刷新快照”查看最新状态。');
    };

    const eventTypes = [
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
    eventTypes.forEach((eventType) => {
      source.addEventListener(eventType, appendEventFromMessage);
    });

    return () => {
      eventTypes.forEach((eventType) => {
        source.removeEventListener(eventType, appendEventFromMessage);
      });
      source.close();
    };
  }, [workflowRunId]);

  const hasWorkflow = Boolean(workflowRunId);
  const hasTraceNodes = (trace?.trace_nodes.length ?? 0) > 0;
  const graph = useMemo(
    () => {
      if (!trace?.trace_nodes.length) {
        return { nodes: [], edges: [] };
      }
      return layoutTraceGraph(trace.trace_nodes, trace.trace_edges ?? []);
    },
    [trace],
  );
  const traceNodeIds = useMemo(
    () => new Set((trace?.trace_nodes ?? []).map((node) => node.node_id)),
    [trace],
  );

  const latestStatus = snapshot?.workflow_run.status ?? 'idle';
  const latestStage = snapshot?.workflow_run.stage ?? 'idle';
  const judgment = snapshot?.judgment ?? null;
  const eventCount = events.length;
  const isWorkflowFailed = latestStatus === 'failed' || latestStage === 'failed';
  const failureSummary = useMemo(() => {
    const failedEvent = [...events].reverse().find((event) => event.event_type === 'workflow_failed');
    return failedEvent ? summarizeFailurePayload(failedEvent.payload) : '';
  }, [events]);

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
    setEvents((current) => {
      const snapshotEvents = nextSnapshot.events ?? [];
      if (eventMode === 'replace_events') {
        return snapshotEvents;
      }
      const byId = new Map(current.map((item) => [item.event_id, item]));
      snapshotEvents.forEach((item) => byId.set(item.event_id, item));
      return [...byId.values()].sort((left, right) => left.sequence - right.sequence);
    });

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
        setSelectedNode({ ...baseNode, detail });
      } catch (error) {
        setErrorMessage(formatApiError(error, 'Evidence 加载失败'));
      }
      return;
    }

    if (node.node_type === 'raw_item') {
      setSelectedNode(baseNode);
      try {
        const detail = await getRawItem(node.node_id);
        setSelectedNode({ ...baseNode, detail });
      } catch (error) {
        setErrorMessage(formatApiError(error, 'Raw Item 加载失败'));
      }
      return;
    }

    if (node.node_type === 'agent_argument') {
      setSelectedNode(baseNode);
      try {
        const detail = await getAgentArgument(node.node_id);
        setSelectedNode({ ...baseNode, detail });
      } catch (error) {
        setErrorMessage(formatApiError(error, 'Agent Argument 加载失败'));
      }
      return;
    }

    setSelectedNode(baseNode as SelectedNode);
  }

  function appendEventFromMessage(message: MessageEvent) {
    try {
      const parsed = JSON.parse(message.data) as WorkflowEvent;
      if (parsed.event_type === 'snapshot') {
        const payloadSnapshot = parsed.payload as unknown as WorkflowSnapshot;
        if (payloadSnapshot.workflow_run) {
          setSnapshot(payloadSnapshot);
        }
      }
      if (
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
    } catch {
      setConnection('error');
    }
  }

  return (
    <main className="analysis-page" aria-label="ConsensusInvest analysis terminal">
      <GlobalNav active="analysis" className="analysis-nav" />

      <aside className="analysis-console" aria-label="Analysis controls">
        <form className="console-block" onSubmit={handleCreateWorkflow}>
          <h1>股票代码</h1>
          <input
            className="stock-input"
            value={ticker}
            onChange={(event) => setTicker(event.target.value)}
            aria-label="Stock ticker"
            placeholder="002594"
          />

          <label className="field-label" htmlFor="workflow-config">
            Workflow
          </label>
          <select
            id="workflow-config"
            className="config-select"
            value={selectedConfigId}
            onChange={(event) => setSelectedConfigId(event.target.value)}
          >
            {configs.length === 0 ? (
              <option value="mvp_bull_judge_v1">mvp_bull_judge_v1</option>
            ) : (
              configs.map((config) => (
                <option value={config.workflow_config_id} key={config.workflow_config_id}>
                  {config.workflow_config_id}
                </option>
              ))
            )}
          </select>

          <button className="run-button" type="submit" disabled={connection === 'creating'}>
            {connection === 'creating' ? '运行中' : '开始分析'}
          </button>
        </form>

        <section className="console-block">
          <button className="refresh-button" type="button" onClick={handleRefresh} disabled={!workflowRunId}>
            刷新快照
          </button>
          <div className="quote-strip">
            <span>{snapshot?.workflow_run.ticker ?? (ticker || '-')}</span>
            <span>{latestStatus}</span>
            <span>{latestStage}</span>
            <span>events</span>
            <span>{eventCount}</span>
            <span>conn</span>
            <span>{connection}</span>
            <span>run</span>
            <span>{workflowRunId ? workflowRunId.slice(-8) : '-'}</span>
          </div>
        </section>

        <section className="console-block">
          <h2>数据源状态</h2>
          <div className="status-table" role="table" aria-label="Data source status">
            <div className="status-row status-head" role="row">
              <span>源</span>
              <span>状态</span>
              <span>延迟</span>
            </div>
            {(snapshot ? sourceRowsFromSnapshot(snapshot) : sourceStatuses).map(([source, status, latency]) => (
              <div className="status-row" role="row" key={source}>
                <span>{source}</span>
                <span>{status}</span>
                <span>{latency}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="console-block">
          <h2>代理模式</h2>
          <div className="mode-list">
            {(snapshot ? agentRowsFromSnapshot(snapshot) : agentModes).map(([mode, state]) => (
              <div className={state === 'ACTIVE' || state === 'completed' ? 'mode-row active' : 'mode-row'} key={mode}>
                <span>{mode}</span>
                <span>{state}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="console-block">
          <h2>推理状态</h2>
          <div className="metric-grid">
            <span>Evidence</span>
            <strong>{snapshot?.evidence_items.length ?? 0}</strong>
            <span>Argument</span>
            <strong>{snapshot?.agent_arguments.length ?? 0}</strong>
            <span>Round Summary</span>
            <strong>{snapshot?.round_summaries.length ?? 0}</strong>
            <span>Tool Call</span>
            <strong>{snapshot?.judge_tool_calls.length ?? 0}</strong>
          </div>
        </section>

        {errorMessage ? <div className="error-banner">{errorMessage}</div> : null}

        <footer className="console-footer">
          <span>系统状态 | {latestStatus}</span>
          <span>API v1</span>
        </footer>
      </aside>

      <section className="analysis-workspace" aria-label="Trace graph workspace">
        <header className="graph-title">
          <span>判断溯源图</span>
          <span>|</span>
          <strong>{snapshot?.workflow_run.ticker ?? (ticker || '未选择')}</strong>
        </header>

        <div className="graph-board">
          {hasTraceNodes ? (
            <svg className="trace-graph" viewBox="0 0 780 690" role="img" aria-labelledby="trace-title">
              <title id="trace-title">Workflow trace graph</title>
              <defs>
                <pattern id="grid" width="62" height="62" patternUnits="userSpaceOnUse">
                  <path d="M 62 0 L 0 0 0 62" fill="none" stroke="#000000" strokeDasharray="2 3" strokeWidth="0.5" opacity="0.35" />
                </pattern>
              </defs>
              <rect className="graph-grid" x="0" y="0" width="780" height="690" fill="url(#grid)" />

              {graph.edges.map((edge) => (
                <g className={`trace-edge ${edge.edge_type}`} key={`${edge.from_node_id}-${edge.to_node_id}-${edge.edge_type}`}>
                  <polyline points={edge.points} />
                  <rect x={edge.labelX - 20} y={edge.labelY - 11} width="40" height="22" />
                  <text x={edge.labelX} y={edge.labelY + 4}>{edge.weight}</text>
                </g>
              ))}

              {graph.nodes.map((node) => (
                <TraceNodeShape
                  isInteractive={traceNodeIds.has(node.node_id)}
                  isSelected={selectedNode?.node_id === node.node_id}
                  key={node.node_id}
                  node={node}
                  onSelect={handleSelectNode}
                />
              ))}
            </svg>
          ) : (
            <TraceGraphEmptyState
              errorMessage={errorMessage}
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
            />
          )}
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

function TraceGraphEmptyState({
  errorMessage,
  failureSummary,
  hasWorkflow,
  isWorkflowFailed,
  latestStage,
  latestStatus,
}: {
  errorMessage: string;
  failureSummary: string;
  hasWorkflow: boolean;
  isWorkflowFailed: boolean;
  latestStage: string;
  latestStatus: string;
}) {
  const title = isWorkflowFailed
    ? 'workflow 已失败，未生成 trace'
    : hasWorkflow
      ? '等待 workflow trace'
      : '需要先创建 workflow';

  return (
    <div className="trace-empty-state" role="status">
      <h2>{title}</h2>
      <p>
        {errorMessage
          ? errorMessage
          : isWorkflowFailed
          ? `当前状态 ${latestStatus} / ${latestStage}。${failureSummary || '后端没有返回具体失败原因，请查看运行事件或后端日志。'}`
          : hasWorkflow
          ? `当前状态 ${latestStatus} / ${latestStage}。判断溯源图只使用后端 workflow trace 节点；trace 返回前不展示示例图。`
          : '选择股票和 workflow 配置后点击开始分析。未创建 workflow 时不展示假图或实体知识图谱。'}
      </p>
    </div>
  );
}

function TraceInspectorEmptyState({
  failureSummary,
  hasWorkflow,
  hasTraceNodes,
  isWorkflowFailed,
}: {
  failureSummary: string;
  hasWorkflow: boolean;
  hasTraceNodes: boolean;
  isWorkflowFailed: boolean;
}) {
  return (
    <div className="description-list">
      <article className="description-item">
        <h3>
          {hasTraceNodes
            ? '选择节点'
            : isWorkflowFailed
              ? 'workflow 失败'
              : hasWorkflow
                ? 'Trace 未就绪'
                : '创建 workflow'}
        </h3>
        <p>
          {hasTraceNodes
            ? '点击判断、Round Summary、Agent Argument、Evidence 或 Raw Item 节点查看下钻详情。'
            : isWorkflowFailed
              ? failureSummary || '任务失败且没有生成可审计判断链；需要先处理失败原因，再重新运行 workflow。'
            : hasWorkflow
              ? '等待 trace_nodes 返回后可从判断溯源图进入节点详情；当前不会用实体关系或演示数据占位。'
              : '先创建分析任务，页面会订阅 SSE 事件并在 trace 可用后展示真实推理链路。'}
        </p>
      </article>
    </div>
  );
}

function TraceNodeShape({
  isInteractive,
  isSelected,
  node,
  onSelect,
}: {
  isInteractive: boolean;
  isSelected: boolean;
  node: ReturnType<typeof layoutTraceGraph>['nodes'][number];
  onSelect: (nodeId: string) => void;
}) {
  return (
    <g
      className={`trace-node ${isInteractive ? 'interactive' : 'static'} ${node.node_type} ${isSelected ? 'selected' : ''}`}
      tabIndex={isInteractive ? 0 : undefined}
      onClick={isInteractive ? () => onSelect(node.node_id) : undefined}
      onKeyDown={
        isInteractive
          ? (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                onSelect(node.node_id);
              }
            }
          : undefined
      }
    >
      <rect x={node.x} y={node.y} width={node.width} height={node.height} />
      <text className="node-title" x={node.x + node.width / 2} y={node.y + 30}>{node.title}</text>
      <text className="node-subtitle" x={node.x + node.width / 2} y={node.y + 52}>
        {node.subtitle} {node.score}
      </text>
    </g>
  );
}

function JudgmentInspector({ judgment }: { judgment: NonNullable<WorkflowSnapshot['judgment']> }) {
  return (
    <div className="description-list">
      <article className="description-item">
        <h3>{judgment.final_signal}</h3>
        <p>{judgment.reasoning}</p>
      </article>
      <article className="description-item">
        <h3>置信度</h3>
        <p>{formatScore(judgment.confidence)} / {judgment.time_horizon}</p>
      </article>
      {judgment.risk_notes.map((note) => (
        <article className="description-item" key={note}>
          <h3>风险</h3>
          <p>{note}</p>
        </article>
      ))}
    </div>
  );
}

function NodeInspector({ node }: { node: SelectedNode }) {
  return (
    <div className="description-list">
      <article className="description-item">
        <h3>{node.title}</h3>
        <p>{node.summary || node.node_id}</p>
      </article>

      {node.node_type === 'agent_argument' && node.detail ? (
        <>
          <article className="description-item">
            <h3>{node.detail.agent_id} R{node.detail.round}</h3>
            <p>{node.detail.argument}</p>
          </article>
          <article className="description-item">
            <h3>引用 Evidence</h3>
            <p>{[...node.detail.referenced_evidence_ids, ...node.detail.counter_evidence_ids].join(', ') || '-'}</p>
          </article>
        </>
      ) : null}

      {node.node_type === 'evidence' && node.detail ? (
        <>
          <article className="description-item">
            <h3>{node.detail.source ?? 'source'}</h3>
            <p>{node.detail.objective_summary || node.detail.content || '-'}</p>
          </article>
          <article className="description-item">
            <h3>质量</h3>
            <p>
              source {formatScore(node.detail.source_quality)} / relevance {formatScore(node.detail.relevance)} /
              structure {formatScore(node.detail.structuring_confidence)}
            </p>
          </article>
          <article className="description-item">
            <h3>Raw</h3>
            <p>{node.detail.raw_ref}</p>
          </article>
        </>
      ) : null}

      {node.node_type === 'raw_item' && node.detail ? (
        <>
          <article className="description-item">
            <h3>{node.detail.source ?? 'raw'}</h3>
            <p>{node.detail.content || node.detail.title || '-'}</p>
          </article>
          <article className="description-item">
            <h3>Payload</h3>
            <p>{JSON.stringify(node.detail.raw_payload).slice(0, 180)}</p>
          </article>
        </>
      ) : null}
    </div>
  );
}

function sourceRowsFromSnapshot(snapshot: WorkflowSnapshot): string[][] {
  const sources = new Map<string, number>();
  snapshot.evidence_items.forEach((item) => {
    const source = item.source || item.source_type || 'unknown';
    sources.set(source, (sources.get(source) ?? 0) + 1);
  });
  if (sources.size === 0) {
    return [['Evidence', snapshot.workflow_run.status, snapshot.workflow_run.stage]];
  }
  return [...sources.entries()].map(([source, count]) => [source, 'OK', `${count} 条`]);
}

function agentRowsFromSnapshot(snapshot: WorkflowSnapshot): string[][] {
  if (snapshot.agent_runs.length === 0) {
    return [['workflow', snapshot.workflow_run.status]];
  }
  return snapshot.agent_runs.map((run) => [run.agent_id, run.status]);
}

function formatScore(value?: number | null): string {
  return typeof value === 'number' ? value.toFixed(2) : '-';
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString('zh-CN', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function summarizeFailurePayload(payload: Record<string, unknown>): string {
  const code = typeof payload.code === 'string' ? payload.code : '';
  const message = typeof payload.message === 'string' ? payload.message : '';
  const gaps = Array.isArray(payload.gaps) ? payload.gaps : [];
  const gapDescriptions = gaps
    .map((gap) => {
      if (!gap || typeof gap !== 'object') {
        return '';
      }
      const value = gap as Record<string, unknown>;
      return typeof value.description === 'string' ? value.description : '';
    })
    .filter(Boolean);

  if (code === 'insufficient_evidence') {
    return gapDescriptions.length > 0
      ? `证据不足：${gapDescriptions.join('；')}`
      : '证据不足，Judge 没有形成最终判断。';
  }
  if (code === 'agent_swarm_failed') {
    return message ? `Agent 论证失败：${message}` : 'Agent 论证失败，未生成最终判断。';
  }
  if (code === 'judge_failed') {
    return message ? `Judge 汇总失败：${message}` : 'Judge 汇总失败，未生成最终判断。';
  }
  if (code === 'evidence_acquisition_failed') {
    return message ? `证据采集失败：${message}` : '证据采集失败，未找到可用于分析的 Evidence。';
  }
  return [friendlyFailureCode(code), message].filter(Boolean).join('：') || '';
}

function friendlyFailureCode(code: string): string {
  const labels: Record<string, string> = {
    missing_judgment: '最终判断缺失',
  };
  return labels[code] ?? code;
}

export default AnalysisPage;
