# Search Agent Pool 设计

Search Agent Pool 是搜索和抓取模块，负责把外部信息源转换为待入库的原始信息包。

## 1. 输入输出

输入是 `SearchTask`，来自 Workflow Orchestrator、Report Module 或维护任务。

输出是 `SearchResultPackage`，包含：

- 来源；
- URL 或等价来源定位；
- 标题；
- 正文或正文抽取；
- 摘要；
- 发布时间；
- 抓取时间；
- provider 原始 payload；
- 来源质量提示。

`SearchResultPackage` 不是草稿，也不是 Evidence。它可以包含完整原文和 URL，但还没有完成系统内去重、时间约束、实体匹配、质量确认和 Evidence ID 分配。

## 2. 并发模型

Search Agent Pool 可以按 source、目标实体、关键词并发多开 worker。

设计后果：

- 多 worker 会返回重复信息，去重归 Evidence Store。
- 单个 provider 失败不应导致整任务失败。
- 任务状态允许 `partial_completed`。
- 幂等必须依赖 `idempotency_key`，不能靠调用方自行避免重复提交。

## 3. 自主扩展边界

Search Agent 可以在同一个 `SearchTask` 内做低判断区扩展，目的是补齐同一事实对象的可回溯材料，而不是改变研究问题。

允许的扩展示例：

- 搜索结果命中转载新闻后，继续抓取原始公告或官方来源。
- provider 返回分页或同一查询的更多结果时，按预算继续拉取。
- 新闻提到交易所公告编号时，补抓对应公告原文。
- 对同一事件做跨 source 核对，补齐 URL、发布时间、作者、正文摘要。

禁止的扩展示例：

- 看到某条负面新闻后，自动扩展到新的行业风险研究。
- 基于搜索结果自行决定新的投资 thesis。
- 为 Debate/Judge 直接准备可用于下结论的未入库材料。
- 绕过 `SearchTask.scope`、`constraints` 或 `analysis_time` 继续搜索。

所有扩展必须受 `SearchTask` 的 source、evidence_types、lookback_days、max_results、budget 和 expansion_policy 约束。超出约束时，Search Agent 应停止扩展并在状态或事件中记录限制原因。

## 4. 状态归属

Search Agent 拥有：

- SearchTask 运行状态；
- worker 状态；
- provider 调用错误；
- SearchResultPackage 临时输出。

Search Agent 不拥有：

- Raw Item；
- Evidence；
- Evidence Structure；
- Agent Argument；
- Judgment；
- Report View。

## 5. 回测安全

Search Agent 可以抓到晚于 `analysis_time` 的信息，但不能决定它是否能用于某次分析。Evidence Store 入库阶段必须根据 `publish_time` 和 `analysis_time` 拒绝或标记不可用。

## 6. 与推理链路的关系

Agent Swarm / Judge 不直接调用 Search Agent。它们只能输出 `EvidenceGap` 或 `suggested_search`，由 Workflow Orchestrator 决定是否补齐。

补齐链路：

```text
Agent Swarm / Judge
  -> EvidenceGap / suggested_search
  -> Workflow Orchestrator
  -> EvidenceAcquisitionService
  -> SearchAgentPool.submit(SearchTask)
  -> Search Agent Worker
  -> EvidenceStore.ingest_search_result(SearchResultPackage)
```

`EvidenceAcquisitionService` 负责把缺口建议转换成正式 `SearchTask`，并施加 workflow 预算、重试次数、source 白名单和回测约束。Search Agent 只执行已经被接受的搜索任务。

## 7. 未决问题

- 第一版任务状态是否落 SQLite 表。
- 是否为 Search Agent 提供独立事件流，还是统一接入 workflow/report 事件系统。
- MarketSnapshot 第一版由 Evidence Store 管理为独立事实类型；Search Agent 可以触发采集，但不能把它当成投资判断。
