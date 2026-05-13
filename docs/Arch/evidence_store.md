# Evidence Store 设计

Evidence Store 是事实层中心。它负责保存 Raw、Evidence、Evidence Structure、MarketSnapshot 和引用关系，并为 Agent Swarm、Judge、Report Module 提供读取能力。

## 1. 数据分层

```text
RawItem
  -> EvidenceItem
  -> EvidenceStructure
  -> EvidenceReference

MarketSnapshot
```

Raw 保存外部来源原貌；Evidence 保存归一化事实；Structure 保存客观摘要和关键 claims；Reference 保存谁引用了哪些 Evidence。
MarketSnapshot 保存某一时刻的行情快照，第一版由 Evidence Store 管理，但不等同于 EvidenceItem。

## 2. 写入边界

允许写入事实层的路径：

- Search Agent 提交 `SearchResultPackage`，由 Evidence Store ingest。
- Evidence Normalizer 通过 Evidence Store 写 Evidence。
- Evidence Structuring Agent 通过 Evidence Store 写 Structure。
- Agent Swarm / Judge / Report 只能通过 Evidence Store 提交引用关系，不能直接写 Evidence 或事实表。
- MarketSnapshot 通过 Evidence Store 写入和回查。

禁止：

- Report Module 把页面文案回写成 Evidence。
- Agent Swarm 把投资解释写入 Evidence。
- Search Agent 直接写 Raw/Evidence 表。

## 3. MarketSnapshot 模型边界

MarketSnapshot 是市场状态快照，不是投资判断。

可以保存：

- 股票价格、涨跌幅、成交额、换手率；
- 指数行情；
- 板块/概念热度；
- 市场预警；
- 快照时间、来源、采集任务 ID。

不能保存投资建议、置信度评分、交易信号或建议动作。

如果某个行情异动需要进入正式分析链路，应通过 Evidence 或可追踪的 snapshot 引用进入 workflow，而不是让 Report Module 直接生成投资建议。

## 4. Evidence 模型边界

Evidence 只描述客观事实和质量维度：

- `source_quality`
- `relevance`
- `freshness`
- `quality_notes`
- `raw_ref`
- `entity_ids`

Evidence 不保存：

- `bullish`
- `bearish`
- `buy`
- `sell`
- `net_impact`

方向性解释属于 Agent/Judge 推理链，Report Module 只能做引用组织和报告呈现，不能生成解读或分析。

## 5. 关联表设计

推理链路引用：

- `evidence_references`
- 闭集合关系：`supports`、`counters`、`cited`、`refuted`
- 绑定 `source_type` 和 `source_id`
- `source_type=report_view` 只能使用 `cited`，不能使用 `supports`、`counters` 或 `refuted` 表达推理关系。

实体语义关联：

- `entities`
- `evidence_entities`
- `entity_relations`
- 开放集合关系：行业、上下游、同业、政策影响等

这两类关系不能混表。推理链路边服务可追溯判断，实体边服务知识组织和检索，查询模式和演化速度不同。

## 6. 存储选择

MVP 使用 SQLite。

迁移触发条件：

- 多人并发写入明显增加；
- Evidence/实体数量进入十万级；
- 全文检索和多跳图查询成为核心体验；
- 需要服务化部署和跨进程任务队列。

迁移候选：

- Postgres；
- Postgres + AGE；
- 专用全文检索组件；
- 专用图数据库。
