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

## 3. 状态归属

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

## 4. 回测安全

Search Agent 可以抓到晚于 `analysis_time` 的信息，但不能决定它是否能用于某次分析。Evidence Store 入库阶段必须根据 `publish_time` 和 `analysis_time` 拒绝或标记不可用。

## 5. 未决问题

- 第一版任务状态是否落 SQLite 表。
- 是否为 Search Agent 提供独立事件流，还是统一接入 workflow/report 事件系统。
- MarketSnapshot 第一版由 Evidence Store 管理为独立事实类型；Search Agent 可以触发采集，但不能把它当成投资判断。
