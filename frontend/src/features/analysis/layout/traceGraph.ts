import type { TraceEdge, TraceEdgeType, TraceGraphLayout, TraceNode, TraceNodeType } from '../../../types/trace';
import {
  GRAPH_LAYOUT,
  NODE_ORDER,
  NODE_SIZE_BY_TYPE,
  SUMMARY_LENGTH_BY_TYPE,
  TITLE_LENGTH_BY_TYPE,
} from './traceConstants';

type RawNode = {
  node_id: string;
  node_type: TraceNodeType;
  title: string;
  summary: string;
};

type RawEdge = {
  from_node_id: string;
  to_node_id: string;
  edge_type: string;
};

type RowPlacement = {
  y: number;
  laneCountsByNextRow: Map<number, number>;
};

export function layoutTraceGraph(nodes: RawNode[], edges: RawEdge[]): TraceGraphLayout {
  if (nodes.length === 0) {
    return { nodes: [], edges: [], width: GRAPH_LAYOUT.minWidth, height: GRAPH_LAYOUT.minHeight };
  }

  const grouped = groupNodes(nodes);
  const groupRowByType = new Map(grouped.map(([type], index) => [type, index]));
  const rowEdgeCounts = edgeCountsByRowPair(edges, nodes, groupRowByType);
  const rowPlacements = placeRows(grouped, rowEdgeCounts);
  const width = Math.max(
    GRAPH_LAYOUT.minWidth,
    ...grouped.map(([type, group]) => {
      const size = NODE_SIZE_BY_TYPE[type];
      return (
        GRAPH_LAYOUT.sidePadding * 2 +
        group.length * size.width +
        Math.max(group.length - 1, 0) * GRAPH_LAYOUT.minNodeGap
      );
    }),
  );
  const lastGroup = grouped[grouped.length - 1];
  const lastRow = rowPlacements[grouped.length - 1];
  const height = Math.max(
    GRAPH_LAYOUT.minHeight,
    lastRow.y + NODE_SIZE_BY_TYPE[lastGroup[0]].height + GRAPH_LAYOUT.bottomPadding,
  );

  const placedNodes: TraceNode[] = grouped.flatMap(([type, group], rowIndex) => {
    const y = rowPlacements[rowIndex].y;
    const size = NODE_SIZE_BY_TYPE[type];
    const availableWidth = width - GRAPH_LAYOUT.sidePadding * 2;
    const spacing = availableWidth / Math.max(group.length, 1);
    return group.map((node, index) => {
      const centerX = GRAPH_LAYOUT.sidePadding + spacing * index + spacing / 2;
      const x = Math.max(GRAPH_LAYOUT.sidePadding, centerX - size.width / 2);
      return {
        node_id: node.node_id,
        node_type: node.node_type,
        title: compactText(node.title || node.node_id, TITLE_LENGTH_BY_TYPE[type]),
        subtitle: node.node_type.replace('_', ' '),
        score: compactText(node.summary, SUMMARY_LENGTH_BY_TYPE[type]),
        x,
        y,
        width: size.width,
        height: size.height,
        rowIndex,
        columnIndex: index,
      };
    });
  });

  const byId = new Map(placedNodes.map((node) => [node.node_id, node]));
  const routableEdges = edges
    .map((edge) => {
      const from = byId.get(edge.from_node_id);
      const to = byId.get(edge.to_node_id);
      return from && to
        ? {
            edge,
            from,
            to,
            laneKey: edgeLaneKey(from, to),
            normalizedType: normalizeEdgeType(edge.edge_type),
            rowPairKey: edgeRowPairKey(from, to),
          }
        : null;
    })
    .filter((edge): edge is NonNullable<typeof edge> => edge !== null);

  const laneCounts = routableEdges.reduce((counts, edge) => {
    counts.set(edge.laneKey, (counts.get(edge.laneKey) ?? 0) + 1);
    return counts;
  }, new Map<string, number>());
  const laneIndexes = new Map<string, number>();
  const rowPairLaneIndexes = new Map<string, number>();

  const placedEdges: TraceEdge[] = routableEdges.map(({ edge, from, to, laneKey, normalizedType, rowPairKey }) => {
    const laneIndex = laneIndexes.get(laneKey) ?? 0;
    laneIndexes.set(laneKey, laneIndex + 1);
    const rowPairLaneIndex = rowPairLaneIndexes.get(rowPairKey) ?? 0;
    rowPairLaneIndexes.set(rowPairKey, rowPairLaneIndex + 1);
    const route = routeTraceEdge(
      from,
      to,
      laneIndex,
      laneCounts.get(laneKey) ?? 1,
      rowPairLaneIndex,
      rowPlacements,
    );
    return {
      from_node_id: edge.from_node_id,
      to_node_id: edge.to_node_id,
      edge_type: normalizedType,
      weight: labelForEdge(normalizedType),
      points: route.points,
      labelX: route.labelX,
      labelY: route.labelY,
    };
  });

  return { nodes: placedNodes, edges: placedEdges, width, height };
}

function groupNodes(nodes: RawNode[]): Array<[TraceNodeType, RawNode[]]> {
  return NODE_ORDER.map((type) => [type, nodes.filter((node) => node.node_type === type)] as [TraceNodeType, RawNode[]])
    .filter(([, group]) => group.length > 0);
}

function placeRows(
  grouped: Array<[TraceNodeType, RawNode[]]>,
  rowEdgeCounts: Map<string, number>,
): RowPlacement[] {
  let nextY = GRAPH_LAYOUT.topPadding;
  return grouped.map(([type], rowIndex) => {
    const y = nextY;
    const laneCountsByNextRow = new Map<number, number>();
    if (rowIndex < grouped.length - 1) {
      const nextRow = rowIndex + 1;
      const edgeCount = rowEdgeCounts.get(rowPairKey(rowIndex, nextRow)) ?? 0;
      const laneCount = Math.min(Math.max(edgeCount, 1), GRAPH_LAYOUT.maxEdgeLanes);
      laneCountsByNextRow.set(nextRow, laneCount);
      const laneSpace = GRAPH_LAYOUT.edgeLaneClearance * 2 + Math.max(laneCount - 1, 0) * GRAPH_LAYOUT.edgeLaneGap;
      nextY += NODE_SIZE_BY_TYPE[type].height + Math.max(GRAPH_LAYOUT.rowGap, laneSpace + 42);
    }
    return { y, laneCountsByNextRow };
  });
}

function routeTraceEdge(
  from: TraceNode,
  to: TraceNode,
  laneIndex: number,
  laneCount: number,
  rowPairLaneIndex: number,
  rowPlacements: RowPlacement[],
): { points: string; labelX: number; labelY: number } {
  const fromCenterX = from.x + from.width / 2;
  const fromCenterY = from.y + from.height / 2;
  const toCenterX = to.x + to.width / 2;
  const toCenterY = to.y + to.height / 2;
  const laneOffset = edgeLaneOffset(laneIndex, laneCount);

  if (Math.abs(fromCenterY - toCenterY) < 16) {
    const fromIsLeft = fromCenterX <= toCenterX;
    const startX = fromIsLeft ? from.x + from.width : from.x;
    const endX = fromIsLeft ? to.x : to.x + to.width;
    const startY = fromCenterY;
    const endY = toCenterY;
    const midX = (startX + endX) / 2;
    const routeAbove = laneIndex % 2 === 0;
    const laneStep = Math.floor(laneIndex / 2) * GRAPH_LAYOUT.edgeLaneGap;
    const midY = routeAbove
      ? Math.min(from.y, to.y) - 18 - laneStep
      : Math.max(from.y + from.height, to.y + to.height) + 18 + laneStep;
    return {
      points: `${startX},${startY} ${midX},${startY} ${midX},${midY} ${endX},${midY} ${endX},${endY}`,
      labelX: midX,
      labelY: midY,
    };
  }

  const flowsDown = fromCenterY < toCenterY;
  const startX = clamp(fromCenterX + laneOffset * 0.65, from.x + 12, from.x + from.width - 12);
  const startY = flowsDown ? from.y + from.height : from.y;
  const endX = clamp(toCenterX - laneOffset * 0.65, to.x + 12, to.x + to.width - 12);
  const endY = flowsDown ? to.y : to.y + to.height;
  const midY = interRowLaneY(from, to, rowPairLaneIndex, rowPlacements);
  return {
    points: `${startX},${startY} ${startX},${midY} ${endX},${midY} ${endX},${endY}`,
    labelX: edgeLabelX(startX, endX, from, to),
    labelY: midY,
  };
}

function edgeLaneKey(from: TraceNode, to: TraceNode): string {
  if (from.rowIndex === to.rowIndex) {
    return `row:${from.rowIndex}:${Math.min(from.columnIndex ?? 0, to.columnIndex ?? 0)}:${Math.max(
      from.columnIndex ?? 0,
      to.columnIndex ?? 0,
    )}`;
  }
  return `rows:${Math.min(from.rowIndex ?? 0, to.rowIndex ?? 0)}:${Math.max(from.rowIndex ?? 0, to.rowIndex ?? 0)}`;
}

function edgeRowPairKey(from: TraceNode, to: TraceNode): string {
  return rowPairKey(from.rowIndex ?? 0, to.rowIndex ?? 0);
}

function rowPairKey(firstRow: number, secondRow: number): string {
  return `${Math.min(firstRow, secondRow)}:${Math.max(firstRow, secondRow)}`;
}

function edgeCountsByRowPair(
  edges: RawEdge[],
  nodes: RawNode[],
  groupRowByType: Map<TraceNodeType, number>,
): Map<string, number> {
  const rowByNodeId = new Map(
    nodes.map((node) => [node.node_id, groupRowByType.get(node.node_type)]),
  );
  return edges.reduce((counts, edge) => {
    const fromRow = rowByNodeId.get(edge.from_node_id);
    const toRow = rowByNodeId.get(edge.to_node_id);
    if (fromRow === undefined || toRow === undefined || fromRow === toRow) {
      return counts;
    }
    const key = rowPairKey(fromRow, toRow);
    counts.set(key, (counts.get(key) ?? 0) + 1);
    return counts;
  }, new Map<string, number>());
}

function interRowLaneY(from: TraceNode, to: TraceNode, laneIndex: number, rowPlacements: RowPlacement[]): number {
  const upper = from.y <= to.y ? from : to;
  const lower = from.y <= to.y ? to : from;
  const upperRowIndex = upper.rowIndex ?? 0;
  const lowerRowIndex = lower.rowIndex ?? upperRowIndex + 1;
  const top = upper.y + upper.height + GRAPH_LAYOUT.edgeLaneClearance;
  const bottom = lower.y - GRAPH_LAYOUT.edgeLaneClearance;
  const rowLaneCount = rowPlacements[upperRowIndex]?.laneCountsByNextRow.get(lowerRowIndex) ?? 1;
  const laneSlots = Math.min(Math.max(rowLaneCount, 1), GRAPH_LAYOUT.maxEdgeLanes);
  const slot = laneIndex % laneSlots;
  const laneY = top + slot * GRAPH_LAYOUT.edgeLaneGap;
  return clamp(laneY, top, Math.max(top, bottom));
}

function edgeLabelX(startX: number, endX: number, from: TraceNode, to: TraceNode): number {
  const left = Math.min(startX, endX);
  const right = Math.max(startX, endX);
  const nodeLeft = Math.min(from.x, to.x);
  const nodeRight = Math.max(from.x + from.width, to.x + to.width);
  const preferred = (startX + endX) / 2;
  if (preferred < nodeLeft || preferred > nodeRight) {
    return preferred;
  }
  const leftGap = Math.max(0, nodeLeft - left);
  const rightGap = Math.max(0, right - nodeRight);
  if (rightGap >= 48 || rightGap >= leftGap) {
    return clamp(nodeRight + 24, left + 24, right - 24);
  }
  return clamp(nodeLeft - 24, left + 24, right - 24);
}

function edgeLaneOffset(laneIndex: number, laneCount: number): number {
  const laneSlots = Math.min(laneCount, GRAPH_LAYOUT.maxEdgeLanes);
  const laneSlot = laneIndex % laneSlots;
  return (laneSlot - (laneSlots - 1) / 2) * GRAPH_LAYOUT.edgeLaneGap;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function compactText(value: string, maxLength: number): string {
  const trimmed = value.trim();
  return trimmed.length > maxLength ? `${trimmed.slice(0, Math.max(maxLength - 1, 1))}...` : trimmed;
}

function normalizeEdgeType(value: string): TraceEdgeType {
  const normalized = value.trim().toLowerCase().replaceAll('-', '_');
  if (normalized === 'summarizes_argument') {
    return 'uses_round_summary';
  }
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
