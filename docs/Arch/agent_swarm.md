# Agent Swarm 与 Judge 设计

Agent Swarm 是主 workflow 的推理模块。它消费 Evidence Store 中的 Evidence 和 Structure，生成可追踪论证。Judge Runtime 基于这些论证和 Evidence 生成最终判断。

Agent 类任务共享 `AgentRuntime` 运行层，用于处理任务生命周期、状态、事件、预算、错误和 trace。`AgentRuntime` 不定义业务输入输出；Search Agent、Debate Agent、Judge Agent 不能因为共享运行层而共享事实生产权或搜索权限。

## 1. Agent 输入

Agent 输入必须来自已入库对象：

- `evidence_ids`
- `evidence_structures`
- `workflow_context`
- 历史 `judgment_ids`

Agent 不接收 Search Agent 的未入库 `SearchResultPackage`。

## 2. Agent 输出

Agent 输出包括：

- `agent_argument`
- `referenced_evidence_ids`
- `counter_evidence_ids`
- `confidence`
- `limitations`
- Agent 专属 `role_output`

重要论点必须引用 Evidence。没有 Evidence 引用的论点可以保留，但应被 Judge 和前端视为低置信度材料。

这里的 `confidence` 只描述 Agent 对自身论证可靠性的估计，不是报告模块字段，也不是投资建议置信度。

## 3. EvidenceGap

当证据不足时，Agent Swarm 输出 `EvidenceGap`，例如缺少同业对比、现金流数据、公告原文等。

设计边界：

- Agent Swarm 不直接调用 Search Agent。
- Agent Swarm 可以附带 `suggested_search`，但它只是搜索建议，不是 `SearchTask`。
- Orchestrator 通过 `EvidenceAcquisitionService` 把可执行的 `EvidenceGap` 转换为 SearchTask 并触发补齐；只有 Research/Search Agent 明确无法补齐时，才进入信息不足报告。
- 这样可以避免推理 Agent 自行扩张数据边界。

`suggested_search` 只能描述缺什么、建议查什么，不能指定 provider 私有调用参数、不能绕过 workflow 预算，也不能要求当前 Agent 同步等待搜索完成。

## 4. Debate Runtime

MVP 可以只实现单侧 `bull_v1`，但运行时必须允许后续加入：

- Bear Agent；
- Technical Agent；
- Fundamental Agent；
- Policy Agent；
- Risk Agent。

Debate Runtime 不应把具体 Agent 写死成特殊分支。Agent 通过 workflow config 装配。

## 5. Judge Runtime

Judge 默认消费：

- Round Summary；
- Agent Argument；
- key Evidence；
- Evidence Structure；
- 必要时通过工具回查 Raw。

Judge 可以输出后续核对建议或 EvidenceGap，但不能直接调用 Search Agent，也不能把未入库搜索结果纳入 Judgment。

Judge 输出 `judgment`，并保存：

- 结论；
- 置信度；
- 关键 Evidence；
- 主要风险；
- 限制条件；
- 工具回查记录。

Judge 的工具调用必须可见，用于解释它核对了哪些 Evidence 或 Raw，以及这些回查如何影响判断。
