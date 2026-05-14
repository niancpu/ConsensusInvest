# 运行模式设计

系统支持三类运行模式：主 workflow、报告生成、异步补齐。三者共享 Evidence Store，但运行 ID、输出对象和用户承诺不同。

## 1. 主 workflow

适用场景：

- 用户需要完整分析链路；
- 需要 Agent Swarm 论证；
- 需要 Judge 最终判断；
- 前端要展示从最终判断下钻到论据和原始材料。

流程：

```text
Create workflow_run
  -> optional SearchTask
  -> Evidence ingest / structure
  -> Agent Swarm
  -> Round Summary
  -> Judge
  -> Judgment / Trace
```

状态：

- 创建 `workflow_run_id`。
- 写 `workflow_runs`、`agent_runs`、`agent_arguments`、`round_summaries`、`judgments`。
- 所有重要论点写 `evidence_references`。
- `workflow_runs` 是主 workflow 运行态事实来源，不能只保存在 Orchestrator 内存中。
- Agent 执行状态写 `agent_runs`；Agent 输出的论点和 Judge 输出分别写入对应产物表。

边界：

- 主 workflow 可以触发 Search Agent，但 Search Agent 结果必须先入 Evidence Store。
- Evidence 不足时，Orchestrator 默认把 `EvidenceGap` 交给 `EvidenceAcquisitionService`，由它转换为 SearchTask 并重试补齐。
- 重试仍无法补齐时，主 workflow 输出信息不足状态和缺口说明，不把缺证场景伪装成完整判断。

## 2. 报告生成

适用场景：

- 客户只想看报告或个股研究卡片；
- 不需要完整 Agent Swarm / Judge；
- 允许基于已有 Evidence 和 MarketSnapshot 编排报告视图。

流程：

```text
Create report_run
  -> Query Evidence Store / MarketSnapshot
  -> report assembly / formatting
  -> Report View
```

状态：

- 不创建 `workflow_run_id`。
- 创建 `report_run_id`。
- `judgment_id` 必须为空。
- 输出必须带 `trace_refs.evidence_ids` / `trace_refs.market_snapshot_ids`，并说明没有主 workflow 判断链。
- `report_runs` 是报告生成运行态事实来源；报告视图缓存不能替代 `report_run_id`。

边界：

- 报告生成不是主链路 Judgment。
- Report Module 不负责解读、分析或生成投资建议。
- 报告生成可以引用 Evidence 和 MarketSnapshot，但不能写 `agent_arguments`、`round_summaries`、`judgments`。
- 报告生成只能编排、格式化和展示已有 Evidence、Evidence Structure、MarketSnapshot 或已有主 workflow 输出，不能创造新的判断语义。
- 如果后续用户升级为完整分析，应新建主 workflow；可以复用已有 Evidence 和 MarketSnapshot，不能复用 `report_run_id` 冒充 `workflow_run_id`。

## 3. 异步补齐

适用场景：

- Evidence Store 数据缺失；
- Report Module 根据数据状态规则发现已有数据过期；
- 主 workflow 需要更多 Evidence 支撑。

流程：

```text
Submit SearchTask
  -> Search Agent Worker
  -> SearchResultPackage
  -> Evidence Store ingest
  -> later query by workflow/report
```

主 workflow 内由证据缺口触发补齐时，完整链路为：

```text
Agent Swarm / Judge finds EvidenceGap
  -> Workflow Orchestrator
  -> EvidenceAcquisitionService
  -> SearchAgentPool.submit(SearchTask)
  -> Search Agent Worker
  -> SearchResultPackage
  -> Evidence Store ingest
  -> Orchestrator re-query Evidence
  -> Agent Swarm / Judge continue
```

状态：

- 可以有 `workflow_run_id`，也可以没有。
- 必须有 `correlation_id`。
- SearchTask 完成不直接生成报告或判断，只生成可被后续消费的 Raw/Evidence。
- `search_tasks` 是异步补齐运行态事实来源。创建补齐任务时必须先持久化任务，再返回 `task_id` 或 `refresh_task_id`。
- 内存 worker、事件流和前端连接只负责执行与观察，不能替代 `search_tasks` 的状态记录。

边界：

- 补齐是异步动作，调用方不能阻塞等待完整搜索结果。
- Report Module 只保存 `refresh_task_id` 和 `data_state`。
- Agent Swarm / Judge 只能返回 `EvidenceGap` 或 `suggested_search`，不能自己直接调用 provider，也不能直接调用 Search Agent。
- `EvidenceAcquisitionService` 属于 Orchestrator 内部能力，只负责任务转换、预算和重试控制，不生产 Raw/Evidence。

## 4. Evidence 不足重试策略

默认策略：

1. Agent Swarm / Judge 发现 Evidence 不足时，返回 `EvidenceGap`。
2. Orchestrator 将 `EvidenceGap` 交给 `EvidenceAcquisitionService`。
3. `EvidenceAcquisitionService` 按 workflow 预算、source 白名单、回测约束和重试次数生成 `SearchTask`。
4. Search Agent 搜集后交由 Evidence Store 入库。
5. Orchestrator 重新选择 Evidence 并继续分析。
6. 若 Research/Search Agent 明确返回无法补齐，workflow 输出信息不足报告。

第一版重试预算：

- 同一 workflow 最多自动补齐 2 轮。
- 同一 `gap_type` 最多重试 1 次。
- Research/Search Agent 明确返回不可补齐原因时，视为该缺口无法补齐。原因可以包括 provider 全失败、无新增可用结果，或命中回测时间约束导致结果全部不可用。
