import { API_TIMEOUT_REASON, ApiRequestError, isAbortError, isTimeoutError, toApiError } from './errors';
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

const REPORT_TIMEOUT_MS = 10_000;
const REPORT_RETRY_DELAY_MS = 500;
const REPORT_RETRY_ATTEMPTS = 2;

export async function searchStocks(keyword: string, signal?: AbortSignal): Promise<StockSearchHit[]> {
  const params = new URLSearchParams({ keyword, limit: '10', include_evidence: 'true' });
  return apiGet<ListResponse<StockSearchHit>>(`/api/v1/stocks/search?${params.toString()}`, signal).then(
    (response) => response.data,
  );
}

export async function getStockAnalysis(stockCode: string, signal?: AbortSignal): Promise<StockAnalysisView> {
  const params = new URLSearchParams({ refresh: 'never', latest: 'true' });
  return getReportResource<SingleResponse<StockAnalysisView>>(
    `/api/v1/stocks/${encodeURIComponent(stockCode)}/analysis?${params.toString()}`,
    signal,
  ).then((response) => response.data);
}

export async function getIndustryDetails(stockCode: string, signal?: AbortSignal): Promise<IndustryDetailsView> {
  return getReportResource<SingleResponse<IndustryDetailsView>>(
    `/api/v1/stocks/${encodeURIComponent(stockCode)}/industry-details`,
    signal,
  ).then((response) => response.data);
}

export async function getEventImpactRanking(stockCode: string, signal?: AbortSignal): Promise<EventImpactRankingView> {
  return getReportResource<SingleResponse<EventImpactRankingView>>(
    `/api/v1/stocks/${encodeURIComponent(stockCode)}/event-impact-ranking?limit=10`,
    signal,
  ).then((response) => response.data);
}

export async function getBenefitsRisks(stockCode: string, signal?: AbortSignal): Promise<BenefitsRisksView> {
  return getReportResource<SingleResponse<BenefitsRisksView>>(
    `/api/v1/stocks/${encodeURIComponent(stockCode)}/benefits-risks`,
    signal,
  ).then((response) => response.data);
}

export async function getIndexOverview(signal?: AbortSignal): Promise<IndexOverview> {
  return getReportResource<SingleResponse<IndexOverview>>('/api/v1/market/index-overview?refresh=stale', signal).then(
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
  return getReportResource<ListResponse<ConceptRadarItem>>('/api/v1/market/concept-radar?limit=8&refresh=stale', signal).then(
    (response) => response.data,
  );
}

export async function getMarketWarnings(signal?: AbortSignal): Promise<MarketWarning[]> {
  return getReportResource<ListResponse<MarketWarning>>('/api/v1/market/warnings?limit=8&refresh=stale', signal).then(
    (response) => response.data,
  );
}

async function getReportResource<T>(path: string, signal?: AbortSignal): Promise<T> {
  let lastError: unknown;

  for (let attempt = 0; attempt <= REPORT_RETRY_ATTEMPTS; attempt += 1) {
    try {
      return await apiGet<T>(path, { signal, timeoutMs: REPORT_TIMEOUT_MS });
    } catch (error) {
      const normalizedError = toApiError(error, path, signal?.reason);
      if (signal?.aborted || isAbortError(normalizedError) || !shouldRetry(normalizedError) || attempt === REPORT_RETRY_ATTEMPTS) {
        throw normalizedError;
      }
      lastError = normalizedError;
    }

    await delay(REPORT_RETRY_DELAY_MS, signal);
  }

  throw lastError;
}

function shouldRetry(error: unknown): boolean {
  if (error instanceof TypeError || isTimeoutError(error)) {
    return true;
  }
  if (error instanceof ApiRequestError) {
    return error.status >= 500;
  }
  return false;
}

async function delay(ms: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    throw new DOMException('The operation was aborted.', 'AbortError');
  }

  await new Promise<void>((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      signal?.removeEventListener('abort', abort);
      resolve();
    }, ms);

    const abort = () => {
      window.clearTimeout(timeoutId);
      reject(new DOMException('The operation was aborted.', 'AbortError'));
    };

    signal?.addEventListener('abort', abort, { once: true });
  });
}
