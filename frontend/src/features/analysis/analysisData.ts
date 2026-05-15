export type TraceNodeType = 'judgment' | 'agent_argument' | 'evidence' | 'raw_item' | 'round_summary';

export type TraceNode = {
  node_id: string;
  node_type: TraceNodeType;
  title: string;
  subtitle: string;
  score: string;
  x: number;
  y: number;
  width: number;
  height: number;
};

export type TraceEdge = {
  from_node_id: string;
  to_node_id: string;
  edge_type: TraceEdgeType;
  weight: string;
  points: string;
  labelX: number;
  labelY: number;
};

export type TraceEdgeType =
  | 'uses_argument'
  | 'supports'
  | 'counters'
  | 'refuted'
  | 'derived_from'
  | 'cited'
  | 'uses_round_summary';

export const sourceStatuses = [
  ['价格行情', 'OK', '00:00:35'],
  ['财务报表', 'OK', '00:02:12'],
  ['新闻资讯', 'OK', '00:01:08'],
  ['市场情绪', 'OK', '00:00:47'],
  ['估值模型', 'OK', '00:03:21'],
  ['宏观数据', 'OK', '00:02:45'],
  ['风险因子', 'OK', '00:01:59'],
];

export const agentModes = [
  ['共识推理模式', 'ACTIVE'],
  ['事件驱动模式', 'INACTIVE'],
  ['风险监控模式', 'INACTIVE'],
];

export const traceNodes: TraceNode[] = [
  {
    node_id: 'ev_price',
    node_type: 'evidence',
    title: '价格',
    subtitle: '趋势强度',
    score: '0.72',
    x: 335,
    y: 30,
    width: 118,
    height: 68,
  },
  {
    node_id: 'arg_finance',
    node_type: 'agent_argument',
    title: '财报',
    subtitle: '质量评分',
    score: '0.81',
    x: 130,
    y: 186,
    width: 118,
    height: 68,
  },
  {
    node_id: 'arg_sentiment',
    node_type: 'agent_argument',
    title: '情绪',
    subtitle: '情绪得分',
    score: '0.64',
    x: 585,
    y: 186,
    width: 118,
    height: 68,
  },
  {
    node_id: 'judgment_consensus',
    node_type: 'judgment',
    title: '共识',
    subtitle: '置信度',
    score: '0.86',
    x: 335,
    y: 285,
    width: 122,
    height: 72,
  },
  {
    node_id: 'raw_news',
    node_type: 'raw_item',
    title: '新闻',
    subtitle: '影响得分',
    score: '0.63',
    x: 130,
    y: 432,
    width: 118,
    height: 68,
  },
  {
    node_id: 'raw_risk',
    node_type: 'raw_item',
    title: '风险',
    subtitle: '风险得分',
    score: '0.69',
    x: 335,
    y: 555,
    width: 118,
    height: 68,
  },
  {
    node_id: 'raw_valuation',
    node_type: 'raw_item',
    title: '估值',
    subtitle: '估值分位',
    score: '0.58',
    x: 585,
    y: 432,
    width: 118,
    height: 68,
  },
];

export const traceEdges: TraceEdge[] = [
  {
    from_node_id: 'ev_price',
    to_node_id: 'arg_finance',
    edge_type: 'supports',
    weight: '0.18',
    points: '335,70 245,70 245,148 190,148 190,186',
    labelX: 250,
    labelY: 122,
  },
  {
    from_node_id: 'ev_price',
    to_node_id: 'arg_sentiment',
    edge_type: 'supports',
    weight: '0.15',
    points: '453,70 550,70 550,148 644,148 644,186',
    labelX: 548,
    labelY: 122,
  },
  {
    from_node_id: 'ev_price',
    to_node_id: 'judgment_consensus',
    edge_type: 'uses_argument',
    weight: '0.24',
    points: '394,98 394,285',
    labelX: 394,
    labelY: 185,
  },
  {
    from_node_id: 'arg_finance',
    to_node_id: 'judgment_consensus',
    edge_type: 'supports',
    weight: '0.28',
    points: '248,220 304,220 304,318 335,318',
    labelX: 290,
    labelY: 218,
  },
  {
    from_node_id: 'arg_sentiment',
    to_node_id: 'judgment_consensus',
    edge_type: 'supports',
    weight: '0.16',
    points: '585,220 520,220 520,318 457,318',
    labelX: 528,
    labelY: 218,
  },
  {
    from_node_id: 'arg_finance',
    to_node_id: 'raw_news',
    edge_type: 'derived_from',
    weight: '0.12',
    points: '190,254 190,432',
    labelX: 190,
    labelY: 340,
  },
  {
    from_node_id: 'arg_sentiment',
    to_node_id: 'raw_valuation',
    edge_type: 'derived_from',
    weight: '0.11',
    points: '644,254 644,432',
    labelX: 644,
    labelY: 340,
  },
  {
    from_node_id: 'judgment_consensus',
    to_node_id: 'raw_risk',
    edge_type: 'counters',
    weight: '0.17',
    points: '394,357 394,555',
    labelX: 394,
    labelY: 452,
  },
  {
    from_node_id: 'raw_news',
    to_node_id: 'raw_risk',
    edge_type: 'supports',
    weight: '0.10',
    points: '248,466 305,466 305,590 335,590',
    labelX: 294,
    labelY: 463,
  },
  {
    from_node_id: 'raw_valuation',
    to_node_id: 'raw_risk',
    edge_type: 'supports',
    weight: '0.13',
    points: '585,466 520,466 520,590 453,590',
    labelX: 532,
    labelY: 463,
  },
];

export const nodeDescriptions = [
  ['共识', '综合多源信息推理得到的投资共识及置信度。'],
  ['价格', '基于价格动量、趋势与波动率的综合信号。'],
  ['财报', '财务质量、盈利能力与成长性的综合评估。'],
  ['情绪', '市场情绪与投资者行为的量化得分。'],
  ['风险', '综合市场风险、行业风险与个股特有风险。'],
];

const nodeSizeByType: Record<TraceNodeType, { width: number; height: number }> = {
  judgment: { width: 150, height: 78 },
  agent_argument: { width: 150, height: 72 },
  round_summary: { width: 150, height: 72 },
  evidence: { width: 132, height: 68 },
  raw_item: { width: 132, height: 68 },
};

export function layoutTraceGraph(
  nodes: Array<{
    node_id: string;
    node_type: TraceNodeType;
    title: string;
    summary: string;
  }>,
  edges: Array<{
    from_node_id: string;
    to_node_id: string;
    edge_type: string;
  }>,
): { nodes: TraceNode[]; edges: TraceEdge[] } {
  if (nodes.length === 0) {
    return { nodes: [], edges: [] };
  }

  const grouped = groupNodes(nodes);
  const placedNodes = grouped.flatMap(([type, group], rowIndex) => {
    const y = 42 + rowIndex * 132;
    const spacing = 700 / Math.max(group.length, 1);

    return group.map((node, index) => {
      const size = nodeSizeByType[type];
      const x = Math.max(30, spacing * index + spacing / 2 + 40 - size.width / 2);
      return {
        node_id: node.node_id,
        node_type: node.node_type,
        title: compactTitle(node.title || node.node_id),
        subtitle: node.node_type.replace('_', ' '),
        score: compactSummary(node.summary),
        x,
        y,
        width: size.width,
        height: size.height,
      };
    });
  });

  const byId = new Map(placedNodes.map((node) => [node.node_id, node]));
  const placedEdges = edges
    .map((edge) => {
      const from = byId.get(edge.from_node_id);
      const to = byId.get(edge.to_node_id);
      if (!from || !to) {
        return null;
      }
      const normalizedType = normalizeEdgeType(edge.edge_type);
      const route = routeTraceEdge(from, to);
      return {
        from_node_id: edge.from_node_id,
        to_node_id: edge.to_node_id,
        edge_type: normalizedType,
        weight: labelForEdge(normalizedType),
        points: route.points,
        labelX: route.labelX,
        labelY: route.labelY,
      } satisfies TraceEdge;
    })
    .filter((edge): edge is TraceEdge => edge !== null);

  return { nodes: placedNodes, edges: placedEdges };
}

function groupNodes(
  nodes: Array<{
    node_id: string;
    node_type: TraceNodeType;
    title: string;
    summary: string;
  }>,
): Array<[TraceNodeType, typeof nodes]> {
  const order: TraceNodeType[] = ['judgment', 'round_summary', 'agent_argument', 'evidence', 'raw_item'];
  return order
    .map((type) => [type, nodes.filter((node) => node.node_type === type)] as [TraceNodeType, typeof nodes])
    .filter(([, group]) => group.length > 0);
}

function routeTraceEdge(
  from: TraceNode,
  to: TraceNode,
): {
  points: string;
  labelX: number;
  labelY: number;
} {
  const fromCenterX = from.x + from.width / 2;
  const fromCenterY = from.y + from.height / 2;
  const toCenterX = to.x + to.width / 2;
  const toCenterY = to.y + to.height / 2;

  if (Math.abs(fromCenterY - toCenterY) < 16) {
    const fromIsLeft = fromCenterX <= toCenterX;
    const startX = fromIsLeft ? from.x + from.width : from.x;
    const endX = fromIsLeft ? to.x : to.x + to.width;
    const startY = fromCenterY;
    const endY = toCenterY;
    const midX = (startX + endX) / 2;
    return {
      points: `${startX},${startY} ${midX},${startY} ${midX},${endY} ${endX},${endY}`,
      labelX: midX,
      labelY: (startY + endY) / 2,
    };
  }

  const flowsDown = fromCenterY < toCenterY;
  const startX = fromCenterX;
  const startY = flowsDown ? from.y + from.height : from.y;
  const endX = toCenterX;
  const endY = flowsDown ? to.y : to.y + to.height;
  const midY = (startY + endY) / 2;
  return {
    points: `${startX},${startY} ${startX},${midY} ${endX},${midY} ${endX},${endY}`,
    labelX: (startX + endX) / 2,
    labelY: midY,
  };
}

function compactTitle(value: string): string {
  const trimmed = value.trim();
  return trimmed.length > 9 ? `${trimmed.slice(0, 8)}...` : trimmed;
}

function compactSummary(value: string): string {
  const trimmed = value.trim();
  return trimmed.length > 7 ? `${trimmed.slice(0, 6)}...` : trimmed;
}

function normalizeEdgeType(value: string): TraceEdgeType {
  const normalized = value.trim().toLowerCase().replaceAll('-', '_');
  if (
    normalized === 'uses_argument' ||
    normalized === 'supports' ||
    normalized === 'counters' ||
    normalized === 'refuted' ||
    normalized === 'derived_from' ||
    normalized === 'cited' ||
    normalized === 'uses_round_summary'
  ) {
    return normalized;
  }
  return 'cited';
}

function labelForEdge(value: TraceEdgeType): string {
  switch (value) {
    case 'uses_argument':
      return 'arg';
    case 'supports':
      return 'sup';
    case 'counters':
      return 'ctr';
    case 'refuted':
      return 'ref';
    case 'derived_from':
      return 'raw';
    case 'uses_round_summary':
      return 'sum';
    case 'cited':
      return 'cite';
  }
}
