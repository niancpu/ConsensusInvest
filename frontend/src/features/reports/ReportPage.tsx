import { FormEvent, type ReactNode, useEffect, useState } from 'react';
import {
  getBenefitsRisks,
  getConceptRadar,
  getEventImpactRanking,
  getIndexOverview,
  getMarketWarnings,
  getStockAnalysis,
  searchStocks,
} from '../../api/report';
import type {
  BenefitsRisksView,
  ConceptRadarItem,
  EventImpactRankingView,
  IndexOverview,
  MarketWarning,
  StockAnalysisView,
  StockSearchHit,
} from '../../types/report';
import { formatApiError, isAbortError } from '../../api/errors';
import GlobalNav from '../../components/GlobalNav';
import './ReportPage.css';

type SectionState<T> = {
  data: T | null;
  loading: boolean;
  error: string;
};

const emptySection = <T,>(): SectionState<T> => ({
  data: null,
  loading: false,
  error: '',
});

function ReportPage() {
  const [stockCode, setStockCode] = useState('002594.SZ');
  const [searchText, setSearchText] = useState('002594');
  const [searchHits, setSearchHits] = useState<StockSearchHit[]>([]);
  const [analysis, setAnalysis] = useState<SectionState<StockAnalysisView>>(() => emptySection());
  const [events, setEvents] = useState<SectionState<EventImpactRankingView>>(() => emptySection());
  const [benefitsRisks, setBenefitsRisks] = useState<SectionState<BenefitsRisksView>>(() => emptySection());
  const [market, setMarket] = useState<IndexOverview | null>(null);
  const [concepts, setConcepts] = useState<ConceptRadarItem[]>([]);
  const [warnings, setWarnings] = useState<MarketWarning[]>([]);
  const [marketLoading, setMarketLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [marketErrorMessage, setMarketErrorMessage] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    setMarketLoading(true);
    setMarketErrorMessage('');
    Promise.all([
      getIndexOverview(controller.signal),
      getConceptRadar(controller.signal),
      getMarketWarnings(controller.signal),
    ])
      .then(([overview, nextConcepts, nextWarnings]) => {
        setMarket(overview);
        setConcepts(nextConcepts);
        setWarnings(nextWarnings);
      })
      .catch((error) => {
        if (!isAbortError(error) && !controller.signal.aborted) {
          setMarketErrorMessage(formatApiError(error, '市场报告加载失败'));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setMarketLoading(false);
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadReport(stockCode, controller.signal);
    return () => controller.abort();
  }, [stockCode]);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!searchText.trim()) {
      return;
    }
    setErrorMessage('');
    try {
      const hits = await searchStocks(searchText.trim());
      setSearchHits(hits);
      if (hits[0]?.stock_code) {
        setStockCode(hits[0].stock_code);
      }
    } catch (error) {
      setErrorMessage(formatApiError(error, '股票搜索失败'));
    }
  }

  async function loadReport(nextStockCode: string, signal?: AbortSignal) {
    setErrorMessage('');
    setAnalysis((current) => ({ data: current.data, loading: true, error: '' }));
    setEvents(emptySection<EventImpactRankingView>());
    setBenefitsRisks(emptySection<BenefitsRisksView>());

    try {
      const nextAnalysis = await getStockAnalysis(nextStockCode, signal);
      if (signal?.aborted) {
        return;
      }
      setAnalysis({ data: nextAnalysis, loading: false, error: '' });
    } catch (error) {
      if (signal?.aborted || isAbortError(error)) {
        return;
      }
      setAnalysis({ data: null, loading: false, error: formatApiError(error, '资讯报告加载失败') });
      return;
    }

    void loadReportSection({
      request: (requestSignal) => getEventImpactRanking(nextStockCode, requestSignal),
      setSection: setEvents,
      signal,
      fallback: '事件影响加载失败',
    });
    void loadReportSection({
      request: (requestSignal) => getBenefitsRisks(nextStockCode, requestSignal),
      setSection: setBenefitsRisks,
      signal,
      fallback: '利好与风险加载失败',
    });
  }

  const currentStockName = analysis.data?.stock_name ?? stockCode;
  const currentDataState = getDataStateLabel(analysis.loading && !analysis.data ? 'loading' : analysis.data?.data_state);
  const currentReportRunId = formatReportRunId(analysis.data?.report_run_id);
  const reportTitle = analysis.data?.report.title ?? '个股研究聚合视图';
  const analysisTicker = analysis.data?.ticker || stockCode;
  const hero = analysis.data?.hero;
  const summaryText = getSummaryText(hero?.summary, analysis.loading);
  const heroTitle = hero?.title ?? currentStockName;
  const heroMeta = hero?.meta ?? [];
  const keyEvidence = analysis.data?.report.key_evidence ?? [];
  const eventItems = events.data?.items ?? [];
  const benefitsRiskItems = buildBenefitsRiskItems(benefitsRisks.data ?? undefined);
  const mainBusy = analysis.loading || events.loading || benefitsRisks.loading;

  return (
    <main className="report-page">
      <GlobalNav active="reports" className="report-nav" />

      <section className="report-shell">
        <aside className="report-sidebar">
          <h1>资讯报告</h1>
          <form className="report-search" onSubmit={handleSearch}>
            <input
              aria-label="股票代码、简称或关键词"
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="002594 / 比亚迪"
            />
            <button type="submit">搜索</button>
          </form>

          <div className="report-meta">
            <span>当前标的</span>
            <strong>{currentStockName}</strong>
            <span>Data State</span>
            <strong>{currentDataState}</strong>
            <span>Report Run</span>
            <strong>{currentReportRunId}</strong>
          </div>

          {searchHits.length > 0 ? (
            <div className="search-hits">
              {searchHits.map((hit) => (
                <button type="button" key={hit.stock_code} onClick={() => setStockCode(hit.stock_code)}>
                  <span>{hit.name}</span>
                  <strong>{hit.stock_code}</strong>
                </button>
              ))}
            </div>
          ) : null}

          {errorMessage ? <div className="report-error">{errorMessage}</div> : null}
          {analysis.error ? <div className="report-error">{analysis.error}</div> : null}
        </aside>

        <section className="report-main" aria-busy={mainBusy}>
          <div className="report-heading">
            <div>
              <span>Report Module</span>
              <h2>{reportTitle}</h2>
              <div className="report-heading-meta">
                <span>{heroTitle}</span>
                <span>{analysis.data?.stock_code ?? stockCode}</span>
                <span>{analysis.data ? getReportModeLabel(analysis.data.report_mode) : '资料汇总视图'}</span>
                <span>{analysis.data ? getDataStateLabel(analysis.data.data_state) : currentDataState}</span>
                <span>{analysis.data ? formatUpdatedAt(analysis.data.updated_at) : '更新时间待加载'}</span>
              </div>
            </div>
            <a className="secondary-action" href={`#analysis?ticker=${encodeURIComponent(analysisTicker)}`}>
              进入主分析
            </a>
          </div>

          <article className="report-summary">
            <h3>{heroTitle}</h3>
            {analysis.error ? <SectionError message={analysis.error} /> : <p>{summaryText}</p>}
            <div className="report-summary-meta">
              {heroMeta.map((item) => (
                <div className="summary-meta-item" key={`${item.label}-${item.value}`}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          </article>

          <section className="report-grid">
            <Panel title="关键证据" className="report-panel--key-evidence">
              {analysis.error ? (
                <SectionError message={analysis.error} />
              ) : keyEvidence.length > 0 ? (
                keyEvidence.map((item) => (
                  <article className="report-item" key={item.evidence_id}>
                    <h4>{item.title}</h4>
                    <p>{item.objective_summary}</p>
                    <small>{item.evidence_id}</small>
                  </article>
                ))
              ) : (
                <EmptyState text={analysis.loading ? '正在读取结构化关键证据。' : '暂无关键证据。'} />
              )}
            </Panel>

            <Panel title="事件影响">
              {events.error ? (
                <SectionError message={events.error} />
              ) : eventItems.length > 0 ? (
                eventItems.map((item) => (
                  <article className="report-item" key={`${item.event_name}-${item.evidence_ids.join(',')}`}>
                    <h4>{item.event_name}</h4>
                    <p>
                      {item.impact_level} / {item.direction ?? '无方向'} / {item.impact_score}
                    </p>
                    <small>{joinEvidenceIds(item.evidence_ids)}</small>
                  </article>
                ))
              ) : (
                <EmptyState text={events.loading ? '正在读取事件影响。' : '暂无事件影响数据。'} />
              )}
            </Panel>

            <Panel title="利好与风险">
              {benefitsRisks.error ? (
                <SectionError message={benefitsRisks.error} />
              ) : benefitsRiskItems.length > 0 ? (
                benefitsRiskItems.map((item) => (
                  <article className="report-item" key={`${item.kind}-${item.source}-${item.text}`}>
                    <h4>{item.heading}</h4>
                    <p>{item.text}</p>
                    <small>{joinEvidenceIds(item.evidence_ids)}</small>
                  </article>
                ))
              ) : (
                <EmptyState text={benefitsRisks.loading ? '正在读取利好与风险。' : '暂无利好或风险信息。'} />
              )}
            </Panel>
          </section>
        </section>

        <aside className="market-report">
          <h2>市场报告</h2>
          <div className="market-state">
            <span>{market?.market_sentiment.label ?? (marketLoading ? '加载中' : '-')}</span>
            <strong>{market?.market_sentiment.score ?? '-'}</strong>
          </div>

          {marketErrorMessage ? <div className="market-error">{marketErrorMessage}</div> : null}

          <div className="market-section">
            {marketLoading && !market ? (
              <p className="market-loading">正在读取市场概览。</p>
            ) : market?.indices.length ? (
              market.indices.map((item) => (
                <div className="market-row" key={item.code}>
                  <span>{item.name}</span>
                  <strong>{item.value.toFixed(2)}</strong>
                  <em className={item.is_up ? 'up' : 'down'}>{item.change_rate.toFixed(2)}%</em>
                </div>
              ))
            ) : (
              <p className="market-empty">暂无指数数据。</p>
            )}
          </div>

          <div className="market-section">
            <h3>概念雷达</h3>
            {concepts.length > 0 ? (
              concepts.map((item) => (
                <div className="market-row" key={item.entity_id}>
                  <span>{item.concept_name}</span>
                  <strong>{item.heat_score}</strong>
                  <em>{item.status}</em>
                </div>
              ))
            ) : (
              <p className="market-empty">{marketLoading ? '正在读取概念雷达。' : '暂无概念雷达数据。'}</p>
            )}
          </div>

          <div className="market-section">
            <h3>预警</h3>
            {warnings.length > 0 ? (
              warnings.map((item) => (
                <article className="warning-item" key={item.warning_id}>
                  <strong>{item.title}</strong>
                  <p>{item.content}</p>
                </article>
              ))
            ) : (
              <p className="market-empty">{marketLoading ? '正在读取市场预警。' : '暂无市场预警。'}</p>
            )}
          </div>
        </aside>
      </section>
    </main>
  );
}

async function loadReportSection<T>({
  request,
  setSection,
  signal,
  fallback,
}: {
  request: (signal?: AbortSignal) => Promise<T>;
  setSection: (value: SectionState<T> | ((current: SectionState<T>) => SectionState<T>)) => void;
  signal?: AbortSignal;
  fallback: string;
}) {
  setSection({ data: null, loading: true, error: '' });
  try {
    const data = await request(signal);
    if (!signal?.aborted) {
      setSection({ data, loading: false, error: '' });
    }
  } catch (error) {
    if (!signal?.aborted && !isAbortError(error)) {
      setSection({ data: null, loading: false, error: formatApiError(error, fallback) });
    }
  }
}

function getSummaryText(summary: string | undefined, loading: boolean) {
  if (summary && summary.trim()) {
    return summary;
  }
  return loading ? '正在读取 Report Module 视图。' : '暂无可展示的顶部摘要。';
}

function getDataStateLabel(dataState: string | undefined) {
  switch (dataState) {
    case 'ready':
      return '已就绪';
    case 'partial':
      return '部分就绪';
    case 'missing':
      return '资料缺失';
    case 'pending_refresh':
      return '等待补齐';
    case 'refreshing':
      return '正在补齐';
    case 'stale':
      return '待更新';
    case 'failed':
      return '加载失败';
    case 'loading':
      return '加载中';
    default:
      return '未加载';
  }
}

function getReportModeLabel(reportMode: StockAnalysisView['report_mode'] | undefined) {
  switch (reportMode) {
    case 'with_workflow_trace':
      return '主链路判断视图';
    case 'report_generation':
      return '资料汇总视图';
    default:
      return '资料汇总视图';
  }
}

function formatUpdatedAt(updatedAt: string | undefined) {
  if (!updatedAt) {
    return '更新时间待加载';
  }
  return `更新于 ${updatedAt.replace('T', ' ').replace('Z', '')}`;
}

function formatReportRunId(reportRunId: string | undefined) {
  if (!reportRunId) {
    return '-';
  }
  return reportRunId.slice(-8);
}

function joinEvidenceIds(evidenceIds: string[]) {
  return evidenceIds.length > 0 ? evidenceIds.join(', ') : '-';
}

function buildBenefitsRiskItems(benefitsRisks: BenefitsRisksView | undefined) {
  if (!benefitsRisks) {
    return [];
  }

  return [
    ...benefitsRisks.benefits.map((item) => ({
      ...item,
      kind: 'benefit' as const,
      heading: `利好 · ${item.source}`,
    })),
    ...benefitsRisks.risks.map((item) => ({
      ...item,
      kind: 'risk' as const,
      heading: `风险 · ${item.source}`,
    })),
  ];
}

function Panel({ children, title, className = '' }: { children: ReactNode; title: string; className?: string }) {
  return (
    <section className={`report-panel ${className}`.trim()}>
      <h3>{title}</h3>
      <div>{children}</div>
    </section>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p className="report-empty">{text}</p>;
}

function SectionError({ message }: { message: string }) {
  return <p className="report-error">{message}</p>;
}

export default ReportPage;
