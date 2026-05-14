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
| `RuntimeEvent` | AgentRuntime | Agent 类任务统一事件日志。 |

## 2. 运行态持久化对象

运行态对象不是临时工程实现。凡是对外返回 ID、可被查询状态、可重试、可恢复或影响 trace 的运行对象，都必须持久化。

| 对象 | 表 | 事实来源 |
| --- | --- | --- |
| `SearchTask` | `search_tasks` | Search Agent Pool 的任务状态、幂等和错误 |
| `WorkflowRun` | `workflow_runs` | 主 workflow 阶段、预算、状态和错误 |
| `AgentRun` | `agent_runs` | Agent 执行生命周期、预算、状态和错误 |
| `RuntimeEvent` | `runtime_events` | Agent 类任务时间线、状态变化、工具调用摘要和错误事件 |
| `AgentArgument` | `agent_arguments` | Agent 论点产物 |
| `RoundSummary` | `round_summaries` | Debate Runtime 压缩产物 |
| `Judgment` | `judgments` | Judge 最终判断 |
| `JudgeToolCall` | `judge_tool_calls` | Judge 回查 Evidence/Raw 的 trace |
| `ReportRun` | `report_runs` | 报告生成状态、完整输入输出快照和限制说明 |
| `ReportViewCache` | `report_view_cache` | 报告视图缓存，不是 Judgment |

事件流、worker 内存对象、HTTP 连接状态和 provider 临时 response 不是事实来源。它们可以丢失，但不能导致已返回 ID 的运行记录消失。

## 3. ID 语义

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

## 4. 表归属建议

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
- `runtime_events`
- `agent_arguments`
- `round_summaries`
- `judgments`
- `judge_tool_calls`
- `report_runs`
- `report_view_cache`
- `market_snapshots`

MVP 中 `search_tasks` 保留在主 SQLite。后续引入独立任务队列时，队列只负责调度和唤醒，不能取代 `search_tasks` 作为任务事实来源。

## 5. 写入原则

- Raw、Evidence、Structure、MarketSnapshot 只由 Evidence Store 写入。
- EvidenceReference 由 Evidence Store 持久化；Agent Swarm、Judge Runtime、Report Module 只能通过 Evidence Store 接口提交引用关系，不能直接写表。
- 主推理链只由 Agent Swarm / Judge Runtime 写入。
- Report Module 只直接写 `report_runs` 和视图缓存；报告视图对 Evidence 的持久引用必须走 Evidence Store。
- 外部搜索结果先入 Store，再被其他模块消费。
- MarketSnapshot 由 Evidence Store 管理，但不等同于 EvidenceItem，不承载投资建议。
- 创建类运行接口必须先写对应运行表，再返回运行 ID。
- AgentRuntime 写 `runtime_events`；该表只保存事件 trace，不保存 Agent 论点、Judgment 或 SearchTask 当前状态。
