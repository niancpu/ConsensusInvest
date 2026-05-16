import type { TraceGraphLayout } from '../../../types/trace';
import TraceNodeShape from './TraceNodeShape';

type Props = {
  graph: TraceGraphLayout;
  traceNodeIds: Set<string>;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
};

export default function TraceGraph({ graph, traceNodeIds, selectedNodeId, onSelectNode }: Props) {
  return (
    <svg
      className="trace-graph"
      height={graph.height}
      role="img"
      viewBox={`0 0 ${graph.width} ${graph.height}`}
      width={graph.width}
      aria-labelledby="trace-title"
    >
      <title id="trace-title">Workflow trace graph</title>
      <defs>
        <pattern id="grid" width="62" height="62" patternUnits="userSpaceOnUse">
          <path
            d="M 62 0 L 0 0 0 62"
            fill="none"
            stroke="#000000"
            strokeDasharray="2 3"
            strokeWidth="0.5"
            opacity="0.35"
          />
        </pattern>
      </defs>
      <rect className="graph-grid" x="0" y="0" width={graph.width} height={graph.height} fill="url(#grid)" />

      {graph.edges.map((edge) => (
        <g
          className={`trace-edge ${edge.edge_type}`}
          key={`${edge.from_node_id}-${edge.to_node_id}-${edge.edge_type}`}
        >
          <polyline points={edge.points} />
          <rect x={edge.labelX - 20} y={edge.labelY - 11} width="40" height="22" />
          <text x={edge.labelX} y={edge.labelY + 4}>{edge.weight}</text>
        </g>
      ))}

      {graph.nodes.map((node) => (
        <TraceNodeShape
          isInteractive={traceNodeIds.has(node.node_id)}
          isSelected={selectedNodeId === node.node_id}
          key={node.node_id}
          node={node}
          onSelect={onSelectNode}
        />
      ))}
    </svg>
  );
}
