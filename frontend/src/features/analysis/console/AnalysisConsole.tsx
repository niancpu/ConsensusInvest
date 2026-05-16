import { FormEvent } from 'react';
import type { WorkflowConfig, WorkflowSnapshot } from '../../../types/workflow';
import {
  AGENT_MODES,
  SOURCE_STATUSES,
  agentRowsFromSnapshot,
  getStageDisplay,
  sourceRowsFromSnapshot,
} from './consoleData';

type Props = {
  ticker: string;
  onTickerChange: (value: string) => void;
  configs: WorkflowConfig[];
  selectedConfigId: string;
  onSelectConfig: (value: string) => void;
  onCreateWorkflow: (event: FormEvent<HTMLFormElement>) => void;
  onRefresh: () => void;
  workflowRunId: string;
  snapshot: WorkflowSnapshot | null;
  connection: string;
  eventCount: number;
  latestStatus: string;
  latestStage: string;
  failedStage: string;
  errorMessage: string;
};

export default function AnalysisConsole({
  ticker,
  onTickerChange,
  configs,
  selectedConfigId,
  onSelectConfig,
  onCreateWorkflow,
  onRefresh,
  workflowRunId,
  snapshot,
  connection,
  eventCount,
  latestStatus,
  latestStage,
  failedStage,
  errorMessage,
}: Props) {
  const stageDisplay = getStageDisplay(latestStage, latestStatus, failedStage);

  return (
    <aside className="analysis-console" aria-label="Analysis controls">
      <form className="console-block" onSubmit={onCreateWorkflow}>
        <h1>股票代码</h1>
        <input
          className="stock-input"
          value={ticker}
          onChange={(event) => onTickerChange(event.target.value)}
          aria-label="Stock ticker"
          placeholder="002594"
        />

        <label className="field-label" htmlFor="workflow-config">Workflow</label>
        <select
          id="workflow-config"
          className="config-select"
          value={selectedConfigId}
          onChange={(event) => onSelectConfig(event.target.value)}
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
        <button className="refresh-button" type="button" onClick={onRefresh} disabled={!workflowRunId}>
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

      <section className={`console-block stage-panel stage-panel-${stageDisplay.tone}`} aria-label="当前分析阶段">
        <div className="stage-panel-header">
          <span>当前阶段</span>
          <strong>{stageDisplay.progressLabel}</strong>
        </div>
        <strong className="stage-title">{stageDisplay.label}</strong>
        <p>{stageDisplay.description}</p>
        {stageDisplay.failedStageLabel ? (
          <div className="stage-failure">
            <span>失败发生阶段</span>
            <strong>{stageDisplay.failedStageLabel}</strong>
          </div>
        ) : null}
        <dl className="stage-meta">
          <div>
            <dt>stage</dt>
            <dd>{latestStage}</dd>
          </div>
          <div>
            <dt>status</dt>
            <dd>{latestStatus}</dd>
          </div>
          <div>
            <dt>conn</dt>
            <dd>{connection}</dd>
          </div>
        </dl>
        <div className="stage-track" aria-label="Workflow stage progress">
          {stageDisplay.steps.map((step) => (
            <span
              aria-current={step.state === 'current' ? 'step' : undefined}
              className={`stage-step stage-step-${step.state}`}
              key={step.key}
              title={step.label}
            >
              {step.label}
            </span>
          ))}
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
          {(snapshot ? sourceRowsFromSnapshot(snapshot) : SOURCE_STATUSES.map((row) => [...row])).map(
            ([source, status, latency]) => (
              <div className="status-row" role="row" key={source}>
                <span>{source}</span>
                <span>{status}</span>
                <span>{latency}</span>
              </div>
            ),
          )}
        </div>
      </section>

      <section className="console-block">
        <h2>代理模式</h2>
        <div className="mode-list">
          {(snapshot ? agentRowsFromSnapshot(snapshot) : AGENT_MODES.map((row) => [...row])).map(
            ([mode, state]) => (
              <div className={state === 'ACTIVE' || state === 'completed' ? 'mode-row active' : 'mode-row'} key={mode}>
                <span>{mode}</span>
                <span>{state}</span>
              </div>
            ),
          )}
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
  );
}
