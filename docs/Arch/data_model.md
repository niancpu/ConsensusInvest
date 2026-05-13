# 数据模型归属

本文档只定义主要数据对象的归属和长期边界。字段级接口协议见 `docs/internal_contracts`。

## 1. 主对象

| 对象 | 归属模块 | 说明 |
| --- | --- | --- |
| `SearchTask` | Search Agent Pool | 搜索/刷新任务。 |
| `SearchResultPackage` | Search Agent Pool 临时输出 | 待入库原始信息包，不是 Evidence。 |
| `RawItem` | Evidence Store | 外部来源原始记录。 |
| `EvidenceItem` | Evidence Store | 可引用事实对象。 |
| `EvidenceStructure` | Evidence Store | 客观摘要、关键事实、claims、质量标记。 |
| `EvidenceReference` | Evidence Store | Agent/Judge/Report 对 Evidence 的引用关系。 |
| `WorkflowRun` | Workflow Runtime | 一次主分析流程。 |
| `AgentRun` | Agent Swarm | Agent 执行记录。 |
| `AgentArgument` | Agent Swarm | Agent 论点。 |
| `RoundSummary` | Debate Runtime | 单轮压缩摘要。 |
| `Judgment` | Judge Runtime | 主 workflow 最终判断。 |
| `ReportRun` | Report Module | 报告生成记录。 |
| `MarketSnapshot` | Evidence Store | 市场快照数据；由 Evidence Store 管理，但不是 `EvidenceItem`。 |

## 2. ID 语义

| ID | 语义 |
| --- | --- |
| `correlation_id` | 跨模块调用追踪 ID，适用于 workflow、报告生成、异步补齐。 |
| `workflow_run_id` | 主 workflow 运行 ID，只在完整分析链路中存在。 |
| `report_run_id` | Report Module 报告生成 ID，可在没有 workflow 时存在。 |
| `task_id` | SearchTask 或异步任务 ID。 |
| `raw_ref` | RawItem 引用。 |
| `evidence_id` | EvidenceItem 引用。 |
| `judgment_id` | Judge 输出 ID，只属于主 workflow。 |

`workflow_run_id` 不应作为所有模块的默认必填字段。没有主 workflow 时，使用 `correlation_id` 和 `report_run_id` 完成追踪。

## 3. 表归属建议

MVP SQLite 表：

- `search_tasks`
- `raw_items`
- `evidence_items`
- `evidence_structures`
- `evidence_references`
- `entities`
- `evidence_entities`
- `entity_relations`
- `workflow_runs`
- `agent_runs`
- `agent_arguments`
- `round_summaries`
- `judgments`
- `judge_tool_calls`
- `report_runs`
- `report_view_cache`
- `market_snapshots`

未决：

- `search_tasks` 是否保留在主 SQLite，还是迁移到任务队列。

## 4. 写入原则

- Raw、Evidence、Structure、MarketSnapshot 只由 Evidence Store 写入。
- EvidenceReference 由 Evidence Store 持久化；Agent Swarm、Judge Runtime、Report Module 只能通过 Evidence Store 接口提交引用关系，不能直接写表。
- 主推理链只由 Agent Swarm / Judge Runtime 写入。
- Report Module 只直接写 `report_runs` 和视图缓存；报告视图对 Evidence 的持久引用必须走 Evidence Store。
- 外部搜索结果先入 Store，再被其他模块消费。
- MarketSnapshot 由 Evidence Store 管理，但不等同于 EvidenceItem，不承载投资建议。
