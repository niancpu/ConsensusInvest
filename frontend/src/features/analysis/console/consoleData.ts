import type { WorkflowSnapshot } from '../../../types/workflow';

type StageDisplay = {
  currentIndex: number;
  description: string;
  label: string;
  progressLabel: string;
  steps: ReadonlyArray<{
    key: string;
    label: string;
    state: 'done' | 'current' | 'pending';
  }>;
  tone: 'idle' | 'active' | 'success' | 'danger' | 'muted';
};

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

const WORKFLOW_STAGE_STEPS: ReadonlyArray<{ key: string; label: string }> = [
  { key: 'queued', label: '排队' },
  { key: 'collecting_raw_items', label: '采集' },
  { key: 'normalizing_evidence', label: '归一' },
  { key: 'structuring_evidence', label: '结构化' },
  { key: 'evidence_selection', label: '筛选' },
  { key: 'debate', label: '辩论' },
  { key: 'round_summary', label: '摘要' },
  { key: 'judge', label: '裁判' },
  { key: 'completed', label: '完成' },
];

const WORKFLOW_STAGE_LABELS: Record<string, { label: string; description: string }> = {
  idle: {
    label: '待开始',
    description: '选择股票和 Workflow 后启动分析。',
  },
  queued: {
    label: '排队中',
    description: '任务已创建，等待执行资源。',
  },
  collecting_raw_items: {
    label: '采集原始信息',
    description: '正在从行情、财务、新闻等来源采集 Raw Item。',
  },
  normalizing_evidence: {
    label: '归一化证据',
    description: '正在把原始信息转换为可追踪 Evidence。',
  },
  structuring_evidence: {
    label: '结构化证据',
    description: '正在抽取证据要点、质量和关联字段。',
  },
  evidence_selection: {
    label: '筛选关键证据',
    description: '正在选择进入 Agent 论证的证据集合。',
  },
  debate: {
    label: 'Agent 辩论',
    description: 'Agent 正在基于 Evidence 生成论证。',
  },
  round_summary: {
    label: '轮次摘要',
    description: '正在汇总本轮 Agent 论证和分歧。',
  },
  judge: {
    label: '最终裁判',
    description: 'Judge 正在回查证据并生成最终判断。',
  },
  completed: {
    label: '分析完成',
    description: 'Workflow 已完成，可以查看判断溯源图和最终判断。',
  },
  failed: {
    label: '分析失败',
    description: 'Workflow 执行失败，请查看错误信息和运行事件。',
  },
  cancelled: {
    label: '已取消',
    description: 'Workflow 已取消。',
  },
  waiting: {
    label: '等待中',
    description: '任务正在等待外部服务、子任务或调度条件。',
  },
  partial_completed: {
    label: '部分完成',
    description: '已有部分结果可用，但仍存在未完成或失败步骤。',
  },
};

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

export function getStageDisplay(stage: string, status: string): StageDisplay {
  const normalizedStage = stage || status || 'idle';
  const stageMeta = WORKFLOW_STAGE_LABELS[normalizedStage] ?? {
    label: normalizedStage,
    description: '后端返回了未登记的阶段，按原始 stage 显示。',
  };
  const rawIndex = WORKFLOW_STAGE_STEPS.findIndex((step) => step.key === normalizedStage);
  const currentIndex = rawIndex >= 0 ? rawIndex : -1;
  const progressLabel =
    currentIndex >= 0 ? `${currentIndex + 1}/${WORKFLOW_STAGE_STEPS.length}` : '未匹配';
  const tone = resolveStageTone(normalizedStage, status);

  return {
    currentIndex,
    description: stageMeta.description,
    label: stageMeta.label,
    progressLabel,
    steps: WORKFLOW_STAGE_STEPS.map((step, index) => ({
      ...step,
      state: currentIndex < 0 ? 'pending' : index < currentIndex ? 'done' : index === currentIndex ? 'current' : 'pending',
    })),
    tone,
  };
}

function resolveStageTone(stage: string, status: string): StageDisplay['tone'] {
  if (stage === 'failed' || status === 'failed') {
    return 'danger';
  }
  if (stage === 'completed' || status === 'completed') {
    return 'success';
  }
  if (stage === 'idle') {
    return 'idle';
  }
  if (status === 'cancelled') {
    return 'muted';
  }
  return 'active';
}
