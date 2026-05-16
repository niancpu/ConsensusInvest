import type { WorkflowSnapshot } from '../../../types/workflow';

export const SOURCE_STATUSES: ReadonlyArray<[string, string, string]> = [
  ['价格行情', 'OK', '00:00:35'],
  ['财务报表', 'OK', '00:02:12'],
  ['新闻资讯', 'OK', '00:01:08'],
  ['市场情绪', 'OK', '00:00:47'],
  ['估值模型', 'OK', '00:03:21'],
  ['宏观数据', 'OK', '00:02:45'],
  ['风险因子', 'OK', '00:01:59'],
];

export const AGENT_MODES: ReadonlyArray<[string, string]> = [
  ['共识推理模式', 'ACTIVE'],
  ['事件驱动模式', 'INACTIVE'],
  ['风险监控模式', 'INACTIVE'],
];

export function sourceRowsFromSnapshot(snapshot: WorkflowSnapshot): string[][] {
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

export function agentRowsFromSnapshot(snapshot: WorkflowSnapshot): string[][] {
  if (snapshot.agent_runs.length === 0) {
    return [['workflow', snapshot.workflow_run.status]];
  }
  return snapshot.agent_runs.map((run) => [run.agent_id, run.status]);
}
