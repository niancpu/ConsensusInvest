import { FormEvent, type ReactNode, useEffect, useState } from 'react';
import {
  BenefitsRisksView,
  ConceptRadarItem,
  EventImpactRankingView,
  IndexOverview,
  IndustryDetailsView,
  MarketWarning,
  StockAnalysisView,
  StockSearchHit,
  getBenefitsRisks,
  getConceptRadar,
  getEventImpactRanking,
  getIndexOverview,
  getIndustryDetails,
  getMarketWarnings,
  getStockAnalysis,
  searchStocks,
} from '../../api/report';
import { formatApiError } from '../../api/errors';
import GlobalNav from '../../components/GlobalNav';
import './ReportPage.css';

type ReportBundle = {
  analysis: StockAnalysisView;
  industry: IndustryDetailsView;
  events: EventImpactRankingView;
  benefitsRisks: BenefitsRisksView;
};

function ReportPage() {
  const [stockCode, setStockCode] = useState('002594.SZ');
  const [searchText, setSearchText] = useState('002594');
  const [searchHits, setSearchHits] = useState<StockSearchHit[]>([]);
  const [report, setReport] = useState<ReportBundle | null>(null);
  const [market, setMarket] = useState<IndexOverview | null>(null);
  const [concepts, setConcepts] = useState<ConceptRadarItem[]>([]);
  const [warnings, setWarnings] = useState<MarketWarning[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    const controller = new AbortController();
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
        if (!controller.signal.aborted) {
          setErrorMessage(formatApiError(error, '市场报告加载失败'));
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadReport(stockCode, controller.signal);
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
    setLoading(true);
    setErrorMessage('');
    try {
      const [analysis, industry, events, benefitsRisks] = await Promise.all([
        getStockAnalysis(nextStockCode, signal),
        getIndustryDetails(nextStockCode, signal),
        getEventImpactRanking(nextStockCode, signal),
        getBenefitsRisks(nextStockCode, signal),
      ]);
      setReport({ analysis, industry, events, benefitsRisks });
    } catch (error) {
      if (!signal?.aborted) {
        setErrorMessage(formatApiError(error, '资讯报告加载失败'));
      }
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }

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
            <strong>{report?.analysis.stock_name ?? stockCode}</strong>
            <span>Data State</span>
            <strong>{report?.analysis.data_state ?? '-'}</strong>
            <span>Report Run</span>
            <strong>{report?.analysis.report_run_id.slice(-8) ?? '-'}</strong>
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
        </aside>

        <section className="report-main" aria-busy={loading}>
          <div className="report-heading">
            <div>
              <span>Report Module</span>
              <h2>{report?.analysis.report.title ?? '个股研究聚合视图'}</h2>
            </div>
            <a className="secondary-action" href={`#analysis?ticker=${report?.analysis.ticker ?? stockCode}`}>
              进入主分析
            </a>
          </div>

          <article className="report-summary">
            <h3>{report?.analysis.stock_name ?? stockCode}</h3>
            <p>{report?.analysis.report.summary ?? '正在读取 Report Module 视图。'}</p>
            {report?.analysis.action ? (
              <div className={`signal-pill ${report.analysis.action.signal}`}>
                <strong>{report.analysis.action.label}</strong>
                <span>{report.analysis.action.reason}</span>
              </div>
            ) : (
              <div className="signal-pill neutral">
                <strong>{report?.analysis.report_mode ?? 'report_generation'}</strong>
                <span>无主链路 Judgment 时不展示投资建议。</span>
              </div>
            )}
          </article>

          <section className="report-grid">
            <Panel title="关键证据">
              {(report?.analysis.report.key_evidence ?? []).map((item) => (
                <article className="report-item" key={item.evidence_id}>
                  <h4>{item.title}</h4>
                  <p>{item.objective_summary}</p>
                  <small>{item.evidence_id}</small>
                </article>
              ))}
            </Panel>

            <Panel title="行业详情">
              {report ? (
                <article className="report-item">
                  <h4>{report.industry.industry_name}</h4>
                  <p>{report.industry.policy_support_desc}</p>
                  <p>{report.industry.supply_demand_status} / {report.industry.competition_landscape}</p>
                </article>
              ) : null}
            </Panel>

            <Panel title="事件影响">
              {(report?.events.items ?? []).map((item) => (
                <article className="report-item" key={item.event_name}>
                  <h4>{item.event_name}</h4>
                  <p>{item.impact_level} / {item.direction ?? '无方向'} / {item.impact_score}</p>
                  <small>{item.evidence_ids.join(', ') || '-'}</small>
                </article>
              ))}
            </Panel>

            <Panel title="利好与风险">
              {[...(report?.benefitsRisks.benefits ?? []), ...(report?.benefitsRisks.risks ?? [])].map((item) => (
                <article className="report-item" key={`${item.source}-${item.text}`}>
                  <h4>{item.source}</h4>
                  <p>{item.text}</p>
                  <small>{item.evidence_ids.join(', ') || '-'}</small>
                </article>
              ))}
            </Panel>
          </section>
        </section>

        <aside className="market-report">
          <h2>市场报告</h2>
          <div className="market-state">
            <span>{market?.market_sentiment.label ?? '-'}</span>
            <strong>{market?.market_sentiment.score ?? '-'}</strong>
          </div>
          {(market?.indices ?? []).map((item) => (
            <div className="market-row" key={item.code}>
              <span>{item.name}</span>
              <strong>{item.value.toFixed(2)}</strong>
              <em className={item.is_up ? 'up' : 'down'}>{item.change_rate.toFixed(2)}%</em>
            </div>
          ))}
          <h3>概念雷达</h3>
          {concepts.map((item) => (
            <div className="market-row" key={item.entity_id}>
              <span>{item.concept_name}</span>
              <strong>{item.heat_score}</strong>
              <em>{item.status}</em>
            </div>
          ))}
          <h3>预警</h3>
          {warnings.map((item) => (
            <article className="warning-item" key={item.warning_id}>
              <strong>{item.title}</strong>
              <p>{item.content}</p>
            </article>
          ))}
        </aside>
      </section>
    </main>
  );
}

function Panel({ children, title }: { children: ReactNode; title: string }) {
  return (
    <section className="report-panel">
      <h3>{title}</h3>
      <div>{children}</div>
    </section>
  );
}

export default ReportPage;
