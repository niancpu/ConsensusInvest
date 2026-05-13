# 架构原则

## 1. Evidence First

系统结论必须建立在已入库 Evidence 上。Search Agent、外部 provider 返回、页面摘要、Agent 临时输出都不能直接充当 Evidence。

影响：

- 所有外部信息先进入 Raw，再归一化为 Evidence。
- Agent Swarm / Judge 引用 `evidence_id`，需要审计时再回查 `raw_ref`。
- Report Module 可以生成报告视图，但不能生成事实、解读或分析；报告中的摘要必须来自 Evidence Structure、Agent/Judge 输出或已有 workflow。

## 2. 可追踪推理

用户看到的判断、报告内容、风险事项和限制条件，都应能回查到 Evidence 或 Raw。

主 workflow 追踪链：

```text
judgment
  -> agent_arguments / round_summaries
  -> evidence_references
  -> evidence_items
  -> raw_items
```

报告生成追踪链：

```text
report_run
  -> trace_refs.evidence_ids / trace_refs.market_snapshot_ids
  -> evidence_items
  -> raw_items
```

## 3. 异步非阻塞

搜索、Agent 推理、Judge 判断都可能耗时，不能把前端请求设计成同步等待完整链路。

要求：

- 创建类接口返回任务 ID 或运行 ID。
- 事件流持续推送阶段性结果。
- 当前响应能返回已有数据和 `data_state`。
- 外部 provider 失败应允许部分完成。

## 4. 判断区暴露

低判断区适合接口协议、字段校验、幂等、错误码、引用扫描。高判断区必须在设计文档里显式暴露：

- 状态归属；
- 模块边界；
- 是否自动触发搜索；
- 报告生成和主 workflow 的结果是否等价；
- Evidence、Judgment、Report View 的长期演化关系。

## 5. 模块可替换

Agent、搜索 provider、Report Module 都应通过稳定边界接入。系统不能把某个具体 Agent 或 provider 写死成不可替换核心。
