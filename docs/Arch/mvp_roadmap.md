# MVP 路线

## Phase 1：事实层骨架

- 定义 Evidence schema。
- 创建 SQLite Evidence Store。
- 实现 Raw/Evidence/Structure 基础表。
- 实现 Evidence 查询和 Raw 回查。
- 优先接入 AkShare 或一个稳定数据源。
- 建立运行态持久化基础约束：创建类接口先写运行表，再返回 ID。

## Phase 2：Search Agent Pool

- 定义 SearchTask。
- 实现 `search_tasks` 持久化状态、幂等键、错误和部分完成状态。
- 实现可并发 source worker。
- 输出 SearchResultPackage。
- 接入 Evidence Store ingest。
- 支持部分失败和幂等提交。

## Phase 3：Evidence 结构化

- 实现 Evidence Normalizer。
- 实现 Evidence Structuring Agent。
- 保存客观摘要、关键事实、claims、质量标记。
- 不写投资方向字段。

## Phase 4：报告生成

- 实现 Report Module 读 Evidence Store 的报告视图。
- 支持 `report_run_id`。
- 持久化 `report_runs`，记录报告生成状态、完整输入输出快照和限制说明。
- 支持 `workflow_run_id=null`。
- 支持 `refresh_policy` 触发异步补齐。
- 明确展示没有主 workflow 判断链的限制。
- 不输出解读、分析或投资建议字段。

## Phase 5：主 workflow MVP

- 定义 workflow config。
- 持久化 `workflow_runs`、`agent_runs`、`runtime_events`、`judge_tool_calls` 和错误状态。
- 实现 `bull_v1`。
- 保存 Agent Argument 和 Evidence Reference。
- 实现 Round Summary。
- 实现 Judge Runtime。
- 输出 Judgment 和可回查 Trace。

## Phase 6：多源与多 Agent 扩展

- 增加 TuShare。
- 增加 Tavily。
- 增加 Exa。
- 增加 Bear / Technical / Fundamental / Policy / Risk Agent。
- 增加多轮 Debate Runtime。

## MVP 非目标

- 自动实盘交易。
- 组合执行。
- 高频信号。
- 复杂前端大屏。
- 一开始实现完整多空专家辩论。
- 完美覆盖所有信息源。

第一目标是验证：Evidence 能否被采集、结构化、引用，并被报告生成和主 workflow 两种路径稳定消费。
