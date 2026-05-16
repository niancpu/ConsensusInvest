export type TraceNodeType = 'judgment' | 'agent_argument' | 'evidence' | 'raw_item' | 'round_summary';

export type TraceEdgeType =
  | 'uses_argument'
  | 'supports'
  | 'counters'
  | 'refuted'
  | 'derived_from'
  | 'cited'
  | 'uses_round_summary';

export type WorkflowTrace = {
  workflow_run_id: string;
  judgment_id?: string | null;
  trace_nodes: Array<{
    node_type: TraceNodeType;
    node_id: string;
    title: string;
    summary: string;
  }>;
  trace_edges: Array<{
    from_node_id: string;
    to_node_id: string;
    edge_type: string;
  }>;
};

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
  rowIndex?: number;
  columnIndex?: number;
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

export type TraceGraphLayout = {
  nodes: TraceNode[];
  edges: TraceEdge[];
  width: number;
  height: number;
};
