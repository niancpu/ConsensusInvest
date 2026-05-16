import type { AgentArgument, RoundSummary } from '../../../types/workflow';
import type { EvidenceDetail, RawItemDetail } from '../../../types/evidence';
import type { TraceNodeType } from '../../../types/trace';

type GenericSelectedNode<T extends TraceNodeType> = {
  node_id: string;
  node_type: T;
  title: string;
  summary: string;
};

export type SelectedNode =
  | GenericSelectedNode<'agent'>
  | GenericSelectedNode<'agent_run'>
  | GenericSelectedNode<'search_request'>
  | GenericSelectedNode<'judgment'>
  | (GenericSelectedNode<'round_summary'> & { detail?: RoundSummary })
  | (GenericSelectedNode<'agent_argument'> & { detail?: AgentArgument })
  | {
      node_id: string;
      node_type: 'evidence';
      title: string;
      summary: string;
      detail?: EvidenceDetail;
      rawDetail?: RawItemDetail;
      rawDetailError?: string;
    }
  | (GenericSelectedNode<'raw_item'> & { detail?: RawItemDetail });
