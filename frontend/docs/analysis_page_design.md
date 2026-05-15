# 分析页面设计

本文档只定义主分析页面。该页面用于围绕某一只股票展示完整 workflow、Agent 辩论、Judge 裁决和可审计图谱。

## 1. 页面判断

分析页中间必须放一张主图，但这张图不是普通知识图谱，也不是报告关系图。

主图使用后端主 workflow 的 Trace Graph：

```http
GET /api/v1/workflow-runs/{workflow_run_id}/trace
```

核心字段：

- `trace_nodes`;
- `trace_edges`;
- `node_type`: `judgment`、`agent_argument`、`evidence`、`raw_item`;
- `edge_type`: `uses_argument`、`supports`、`counters`、`derived_from` 等。

取舍：

- 主图优先回答“这个判断为什么成立”。
- Evidence References 图可以作为主图的数据补充，用于展示 Agent/Judge 对 Evidence 的引用强度和角色。
- Entity Relations 图只回答实体关系，例如公司、行业、政策、事件之间的关系；它不能放在分析页中心替代 Trace Graph。

## 2. 总体布局

分析页采用三栏一底结构：

```text
┌──────────────────────────────────────────────────────────────┐
│ Stock Context / Workflow Status / Actions                    │
├──────────────┬─────────────────────────────┬─────────────────┤
│ Debate Rail  │ Trace Graph Canvas           │ Inspector       │
│              │                             │                 │
│ Bull / Bear  │ Judgment -> Arguments        │ Selected Node   │
│ Rounds       │ -> Evidence -> Raw           │ Evidence / Raw  │
│ Agent State  │                             │ Details         │
├──────────────┴─────────────────────────────┴─────────────────┤
│ Runtime Event Tape                                             │
└──────────────────────────────────────────────────────────────┘
```

页面优先级：

1. 中间主图：Trace Graph。
2. 左侧辩论轨：Agent 轮次和立场。
3. 右侧详情面板：当前选中节点的证据、原文、论点或 Judgment。
4. 底部事件带：运行过程和错误状态。

## 3. 顶部上下文栏

顶部栏展示当前分析对象和 workflow 身份。

必须展示：

- 股票代码 / 股票名称；
- `workflow_run_id`;
- `status`;
- `stage`;
- `analysis_time`;
- `workflow_config_id`;
- SSE 连接状态；
- 最新事件序号；
- 创建新分析按钮；
- 打开历史按钮。

规则：

- `analysis_time` 必须显眼，避免用户把旧分析误认为实时结论。
- `workflow_run_id` 可折叠，但要能复制。
- 如果当前页面没有 `workflow_run_id`，只能停留在创建态，不能展示 Judgment。

## 4. 中间 Trace Graph

页面主图命名为“判断溯源图”，也可在说明文案中称为“推理链路图”。该命名用于强调数据来自 workflow trace，而不是实体知识图谱。

### 4.1 节点类型

| 节点类型 | 展示名称 | 视觉层级 | 点击后右侧面板 |
| --- | --- | --- | --- |
| `judgment` | Judge | 最高层，放顶部或最右终点 | Judgment 摘要、置信度、风险、引用 |
| `agent_argument` | Agent Argument | 中间层，按 Agent 和轮次分组 | 论点正文、Agent、轮次、引用 Evidence |
| `evidence` | Evidence | 事实层，按来源或类型分组 | Evidence 结构、质量、来源、冲突标记 |
| `raw_item` | Raw Item | 原始层，放底部或最左来源层 | 原始来源、抓取时间、payload 下钻入口 |

视觉编码：

- `judgment` 使用克莱因蓝底、白字；
- `agent_argument` 使用白底、黑框、Agent 标签；
- `evidence` 使用白底、克莱因蓝左边线；
- `raw_item` 使用白底、等宽小字号；
- 低质量或冲突 Evidence 只用极小红色标记，不大面积染色。

### 4.2 边类型

| 边类型 | 含义 | 展示 |
| --- | --- | --- |
| `uses_argument` | Judgment 使用某个 Agent 论点 | 黑色直角线 |
| `supports` | 论点引用 Evidence 作为支持 | 克莱因蓝直角线 |
| `counters` / `refuted` | 反驳或削弱 | 红色短标记 + 黑色直角线 |
| `derived_from` | Evidence 来自 Raw Item | 黑色细线 |
| `cited` | 仅引用 | 灰度不可用；使用黑色虚线或细线标签 |

所有连线必须是 90 度直角折线。禁止力导向、圆形节点和曲线连线。

### 4.3 布局方向

推荐默认布局：

```text
Raw Item -> Evidence -> Agent Argument -> Judgment
```

也可以提供切换：

- 证据到结论：适合审计；
- 结论到证据：适合阅读最终 Judgment 后下钻；
- Agent 轮次视图：适合观察 Bull/Bear 辩论。

MVP 先做一种默认布局，不需要复杂图编辑能力。

### 4.4 运行中状态

运行中不能等待最终 `trace` 才显示图。

前端构图策略：

1. 创建 workflow 后订阅 SSE；
2. 根据事件生成临时运行节点，例如 connector、evidence、agent、judge；
3. `agent_argument_delta` 和 `judgment_delta` 只显示为流式文本，不写入最终图节点；
4. 收到 `agent_argument_completed`、`round_summary_completed`、`judgment_completed` 后，查询或合并对应资源；
5. workflow 完成后拉取 `trace`，用后端 Trace Graph 替换临时图。

规则：

- 临时节点必须有“running / tentative”视觉状态；
- 最终 `trace` 返回后，图以 `trace_nodes/trace_edges` 为准；
- 如果 SSE 断线，先显示连接状态，再用 `snapshot` 恢复。

## 5. 左侧 Debate Rail

左侧不是聊天窗口，而是辩论目录和运行态索引。

展示：

- Agent 列表：Bull、Bear、Risk、Valuation、Judge 等；
- 每个 Agent 的运行状态；
- 轮次；
- 已完成论点数量；
- 当前正在生成的 delta 片段；
- 引用 Evidence 数量。

点击行为：

- 点击 Agent：主图高亮该 Agent 的所有 argument；
- 点击 Round：主图过滤该轮；
- 点击 Argument：右侧打开论点详情，中间图定位到节点。

## 6. 右侧 Inspector

右侧详情面板根据选中节点切换内容。

### 6.1 Judgment 面板

展示：

- final signal；
- confidence；
- reasoning 摘要；
- risk notes；
- referenced argument ids；
- trace 入口。

禁止：

- 展示没有 `judgment_id` 的最终投资结论；
- 把报告视图 summary 当 Judgment。

### 6.2 Agent Argument 面板

展示：

- Agent ID；
- round；
- thesis / argument 文本；
- referenced evidence ids；
- completed 状态；
- 对应 Evidence 列表。

### 6.3 Evidence 面板

展示：

- evidence id；
- evidence type；
- source；
- source quality；
- structuring confidence；
- objective summary；
- claims；
- conflicts；
- raw item 链接。

规则：

- Evidence 自身没有天然利多/利空属性；
- `reference_role` 才表达它在某个论点中的引用角色。

### 6.4 Raw Item 面板

展示：

- raw ref；
- provider；
- title / url；
- collected_at；
- payload 摘要；
- 打开完整原文或 payload 的入口。

## 7. 底部 Runtime Event Tape

底部事件带用于展示 workflow 当前发生了什么。

事件分组：

- 采集：`connector_started`、`connector_progress`、`raw_item_collected`;
- 证据：`evidence_normalized`、`evidence_structuring_started`、`evidence_structured`;
- 辩论：`agent_run_started`、`agent_argument_delta`、`agent_argument_completed`;
- 裁决：`judge_started`、`judge_tool_call_started`、`judge_tool_call_completed`、`judgment_delta`、`judgment_completed`;
- 终态：`workflow_completed`、`workflow_failed`。

展示规则：

- 默认只展示最近事件；
- 支持展开完整事件日志；
- 每个事件保留 `event_id`、`sequence`、`created_at`；
- 错误事件必须给出可见状态，不能只在控制台打印。

## 8. 主要接口

创建与恢复：

```http
POST /api/v1/workflow-runs
GET /api/v1/workflow-runs/{workflow_run_id}
GET /api/v1/workflow-runs/{workflow_run_id}/snapshot
GET /api/v1/workflow-runs/{workflow_run_id}/events
```

图和下钻：

```http
GET /api/v1/workflow-runs/{workflow_run_id}/trace
GET /api/v1/workflow-runs/{workflow_run_id}/evidence
GET /api/v1/workflow-runs/{workflow_run_id}/evidence-references
GET /api/v1/workflow-runs/{workflow_run_id}/agent-arguments
GET /api/v1/workflow-runs/{workflow_run_id}/judgment
```

实体关系只做辅助下钻：

```http
GET /api/v1/entities/{entity_id}/relations?depth=1
```

## 9. 空状态

### 9.1 未创建 workflow

中间图区域展示“需要先创建 workflow”的空态，不展示假图、演示图或实体知识图谱。

### 9.2 已创建但排队中

中间图展示 workflow 根节点和 queued 状态；底部事件带等待首个事件。

### 9.3 运行中

展示临时运行图和实时事件。

### 9.4 已完成

展示后端 `trace` 返回的最终图，并允许从图进入 Evidence、Raw、Agent Argument 和 Judgment。

### 9.5 失败

保留已经产生的 Evidence、事件和错误信息。不能把失败页清空。

## 10. 视觉规范

遵循 `design_skill.md`：

- 中间图是纯白底、纯黑 1px 网格；
- 节点全部是直角矩形；
- 连接全部是直角折线；
- 图上标签使用等宽字体；
- Judge 节点可使用克莱因蓝实底；
- 不使用阴影、圆角、渐变和大面积灰色；
- hover 使用瞬时反色；
- 当前选中路径使用克莱因蓝描边；
- 冲突或错误只用小面积红色标记。

## 11. MVP 范围

MVP 必须实现：

- `workflow_run_id` 路由；
- 创建 workflow；
- SSE 订阅和断线恢复；
- 中间 Trace Graph；
- 节点点击 Inspector；
- Evidence / Raw 下钻入口；
- workflow completed 后拉取最终 `trace`；
- 历史 workflow 打开后复用同一分析页。

MVP 暂不实现：

- 手动编辑图；
- 多人协作；
- WebSocket；
- 跨 workflow 多跳知识图谱；
- 把 report view 混入主图。
