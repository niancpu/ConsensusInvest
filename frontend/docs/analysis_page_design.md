# 分析页面设计

本文档描述 `frontend/src/features/analysis/` 的**实际页面结构、数据流和节点交互**。完整字段协议见 `docs/web_api/workflow.md`。

## 0. 文件结构（4 层拆分）

```text
features/analysis
├── AnalysisPage.tsx              // 编排：state + handler + 渲染外壳；不放 UI 子结构
├── AnalysisPage.css
├── console/
│   ├── AnalysisConsole.tsx       // 左侧控制台整列
│   └── consoleData.ts            // 兜底静态数据 + sourceRowsFromSnapshot / agentRowsFromSnapshot
├── graph/
│   ├── TraceGraph.tsx            // SVG 主图（grid / edges / nodes）
│   ├── TraceNodeShape.tsx        // 单节点：rect + title + subtitle，交互/选中态
│   └── TraceGraphEmptyState.tsx  // 4 种空状态文案
├── inspector/
│   ├── NodeInspector.tsx         // 5 种节点的中文 description-list
│   ├── JudgmentInspector.tsx     // judgment 默认视图
│   ├── TraceInspectorEmptyState.tsx
│   └── types.ts                  // SelectedNode 联合类型
├── layout/
│   ├── traceGraph.ts             // layoutTraceGraph + routeTraceEdge + 标签/类型规整
│   └── traceConstants.ts         // NODE_ORDER / NODE_SIZE_BY_TYPE / NODE_TYPE_LABELS / GRAPH_LAYOUT
└── utils/
    ├── failure.ts                // summarizeFailurePayload + friendlyFailureCode
    └── format.ts                 // formatScore / formatTime / truncate
```

SSE 订阅、API 调用、类型定义不在本目录：

- 事件流走 `src/hooks/useWorkflowStream.ts`；
- workflow / evidence / round-summary 接口走 `src/api/workflow.ts` + `src/api/evidence.ts`；
- `WorkflowSnapshot` / `WorkflowEvent` / `WorkflowTrace` / `TraceNode` / `TraceEdge` / `Judgment` / `AgentArgument` / `RoundSummary` / `EvidenceDetail` / `RawItemDetail` 等类型在 `src/types/{workflow,evidence,trace}.ts`。

## 1. 页面判断

分析页中间放一张图，但这张图不是知识图谱，也不是报告关系图。

主图使用后端主 workflow 的 Trace Graph：

```http
GET /api/v1/workflow-runs/{workflow_run_id}/trace
```

节点类型（与 `layout/traceGraph.ts` 对齐）：

- `judgment`
- `round_summary`
- `agent_argument`
- `evidence`
- `raw_item`

边类型（与 `types/trace.ts:TraceEdgeType` 对齐）：

- `uses_argument`
- `supports`
- `counters`
- `refuted`
- `derived_from`
- `cited`
- `uses_round_summary`

`layout/traceGraph.ts:layoutTraceGraph` 把节点按 `judgment → round_summary → agent_argument → evidence → raw_item` 分行，把不在该枚举内的 edge_type 归一为 `cited`，连线统一走 `routeTraceEdge` 生成的 90° 折线。

## 2. 总体布局

实际采用三栏布局（CSS 见 `AnalysisPage.css`，整体宽度为 grid，左 / 中 / 右三列）：

```text
┌──────────────────────────────────────────────────────────────┐
│ GlobalNav (主页 / 分析 / 资讯报告 / 历史)                     │
├────────────┬─────────────────────────────┬───────────────────┤
│ Console    │ Workspace                   │ Inspector         │
│            │                             │                   │
│ 股票表单    │ 判断溯源图（SVG）             │ 节点说明           │
│ 刷新快照    │  - judgment                  │  - judgment       │
│ Quote Strip│  - round_summary             │  - agent_argument │
│ 数据源状态  │  - agent_argument            │  - evidence       │
│ 代理模式    │  - evidence                  │  - raw_item       │
│ 推理状态    │  - raw_item                  │                   │
│ 错误 banner│                             │ 图例              │
│            │ 运行事件（最近 8 条）          │                   │
└────────────┴─────────────────────────────┴───────────────────┘
```

设计取舍（与早期草稿的区别）：

- 没有独立的「顶部 Stock Context」栏。`ticker` / `status` / `stage` / `events` / `conn` / `run` 全部压在左侧 Console 的 `quote-strip` 里。
- 左栏不是 Debate Rail（按 Agent 分组的轮次列表），而是**控制台 + 状态面板**。Bull/Bear 等代理状态来自 `snapshot.agent_runs`，不是单独建模的 rail。
- 「Runtime Event Tape」从全宽底部带改成贴在 Trace 图下方的 `timeline-panel`，只显示最近 8 条事件。

## 3. 左侧 Console（`console/AnalysisConsole.tsx`）

`analysis-console` 内自上而下包含 5 个 `console-block`：

1. **股票代码 + Workflow + 开始分析按钮**：表单提交触发 `handleCreateWorkflow`。`workflow_config_id` 来自 `GET /api/v1/workflow-configs`，无配置时回退到 `mvp_bull_judge_v1`。
2. **刷新快照 + Quote Strip**：`刷新快照` 调用 `loadWorkflowState(runId, 'merge_events')`。Strip 显示 `ticker / status / stage / events / conn / run（取 workflow_run_id 末 8 位）`。
3. **数据源状态**：默认显示 `SOURCE_STATUSES` 静态行；有 `snapshot` 时改为 `sourceRowsFromSnapshot` 按 `evidence_items.source` 聚合的真实计数。
4. **代理模式**：默认显示 `AGENT_MODES`；有 `snapshot` 时改为 `agentRowsFromSnapshot`（即 `agent_runs.map(run => [run.agent_id, run.status])`）。
5. **推理状态**：`Evidence / Argument / Round Summary / Tool Call` 计数，分别取 `snapshot.evidence_items / agent_arguments / round_summaries / judge_tool_calls` 长度。

底部：

- `errorMessage` → `error-banner`；
- `console-footer` 显示 `latestStatus` + `API v1`。

## 4. 中间 Workspace

### 4.1 Trace Graph SVG（`graph/TraceGraph.tsx` + `graph/TraceNodeShape.tsx`）

- 画布尺寸来自 `layout/traceGraph.ts:layoutTraceGraph`，最小宽度 780px，并按最拥挤层级的节点数量横向扩展；
- 背景 `<pattern id="grid">` 1px 黑虚线 62×62 网格；
- 节点：`TraceNodeShape` 渲染矩形 + 中心标题 + 子标题（`node_type` + `score`）；只有 `traceNodeIds` 集合（来自后端 trace）内的节点 `isInteractive=true`，可点击 / 键盘 Enter / Space 触发；
- 边：`polyline` + 中间 `rect` 背景框 + 等宽字体 `text` 标签（标签由 `labelForEdge` 给出 `arg / sup / ctr / ref / raw / sum / cite`）。

布局算法 `layout/traceGraph.ts:layoutTraceGraph`：

- 按 `judgment → round_summary → agent_argument → evidence → raw_item` 顺序分行；
- 行间距 126px，行高基于 `NODE_SIZE_BY_TYPE`；
- 每行内按实际画布宽度等分，Evidence / Raw Item 使用更紧凑节点与更短标题，画布溢出时由 `graph-board` 横向滚动；
- 边路由 `routeTraceEdge`：同行 → 走带上下 lane 的 90° 折线；跨行 → 走「V-H-V」并按相邻层级分配 lane，错开水平段和节点连接点，避免大量边重叠在同一通道。

### 4.2 空状态（`graph/TraceGraphEmptyState.tsx`）

`TraceGraphEmptyState` 处理 4 种情况：

| `hasWorkflow` | `isWorkflowFailed` | 渲染标题 | 说明 |
| --- | --- | --- | --- |
| false | — | 需要先创建 workflow | 不展示假图或实体知识图谱 |
| true | false（trace 未到） | 等待 workflow trace | 显示当前 `status / stage` |
| true | true | workflow 已失败，未生成 trace | 显示 `failureSummary` 或 `errorMessage` |

`isWorkflowFailed` 取 `status === 'failed'` 或 `stage === 'failed'`。

### 4.3 运行事件 timeline-panel

- 取 `events.slice(-8)`；
- 每行 `sequence + event_type + 本地化时间`；
- 没有事件时显示「尚未创建分析任务」。

## 5. 右侧 Inspector

### 5.1 节点说明（顶部 `inspector-panel`，`inspector/*`）

按优先级渲染：

1. `selectedNode` 存在 → `inspector/NodeInspector.tsx`；
2. 否则 `judgment` 存在 → `inspector/JudgmentInspector.tsx`；
3. 否则 `inspector/TraceInspectorEmptyState.tsx`。

### 5.2 NodeInspector

每种节点类型都用**中文标签**渲染 description-list，顶部固定一项「{NODE_TYPE_LABELS[node.node_type]}」+ `summary`（`NODE_TYPE_LABELS` 在 `layout/traceConstants.ts`）：

- `agent_argument`：代理身份（`agent_id · role · 第 N 轮`）/ 论证内容（`argument` 全文）/ 置信度 / 支持证据 / 反驳证据 / 已声明局限；
- `round_summary`：轮次 / 本轮摘要 / 参与代理 / 该轮论证 ID 列表（提示用户点击图上对应节点查看正文）/ 引用证据 / 争议证据；
- `evidence`：来源（`source · source_type`）/ 标题（可选）/ 客观摘要（`objective_summary || content`）/ 质量评分（来源 / 相关性 / 结构化置信度）/ 原始数据引用；
- `raw_item`：来源 / 标题（可选）/ 链接（可选）/ 原始内容（`truncate(content, 360)`）/ 原始 Payload 节选（`<pre class="payload-block">` 渲染 `JSON.stringify(raw_payload, null, 2)`，截断 480 字符，最高 220px 滚动）/ 派生证据；
- `judgment`：只渲染顶部一项；详情由 `JudgmentInspector` 接管。

`NODE_TYPE_LABELS` 映射：`judgment→最终判断 / round_summary→本轮辩论 / agent_argument→代理论证 / evidence→证据 / raw_item→原始数据`。

`detail` 字段通过点击节点时按需拉取（接口实现在 `src/api/evidence.ts`，类型在 `src/types/`）：

| 类型 | 接口函数 | URL |
| --- | --- | --- |
| `evidence` | `getEvidence(id)` | `GET /api/v1/evidence/{evidence_id}` |
| `raw_item` | `getRawItem(rawRef)` | `GET /api/v1/raw-items/{raw_ref}` |
| `agent_argument` | `getAgentArgument(id)` | `GET /api/v1/agent-arguments/{agent_argument_id}` |
| `round_summary` | `getRoundSummary(id)` | `GET /api/v1/round-summaries/{round_summary_id}` |
| `judgment` | — | 不另发请求；只用 trace 节点自带的 `title`/`summary` |

### 5.3 JudgmentInspector

来自 `snapshot.judgment`：

- final_signal（标题）+ reasoning（正文）；
- 置信度行：`formatScore(confidence) / time_horizon`；
- `risk_notes` 每条单独一项。

禁止：没有 `judgment` 时不展示「最终结论」相关文案，只显示 EmptyState。

### 5.4 图例 `legend-panel`

固定显示「推理边 / Trace 节点」两个示意图。

## 6. 创建任务

`handleCreateWorkflow`：

1. 校验 `ticker.trim()` 与 `selectedConfigId`；
2. 置 `connection='creating'`、清空 `snapshot/trace/events/selectedNode`；
3. 调用 `createWorkflowRun`，body 包含：
   - `ticker / stock_code`（同值，临时双发，等后端协议确认后取其一）；
   - `analysis_time`：默认 `new Date().toISOString()`；
   - `workflow_config_id`；
   - `query`：`lookback_days=30`、`sources=[akshare,tavily,exa]`、`evidence_types=[financial_report,company_news,industry_news]`、`max_results=50`；
   - `options`：`stream=true, include_raw_payload=false, auto_run=true`。
4. 创建成功 → `setWorkflowRunId(created.workflow_run_id)` → `loadWorkflowState(runId, 'replace_events')`；
5. 失败 → `connection='error'`，错误消息走 `formatApiError`。

## 7. SSE 订阅

`AnalysisPage` 调用 `src/hooks/useWorkflowStream.ts` 把订阅生命周期抽到 hook 内：

- 输入：`workflowRunId`；
- 回调：`onReplaying`（建立连接前置 `connection='replaying'`）、`onOpen`、`onError`、`onParseError`、`onMessage(event)`；
- 内部：`new EventSource(eventStreamUrl(runId, 0))`，覆盖 22 种事件类型的显式 `addEventListener`（含 `snapshot`）；`onerror → source.close()`，不自动重连；
- 卸载：清理所有监听并关闭 `EventSource`。

`AnalysisPage.handleStreamMessage(parsed)`：

1. 如果 `event_type==='snapshot'`，把 `payload as WorkflowSnapshot` 写进 `snapshot`；
2. 如果是 `workflow_failed / *_completed` 终态事件，触发 `loadWorkflowState(runId, 'merge_events')`；
3. 按 `event_id` 去重，按 `sequence` 排序后写回 `events`。

约束与缺口：

- 当前每次重订阅都 `after_sequence=0`，依赖后端 replay 全量重放；前端没有持久化 `lastSequence`。
- SSE 断线后不会自动重连，用户必须点击「刷新快照」。
- `agent_argument_delta`、`judgment_delta`、`round_summary_delta` 目前只进 events 列表，**没有**驱动 Inspector 流式拼接。

## 8. 主要接口

接口实现散布在 `src/api/workflow.ts`（workflow 域）与 `src/api/evidence.ts`（节点下钻域）：

```http
GET  /api/v1/workflow-configs                                  -- listWorkflowConfigs
POST /api/v1/workflow-runs                                     -- createWorkflowRun
GET  /api/v1/workflow-runs/{workflow_run_id}/snapshot?include_events=true  -- getWorkflowSnapshot
GET  /api/v1/workflow-runs/{workflow_run_id}/trace             -- getWorkflowTrace
GET  /api/v1/workflow-runs/{workflow_run_id}/events?follow=true[&after_sequence=N]  -- eventStreamUrl
GET  /api/v1/evidence/{evidence_id}                            -- getEvidence
GET  /api/v1/raw-items/{raw_ref}                               -- getRawItem
GET  /api/v1/agent-arguments/{agent_argument_id}               -- getAgentArgument
GET  /api/v1/round-summaries/{round_summary_id}                -- getRoundSummary
```

未启用但保留协议位的接口：

- `evidence-references`、`round-summaries/{id}`、`entities/{id}/relations`：当前 UI 不消费，需要时再接入。

## 9. 错误与失败

`WorkflowRunCreateView` 和 `WorkflowSnapshot.workflow_run` 都新增了 `failure_code?: string | null` + `failure_message?: string | null`，作为 workflow 失败时的结构化原因。

### 9.1 创建失败

- 网络/HTTP 错误：`connection='error'` + `formatApiError(error, '分析任务创建失败')`。
- 后端立即返回 `status==='failed'` + `failure_message`：写入 `errorMessage`，仍记录 `workflow_run_id` 以便后续 snapshot 拉取失败上下文。

### 9.2 Workflow 失败

`isWorkflowFailed = status==='failed' || stage==='failed'`：

- 清空 `trace`、`selectedNode`；
- `failureSummary` 优先取 `snapshot.workflow_run.failure_message`；其次找最近一条 `workflow_failed` 事件，按 `payload.code` 走 `utils/failure.ts:summarizeFailurePayload` 映射；
- 映射的友好文案（中文）：

  | code | 文案 |
  | --- | --- |
  | `insufficient_evidence` | 证据不足：{gaps} 或「证据不足，Judge 没有形成最终判断。」 |
  | `agent_swarm_failed` | Agent 论证失败：{message} |
  | `judge_failed` | Judge 汇总失败：{message} |
  | `evidence_acquisition_failed` | 证据采集失败：{message} |
  | `missing_runtime_configuration` | 「分析无法开始：后端运行配置不完整，请先配置数据源或模型 key。」 |
  | `missing_judgment` | 「最终判断缺失：…」 |

### 9.3 节点详情拉取失败

不阻断已选中节点的 baseNode 展示，只在 `errorMessage` 上记账：`Evidence 加载失败 / Raw Item 加载失败 / Agent Argument 加载失败`。

## 10. 视觉规范（落地版）

- 中间图区：纯白底 + 1px 黑虚线网格；
- 节点矩形黑框，hover / focus 状态切换为克莱因蓝描边但宽度不变（避免双框错觉）；
- selected 状态走**反色**：节点矩形填充克莱因蓝、标题副标题文字变白；judgment 节点本来就是蓝底白字，选中后保持一致；
- `judgment` 节点保留可换为蓝底白字的能力（CSS 类 `.trace-node.judgment`）；
- 连线 90° 折线、标签等宽字体 + 实色背景框；
- 冲突 / 反驳边类型只通过 `edge_type` 区分，不大面积染色；
- 悬停 / 选中使用瞬时反色，不使用阴影、不使用圆角。

完整调色板和字体规范见 `design_skill.md`。

## 11. MVP 范围

已实现：

- workflow 创建 + 表单；
- snapshot + trace + events 三接口联调；
- SSE 订阅 + 终态事件触发 snapshot/trace 复拉；
- 中间 Trace Graph SVG + 节点点击下钻；
- Evidence / Raw / Argument Inspector；
- 失败态友好文案。

暂未实现（已知缺口）：

- `workflow_run_id` 写入 URL；
- SSE 自动重连 + `after_sequence` 续传；
- delta 流式拼接到 Inspector；
- `evidence-references` 视图、Entity Relations 下钻；
- 多 workflow tab；
- 图布局切换（证据→结论 / 结论→证据 / 按 Agent 轮次分组）。
