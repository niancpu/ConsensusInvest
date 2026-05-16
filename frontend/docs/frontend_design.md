# ConsensusInvest 前端设计文档

本文档描述前端在 `frontend/src` 下的**实际实现**：页面拆分、路由方式、API 客户端组织、状态归属、与后端协议的对接边界。字段级协议以 `D:\WorkField\Projects\ConsensusInvest\docs\web_api` 与 `D:\WorkField\Projects\ConsensusInvest\docs\report_module` 为准；本文档不重复维护完整 API schema。

> 视觉规范见 `design_skill.md`。分析页设计见 `analysis_page_design.md`。其余页面见各自的 `*_page_design.md`。

## 1. 前端定位

前端只负责：

- 通过 `POST /api/v1/workflow-runs` 发起主分析；
- 订阅 workflow SSE 事件流并按 `sequence` 幂等合并；
- 查询 `snapshot`、`trace`、`evidence`、`agent-arguments`、`raw-items`、`round-summaries`；
- 渲染 Report Module 的 `stocks/*`、`market/*` 聚合视图；
- 组织页面状态、节点下钻和错误展示。

前端不得：

- 在本地拼装投资结论；
- 把 Report Module 的 `report_run_id` 当作主分析 `workflow_run_id`；
- 把 MarketSnapshot、报告摘要或行情看板等同为 Judgment；
- 在生产页面用静态假数据替代后端数据；
- 隐藏 `partial`、`stale`、`refreshing`、低质量来源或冲突信息。

## 2. 技术栈与目录

- React 19 + TypeScript 5，Vite 6 构建；
- 唯一第三方运行时依赖：`react`、`react-dom`、`lucide-react`；
- 没有引入 Router、状态库、查询缓存库或 UI 框架；
- 入口 `src/main.tsx` 渲染 `src/App.tsx`。

目录结构（实际）：

```text
frontend/src
├── App.tsx                       // 调用 useHashRoute() 分发到 5 个页面
├── main.tsx                      // ReactDOM 入口
├── styles.css                    // 全局样式（先锋金融终端风）
│
├── api/                          // 唯一 fetch 层
│   ├── http.ts                   // withBase / apiGet / apiPost / SingleResponse / ListResponse
│   ├── errors.ts                 // ApiRequestError + readJsonResponse + formatApiError
│   ├── workflow.ts               // workflow-configs / workflow-runs（创建+列表+详情）/ snapshot / trace / eventStreamUrl
│   ├── evidence.ts               // evidence / raw-items / agent-arguments / round-summaries
│   └── report.ts                 // stocks/* + market/* + search-tasks
│
├── types/                        // 与后端协议对齐的纯类型
│   ├── workflow.ts               // WorkflowStatus / Snapshot / Event / Judgment / AgentArgument / RoundSummary / RunListItemView ...
│   ├── evidence.ts               // EvidenceDetail / RawItemDetail
│   ├── trace.ts                  // TraceNodeType / TraceEdgeType / WorkflowTrace / TraceNode / TraceEdge / TraceGraphLayout
│   └── report.ts                 // Stock/Market/Concept/Warning 等 Report Module 视图类型
│
├── router/
│   └── index.ts                  // useHashRoute() hook：解析 #home/#analysis/#reports/#history/#details + query 参数
│
├── hooks/
│   └── useWorkflowStream.ts      // SSE 订阅：onReplaying / onOpen / onMessage / onError / onParseError 回调式
│
├── components/
│   └── GlobalNav.tsx             // 顶部品牌 + 主页/分析/资讯报告/历史 4 个 hash 链接
│
└── features/
    ├── home/HomePage.tsx
    ├── reports/{ReportPage.tsx, ReportPage.css}
    ├── history/{HistoryPage.tsx, HistoryPage.css}
    ├── details/{DetailsPage.tsx, DetailsPage.css}
    └── analysis/                 // 4 层拆分：console / graph / inspector / utils + layout 算法
        ├── AnalysisPage.tsx      // 状态编排：configs / runId / snapshot / trace / events / connection / selectedNode
        ├── AnalysisPage.css
        ├── console/
        │   ├── AnalysisConsole.tsx
        │   └── consoleData.ts    // SOURCE_STATUSES / AGENT_MODES 兜底 + sourceRowsFromSnapshot / agentRowsFromSnapshot
        ├── graph/
        │   ├── TraceGraph.tsx
        │   ├── TraceNodeShape.tsx
        │   └── TraceGraphEmptyState.tsx
        ├── inspector/
        │   ├── NodeInspector.tsx
        │   ├── JudgmentInspector.tsx
        │   ├── TraceInspectorEmptyState.tsx
        │   └── types.ts          // SelectedNode 联合类型
        ├── layout/
        │   ├── traceGraph.ts     // layoutTraceGraph + routeTraceEdge + 边类型规整 / 标签
        │   └── traceConstants.ts // NODE_ORDER / NODE_SIZE_BY_TYPE / NODE_TYPE_LABELS / GRAPH_LAYOUT 等
        └── utils/
            ├── failure.ts        // summarizeFailurePayload / friendlyFailureCode
            └── format.ts         // formatScore / formatTime / truncate
```

## 3. 路由

`src/router/index.ts` 暴露 `useHashRoute(): Route`。`Route` 包含 `name`、`hash`、`pathname`、`query`（`URLSearchParams`）。`App.tsx` 用 `switch (route.name)` 渲染对应页面，hook 内部监听 `hashchange` / `popstate`。

| Hash / 路径前缀 | `route.name` | 渲染组件 | GlobalNav active |
| --- | --- | --- | --- |
| 其他（含 `#home`） | `home` | `HomePage` | `home` |
| `#analysis`、`/analysis*` | `analysis` | `AnalysisPage` | `analysis` |
| `#reports`、`/reports*` | `reports` | `ReportPage` | `reports` |
| `#history`、`/history*` | `history` | `HistoryPage` | `history` |
| `#details`、`/details*` | `details` | `DetailsPage` | — |

约束：

- 当前没有 `/analysis/runs/{workflow_run_id}` 这种深层路由；分析页使用 hash query 表达可恢复状态。
- `#analysis?ticker=002594` —— `AnalysisPage` 在 mount 时读取 `ticker` 用作初值。
- `#analysis?ticker=002594&run=wr_...` —— `AnalysisPage` 读取 `run` 后重新拉 `snapshot` / `trace`，支持 F5 刷新和从历史页回看。
- `ReportPage` 不会把 `stock_code` 写回 URL。

## 4. API 客户端组织

所有 fetch 都过 `src/api/http.ts`：`apiGet` / `apiPost` 共享 `withBase` 与 `readJsonResponse`，统一解析 `data / meta / pagination / error` 外壳，统一抛 `ApiRequestError`。各域文件只声明 endpoint，不重复实现 HTTP 细节。

| 文件 | 覆盖资源 | 备注 |
| --- | --- | --- |
| `src/api/http.ts` | `withBase` / `apiGet` / `apiPost` / `SingleResponse<T>` / `ListResponse<T>` | 读取 `import.meta.env.VITE_API_BASE_URL`；唯一可注入鉴权 header、追踪 header 的位置 |
| `src/api/errors.ts` | `ApiRequestError` / `readJsonResponse` / `formatApiError` | 把后端 `error.code` 包成异常；`formatApiError` 给出中文文案 |
| `src/api/workflow.ts` | `listWorkflowConfigs`、`createWorkflowRun`、`listWorkflowRuns`、`getWorkflowRun`、`getWorkflowSnapshot`、`getWorkflowTrace`、`eventStreamUrl` | 历史页和分析页共享同一 workflow 客户端 |
| `src/api/evidence.ts` | `getEvidence`、`getRawItem`、`getAgentArgument`、`getRoundSummary` | NodeInspector 下钻使用 |
| `src/api/report.ts` | `stocks/search`、`stocks/{code}/analysis`、`industry-details`、`event-impact-ranking`、`benefits-risks`、`market/index-overview`、`market/index-intraday`、`market/stocks`、`market/concept-radar`、`market/warnings`、`search-tasks/{id}` | 所有 `refresh` 默认 `stale`，`stocks/{code}/analysis` 用 `refresh=never&latest=true` |

SSE：

- `src/hooks/useWorkflowStream.ts` 封装 `EventSource` 生命周期：接收 `workflowRunId` 与 `{ onReplaying, onOpen, onMessage, onError, onParseError }`；内部覆盖 22 种事件类型（含 `snapshot`），断线时关闭并回调 `onError`，**不自动重连**。
- 当前重订阅一律 `after_sequence=0`，前端无 `lastSequence` 持久化，依赖后端 replay 全量重放。

## 5. 状态分层

```
Server Cache    → 各 useEffect / 表单提交内的 fetch；无全局缓存
Runtime Stream  → AnalysisPage 内 useState（snapshot、trace、events、connection）
                  + useWorkflowStream hook 推送的事件
UI State        → 组件局部 state：ticker、selectedConfigId、selectedNode、errorMessage
```

约束：

- `AnalysisPage` 用一个 `events: WorkflowEvent[]` 数组保存所有事件，合并时按 `event_id` 去重、按 `sequence` 排序。
- `connection` 状态机：`idle` → `creating` → `replaying` → `open` → `error`（不会主动回到 `closed`，错误后停留在 `error` 直到用户点 `刷新快照`）。`creating` 由 `handleCreateWorkflow` 设置，其余转移由 hook 回调推动。
- `snapshot` 加载用 `eventMode='replace_events'` 在创建任务时覆盖事件列表，用 `'merge_events'` 在终态事件回流时合并。
- 多 tab 同时打开同一个 workflow 不会冲突，但也不会同步：每个 tab 各自维护自己的 events 数组。

## 6. 与后端协议的对接边界

### 6.1 通用响应外壳

所有响应统一走 `data / meta / pagination / error`。`src/api/errors.ts:readJsonResponse` 解析后：

- 成功 → 返回 `payload as T`（T 必须包含 `data` 字段）；
- 失败 → 抛 `ApiRequestError`，带 `status`、`path`、`code`、`message`、`details`。

调用方一般用 `formatApiError(error, fallback)` 转成中文文案：`fallback（path，HTTP 4xx，错误码：XYZ）：message`。

### 6.2 实时与快照分工

`AnalysisPage` 的两条链路：

```text
POST /api/v1/workflow-runs                       // 创建
  → snapshot?include_events=true                  // 拿到首批事件 + 当前状态
  → trace                                         // 拿到 Trace Graph
  → useWorkflowStream(runId)                      // 订阅增量
        ↘ workflow_failed / *_completed
              → snapshot + trace 再拉一次（merge_events）
```

规则：

- 收到 `workflow_failed`、`agent_argument_completed`、`round_summary_completed`、`judgment_completed`、`workflow_completed` 任一事件，触发 `loadWorkflowState(runId, 'merge_events')`，用 snapshot 校准、用 trace 替换图。
- `snapshot.events` 里的事件以 `event_id` 去重再合并进本地 events。
- 失败任务（`status==='failed'` 或 `stage==='failed'`）：清空 trace、清空 selectedNode、显示 `failure_message` 或 `summarizeFailurePayload(payload)` 推导的失败摘要。
- 失败摘要按 `payload.code` 映射友好文案：`insufficient_evidence` / `agent_swarm_failed` / `judge_failed` / `evidence_acquisition_failed` / `missing_runtime_configuration`（实现见 `features/analysis/utils/failure.ts`）。

### 6.3 报告视图

`ReportPage` 与 `HomePage` 调用 Report Module 接口；同一个 `stock_code` 切换时并发拉 4 个聚合视图：

```text
GET /api/v1/stocks/{code}/analysis?refresh=never&latest=true
GET /api/v1/stocks/{code}/industry-details
GET /api/v1/stocks/{code}/event-impact-ranking?limit=10
GET /api/v1/stocks/{code}/benefits-risks
```

边界：

- `report_run_id` ≠ `workflow_run_id`。`ReportPage` 显示 `report_run_id` 末 8 位，但侧栏「进入主分析」按钮跳到 `#analysis?ticker=...`，不会带 `report_run_id` 过去。
- `analysis.action` 为空时显示 neutral pill「无主链路 Judgment 时不展示投资建议」。
- `data_state` 直接显示在 sidebar；任何 `partial/stale/refreshing` 都不阻塞主体内容。

### 6.4 历史回看

`HistoryPage` 调 `src/api/workflow.ts:listWorkflowRuns` 列出最近 20 条，点击拉单个详情。当前只展示 `status`、`workflow_config_id`、`judgment_id`、`final_signal`，不拉 snapshot/trace；从详情区跳到 `#analysis?ticker=...&run=...`，由分析页恢复 Trace 图。

## 7. 错误与失败展示规则

- 网络 / HTTP 错误：`formatApiError` 输出统一文案，挂到对应页面的 `errorMessage` 状态；在分析页显示在左侧控制台底部，在报告页显示在侧栏，在历史页显示在列表下方。
- Workflow 失败：图区显示 `TraceGraphEmptyState`，标题随 `hasWorkflow / isWorkflowFailed` 切换；右侧 Inspector 用 `TraceInspectorEmptyState` 给出原因。
- SSE 断连：`useWorkflowStream` 的 `onerror` 关闭 EventSource，置 `connection='error'`，提示用户手动「刷新快照」。**不会**自动重连（避免在 5xx 风暴时打爆后端）。
- Report `data_state==='failed' / refreshing / pending_refresh` 由 `HomePage.getChartEmptyLabel` 等本地工具映射为中文标签，不阻塞页面。

## 8. 视觉与交互约束（速览）

完整规范见 `design_skill.md`。本仓库实际遵循：

- 仅四色：纯白 `#FFFFFF`、纯黑 `#000000`、克莱因蓝 `#002FA7`，以及极小面积的告警红/增长绿；
- `border-radius: 0`、零阴影、1px 黑线 + 2px 顶部封口；
- Trace 图节点使用 1px 黑框直角矩形、连线 90° 折线、标签等宽字体；
- 字体三轨：Georgia 衬线（品牌/标题）、Helvetica 无衬线（UI）、等宽字体（数据，全局 CSS 用系统等宽字体回退）；
- 动效仅使用瞬时反色和光标闪烁；
- 全局 SVG 网格使用虚线 + 低透明度作为底噪。

## 9. 与早期设计的差异与未决项

差异（落地实现 ≠ 早期 `frontend_design` 草稿）：

- 路由：使用 hash 而非 BrowserRouter；`workflow_run_id` 通过 `#analysis?...&run=...` 表达，不使用深层路径。
- 分析页布局：左侧不是 Debate Rail，而是**控制台**（表单 + 数据源 + 代理模式 + 推理状态）。事件带紧贴中间 Trace 图下方，没有单独「顶部上下文栏」。
- Trace 节点类型新增 `round_summary`；与 web_api 协议保持一致。
- 历史页只展示摘要，没有内置 Trace / Judgment / Evidence 视图。

未决项：

- 是否在历史详情页复用 `AnalysisPage` 渲染只读 Trace。
- SSE 断线重连、`Last-Event-ID` / `after_sequence` 是否要在前端真正实现，而不是依赖后端 replay。
- Report Module 是否独立事件流入口，当前以 `data_state` + `refresh_task_id` 为准。
- `src/api/http.ts` 暂未注入鉴权 header / `X-Request-Id`；接入时统一在这一层做。
