# 首页设计

本文档描述 `frontend/src/features/home/HomePage.tsx` 的页面结构与数据流。

## 1. 页面定位

首页是默认入口（hash 为空、`#home` 或未匹配其它路由时落到这里）。职责：

- 给出 ConsensusInvest 的产品定位标语；
- 用一张实时指数面板让用户立即看到“市场状态”；
- 在底部市场资讯条展示几只重点股票的实时价格；
- 提供「开始分析」「了解更多」两个入口。

不在首页内做：

- 启动 workflow（只跳到 `#analysis`）；
- 渲染单只股票完整报告（跳到 `#reports`）；
- 渲染历史 workflow（跳到 `#history`）。

## 2. 布局

```text
┌────────────────────────────────────────────────────────────┐
│ GlobalNav                                                  │
├──────────────────────────────────────┬─────────────────────┤
│ Hero Copy                            │ Market Panel        │
│  - 大标题（衬线 Georgia）              │  - 指数标题 + 实时点 │
│  - 副标题                             │  - 当前点位 + 涨跌幅 │
│  - 「开始分析」「了解更多」按钮          │  - 8 项 OHLC / VOL  │
│                                      │  - 日内走势 SVG     │
│                                      │  - 刷新任务摘要     │
├──────────────────────────────────────┴─────────────────────┤
│ Market Ticker（横向资讯条）                                  │
└────────────────────────────────────────────────────────────┘
```

整个 `<main>` 是一个 `terminal-page` grid，3 行：`72px (nav) / 1fr (hero) / 132px (ticker)`，外层 1px 黑边框包裹。

## 3. 数据入口

`useEffect` 一次性并发拉 3 个接口：

```ts
Promise.all([
  getIndexOverview(),                   // /api/v1/market/index-overview?refresh=stale
  getIndexIntraday('000001.SH'),        // /api/v1/market/index-intraday?code=000001.SH&refresh=stale
  getMarketStocks(),                    // /api/v1/market/stocks?page=1&page_size=5&refresh=stale
])
```

如果 `intraday.refresh_task_id` 非空，再额外拉一次：

```ts
getSearchTaskStatus(refresh_task_id);   // /api/v1/search-tasks/{task_id}
```

约束：

- 没有轮询；首页只在 mount 时拉一次，后续依赖用户切换路由回来时重新 mount。
- 任何接口失败都走 `formatApiError`，写入 `marketError`，在 ticker 区域以「市场数据加载失败」兜底。
- 刷新任务失败不影响主面板，单独写入 `refreshTaskError`，作为右下脚 footer 的 `title` 显示。

## 4. Market Panel

- `primaryIndex = overview.indices[0]`，默认期望「上证指数 000001.SH」；
- `quote-header` 显示指数名、代码、实时状态（用 `data_state` 字段）、`updated_at` 时间和日期；
- `quote-value` 显示 `value.toFixed(2)` 和带正负号的 `change_rate`；
- `stats-grid` 8 项：`OPEN / HIGH / LOW / PREV / POINTS / VOL / AMT / STATE`，VOL/AMT 取 `points[last]` 的成交量和成交额；
- `chart-frame` SVG（`540x260` viewBox）：
  - 水平基准线 + 横轴刻度（09:30 / 10:30 / 11:30 / 13:00 / 14:00 / 15:00）；
  - `buildChart(intraday)` 把 `points[].value` 归一化到 SVG 坐标后输出 `polyline`；
  - 5 个右侧价格标签按 max→min 等距渲染；
  - 点位不足 2 个时只显示「-」标签，并用 `chart-empty` 文本中央占位；
- `panel-footer` 显示 `UPDATE: HH:MM:SS` 和刷新任务摘要（`TASK: {shortId} {source/status}` 或 `SOURCE: MarketSnapshot / AkShare`）。

`getChartEmptyLabel` 把 `data_state` 映射成中文：`failed → MarketSnapshot 刷新失败`、`pending_refresh / refreshing → MarketSnapshot 刷新中`、`missing → 暂无 MarketSnapshot 日内走势`，其它无 polyline 情况显示「暂无日内走势点位」。

## 5. Market Ticker

底部 `market-ticker` 是一条横向条，逐项渲染 `marketStocks.list`：

```text
{time}  {name}  {price.toFixed(2)}  {change_rate ± %}  {view_label}/{snapshot_id}
```

`time` 取 `market.updated_at` 而非 stock 自己的时间，因为接口里没有逐股的 `updated_at`。

`view_label` 和 `snapshot_id` 用于审计提示——这是 Report Module 计算出的视图分类，不是单纯涨跌标签。

`marketStocks.list` 为空时显示「正在读取市场股票列表。」或 `marketError`。

## 6. 边界与已知缺口

- 首页没有「最近 workflow / 最近报告」列表；早期设计提到的入口需要再补。
- 指数固定为 `000001.SH`，不支持切换；想看其他指数得改代码或加 URL 参数。
- 没有市场情绪条（`market.market_sentiment`）的可视化，只在 `ReportPage` 用。
- 「了解更多」按钮指向 `#details`，但 `DetailsPage` 目前是占位介绍页，没有深度内容。
- Chart SVG 是自绘的，不支持 hover、tooltip 或缩放；当前是「看一眼就走」的展示，不是交互图。
