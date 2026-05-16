import type { AgentArgument, RoundSummary } from '../../../types/workflow';
import type { EvidenceDetail, RawItemDetail } from '../../../types/evidence';

export type SelectedNode =
  | { node_id: string; node_type: 'judgment'; title: string; summary: string }
  | { node_id: string; node_type: 'round_summary'; title: string; summary: string; detail?: RoundSummary }
  | { node_id: string; node_type: 'agent_argument'; title: string; summary: string; detail?: AgentArgument }
  | { node_id: string; node_type: 'evidence'; title: string; summary: string; detail?: EvidenceDetail }
  | { node_id: string; node_type: 'raw_item'; title: string; summary: string; detail?: RawItemDetail };
