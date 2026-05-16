# 资讯报告页面设计

本文档描述 `frontend/src/features/reports/ReportPage.tsx` 的页面结构与数据流。完整 Report Module 协议见 `docs/report_module/endpoints.md`。

## 1. 页面定位

资讯报告页面读取 Report Module 的 `stocks/*`、`market/*` 聚合视图，**不创建主 workflow**。

页面回答：

- 当前标的的事实摘要、关键证据、行业关系、事件影响、利好/风险列表是什么？
- 当前数据是 `partial / stale / refreshing / fresh` 哪种状态？
- 想看 Agent 辩论怎么跳转主分析？

页面不回答：

- 是否买卖（`action` 为空时显式标注「无主链路 Judgment 时不展示投资建议」）；
- workflow Trace、Agent Argument、Judgment 的细节（去 `#analysis`）。

## 2. 布局

三栏 grid：

```text
┌────────────────────────────────────────────────────────────────┐
│ GlobalNav                                                      │
├────────────┬──────────────────────────────────┬───────────────┤
│ Sidebar    │ Main                             │ Market Aside   │
│            │                                  │                │
│ 标题        │ Report Heading + 进入主分析按钮    │ 市场情绪 / 分数 │
│ 搜索表单    │ Report Summary（含 signal-pill）  │ 指数列表       │
│ 当前标的    │ ┌──────────┬──────────┐         │ 概念雷达       │
│ Data State │ │ 关键证据  │ 行业详情  │         │ 预警列表       │
│ Report Run │ ├──────────┼──────────┤         │                │
│ 搜索结果    │ │ 事件影响  │ 利好风险  │         │                │
│ 错误提示    │ └──────────┴──────────┘         │                │
└────────────┴──────────────────────────────────┴───────────────┘
```

## 3. 数据入口

### 3.1 初次 mount

并发拉 3 个市场接口写入右栏：

```ts
Promise.all([
  getIndexOverview(),
  getConceptRadar(),
  getMarketWarnings(),
])
```

### 3.2 按 stockCode 拉报告

`stockCode` 变化时（`useEffect([stockCode])`）并发拉 4 个个股接口：

```ts
Promise.all([
  getStockAnalysis(code),          // refresh=never&latest=true
  getIndustryDetails(code),
  getEventImpactRanking(code, limit=10),
  getBenefitsRisks(code),
])
```

结果合并写入 `report: ReportBundle | null`。初始 `stockCode` 写死为 `002594.SZ`（比亚迪）。

### 3.3 搜索

`handleSearch` 调 `searchStocks(keyword)`：

- 拿到 `StockSearchHit[]` 写入 `searchHits`；
- 自动把 `hits[0].stock_code` 设为新 `stockCode`，触发 4 路并发；
- 错误走 `formatApiError(error, '股票搜索失败')`。

## 4. Sidebar

- 标题「资讯报告」+ 搜索表单（input + 搜索按钮）；
- `report-meta`：当前标的名 / `Data State` / `Report Run`（取 `report_run_id` 末 8 位）；
- `search-hits`：搜索结果列表，每项点击切换 `stockCode`；
- 底部错误 banner（`errorMessage`）。

## 5. Main

### 5.1 Heading + 进入主分析

```text
Report Module / <report.title>           [进入主分析] → #analysis?ticker=<ticker>
```

跳到分析页时只带 `ticker`，不带 `report_run_id`、`workflow_run_id`，避免把报告身份误传成主分析身份。

### 5.2 Summary + Signal Pill

- 大标题 = `stock_name`；
- 摘要 = `report.summary`，空时显示「正在读取 Report Module 视图。」；
- Signal Pill：
  - `analysis.action` 存在 → 显示 `action.label` + `action.reason`，类名带 `positive / neutral / negative`；
  - 不存在 → 中性 pill，文字「无主链路 Judgment 时不展示投资建议。」标题为 `report_mode`（`report_generation` 或 `with_workflow_trace`）。

### 5.3 Report Grid

4 个 Panel 用 `Panel({ title, children })`：

| Panel | 数据源 | 渲染字段 |
| --- | --- | --- |
| 关键证据 | `analysis.report.key_evidence[]` | `title / objective_summary / evidence_id` |
| 行业详情 | `industry` | `industry_name / policy_support_desc / supply_demand_status / competition_landscape` |
| 事件影响 | `events.items[]` | `event_name / impact_level / direction / impact_score / evidence_ids` |
| 利好与风险 | `benefitsRisks.benefits[] + risks[]` 串联 | `source / text / evidence_ids` |

每张卡片必须保留 `evidence_id` / `evidence_ids` / `source`，确保用户能追到证据。

## 6. Market Aside

- `market.market_sentiment.label + score`；
- `market.indices[]` 列表，每条 `name / value / change_rate`，根据 `is_up` 切换上涨/下跌颜色（小面积红绿）；
- `concept-radar` 列表，每条 `concept_name / heat_score / status`；
- 预警列表，每条 `title + content`。

约束：

- 整列只读，不点击进入；与主分析没有跳转关系；
- 没有概念雷达的趋势图，只展示数字。

## 7. 错误与刷新

- 任何接口失败都走 `formatApiError`，写入 `errorMessage`，显示在 Sidebar 底部；
- `loading` 用 `aria-busy` 标在 `report-main`，没有 skeleton；
- `data_state` 是 Sidebar 必显字段；当前没有手动「刷新报告」按钮，刷新依赖切换 `stockCode` 或重新 mount。

## 8. 边界与已知缺口

- 个股报告固定 `refresh=never&latest=true`，意味着前端永远拿缓存视图。等用户主动要新数据时需要新增「触发刷新」按钮，走 `refresh=stale` 或 `refresh=force`。
- 搜索没有自动联想；必须点击搜索按钮才发请求。
- 当前没有概念详情、事件详情下钻入口，只是平铺信息。
- 跨页面状态：从 `ReportPage` 跳到 `#analysis?ticker=...` 后，分析页只读 `ticker`，不会感知 Report 端的 `report_run_id`；多窗口审计审计链不互通是已知限制。
