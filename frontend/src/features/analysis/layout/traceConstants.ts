import type { TraceNodeType } from '../../../types/trace';

export const NODE_SIZE_BY_TYPE: Record<TraceNodeType, { width: number; height: number }> = {
  agent: { width: 136, height: 60 },
  agent_run: { width: 150, height: 66 },
  judgment: { width: 150, height: 72 },
  round_summary: { width: 150, height: 66 },
  agent_argument: { width: 150, height: 66 },
  search_request: { width: 124, height: 54 },
  evidence: { width: 118, height: 54 },
  raw_item: { width: 118, height: 54 },
};

export const TITLE_LENGTH_BY_TYPE: Record<TraceNodeType, number> = {
  agent: 9,
  agent_run: 9,
  judgment: 10,
  round_summary: 10,
  agent_argument: 9,
  search_request: 6,
  evidence: 6,
  raw_item: 6,
};

export const SUMMARY_LENGTH_BY_TYPE: Record<TraceNodeType, number> = {
  agent: 8,
  agent_run: 8,
  judgment: 9,
  round_summary: 9,
  agent_argument: 8,
  search_request: 5,
  evidence: 5,
  raw_item: 5,
};

export const GRAPH_LAYOUT = {
  minWidth: 780,
  minHeight: 620,
  topPadding: 42,
  sidePadding: 40,
  bottomPadding: 48,
  rowGap: 150,
  minNodeGap: 28,
  edgeLaneGap: 16,
  edgeLaneClearance: 28,
  maxEdgeLanes: 16,
};

export const NODE_ORDER: TraceNodeType[] = [
  'agent',
  'agent_run',
  'judgment',
  'round_summary',
  'agent_argument',
  'search_request',
  'evidence',
  'raw_item',
];

export const NODE_TYPE_LABELS: Record<TraceNodeType, string> = {
  agent: 'Agent 实体',
  agent_run: 'Agent 执行',
  judgment: '最终判断',
  round_summary: '本轮辩论',
  agent_argument: '代理论证',
  search_request: '搜索请求',
  evidence: '证据',
  raw_item: '原始数据',
};
