import { useEffect, useMemo, useState } from 'react';
import {
  IndexIntraday,
  IndexOverview,
  MarketStocksList,
  SearchTaskStatusView,
  getIndexIntraday,
  getIndexOverview,
  getMarketStocks,
  getSearchTaskStatus,
} from '../../api/report';
import { formatApiError } from '../../api/errors';
import GlobalNav from '../../components/GlobalNav';

function HomePage() {
  const [market, setMarket] = useState<IndexOverview | null>(null);
  const [indexIntraday, setIndexIntraday] = useState<IndexIntraday | null>(null);
  const [marketStocks, setMarketStocks] = useState<MarketStocksList | null>(null);
  const [refreshTask, setRefreshTask] = useState<SearchTaskStatusView | null>(null);
  const [marketError, setMarketError] = useState('');
  const [refreshTaskError, setRefreshTaskError] = useState('');
  const primaryIndex = market?.indices[0];
  const chart = useMemo(() => buildChart(indexIntraday), [indexIntraday]);
  const chartEmptyLabel = getChartEmptyLabel(indexIntraday, marketError);
  const indexStats = useMemo(
    () => [
      ['OPEN', formatNumber(indexIntraday?.open)],
      ['HIGH', formatNumber(indexIntraday?.high)],
      ['LOW', formatNumber(indexIntraday?.low)],
      ['PREV', formatNumber(indexIntraday?.previous_close)],
      ['POINTS', String(indexIntraday?.points.length ?? 0)],
      ['VOL', formatLargeNumber(latestPoint(indexIntraday)?.volume)],
      ['AMT', formatLargeNumber(latestPoint(indexIntraday)?.amount)],
      ['STATE', indexIntraday?.data_state ?? '-'],
    ],
    [indexIntraday],
  );
  const tickerItems = useMemo(
    () =>
      marketStocks?.list.map((item) => ({
        time: market?.updated_at ? formatTime(market.updated_at) : '-',
        name: item.name,
        value: item.price.toFixed(2),
        change: `${item.change_rate >= 0 ? '+' : ''}${item.change_rate.toFixed(2)}%`,
        detail: `${item.view_label} / ${item.snapshot_id}`,
      })) ?? [],
    [market?.updated_at, marketStocks],
  );

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      getIndexOverview(controller.signal),
      getIndexIntraday('000001.SH', controller.signal),
      getMarketStocks(controller.signal),
    ])
      .then(([overview, intraday, stocks]) => {
        setMarket(overview);
        setIndexIntraday(intraday);
        setMarketStocks(stocks);
        if (intraday.refresh_task_id) {
          setRefreshTaskError('');
          getSearchTaskStatus(intraday.refresh_task_id, controller.signal)
            .then(setRefreshTask)
            .catch((error) => {
              if (!controller.signal.aborted) {
                setRefreshTask(null);
                setRefreshTaskError(formatApiError(error, '刷新任务状态加载失败'));
              }
            });
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setMarketError(formatApiError(error, '市场数据加载失败'));
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <main className="terminal-page">
      <GlobalNav active="home" className="top-nav" />

      <section className="hero-grid" id="home">
        <div className="hero-copy">
          <h1>
            <span>ConsensusInvest,</span>
            <span>您的多Agent投研团队</span>
          </h1>
          <p>收集市场、公司和行业数据，让不同Agent基于证据辩论，最后汇总分歧、风险和投资建议。</p>
          <div className="hero-actions" aria-label="Analysis actions">
            <a className="primary-action" href="#analysis">开始分析</a>
            <a className="text-action" href="#details">了解更多 <span aria-hidden="true">{'->'}</span></a>
          </div>
        </div>

        <aside className="market-panel" aria-label="Market index panel">
          <div className="quote-header">
            <div>
              <h2>{primaryIndex?.name ?? '上证指数'}</h2>
              <span>{primaryIndex?.code ?? '000001.SH'}</span>
            </div>
            <div className="live-status">
              <span className="live-dot" />
              <span>{market?.data_state ?? 'LOADING'}</span>
              <time>{market?.updated_at ? formatTime(market.updated_at) : '--:--:--'}</time>
              <time>{market?.updated_at ? formatDate(market.updated_at) : '---- -- --'}</time>
            </div>
          </div>

          <div className="quote-value">
            <strong>{primaryIndex?.value.toFixed(2) ?? '-'}</strong>
            <span>{primaryIndex ? `${primaryIndex.change_rate >= 0 ? '+' : ''}${primaryIndex.change_rate.toFixed(2)}%` : '-'}</span>
          </div>

          <dl className="stats-grid">
            {indexStats.map(([label, value]) => (
              <div className="stat-row" key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>

          <div className="range-summary" aria-label="Chart range">
            <span>1D</span>
            <span>日内走势</span>
          </div>

          <div className="chart-frame" aria-label="Intraday chart">
            <svg viewBox="0 0 540 260" role="img" aria-labelledby="chart-title">
              <title id="chart-title">上证指数日内走势</title>
              <line className="guide-line" x1="0" x2="520" y1="130" y2="130" />
              {chart.polyline ? <polyline className="chart-line" points={chart.polyline} /> : null}
              <line className="axis-line" x1="8" x2="508" y1="220" y2="220" />
              <line className="tick" x1="8" x2="8" y1="216" y2="224" />
              <line className="tick" x1="117" x2="117" y1="216" y2="224" />
              <line className="tick" x1="226" x2="226" y1="216" y2="224" />
              <line className="tick" x1="335" x2="335" y1="216" y2="224" />
              <line className="tick" x1="444" x2="444" y1="216" y2="224" />
              <text x="8" y="238">09:30</text>
              <text x="96" y="238">10:30</text>
              <text x="202" y="238">11:30</text>
              <text x="312" y="238">13:00</text>
              <text x="421" y="238">14:00</text>
              <text x="500" y="238">15:00</text>
              {chart.priceLabels.map((label) => (
                <text className="price-label" x="514" y={label.y} key={label.y}>{label.text}</text>
              ))}
              {!chart.polyline ? <text className="chart-empty" x="270" y="124">{chartEmptyLabel}</text> : null}
            </svg>
          </div>

          <footer className="panel-footer">
            <span>UPDATE: {indexIntraday?.updated_at ? formatTime(indexIntraday.updated_at) : '-'}</span>
            <span title={refreshTaskError || refreshTask?.last_error || undefined}>
              {refreshTaskError
                ? refreshTaskError
                : indexIntraday?.refresh_task_id
                ? taskSummary(refreshTask, indexIntraday.refresh_task_id)
                : 'SOURCE: MarketSnapshot / AkShare'}
            </span>
          </footer>
        </aside>
      </section>

      <section className="market-ticker" aria-label="Market news ticker">
        <h2>市场资讯</h2>
        <div className="ticker-track">
          {tickerItems.length > 0 ? tickerItems.map((item) => (
            <article className="ticker-item" key={`${item.name}-${item.value}`}>
              <span>{item.time}</span>
              <strong>{item.name}</strong>
              <span>{item.value}</span>
              {item.change && <span>{item.change}</span>}
              <small>{item.detail}</small>
            </article>
          )) : <p className="market-error">{marketError || '正在读取市场股票列表。'}</p>}
        </div>
      </section>
    </main>
  );
}

function buildChart(intraday: IndexIntraday | null): {
  polyline: string;
  priceLabels: Array<{ text: string; y: number }>;
} {
  const points = intraday?.points ?? [];
  const values = points.map((point) => point.value).filter(Number.isFinite);
  if (values.length < 2) {
    return {
      polyline: '',
      priceLabels: [
        { text: '-', y: 32 },
        { text: '-', y: 73 },
        { text: '-', y: 114 },
        { text: '-', y: 155 },
        { text: '-', y: 196 },
      ],
    };
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const xStart = 8;
  const xEnd = 500;
  const yTop = 32;
  const yBottom = 196;
  const polyline = values
    .map((value, index) => {
      const x = xStart + (index / Math.max(values.length - 1, 1)) * (xEnd - xStart);
      const y = yBottom - ((value - min) / span) * (yBottom - yTop);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const priceLabels = [0, 1, 2, 3, 4].map((index) => {
    const value = max - (index / 4) * span;
    return { text: formatNumber(value), y: [32, 73, 114, 155, 196][index] };
  });

  return { polyline, priceLabels };
}

function latestPoint(intraday: IndexIntraday | null | undefined): IndexIntraday['points'][number] | undefined {
  return intraday?.points[intraday.points.length - 1];
}

function getChartEmptyLabel(intraday: IndexIntraday | null, error: string): string {
  if (error) {
    return '市场数据加载失败';
  }
  if (!intraday) {
    return '正在读取 MarketSnapshot';
  }
  if (intraday.data_state === 'failed') {
    return 'MarketSnapshot 刷新失败';
  }
  if (intraday.data_state === 'pending_refresh' || intraday.data_state === 'refreshing') {
    return 'MarketSnapshot 刷新中';
  }
  if (intraday.data_state === 'missing') {
    return '暂无 MarketSnapshot 日内走势';
  }
  return '暂无日内走势点位';
}

function taskSummary(task: SearchTaskStatusView | null, taskId: string): string {
  const shortId = taskId.slice(0, 8);
  if (!task) {
    return `TASK: ${shortId}`;
  }
  const source = task.source_status[0];
  const sourceText = source ? `${source.source}/${source.status}` : task.status;
  return `TASK: ${shortId} ${sourceText}`;
}

function formatNumber(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : '-';
}

function formatLargeNumber(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return '-';
  }
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(value);
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString('zh-CN', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleDateString('zh-CN');
}

export default HomePage;
