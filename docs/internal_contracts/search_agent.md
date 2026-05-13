# Search Agent Pool 接口协议

Search Agent Pool 是内部搜索/抓取能力，对其他模块只暴露任务提交和状态查询接口。它可以多 worker 并发执行，返回待入库的原始信息包 `SearchResultPackage`。该结果包含原信息、URL 和元数据，但必须先交给 Evidence Store 入库后，其他模块才能通过 `raw_ref` / `evidence_id` 引用。

## 1. submit

```text
SearchAgentPool.submit(envelope: InternalCallEnvelope, request: SearchTask) -> AsyncTaskReceipt
```

请求：

```json
{
  "task_type": "stock_research",
  "target": {
    "ticker": "002594",
    "stock_code": "002594.SZ",
    "entity_id": "ent_company_002594",
    "keywords": ["比亚迪", "BYD"]
  },
  "scope": {
    "sources": ["tavily", "exa", "akshare", "tushare"],
    "evidence_types": ["company_news", "financial_report", "industry_news"],
    "lookback_days": 30,
    "max_results": 50
  },
  "constraints": {
    "allow_stale_cache": true,
    "dedupe_hint": true,
    "language": "zh-CN",
    "expansion_policy": {
      "allowed": true,
      "max_depth": 1,
      "allowed_actions": [
        "fetch_original_url",
        "follow_official_source",
        "provider_pagination",
        "same_event_cross_source"
      ]
    },
    "budget": {
      "max_provider_calls": 20,
      "max_runtime_ms": 60000
    }
  },
  "callback": {
    "ingest_target": "evidence_store",
    "workflow_run_id": null
  }
}
```

字段注解：

| 字段 | 说明 |
| --- | --- |
| `task_type` | 搜索任务类型。第一版建议支持 `stock_research`、`market_snapshot`、`entity_news`。 |
| `target.ticker` | A 股六位代码，用于和 Evidence/Entity 对齐。 |
| `target.stock_code` | 带交易所后缀的代码，如 `002594.SZ`。 |
| `target.entity_id` | 主系统实体 ID；没有时可为空，但入库阶段必须完成实体匹配或标记未匹配。 |
| `target.keywords` | 搜索关键词，不等同于最终实体识别结果。 |
| `scope.sources` | 允许使用的数据源/provider；实现可按可用性部分执行。 |
| `scope.evidence_types` | 期望补齐的信息类型；Search Agent 可用它生成查询，但不直接生成 Evidence。 |
| `scope.lookback_days` | 从 `envelope.analysis_time` 向前回看。 |
| `scope.max_results` | 本任务最多返回的原始信息项数量。 |
| `constraints.allow_stale_cache` | 允许先返回缓存命中；入库仍需保留 `fetched_at`。 |
| `constraints.expansion_policy` | 可选。约束 Search Agent 在同一任务内能否继续抓原文、翻页、跟随官方来源或做同事件跨源核对。 |
| `constraints.budget` | 可选。约束 provider 调用次数、运行时间等资源上限；Search Agent 不得越过预算自主扩展。 |
| `callback.ingest_target` | 当前固定为 `evidence_store`。 |
| `callback.workflow_run_id` | 可为空；主 workflow 触发搜索时填写，`report_generation` 或预热补齐时为空。 |

返回：

```json
{
  "task_id": "st_20260513_002594_0001",
  "status": "queued",
  "accepted_at": "2026-05-13T11:00:00+08:00",
  "idempotency_key": "search_002594_20260513_missing_news",
  "poll_after_ms": 1000
}
```

## 2. get_status

```text
SearchAgentPool.get_status(envelope: InternalCallEnvelope, task_id: string) -> SearchTaskStatus
```

返回：

```json
{
  "task_id": "st_20260513_002594_0001",
  "status": "partial_completed",
  "started_at": "2026-05-13T11:00:02+08:00",
  "completed_at": null,
  "source_status": [
    {
      "source": "tavily",
      "status": "completed",
      "found_count": 12,
      "ingested_count": 10,
      "rejected_count": 2
    },
    {
      "source": "tushare",
      "status": "running",
      "found_count": 0,
      "ingested_count": 0,
      "rejected_count": 0
    }
  ],
  "last_error": null
}
```

## 3. SearchResultPackage

Search Agent Worker 完成一批抓取后，向 Evidence Store 提交：

```text
EvidenceStore.ingest_search_result(envelope: InternalCallEnvelope, package: SearchResultPackage) -> IngestResult
```

数据结构：

```json
{
  "task_id": "st_20260513_002594_0001",
  "worker_id": "search_worker_03",
  "source": "tavily",
  "source_type": "web_news",
  "target": {
    "ticker": "002594",
    "stock_code": "002594.SZ",
    "entity_id": "ent_company_002594",
    "keywords": ["比亚迪", "BYD"]
  },
  "items": [
    {
      "external_id": "tavily_url_hash_001",
      "title": "比亚迪发布一季度报告",
      "url": "https://example.com/news/001",
      "content": "正文或正文抽取...",
      "content_preview": "页面摘要或搜索摘要...",
      "publish_time": "2026-04-30T18:00:00+08:00",
      "fetched_at": "2026-05-13T11:00:12+08:00",
      "author": "示例媒体",
      "language": "zh-CN",
      "raw_payload": {
        "provider_response": {}
      },
      "source_quality_hint": 0.65
    }
  ],
  "completed_at": "2026-05-13T11:00:20+08:00"
}
```

字段注解：

| 字段 | 说明 |
| --- | --- |
| `external_id` | provider 原始 ID；没有时用 URL/hash 生成。 |
| `url` | 可回溯来源地址；无 URL 的数据源必须提供等价来源定位字段。 |
| `content` | 抓取到的正文或结构化文本；过大时可截断，但 `raw_payload` 应保留回查材料。 |
| `content_preview` | 搜索摘要或正文摘要，只用于预览，不作为完整事实。 |
| `publish_time` | 信息发布时间；入库时用它检查是否晚于 `analysis_time`。 |
| `fetched_at` | 系统抓取时间，不能替代 `publish_time`。 |
| `raw_payload` | provider 原始响应或足够复现来源的数据。 |
| `source_quality_hint` | Search Agent 的来源质量提示，不是最终 Evidence 质量分。 |

## 4. 约束

- Search Agent 可以并发返回重复信息；去重由 Evidence Store 入库阶段处理。
- Search Agent 可以在同一 `SearchTask` 内做受约束的低判断区扩展，例如抓原文、翻页、跟随官方来源、同事件跨源核对。
- Search Agent 不能基于搜索结果自主开启新的研究方向；新的研究方向必须由 Orchestrator 根据 `EvidenceGap` 或用户请求生成新的 `SearchTask`。
- Search Agent 的自主扩展必须受 `scope`、`constraints.expansion_policy`、`constraints.budget` 和 `envelope.analysis_time` 约束。
- `SearchResultPackage` 不能被 Agent Swarm、Judge 或 Report Module 直接引用。
- `publish_time > envelope.analysis_time` 的 item 必须在入库阶段拒绝或标记为不适用于该 workflow。
- 单个 source 失败不要求整个任务失败；状态可返回 `partial_completed`。
- Search Agent 不输出投资判断、利多利空解释、买卖建议。

## 5. 事件

Search Agent 建议产生：

| event_type | payload |
| --- | --- |
| `search.task_queued` | `task_id`、`target`、`sources` |
| `search.source_started` | `task_id`、`source`、`worker_id` |
| `search.item_found` | `task_id`、`source`、`external_id`、`url`、`title` |
| `search.source_failed` | `task_id`、`source`、`error.code` |
| `search.task_completed` | `task_id`、`status`、`found_count` |
