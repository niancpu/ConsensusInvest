import type { TraceNode } from '../../../types/trace';

type Props = {
  isInteractive: boolean;
  isSelected: boolean;
  node: TraceNode;
  onSelect: (nodeId: string) => void;
};

export default function TraceNodeShape({ isInteractive, isSelected, node, onSelect }: Props) {
  const isCompactNode =
    node.node_type === 'search_request' || node.node_type === 'evidence' || node.node_type === 'raw_item';
  const titleY = node.y + (isCompactNode ? 21 : 28);
  const subtitleY = node.y + (isCompactNode ? 39 : 49);

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
      <text className="node-title" x={node.x + node.width / 2} y={titleY}>{node.title}</text>
      <text className="node-subtitle" x={node.x + node.width / 2} y={subtitleY}>
        {node.subtitle} {node.score}
      </text>
    </g>
  );
}
