import type { EvidenceSnapshot } from './workflow';

export type EvidenceDetail = EvidenceSnapshot & {
  workflow_run_id?: string | null;
  objective_summary?: string | null;
  entities: string[];
  tags: string[];
  key_facts: Array<Record<string, unknown>>;
  claims: Array<Record<string, unknown>>;
  structuring_confidence?: number | null;
  quality_notes: string[];
  links: {
    structure: string;
    raw: string;
    references: string;
  };
};

export type RawItemDetail = {
  raw_ref: string;
  workflow_run_id?: string | null;
  source?: string | null;
  source_type?: string | null;
  ticker?: string | null;
  title?: string | null;
  content?: string | null;
  url?: string | null;
  publish_time?: string | null;
  fetched_at?: string | null;
  raw_payload: Record<string, unknown>;
  derived_evidence_ids: string[];
};
