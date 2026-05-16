# Evidence Store 接口协议

Evidence Store 对内提供三类接口能力：接收 Search Agent 的原始信息包并生成可引用对象；按 ID 或查询条件提供 Evidence、Raw、Structure 和引用关系；写入和查询 MarketSnapshot。本文只定义模块接口契约，不定义表结构，也不表示 HTTP endpoint。

## 1. ingest_search_result

```text
EvidenceStore.ingest_search_result(envelope: InternalCallEnvelope, package: SearchResultPackage) -> IngestResult
```

返回：

```json
{
  "task_id": "st_20260513_002594_0001",
  "workflow_run_id": null,
  "status": "partial_accepted",
  "accepted_raw_refs": [
    "raw_20260513_002594_tavily_001"
  ],
  "created_evidence_ids": [
    "ev_20260513_002594_tavily_001"
  ],
  "updated_evidence_ids": [],
  "rejected_items": [
    {
      "external_id": "tavily_url_hash_099",
      "reason": "publish_time_after_analysis_time",
      "message": "item publish_time is later than envelope.analysis_time"
    }
  ]
}
```

入库规则：

| 规则 | 说明 |
| --- | --- |
| Raw 必须可回溯 | 保存 `url` 或等价来源定位字段，并保留 `raw_payload` 或可复查摘要。 |
| Evidence 必须带 `raw_ref` | 任何 Evidence 都必须能回查到 Raw Item。 |
| 去重不能只按标题 | 至少结合 `url`、`source`、`publish_time`、内容 hash、实体命中。 |
| 重复命中要保留 workflow 关联 | 已存在 Evidence 被新的主 workflow 搜索命中时，不复制 Evidence，但必须把既有 `evidence_id` 关联到当前 `workflow_run_id`，并计入 `updated_evidence_ids`。 |
| 质量可拒绝但要留原因 | `rejected_items` 必须包含机器可读 `reason`。 |
| 不做投资解释 | 入库阶段不能写入 `bullish`、`bearish`、`buy`、`sell` 等立场字段。 |

## 2. RawItem

```json
{
  "raw_ref": "raw_20260513_002594_tavily_001",
  "source": "tavily",
  "source_type": "web_news",
  "ticker": "002594",
  "entity_ids": ["ent_company_002594"],
  "title": "比亚迪发布一季度报告",
  "content": "正文或正文抽取...",
  "content_preview": "页面摘要或搜索摘要...",
  "url": "https://example.com/news/001",
  "publish_time": "2026-04-30T18:00:00+08:00",
  "fetched_at": "2026-05-13T11:00:12+08:00",
  "author": "示例媒体",
  "language": "zh-CN",
  "raw_payload": {
    "provider_response": {}
  },
  "ingest_context": {
    "task_id": "st_20260513_002594_0001",
    "workflow_run_id": null,
    "requested_by": "report_module"
  }
}
```

## 3. EvidenceItem

```json
{
  "evidence_id": "ev_20260513_002594_tavily_001",
  "raw_ref": "raw_20260513_002594_tavily_001",
  "ticker": "002594",
  "entity_ids": ["ent_company_002594"],
  "source": "tavily",
  "source_type": "web_news",
  "evidence_type": "company_news",
  "title": "比亚迪发布一季度报告",
  "content": "正文或摘要...",
  "url": "https://example.com/news/001",
  "publish_time": "2026-04-30T18:00:00+08:00",
  "fetched_at": "2026-05-13T11:00:12+08:00",
  "source_quality": 0.65,
  "relevance": 0.84,
  "freshness": 0.72,
  "quality_notes": []
}
```

字段注解：

| 字段 | 说明 |
| --- | --- |
| `source_quality` | 来源可靠性评分，不代表投资方向。 |
| `relevance` | 和目标实体/主题的相关性。 |
| `freshness` | 相对 `analysis_time` 的时效性。 |
| `quality_notes` | 质量问题，如来源不明、正文截断、需公告核对。 |

## 4. save_structure

```text
EvidenceStore.save_structure(envelope: InternalCallEnvelope, draft: EvidenceStructureDraft) -> EvidenceStructure
```

请求：

```json
{
  "evidence_id": "ev_20260513_002594_tavily_001",
  "objective_summary": "公司披露一季度经营数据，收入和利润保持增长。",
  "key_facts": [
    {
      "name": "归母净利润",
      "value": "示例值",
      "unit": "亿元",
      "period": "2026Q1"
    }
  ],
  "claims": [
    {
      "claim": "公司一季度归母净利润同比增长。",
      "evidence_span": "原文片段...",
      "claim_type": "reported_fact"
    }
  ],
  "structuring_confidence": 0.82,
  "quality_notes": ["部分指标需与公告原文核对"],
  "created_by_agent_id": "evidence_structurer_v1"
}
```

约束：

- `objective_summary` 只写原文客观内容，不写投资含义。
- `claims[].evidence_span` 应能定位到 Raw/Evidence 文本片段。
- 同一 `evidence_id` 可有多个 structure 版本；实现需保留 `created_by_agent_id` 和时间。

## 5. 查询接口

```text
EvidenceStore.query_evidence(envelope: InternalCallEnvelope, query: EvidenceQuery) -> EvidencePage
EvidenceStore.get_evidence(envelope: InternalCallEnvelope, evidence_id: string) -> EvidenceDetail
EvidenceStore.get_raw(envelope: InternalCallEnvelope, raw_ref: string) -> RawItem
EvidenceStore.query_references(envelope: InternalCallEnvelope, query: EvidenceReferenceQuery) -> EvidenceReference[]
```

`EvidenceQuery`：

```json
{
  "ticker": "002594",
  "entity_ids": ["ent_company_002594"],
  "workflow_run_id": null,
  "evidence_types": ["financial_report", "company_news"],
  "publish_time_lte": "2026-05-13T10:00:00+08:00",
  "source_quality_min": 0.6,
  "limit": 50,
  "offset": 0
}
```

查询约束：

- Workflow Orchestrator 选择主链路 Evidence 时必须传入当前 `workflow_run_id`；Evidence Store 只返回该 workflow 采集或显式关联的 Evidence。其他 workflow 的历史 Evidence 不能被新 workflow 自动选中。
- 新 workflow 如果没有当前 run 关联 Evidence，应由 Orchestrator 进入 initial acquisition 或 EvidenceGap 补齐流程，而不是放宽 `workflow_run_id` 去读取历史 Evidence。
- Report Module 构建报告视图时可以不传 `workflow_run_id`，读取已入库历史 Evidence；但输出必须携带 Evidence 时间字段，例如 `publish_time`、`fetched_at`，并保留 `report_run_id` / `updated_at` 作为本次视图生成时间。

`EvidenceDetail` 应包含：

```json
{
  "evidence": {},
  "structure": {},
  "raw_ref": "raw_20260513_002594_tavily_001",
  "references": [
    {
      "source_type": "agent_argument",
      "source_id": "arg_20260513_bull_v1_r1_001",
      "reference_role": "supports"
    }
  ]
}
```

## 6. save_references

```text
EvidenceStore.save_references(envelope: InternalCallEnvelope, batch: EvidenceReferenceBatch) -> EvidenceReferenceResult
```

请求：

```json
{
  "source_type": "agent_argument",
  "source_id": "arg_20260513_bull_v1_r1_001",
  "references": [
    {
      "evidence_id": "ev_20260513_002594_tushare_001",
      "reference_role": "supports",
      "round": 1
    },
    {
      "evidence_id": "ev_20260513_002594_news_003",
      "reference_role": "counters",
      "round": 1
    }
  ]
}
```

允许的 `source_type`：

```text
agent_argument
round_summary
judgment
judge_tool_call
report_view
```

引用角色约束：

| source_type | 允许的 reference_role | 说明 |
| --- | --- | --- |
| `agent_argument` | `supports`、`counters`、`cited`、`refuted` | Agent 论证链路可以表达推理使用方式。 |
| `round_summary` | `supports`、`counters`、`cited`、`refuted` | Round Summary 只能压缩已有论证和引用。 |
| `judgment` | `supports`、`counters`、`cited`、`refuted` | Judge 最终判断可以记录证据使用角色。 |
| `judge_tool_call` | `cited` | 工具回查只表示读取或核对，不表达方向性推理。 |
| `report_view` | `cited` | 报告视图只能记录引用，不能用 `supports`、`counters`、`refuted` 表达推理关系。 |

如果 `source_type=report_view` 但 `reference_role` 不是 `cited`，Evidence Store 必须拒绝并返回 `write_boundary_violation`。

## 7. MarketSnapshot

MarketSnapshot 是 Evidence Store 管理的独立事实类型，不是 `EvidenceItem`，不能承载投资建议、置信度评分、交易信号或建议动作。

```json
{
  "market_snapshot_id": "mkt_snap_20260513_002594",
  "snapshot_type": "stock_quote",
  "ticker": "002594",
  "entity_ids": ["ent_company_002594"],
  "source": "akshare",
  "snapshot_time": "2026-05-13T11:05:00+08:00",
  "fetched_at": "2026-05-13T11:05:02+08:00",
  "metrics": {
    "price": 218.5,
    "change_rate": 2.15,
    "turnover_rate": 1.8,
    "amount": 1234567890
  },
  "ingest_context": {
    "task_id": "st_20260513_002594_market_0001",
    "workflow_run_id": null,
    "requested_by": "report_module"
  }
}
```

允许的 `snapshot_type`：

```text
stock_quote
index_quote
sector_heat
concept_heat
market_warning
```

约束：

- `snapshot_time` 是行情业务时间，不能用 `fetched_at` 替代。
- `metrics` 只能保存行情、热度、成交、换手、预警等级等客观市场状态。
- 如果行情异动需要进入正式分析链路，应通过 `market_snapshot_id` 或后续 Evidence 引用进入 workflow，不由 Report Module 直接生成投资建议。

## 8. MarketSnapshot 接口

```text
EvidenceStore.save_market_snapshot(envelope: InternalCallEnvelope, snapshot: MarketSnapshotDraft) -> MarketSnapshot
EvidenceStore.query_market_snapshots(envelope: InternalCallEnvelope, query: MarketSnapshotQuery) -> MarketSnapshotPage
EvidenceStore.get_market_snapshot(envelope: InternalCallEnvelope, market_snapshot_id: string) -> MarketSnapshot
```

`MarketSnapshotQuery`：

```json
{
  "ticker": "002594",
  "entity_ids": ["ent_company_002594"],
  "snapshot_types": ["stock_quote", "market_warning"],
  "snapshot_time_lte": "2026-05-13T10:00:00+08:00",
  "limit": 50,
  "offset": 0
}
```

查询约束：

- 回测或历史分析必须使用 `snapshot_time_lte <= envelope.analysis_time`。
- 查询结果可以被 Report Module 作为视图材料，也可以被 workflow 作为可追踪输入，但不能自动等价为 Evidence。
