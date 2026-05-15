# ConsensusInvest 前端设计文档

本文档定义前端页面职责、数据流、实时更新策略和视觉设计边界。字段级协议以 `D:\WorkField\Projects\ConsensusInvest\docs\web_api` 与 `D:\WorkField\Projects\ConsensusInvest\docs\report_module` 为准；本文档不重复维护完整 API schema。

## 1. 前端定位

前端不是静态展示页，也不是本地推理入口。前端只负责：

- 发起主分析 workflow；
- 订阅 workflow 实时事件；
- 查询快照、trace、Evidence、Judgment、Report Module 视图；
- 组织页面状态、交互和下钻路径；
- 清楚展示数据状态、来源引用和限制说明。

前端不得：

- 在本地拼装投资结论；
- 把 Report Module 的 `report_run_id` 当成主分析 `workflow_run_id`；
- 把 MarketSnapshot、报告摘要或行情看板等同于 Judgment；
- 用静态假数据替代后端实时数据进入正式页面；
- 隐藏 `partial`、`stale`、`refreshing`、低质量来源或冲突信息。

## 2. 页面地图

| 页面 | 主要用途 | 主数据入口 | 是否实时 |
| --- | --- | --- | --- |
| 首页 / 市场总览 | 展示市场概览、入口和最近任务 | Report Module `market/*`、workflow 列表摘要 | 轮询或刷新，不挂 workflow SSE |
| 分析页面 | 针对某一只股票发起和观看多 Agent 辩论 | `POST /api/v1/workflow-runs`、`events`、`snapshot`、`trace`、`evidence`、`judgment` | 是，使用 SSE |
| 资讯报告页面 | 展示 Report Module 生成的个股/市场报告视图 | `stocks/*`、`market/*` 报告视图接口 | 以 `data_state` 和刷新任务状态为准 |
| 历史页面 | 回看已完成 workflow | `GET /api/v1/workflow-runs?status=completed`、`snapshot`、`trace` | 默认否；打开运行中任务时可恢复 SSE |
| Evidence / Trace 下钻 | 审计结论来源 | workflow Evidence、Raw Item、Agent Argument、Judgment 详情 | 按需查询 |

## 3. 数据原则

### 3.1 后端是事实来源

所有业务数据必须来自后端 API。前端可以缓存和投影，但不能把本地状态升级为事实。

前端缓存只允许保存：

- 请求结果缓存；
- SSE 已处理事件序号；
- 页面筛选条件；
- 展开、折叠、选中节点等纯 UI 状态；
- 开发态 fixture，且必须位于明确的 mock/fixture 目录，不进入生产数据链路。

### 3.2 实时与快照分工

主分析页面使用两条链路：

```text
POST /api/v1/workflow-runs
  -> receive workflow_run_id
  -> subscribe GET /api/v1/workflow-runs/{workflow_run_id}/events
  -> apply SSE events by sequence
  -> query snapshot / trace / evidence / judgment for complete state
```

SSE 是运行日志和增量结果，不是完整数据库状态。页面刷新、断线重连、历史回看必须以 `snapshot` 恢复。

前端处理规则：

- 按 `sequence` 幂等处理事件；
- 记录最后处理的 `sequence`；
- 重连时使用 `after_sequence` 或 `Last-Event-ID`；
- 如果 `snapshot.last_event_sequence` 小于本地最后事件序号，不能用旧快照覆盖新事件状态；
- `agent_argument_delta`、`judgment_delta` 只用于实时展示，最终结构以 completed 事件或详情接口为准。

### 3.3 报告视图分工

资讯报告页面走 Report Module。它可以展示事实摘要、事件、风险事项、行业信息、市场快照和引用，但不能伪装成完整 Agent 辩论。

关键约束：

- `GET /api/v1/stocks/{stock_code}/analysis` 是个股研究聚合视图，不启动主 workflow；
- `report_run_id` 代表报告视图生成或缓存，不代表已完成主链路 Judgment；
- 报告生成模式下 `workflow_run_id` 和 `judgment_id` 可以为空；
- `data_state=partial/stale/refreshing` 必须展示给用户；
- `refresh_task_id` 只表示后端异步刷新任务，不表示页面应阻塞等待。

### 3.4 历史回看分工

历史页面只回看已经存在的 workflow，不创建新结论。

列表使用：

```http
GET /api/v1/workflow-runs?status=completed&limit=20&offset=0
```

详情使用：

```http
GET /api/v1/workflow-runs/{workflow_run_id}/snapshot
GET /api/v1/workflow-runs/{workflow_run_id}/trace
GET /api/v1/workflow-runs/{workflow_run_id}/judgment
```

如果用户打开的是 `running` 或 `queued` 状态的历史任务，页面可以恢复订阅该任务的 SSE；如果是 `completed`，默认不订阅实时事件。

## 4. 分析页面设计

分析页面的核心任务是展示“某一只股票的辩论过程”，不是只展示最终结论。

详细页面设计见 `D:\WorkField\Projects\ConsensusInvest\frontend\docs\analysis_page_design.md`。分析页中间主图使用 `GET /api/v1/workflow-runs/{workflow_run_id}/trace` 返回的 Trace Graph；Evidence References 可以作为补充，Entity Relations 只做辅助下钻，不能替代主图。

### 4.1 页面区域

| 区域 | 内容 | 数据来源 |
| --- | --- | --- |
| 股票上下文栏 | 股票代码、名称、分析基准时间、workflow 状态 | workflow run、stock search/report view |
| 发起分析面板 | 股票输入、workflow config、lookback、sources、stream 选项 | workflow configs、用户输入 |
| 实时事件轨 | connector、Evidence、Agent、Judge 事件 | SSE events |
| 辩论区 | Bull/Bear/其他 Agent 论点、轮次摘要、引用 Evidence | Agent Argument、Round Summary、SSE delta |
| 证据区 | Evidence 列表、质量、来源、冲突标记 | workflow evidence |
| Judge 区 | 最终 Judgment、置信度、风险、引用 | judgment |
| Trace 区 | Judgment -> Argument -> Evidence -> Raw 的可审计链路 | trace |

### 4.2 创建任务

发起分析时，前端调用：

```http
POST /api/v1/workflow-runs
```

前端必须保存并路由到 `workflow_run_id`。推荐路由：

```text
/analysis/runs/{workflow_run_id}
```

如果用户从股票搜索进入，还可以使用：

```text
/analysis/new?stock_code=002594.SZ
```

但创建成功后必须切换到 `workflow_run_id` 路由，避免刷新页面后丢失任务身份。

### 4.3 事件渲染

事件轨按阶段分组：

- 采集：`connector_started`、`connector_progress`、`raw_item_collected`;
- 证据：`evidence_normalized`、`evidence_structuring_started`、`evidence_structured`;
- 辩论：`agent_run_started`、`agent_argument_delta`、`agent_argument_completed`、`round_summary_*`;
- 裁决：`judge_started`、`judge_tool_call_*`、`judgment_delta`、`judgment_completed`;
- 终态：`workflow_completed`、`workflow_failed`。

页面不能只显示最终结论；必须保留中间过程和可下钻引用。

## 5. 资讯报告页面设计

资讯报告页面面向“读报告”和“看资讯”，数据来自 Report Module。

推荐页面：

- 个股研究报告：`/reports/stocks/{stock_code}`;
- 市场报告：`/reports/market`;
- 概念/预警：`/reports/concepts`、`/reports/warnings`。

主要接口：

```http
GET /api/v1/stocks/search?keyword={keyword}&limit=10
GET /api/v1/stocks/{stock_code}/analysis?query={query}&workflow_run_id={workflow_run_id}&refresh=never
GET /api/v1/stocks/{stock_code}/industry-details?workflow_run_id={workflow_run_id}
GET /api/v1/stocks/{stock_code}/event-impact-ranking?workflow_run_id={workflow_run_id}&limit=10
GET /api/v1/stocks/{stock_code}/benefits-risks?workflow_run_id={workflow_run_id}
GET /api/v1/market/index-overview?refresh=stale
GET /api/v1/market/stocks?page=1&page_size=20&keyword={keyword}&refresh=stale
GET /api/v1/market/concept-radar?limit=20&refresh=stale
GET /api/v1/market/warnings?limit=10&severity=notice&refresh=stale
```

展示规则：

- 所有摘要、风险、事件、行业关系必须保留可追踪 ID；
- 没有 `judgment_id` 时，不展示“最终判断”“投资建议”“多空结论”等文案；
- `benefits`、`risks` 中带方向性的内容只能来自主链路 Judgment 或已有 workflow；
- `data_state` 必须放在页面明显位置；
- `refreshing` 时展示当前可用结果和刷新状态，不阻塞页面。

## 6. 历史页面设计

历史页面用于回看已完成 workflow，重点是复现“当时如何得到这个判断”。

### 6.1 列表

列表字段：

- `workflow_run_id`;
- `ticker` / `stock_code`;
- `status`;
- `analysis_time`;
- `workflow_config_id`;
- `created_at`;
- `completed_at`;
- `final_signal`;
- `confidence`;
- `judgment_id`。

列表只展示摘要，不展示完整链路。

### 6.2 详情

详情页必须展示：

- workflow 基本信息；
- Judgment；
- Agent Argument；
- Round Summary；
- Evidence；
- Trace 图；
- Raw Item 下钻入口。

历史详情不能重新解释旧结果。若用户要基于最新数据重新分析，必须创建新的 workflow。

## 7. 前端状态管理

推荐把状态分三层：

| 状态层 | 内容 | 归属 |
| --- | --- | --- |
| Server Cache | API 响应、snapshot、trace、Evidence、Report view | 查询缓存 |
| Runtime Stream | SSE 连接状态、已处理 sequence、临时 delta | workflow run 页面状态 |
| UI State | 当前 tab、筛选、展开节点、选中 Evidence | 组件或路由状态 |

硬约束：

- 不能把 SSE delta 直接长期保存为最终 Judgment；
- 不能在多个页面各自实现一套 API 外壳解析；
- `data/meta/error` 响应外壳应由统一 API client 处理；
- 错误展示使用 `error.code` 映射本地文案，`details` 只用于开发态或可折叠排查信息。

## 8. API Client 设计

建议前端实现统一客户端：

```text
src/api/http.ts
src/api/workflow.ts
src/api/report.ts
src/api/evidence.ts
src/api/agents.ts
src/api/entities.ts
src/api/sse.ts
```

职责：

- `http.ts` 处理 base URL、`data/meta/error` 外壳、错误归一化；
- `workflow.ts` 创建任务、查列表、详情、snapshot、trace；
- `sse.ts` 封装 EventSource、重连、`after_sequence`、事件幂等；
- `report.ts` 只封装 Report Module 视图接口，不创建主 workflow；
- `evidence.ts` 封装 Evidence/Raw/Reference 查询；
- `agents.ts` 封装 Agent Run、Argument、Round Summary、Judgment 查询。

## 9. 视觉设计边界

视觉风格遵循 `D:\WorkField\Projects\ConsensusInvest\frontend\docs\design_skill.md`。

核心规则：

- 叙事标题使用高对比衬线字体；
- 数据、行情、AI 状态使用等宽字体；
- UI 控件使用克制无衬线字体；
- 数据区使用纯白底、纯黑线和克莱因蓝强调；
- 控制台或沉浸式 AI 区可使用克莱因蓝底和白色线框；
- 禁止阴影和圆角；
- 使用 1px 黑/白硬边网格；
- 图谱使用矩形节点和直角连线；
- 动效只使用瞬时反色、光标闪烁或非常克制的状态变化。

页面设计要服务于审计链路。视觉重点不应只压在首页英雄区，而要让分析页、Trace、Evidence、Report 引用在高密度信息下仍然可读。

## 10. 已定取舍

- 主分析和资讯报告分离。后果是同一只股票可能同时有 report view 和 workflow run，前端必须清晰标注两者身份。
- 主分析实时过程只使用 SSE，不默认引入 WebSocket。后果是前端只能接收后端推送，暂停/恢复/多人协作等双向能力后续再设计。
- Report Module 的 `data_state` 是页面状态的一部分。后果是报告页必须能优雅展示不完整数据，不能为了视觉完整而隐藏 partial/stale。
- 历史页以 workflow snapshot/trace 回看，不重新计算。后果是旧结果和当前市场数据可能不一致，页面必须展示 `analysis_time`。
- 前端不做投资解释。后果是所有方向性文案必须能追到 Agent/Judge 或已有 report 引用。

## 11. 未决问题

- Report Module 是否需要独立事件流入口。当前文档按 `data_state`、`refresh_task_id` 和后续查询处理。
- 股票搜索返回的 `stock_code`、`ticker`、`entity_id` 在创建 workflow 时的优先级，需要以后端最终请求 schema 为准。
- 首页市场概览的刷新频率需要结合后端缓存和 provider 成本确定，前端暂不自行高频轮询。
- 历史页是否展示失败 workflow。当前优先展示 completed；失败任务可后续作为排障视图纳入。
