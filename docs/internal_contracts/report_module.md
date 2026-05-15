# Report Module 内部接口协议

Report Module 对应 `docs/report_module`，承接个股研究、市场看板、事件、利好、风险等报告视图能力。本文定义它和主系统内部模块之间的接口契约，不定义前端 HTTP API。它不是主链路 Agent，也不是数据抓取模块；它负责把主系统已有的 Evidence、Judgment、Trace、Market Snapshot 聚合成页面可用的报告视图。

Report Module 有两条执行路径：

| 路径 | 会调用什么 | 说明 |
| --- | --- | --- |
| 读视图路径 | Evidence Store、Main Runtime Query | 默认路径。只读取已入库 Evidence、Raw、Structure、MarketSnapshot、Judgment、Trace，不触发外部搜索。 |
| 异步补齐路径 | Search Agent Pool | 仅当数据缺失/过期且 `refresh_policy` 允许时提交 SearchTask；Report Module 不自己抓 provider，也不直接消费 SearchResultPackage。 |

Report Module 可以不依赖主 workflow 运行。客户只请求报告视图时，系统创建 `report_run_id`，`workflow_run_id` 为空，`report_mode=report_generation`；这条链路只输出报告视图，不生成主链路 `agent_arguments`、`round_summaries`、`judgments`。

高判断区边界：

- `report_generation` 不是主 workflow 的降级结果，也不是 `Judgment`。
- Report Module 不能生成投资解读、分析结论、方向性判断或操作建议。
- 报告视图字段只能来自 Evidence Structure、MarketSnapshot、Entity、已有 Workflow Trace/Judgment，或对这些对象的格式化投影。
- 如果视图字段包含方向性语义，例如 benefit、risk、signal、action，必须来自已有 `judgment_id` 或 Evidence Structure 中明确存在的客观风险披露；Report Module 不能自行推断方向。

## 1. build_stock_research_view

```text
ReportModule.build_stock_research_view(envelope: InternalCallEnvelope, request: StockResearchViewRequest) -> StockResearchView
```

请求：

```json
{
  "stock_code": "002594.SZ",
  "ticker": "002594",
  "entity_id": "ent_company_002594",
  "workflow_run_id": null,
  "query": "比亚迪基本面",
  "refresh_policy": "missing",
  "report_mode": "report_generation"
}
```

字段注解：

| 字段 | 说明 |
| --- | --- |
| `workflow_run_id` | 指定后优先读取该 workflow 的 Judgment、Trace、Evidence。 |
| `query` | 用户查询文本，用于视图聚合，不作为事实来源。 |
| `refresh_policy` | `never`、`missing`、`stale`、`force`。 |
| `report_mode` | `report_generation` 或 `with_workflow_trace`；默认按 `workflow_run_id` 是否为空推断。 |

`refresh_policy` 行为：

| 值 | 行为 |
| --- | --- |
| `never` | 只读现有 Store 和 Trace；缺数据也不提交 SearchTask。 |
| `missing` | 关键数据缺失时提交异步 SearchTask。 |
| `stale` | 数据缺失或过期时提交异步 SearchTask。 |
| `force` | 无论当前是否已有数据，都提交异步 SearchTask；当前响应仍先返回已有数据。 |

返回：

```json
{
  "stock_code": "002594.SZ",
  "entity_id": "ent_company_002594",
  "workflow_run_id": null,
  "judgment_id": null,
  "report_run_id": "rpt_20260513_002594_0001",
  "report_mode": "report_generation",
  "data_state": "ready",
  "summary": "报告视图基于已入库财务数据、公告摘要和市场快照生成，未运行主 workflow。",
  "key_evidence_ids": [
    "ev_20260513_002594_tushare_001"
  ],
  "benefits": [],
  "risks": [
    {
      "text": "公告中披露现金流质量需要继续核对。",
      "evidence_ids": ["ev_20260513_002594_report_003"],
      "source": "evidence_structure_risk_disclosure"
    }
  ],
  "trace_refs": {
    "evidence_ids": ["ev_20260513_002594_tushare_001"],
    "market_snapshot_ids": ["mkt_snap_20260513_002594"],
    "raw_refs": ["raw_20260513_002594_tushare_001"],
    "judgment_id": null,
    "workflow_run_id": null
  },
  "limitations": [
    "本报告未运行主 workflow，因此没有 Agent Swarm 论证链和 Judge 最终判断。"
  ],
  "refresh_task_id": null
}
```

`data_state`：

```text
ready
partial
missing
refreshing
stale
failed
```

约束：

- 当前调用必须返回已有数据和 `data_state`，不得阻塞等待 Search Agent 完成。
- 当 `refresh_policy` 允许且数据不足时，`build_stock_research_view` 可以在内部调用 `request_refresh`，并在响应中返回 `refresh_task_id`。
- `refresh_task_id != null` 只表示已提交补齐任务，不表示新数据已经可用于当前响应。
- `summary` 只能来自 Evidence Structure 的客观摘要、已有 Judgment 摘要，或对引用对象的模板化说明；作为字符串字段时，必须能通过 `trace_refs` 回查来源。
- `benefits` 在 `report_generation` 下必须为空；只有 `with_workflow_trace` 且存在 `judgment_id` 时才可从主 Judgment 投影。
- `risks` 在 `report_generation` 下只能来自 Evidence Structure 中明确的客观风险披露或限制说明；不能由 Report Module 推断。
- `benefits`、`risks` 条目必须保留 `evidence_ids`、`market_snapshot_ids`、`workflow_run_id` 或 `judgment_id`；`summary` 必须通过 `trace_refs` 或后续 `summary_refs` 等价字段保留来源。
- Report Module 不写主链路 `agent_arguments`、`judgments`。

## 2. report_generation 模式

客户只需要报告、不需要主 workflow 时，调用仍走 `build_stock_research_view`，但 `workflow_run_id=null`，`report_mode=report_generation`。

执行规则：

1. 用 `ticker` / `entity_id` 从 Evidence Store 查询最新可用 Evidence、Structure、Market Snapshot。
2. 如数据足够，Report Module 只能编排 Evidence Structure、MarketSnapshot、Entity 和已有引用，生成报告视图字段。
3. 如数据不足且 `refresh_policy` 允许，提交异步 SearchTask，并返回 `data_state=refreshing` 或 `partial`。
4. Search Agent 结果入库后，下一次 Report 查询再读取新的 Evidence。

`report_generation` 输出必须显式标记：

| 字段 | 要求 |
| --- | --- |
| `workflow_run_id` | 必须为 `null`。 |
| `judgment_id` | 必须为 `null`，因为没有运行 Judge。 |
| `report_run_id` | 必填，用于追踪本次报告生成。 |
| `trace_refs.evidence_ids` | 必填或为空数组；报告引用了哪些 Evidence。 |
| `trace_refs.market_snapshot_ids` | 必填或为空数组；报告引用了哪些 MarketSnapshot。 |
| `trace_refs.raw_refs` | 可选；需要前端直接下钻 Raw 时返回。 |
| `limitations` | 必须说明没有主 workflow 判断链。 |

`report_generation` 模式允许输出页面摘要，但摘要必须是客观材料的组织结果，不能包装成主链路 Judgment。后续如果用户升级为完整分析，应新建主 workflow；Report 可以复用已有 Evidence 和 MarketSnapshot，但不能复用 `report_run_id` 冒充 `workflow_run_id`。

## 3. request_refresh

Report Module 发现数据缺失或过期时，可以提交 SearchTask。这个动作可以由 `build_stock_research_view` 内部触发，也可以由调度器显式调用：

```text
ReportModule.request_refresh(envelope: InternalCallEnvelope, request: ReportRefreshRequest) -> AsyncTaskReceipt
```

请求：

```json
{
  "reason": "missing_company_news",
  "target": {
    "ticker": "002594",
    "stock_code": "002594.SZ",
    "entity_id": "ent_company_002594",
    "keywords": ["比亚迪", "BYD"]
  },
  "scope": {
    "evidence_types": ["company_news", "financial_report"],
    "lookback_days": 30,
    "max_results": 30
  }
}
```

内部行为：

1. 生成 `SearchTask`。
2. 调用 `SearchAgentPool.submit(envelope, SearchTask)`。
3. 保存 `refresh_task_id` 和 `data_state=refreshing` 到报告视图缓存或运行记录。
4. 后续通过 Evidence Store 重新查询入库结果。

约束：

- `envelope.requested_by` 必须是 `report_module` 或具体报告子模块名。
- `SearchTask.callback.ingest_target` 必须是 `evidence_store`。
- Report Module 不保存 Search Agent 返回的 `SearchResultPackage`。
- Report Module 不等待 SearchTask 完成；搜索结果入库后才会在后续视图构建中被读取。

## 4. Report View Assembler 输出

Report Module 可以有视图装配器或轻量格式化器，但它只做排序、摘录、模板填充和引用组织，不能生成新的投资解释。输出只归报告视图层：

```json
{
  "report_run_id": "rpt_20260513_002594_0001",
  "assembler_id": "report_view_assembler_v1",
  "input_refs": {
    "workflow_run_id": "wr_20260513_002594_000001",
    "judgment_id": "jdg_20260513_002594_001",
    "evidence_ids": ["ev_20260513_002594_tushare_001"],
    "market_snapshot_ids": ["mkt_snap_20260513_002594"]
  },
  "output": {
    "summary": "基于已入库 Evidence Structure 和已有 Judgment 的报告摘要。",
    "benefits": [],
    "risks": []
  },
  "created_at": "2026-05-13T11:10:00+08:00"
}
```

字段注解：

| 字段 | 说明 |
| --- | --- |
| `report_run_id` | Report Module 运行 ID，不等同于主 workflow。 |
| `input_refs` | 必须保留输入引用，避免页面文案失去证据链。 |
| `output` | 页面聚合结果，不回写 Evidence。 |

在 `report_generation` 模式下，`input_refs.workflow_run_id` 和 `input_refs.judgment_id` 为 `null`，但 `evidence_ids` 或 `market_snapshot_ids` 仍必须保留。

## 5. 读取主链路 Trace

```text
MainRuntimeQuery.get_workflow_trace(envelope: InternalCallEnvelope, workflow_run_id: string) -> WorkflowTrace
```

返回应包含：

```json
{
  "workflow_run_id": "wr_20260513_002594_000001",
  "agent_argument_ids": ["arg_20260513_bull_v1_r1_001"],
  "round_summary_ids": ["rsum_20260513_002594_r1"],
  "judgment_id": "jdg_20260513_002594_001",
  "key_evidence_ids": ["ev_20260513_002594_tushare_001"],
  "event_ids": ["evt_20260513_000001"]
}
```

## 6. 事件

| event_type | payload |
| --- | --- |
| `report.view_built` | `report_run_id`、`stock_code`、`data_state` |
| `report.refresh_requested` | `refresh_task_id`、`reason`、`target` |
| `report.view_cache_updated` | `report_run_id`、`input_refs` |
