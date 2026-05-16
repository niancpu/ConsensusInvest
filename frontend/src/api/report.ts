import { apiGet, type ListResponse, type SingleResponse } from './http';
import type {
  BenefitsRisksView,
  ConceptRadarItem,
  EventImpactRankingView,
  IndexIntraday,
  IndexOverview,
  IndustryDetailsView,
  MarketStocksList,
  MarketWarning,
  SearchTaskStatusView,
  StockAnalysisView,
  StockSearchHit,
} from '../types/report';

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
