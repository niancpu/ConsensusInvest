# 运行态持久化设计

运行态持久化不是工程细节，而是系统对外承诺的一部分。所有可能跨请求、跨进程、跨重启被用户观察到的运行状态，都必须有明确归属、持久化位置和恢复语义。

本文只定义架构边界和取舍。字段级协议见 `docs/internal_contracts`，表结构由实现文档或迁移脚本维护。

## 1. 问题定义

运行态分三类：

| 类型 | 定义 | 是否必须持久化 |
| --- | --- | --- |
| 可观察运行态 | 用户或上游模块已经拿到 ID，后续会查询状态、结果或错误 | 必须 |
| 业务产物 | Evidence、Argument、Judgment、Report View 等可被后续消费的对象 | 必须 |
| 进程内临时态 | 当前函数栈、worker 内部游标、provider SDK 临时对象、HTTP 连接 | 不必须 |

判断标准：

- 只要已经返回 `task_id`、`workflow_run_id`、`agent_run_id`、`report_run_id`，对应运行态就不能只存在内存里。
- 只要影响用户可见结果、重试策略、预算扣减、错误展示或 trace，下次查询必须能回放或解释。
- 只服务当前进程调度、丢失后可由持久状态重新推导的对象，可以留在内存中。

## 2. 架构决定

MVP 使用 SQLite 持久化运行态，不先引入独立任务队列。

原因：

- 当前核心目标是验证 Evidence、报告生成和主 workflow 的可追踪消费链路。
- SQLite 足够表达运行状态、幂等键、错误、预算和重启恢复。
- 独立队列会提前引入分布式投递、可见性超时、重复消费和运维复杂度。

后果：

- 所有长任务必须先写运行表，再启动 worker。
- worker 可以是进程内异步 worker，但任务来源必须是持久表扫描或已持久化任务 ID。
- 重启后允许继续、重试或标记失败，但不能让用户拿到的 ID 永久消失。
- 后续迁移到队列时，队列只能承载投递和唤醒，不能取代运行表作为事实来源。

迁移触发条件：

- 多进程 worker 并发成为默认部署形态；
- SQLite 写锁成为瓶颈；
- 需要跨机器任务调度；
- 需要可见性超时、延迟队列、死信队列等队列能力。

## 3. 状态归属

| 运行态 | 归属模块 | 持久化对象 | 恢复语义 |
| --- | --- | --- | --- |
| 搜索/刷新任务 | Search Agent Pool | `search_tasks` | 根据状态继续执行、重试、标记部分完成或失败 |
| 主 workflow | Workflow Runtime | `workflow_runs` | 恢复阶段、预算、错误和最终状态 |
| Evidence 补齐请求 | Workflow Orchestrator / EvidenceAcquisitionService | `search_tasks` + `workflow_run_id` / `correlation_id` | 重启后可知道哪个缺口触发了哪个搜索任务 |
| Agent 执行 | AgentRuntime / Agent Swarm | `agent_runs` | 恢复 Agent 状态、错误、预算、trace |
| AgentRuntime 事件 | AgentRuntime | `runtime_events` | 回放 Agent 类任务时间线、状态变化、工具调用摘要和错误事件 |
| Agent 论点 | Agent Swarm | `agent_arguments` | 作为 Judge 和前端下钻输入 |
| Debate 摘要 | Debate Runtime | `round_summaries` | 作为跨轮压缩和 Judge 输入 |
| Judge 工具回查 | Judge Runtime | `judge_tool_calls` | 展示 Judge 查了哪些 Evidence/Raw 以及结果 |
| Judgment | Judge Runtime | `judgments` | 主 workflow 最终判断 |
| 报告生成运行 | Report Module | `report_runs` | 查询报告生成状态、限制说明和输入引用 |
| 报告视图缓存 | Report Module | `report_view_cache` | 加速读取；不是 Judgment，不替代 Evidence |

禁止把所有运行态塞进一个无语义的通用 `runs` 表。可以有统一运行层能力，但持久化对象必须保留模块语义和状态边界。

## 4. 状态机要求

各模块可以有自己的细分状态，但必须映射到下列通用阶段：

| 阶段 | 含义 |
| --- | --- |
| `queued` | 已持久化，等待执行 |
| `running` | 已被 worker 接收 |
| `waiting` | 等待外部 provider、子任务或预算窗口 |
| `partial_completed` | 部分来源或部分步骤完成，存在可用产物和失败项 |
| `completed` | 运行结束且产物已持久化 |
| `failed` | 运行失败，错误已持久化 |
| `cancelled` | 调用方或系统取消，后续不再执行 |

状态变更规则：

- 创建类接口必须先写 `queued`，再返回 ID。
- worker 接手后写 `running`，并记录开始时间。
- 外部 provider 部分失败不能默认升级为整体失败；SearchTask 应允许 `partial_completed`。
- `completed` 之前，关键业务产物必须已经持久化。
- `failed` 必须保存可展示错误和可排查错误；不能只写异常字符串到日志。
- 取消是显式状态，不等于删除任务。

## 5. 事件日志与状态

AgentRuntime 第一版提供统一事件日志表 `runtime_events`，用于记录 Agent 类任务的时间线和可审计事件。

`runtime_events` 保存：

- `agent_run_id`；
- `workflow_run_id` / `correlation_id`；
- `event_type`，例如 `queued`、`started`、`status_changed`、`tool_call_started`、`tool_call_finished`、`budget_updated`、`failed`、`completed`；
- 事件时间；
- 事件摘要；
- 结构化 payload；
- 可展示错误和可排查错误引用。

边界：

- `runtime_events` 是 trace / audit，不替代 `agent_runs` 的当前状态。
- `runtime_events` 不保存 Agent 论点正文；论点归 `agent_arguments`。
- `runtime_events` 不保存 Judge 最终判断；判断归 `judgments`。
- `runtime_events` 不保存 SearchTask 状态；搜索任务状态归 `search_tasks`。
- `runtime_events` 可以记录工具调用摘要，但 Judge 工具回查的业务 trace 仍归 `judge_tool_calls`。

事件流只用于前端和调用方观察进度，不是运行态事实来源。

要求：

- 事件可以丢失、断线和重放失败；状态查询必须仍能给出当前结果。
- 事件流内容必须能由运行表、产物表或 `runtime_events` 解释，不能只存在连接里。
- `runtime_events` 是持久审计日志，不是 SSE / WebSocket 连接状态。

## 6. 幂等与恢复

幂等是运行态持久化的一部分。

- SearchTask 必须支持 `idempotency_key`，不能依赖调用方避免重复提交。
- 创建 workflow/report 时，如果提供幂等键，应返回已有运行 ID 或明确冲突。
- worker 重启后重复领取任务时，必须能基于持久状态判断是否可重入。
- 对外部 provider 的重复抓取允许发生，但 Raw/Evidence 去重归 Evidence Store。

恢复策略：

- `queued`：可重新调度。
- `running`：重启后进入恢复扫描；超过心跳或租约时间后可重试或标记失败。
- `waiting`：恢复等待条件，或转回 `queued`。
- `partial_completed`：保留已入库产物，继续补齐失败部分或返回部分完成。
- `completed` / `failed` / `cancelled`：终态，不自动重跑。

## 7. 允许的内存态

以下对象可以只在内存中：

- 当前 worker 的局部变量；
- provider SDK client、连接池、临时 response 对象；
- 尚未对外暴露 ID 的组装中输入；
- SSE / WebSocket 连接状态；
- 可从持久表重新计算的进度百分比；
- 单次请求内的 view model 临时对象。

但一旦这些对象影响对外状态、预算、错误、引用或产物，就必须落到对应模块的持久对象中。

## 8. 高判断区

已定：

- 运行态持久化是架构边界，不是后补工程优化。
- MVP 运行态事实来源是 SQLite 表，不是内存对象，也不是事件流。
- 持久化按模块归属拆分，不能用无语义通用运行表吞掉 Search、Workflow、Agent、Report 的边界。
- 队列未来可以加入，但只能作为调度层，不能替代运行态事实来源。
- `report_runs` 第一版保存完整输入输出快照，用于复现用户当时看到的报告视图。
- AgentRuntime 第一版提供统一事件日志表 `runtime_events`，用于 Agent 类任务 trace / audit。
- `runtime_events` 在线热数据保留 180 天；超过 180 天的终态运行事件按月归档，归档保留 3 年。
- `runtime_events` MVP 归档格式使用 gzip 压缩 JSONL，按月份分文件。

## 9. `runtime_events` 保留与归档

`runtime_events` 的保留策略按“运行排查优先、长期审计可恢复、主库不无限膨胀”处理。

在线保留：

- SQLite 主库保留最近 180 天的 `runtime_events`。
- 未进入终态的 `agent_run_id` 对应事件不得归档。
- 已进入 `completed`、`failed`、`cancelled` 的 Agent 运行，完成时间超过 180 天后可以归档。

归档周期：

- 每月归档一次上月已满足条件的事件。
- 归档粒度按月份和 `workflow_run_id` / `agent_run_id` 分组。
- 归档文件保留 3 年。
- MVP 归档格式使用 gzip 压缩 JSONL，文件名包含月份和归档批次。

归档内容：

- `runtime_events` 原始事件；
- 事件所属的 `agent_run_id`、`workflow_run_id`、`correlation_id`；
- 事件时间、事件类型、摘要、结构化 payload；
- 错误摘要和可排查错误引用。

边界：

- 归档只处理 `runtime_events`，不删除 `agent_runs`、`agent_arguments`、`judgments`、`judge_tool_calls`、`report_runs` 或 Evidence。
- 归档后的事件不参与当前状态查询；当前状态以 `agent_runs` 和业务产物表为准。
- 归档用于审计和历史排查，不作为前端实时进度来源。
- 如果某个 workflow/report 仍处于争议、人工复核或审计状态，相关 `runtime_events` 延迟归档或归档后禁止删除。
