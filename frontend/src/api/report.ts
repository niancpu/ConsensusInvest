import { readJsonResponse } from './errors';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

type SingleResponse<T> = {
  data: T;
  meta?: {
    request_id?: string;
    data_state?: string;
    refresh_task_id?: string | null;
  };
};

type ListResponse<T> = {
  data: T[];
  pagination?: {
    limit?: number;
    offset?: number;
    total: number;
    has_more?: boolean;
  };
  meta?: {
    request_id?: string;
    data_state?: string;
    refresh_task_id?: string | null;
  };
};

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

export type IndustryDetailsView = {
  stock_code: string;
  ticker: string;
  industry_entity_id: string;
  industry_name: string;
  policy_support_level: 'low' | 'medium' | 'high';
  policy_support_desc: string;
  supply_demand_status: string;
  competition_landscape: string;
  referenced_evidence_ids: string[];
  market_snapshot_ids: string[];
  updated_at: string;
};

export type EventImpactRankingView = {
  stock_code: string;
  ticker: string;
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

export async function searchStocks(keyword: string, signal?: AbortSignal): Promise<StockSearchHit[]> {
  const params = new URLSearchParams({ keyword, limit: '10', include_evidence: 'true' });
  return apiGet<ListResponse<StockSearchHit>>(`/api/v1/stocks/search?${params.toString()}`, signal).then(
    (response) => response.data,
  );
}

export async function getStockAnalysis(stockCode: string, signal?: AbortSignal): Promise<StockAnalysisView> {
  const params = new URLSearchParams({ refresh: 'never', latest: 'true' });
  return apiGet<SingleResponse<StockAnalysisView>>(
    `/api/v1/stocks/${encodeURIComponent(stockCode)}/analysis?${params.toString()}`,
    signal,
  ).then((response) => response.data);
}

export async function getIndustryDetails(stockCode: string, signal?: AbortSignal): Promise<IndustryDetailsView> {
  return apiGet<SingleResponse<IndustryDetailsView>>(
    `/api/v1/stocks/${encodeURIComponent(stockCode)}/industry-details`,
    signal,
  ).then((response) => response.data);
}

export async function getEventImpactRanking(stockCode: string, signal?: AbortSignal): Promise<EventImpactRankingView> {
  return apiGet<SingleResponse<EventImpactRankingView>>(
    `/api/v1/stocks/${encodeURIComponent(stockCode)}/event-impact-ranking?limit=10`,
    signal,
  ).then((response) => response.data);
}

export async function getBenefitsRisks(stockCode: string, signal?: AbortSignal): Promise<BenefitsRisksView> {
  return apiGet<SingleResponse<BenefitsRisksView>>(
    `/api/v1/stocks/${encodeURIComponent(stockCode)}/benefits-risks`,
    signal,
  ).then((response) => response.data);
}

export async function getIndexOverview(signal?: AbortSignal): Promise<IndexOverview> {
  return apiGet<SingleResponse<IndexOverview>>('/api/v1/market/index-overview?refresh=stale', signal).then(
    (response) => response.data,
  );
}

export async function getIndexIntraday(code = '000001.SH', signal?: AbortSignal): Promise<IndexIntraday> {
  const params = new URLSearchParams({ code, refresh: 'stale' });
  return apiGet<SingleResponse<IndexIntraday>>(`/api/v1/market/index-intraday?${params.toString()}`, signal).then(
    (response) => response.data,
  );
}

export async function getSearchTaskStatus(taskId: string, signal?: AbortSignal): Promise<SearchTaskStatusView> {
  return apiGet<SingleResponse<SearchTaskStatusView>>(
    `/api/v1/search-tasks/${encodeURIComponent(taskId)}`,
    signal,
  ).then((response) => response.data);
}

export async function getMarketStocks(signal?: AbortSignal): Promise<MarketStocksList> {
  return apiGet<SingleResponse<MarketStocksList>>('/api/v1/market/stocks?page=1&page_size=5&refresh=stale', signal).then(
    (response) => response.data,
  );
}

export async function getConceptRadar(signal?: AbortSignal): Promise<ConceptRadarItem[]> {
  return apiGet<ListResponse<ConceptRadarItem>>('/api/v1/market/concept-radar?limit=8&refresh=stale', signal).then(
    (response) => response.data,
  );
}

export async function getMarketWarnings(signal?: AbortSignal): Promise<MarketWarning[]> {
  return apiGet<ListResponse<MarketWarning>>('/api/v1/market/warnings?limit=8&refresh=stale', signal).then(
    (response) => response.data,
  );
}

async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(withBase(path), {
    headers: {
      Accept: 'application/json',
    },
    signal,
  });
  return readJson<T>(response);
}

async function readJson<T>(response: Response): Promise<T> {
  return readJsonResponse<T>(response, response.url);
}

function withBase(path: string): string {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }
  return `${API_BASE}${path}`;
}
