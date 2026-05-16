export type StockSearchHit = {
  stock_code: string;
  ticker: string;
  exchange: string;
  name: string;
  market: string;
  entity_id: string;
  evidence_matches: Array<{
    evidence_id: string;
    title: string;
    objective_summary: string;
    published_at: string;
    source_quality: number;
  }>;
};

export type StockAnalysisView = {
  stock_code: string;
  ticker: string;
  stock_name: string;
  entity_id: string;
  workflow_run_id: string | null;
  judgment_id: string | null;
  report_run_id: string;
  report_mode: 'report_generation' | 'with_workflow_trace';
  data_state: string;
  hero: {
    title: string;
    summary: string;
    status_note: string;
    source_note: string;
    limitation_note: string | null;
    meta: Array<{
      label: string;
      value: string;
    }>;
  };
  action: {
    label: string;
    signal: 'positive' | 'neutral' | 'negative';
    reason: string;
    source: string;
  } | null;
  report: {
    title: string;
    summary: string;
    key_evidence: Array<{
      evidence_id: string;
      title: string;
      objective_summary: string;
      publish_time?: string;
      fetched_at?: string;
      source_quality: number;
      relevance: number;
    }>;
    risks: Array<{
      text: string;
      evidence_ids: string[];
      source: string;
    }>;
  };
  trace_refs: {
    evidence_ids: string[];
    market_snapshot_ids: string[];
    workflow_run_id: string | null;
    judgment_id: string | null;
  };
  links: {
    workflow_run: string | null;
    trace: string | null;
    judgment: string | null;
    entity: string | null;
  };
  updated_at: string;
};

export type EventImpactRankingView = {
  stock_code: string;
  ticker: string;
  report_run_id: string;
  ranker: string;
  items: Array<{
    event_name: string;
    impact_score: number;
    impact_level: 'low' | 'medium' | 'high';
    direction: 'positive' | 'neutral' | 'negative' | null;
    evidence_ids: string[];
    workflow_run_id: string | null;
    judgment_id: string | null;
  }>;
  updated_at: string;
};

export type BenefitsRisksView = {
  stock_code: string;
  ticker: string;
  workflow_run_id: string | null;
  report_run_id: string;
  benefits: Array<{ text: string; evidence_ids: string[]; source: string }>;
  risks: Array<{ text: string; evidence_ids: string[]; source: string }>;
  updated_at: string;
};

export type IndexOverview = {
  report_run_id: string;
  indices: Array<{
    name: string;
    code: string;
    value: number;
    change_rate: number;
    is_up: boolean;
    snapshot_id: string;
  }>;
  market_sentiment: {
    label: string;
    score: number;
    source: string;
    snapshot_ids: string[];
  };
  data_state: string;
  refresh_task_id: string | null;
  updated_at: string;
};

export type IndexIntraday = {
  report_run_id: string;
  code: string;
  name: string;
  trade_date: string;
  points: Array<{
    time: string;
    timestamp: string;
    value: number;
    change: number | null;
    change_rate: number | null;
    volume: number | null;
    amount: number | null;
  }>;
  previous_close: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  snapshot_ids: string[];
  data_state: string;
  refresh_task_id: string | null;
  updated_at: string;
};

export type SearchTaskStatusView = {
  task_id: string;
  status: string;
  last_error: string | null;
  source_status: Array<{
    source: string;
    status: string;
    error: string | null;
    items_count: number;
    ingested_count: number;
    rejected_count: number;
  }>;
};

export type MarketStocksList = {
  report_run_id: string;
  list: Array<{
    stock_code: string;
    ticker: string;
    name: string;
    price: number;
    change_rate: number;
    is_up: boolean;
    view_score: number;
    view_label: string;
    entity_id: string;
    snapshot_id: string;
  }>;
  pagination: {
    page: number;
    page_size: number;
    total: number;
  };
  data_state: string;
  refresh_task_id: string | null;
};

export type ConceptRadarItem = {
  concept_name: string;
  entity_id: string;
  status: string;
  heat_score: number;
  trend: 'warming' | 'cooling' | 'flat';
  snapshot_ids: string[];
  evidence_ids: string[];
};

export type MarketWarning = {
  warning_id: string;
  time: string;
  title: string;
  content: string;
  severity: 'info' | 'notice' | 'alert';
  related_stock_codes: string[];
  related_entity_ids: string[];
  snapshot_ids: string[];
  evidence_ids: string[];
};
