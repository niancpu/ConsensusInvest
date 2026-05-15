# Evidence API

本文档定义 Raw Item、Evidence、Evidence Structure、Evidence References 和 MarketSnapshot 详情。

## 查询边界

- `/workflow-runs/{workflow_run_id}/raw-items`、`/workflow-runs/{workflow_run_id}/evidence`、`/workflow-runs/{workflow_run_id}/evidence-references` 只查询某次主 workflow 关联的数据。
- 跨 workflow 或无 workflow 的 Evidence 不新增按 `ticker` 直接查询入口；前端需要股票/实体维度证据时，使用 `GET /api/v1/entities/{entity_id}/evidence` 或 Report Module 视图接口。
- 已知 `raw_ref` / `evidence_id` 时，可以直接使用详情接口下钻。
- 列表和详情示例中的 `workflow_run_id` 是当前查询上下文或引用关系投影，不表示 Raw Item / Evidence Item 只能归属单个 workflow。

## 6. Raw Items

### 6.1 查询 Raw Item 列表

```http
GET /api/v1/workflow-runs/{workflow_run_id}/raw-items?source=tushare&limit=50&offset=0
```

响应：

```json
{
  "data": [
    {
      "raw_ref": "raw_20260513_000001_tushare_001",
      "workflow_run_id": "wr_20260513_000001_000001",
      "source": "tushare",
      "source_type": "financial_data",
      "ticker": "000001",
      "title": "2026Q1 financial data",
      "publish_time": "2026-04-30T18:00:00+08:00",
      "fetched_at": "2026-05-13T10:00:12+08:00",
      "url": null,
      "payload_preview": {
        "period": "2026Q1"
      }
    }
  ],
  "pagination": {
    "limit": 50,
    "offset": 0,
    "total": 42,
    "has_more": false
  },
  "meta": {
    "request_id": "req_20260513_100100"
  }
}
```

前端注解：

- Raw Item 是审计和问题定位入口，不建议默认在主列表展开完整 payload。
- 展示给用户时优先展示 `title/source/publish_time/fetched_at/url`。

### 6.2 查询 Raw Item 详情

```http
GET /api/v1/raw-items/{raw_ref}
```

响应：

```json
{
  "data": {
    "raw_ref": "raw_20260513_000001_tushare_001",
    "workflow_run_id": "wr_20260513_000001_000001",
    "source": "tushare",
    "source_type": "financial_data",
    "ticker": "000001",
    "title": "2026Q1 financial data",
    "content": null,
    "url": null,
    "publish_time": "2026-04-30T18:00:00+08:00",
    "fetched_at": "2026-05-13T10:00:12+08:00",
    "raw_payload": {
      "period": "2026Q1",
      "net_profit_yoy": "..."
    },
    "derived_evidence_ids": ["ev_20260513_000001_tushare_001"]
  },
  "meta": {
    "request_id": "req_20260513_100110"
  }
}
```

前端注解：

- `raw_payload` 可能很大，也可能包含供应商原始字段名。UI 应提供折叠展示。
- 如果用户质疑某条 Evidence 的来源，最终要落到这个接口。


## 7. Evidence

### 7.1 查询任务 Evidence 列表

```http
GET /api/v1/workflow-runs/{workflow_run_id}/evidence?type=company_news&source_quality_min=0.6&limit=50&offset=0
```

响应：

```json
{
  "data": [
    {
      "evidence_id": "ev_20260513_000001_tushare_001",
      "workflow_run_id": "wr_20260513_000001_000001",
      "ticker": "000001",
      "source": "tushare",
      "source_type": "financial_data",
      "evidence_type": "financial_report",
      "title": "2026Q1 财务数据",
      "objective_summary": "公司披露 2026Q1 归母净利润同比增长。",
      "publish_time": "2026-04-30T18:00:00+08:00",
      "fetched_at": "2026-05-13T10:00:12+08:00",
      "source_quality": 0.9,
      "relevance": 0.86,
      "freshness": 0.72,
      "structuring_confidence": 0.82,
      "quality_notes": ["部分指标需与历史口径核对"],
      "raw_ref": "raw_20260513_000001_tushare_001"
    }
  ],
  "pagination": {
    "limit": 50,
    "offset": 0,
    "total": 31,
    "has_more": false
  },
  "meta": {
    "request_id": "req_20260513_100200"
  }
}
```

前端注解：

- Evidence 列表应展示质量和置信度，不要只展示标题摘要。
- `source_quality/relevance/freshness/structuring_confidence` 是不同维度，不要合成一个模糊分数后丢弃原字段。

### 7.2 查询 Evidence 详情

```http
GET /api/v1/evidence/{evidence_id}
```

响应：

```json
{
  "data": {
    "evidence_id": "ev_20260513_000001_tushare_001",
    "workflow_run_id": "wr_20260513_000001_000001",
    "ticker": "000001",
    "source": "tushare",
    "source_type": "financial_data",
    "evidence_type": "financial_report",
    "title": "2026Q1 财务数据",
    "content": "...",
    "url": null,
    "publish_time": "2026-04-30T18:00:00+08:00",
    "fetched_at": "2026-05-13T10:00:12+08:00",
    "entities": ["ent_company_000001"],
    "tags": ["业绩", "银行", "财报"],
    "objective_summary": "公司披露 2026Q1 归母净利润同比增长。",
    "key_facts": [
      {
        "name": "归母净利润",
        "value": "...",
        "unit": "亿元",
        "period": "2026Q1"
      }
    ],
    "claims": [
      {
        "claim": "归母净利润同比增长...",
        "evidence_span": "...",
        "claim_type": "reported_fact"
      }
    ],
    "source_quality": 0.9,
    "relevance": 0.86,
    "freshness": 0.72,
    "structuring_confidence": 0.82,
    "quality_notes": ["部分指标需与历史口径核对"],
    "raw_ref": "raw_20260513_000001_tushare_001",
    "links": {
      "structure": "/api/v1/evidence/ev_20260513_000001_tushare_001/structure",
      "raw": "/api/v1/evidence/ev_20260513_000001_tushare_001/raw",
      "references": "/api/v1/evidence/ev_20260513_000001_tushare_001/references"
    }
  },
  "meta": {
    "request_id": "req_20260513_100210"
  }
}
```

前端注解：

- Evidence 是客观证据层，不应显示为“利多/利空事实”。
- 利多/利空解释来自 Agent Argument 或 Judgment，不来自 Evidence 自身。

### 7.3 查询 Evidence 结构化结果

```http
GET /api/v1/evidence/{evidence_id}/structure
```

响应：

```json
{
  "data": {
    "evidence_structure_id": "estr_20260513_000001_001",
    "evidence_id": "ev_20260513_000001_tushare_001",
    "objective_summary": "公司披露 2026Q1 归母净利润同比增长。",
    "key_facts": [],
    "claims": [],
    "source_quality": 0.9,
    "relevance": 0.86,
    "freshness": 0.72,
    "structuring_confidence": 0.82,
    "quality_notes": ["部分指标需与历史口径核对"],
    "created_by_agent_id": "evidence_structurer_v1",
    "created_at": "2026-05-13T10:00:33+08:00"
  },
  "meta": {
    "request_id": "req_20260513_100220"
  }
}
```

前端注解：

- 这个接口适合 Evidence 详情页展示“结构化抽取是怎么来的”。
- `created_by_agent_id` 说明结构化结果来自哪个 Agent 版本。

### 7.4 查询 Evidence 对应 Raw Item

```http
GET /api/v1/evidence/{evidence_id}/raw
```

响应等价于 `GET /api/v1/raw-items/{raw_ref}`。

前端注解：

- 这是为了简化从 Evidence 下钻到 Raw 的路径。
- 如果已经有 `raw_ref`，也可以直接调用 Raw Item 详情接口。

### 7.5 查询 Evidence 被引用情况

```http
GET /api/v1/evidence/{evidence_id}/references
```

响应：

```json
{
  "data": [
    {
      "reference_id": "eref_20260513_000001_001",
      "workflow_run_id": "wr_20260513_000001_000001",
      "source_type": "agent_argument",
      "source_id": "arg_20260513_bull_v1_r1_001",
      "evidence_id": "ev_20260513_000001_tushare_001",
      "reference_role": "supports",
      "round": 1,
      "created_at": "2026-05-13T10:01:30+08:00"
    }
  ],
  "meta": {
    "request_id": "req_20260513_100230"
  }
}
```

前端注解：

- 这个接口回答“这条证据被哪些 Agent / Summary / Judgment 用过”。
- `reference_role` 只描述引用关系，不代表 Evidence 自身天然利多或利空。


## 11. Evidence References

### 11.1 查询任务内全部引用关系

```http
GET /api/v1/workflow-runs/{workflow_run_id}/evidence-references
```

响应：

```json
{
  "data": [
    {
      "reference_id": "eref_20260513_000001_001",
      "workflow_run_id": "wr_20260513_000001_000001",
      "source_type": "agent_argument",
      "source_id": "arg_20260513_bull_v1_r1_001",
      "evidence_id": "ev_20260513_000001_tushare_001",
      "reference_role": "supports",
      "round": 1,
      "created_at": "2026-05-13T10:01:30+08:00"
    }
  ],
  "meta": {
    "request_id": "req_20260513_100600"
  }
}
```

前端注解：

- 这个接口适合一次性构建 Evidence 引用关系图。
- 它和实体关系图不是一回事。Evidence References 是一次 workflow 内的推理链路。
- `source_type=report_view` 的引用只能使用 `reference_role=cited`，表示报告视图引用了该 Evidence，不表示支持、反驳或形成投资判断。


## 12. MarketSnapshot 引用边界

MarketSnapshot 由 Evidence Store 管理，但不是 Evidence。公开接口中出现 `market_snapshot_id` 时，只表示该视图引用了已入库市场快照。

### 12.1 查询 MarketSnapshot 详情

```http
GET /api/v1/market-snapshots/{market_snapshot_id}
```

响应：

```json
{
  "data": {
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
  },
  "meta": {
    "request_id": "req_20260513_100900"
  }
}
```

约束：

- 该接口只读已入库 MarketSnapshot，不触发行情刷新。
- `metrics` 只能表达行情、热度、成交、换手、预警等级等客观市场状态。
- MarketSnapshot 详情不返回投资建议、交易动作或 Judge 置信度。

前端注解：

- 行情价格、指数、概念热度、市场预警等视图应优先下钻到 `market_snapshot_id`。
- `market_snapshot_id` 不能替代 `evidence_id`、`judgment_id` 或 `workflow_run_id`。
- 如果某个市场快照需要进入正式投资判断，应创建或选择 workflow，让主链路基于可追踪输入生成 Judgment。

