import { useEffect, useState } from 'react';
import GlobalNav from '../../components/GlobalNav';
import { formatApiError } from '../../api/errors';
import { getWorkflowRun, listWorkflowRuns } from '../../api/workflow';
import type { WorkflowRunListItemView } from '../../types/workflow';
import './HistoryPage.css';

function HistoryPage() {
  const [runs, setRuns] = useState<WorkflowRunListItemView[]>([]);
  const [selectedRun, setSelectedRun] = useState<WorkflowRunListItemView | null>(null);
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    listWorkflowRuns(controller.signal)
      .then((items) => {
        setRuns(items);
        setSelectedRun(items[0] ?? null);
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setErrorMessage(formatApiError(error, '历史列表加载失败'));
        }
      });
    return () => controller.abort();
  }, []);

  async function handlePickRun(workflowRunId: string) {
    setErrorMessage('');
    try {
      const detail = await getWorkflowRun(workflowRunId);
      setSelectedRun(detail);
    } catch (error) {
      setErrorMessage(formatApiError(error, '历史详情加载失败'));
    }
  }

  return (
    <main className="history-page">
      <GlobalNav active="history" className="history-nav" />

      <section className="history-layout">
        <aside className="history-list">
          <h1>历史</h1>
          <p>已完成和运行中的 workflow 列表。</p>
          {runs.map((run) => (
            <button className="history-row" type="button" key={run.workflow_run_id} onClick={() => handlePickRun(run.workflow_run_id)}>
              <strong>{run.ticker}</strong>
              <span>{run.status}</span>
              <small>{run.workflow_config_id}</small>
            </button>
          ))}
          {errorMessage ? <div className="history-error">{errorMessage}</div> : null}
        </aside>

        <section className="history-detail">
          {selectedRun ? (
            <>
              <h2>{selectedRun.ticker}</h2>
              <p>{selectedRun.workflow_run_id}</p>
              <dl>
                <div>
                  <dt>Status</dt>
                  <dd>{selectedRun.status}</dd>
                </div>
                <div>
                  <dt>Config</dt>
                  <dd>{selectedRun.workflow_config_id}</dd>
                </div>
                <div>
                  <dt>Judgment</dt>
                  <dd>{selectedRun.judgment_id ?? '-'}</dd>
                </div>
                <div>
                  <dt>Signal</dt>
                  <dd>{selectedRun.final_signal ?? '-'}</dd>
                </div>
              </dl>
              <a className="primary-action" href={`#analysis?ticker=${selectedRun.ticker}`}>
                回到分析
              </a>
            </>
          ) : (
            <p>没有可显示的历史项。</p>
          )}
        </section>
      </section>
    </main>
  );
}

export default HistoryPage;
