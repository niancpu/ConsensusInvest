# Market API

本文档定义 Report Module 的行情看板、市场股票列表、概念雷达和市场预警视图。

本节接口承接旧 `fontWebUI` 的 `market/*` 页面能力，但不让 Report Module 自行接入外部行情源。行情数据来源应是主系统已有市场快照、Evidence、实体关系，或由 Report Module 请求主系统已有 Search Agent / 数据刷新能力异步补齐。

## 1. 设计原则

- `market/*` 是视图接口，不是事实生产接口。
- Report Module 不直接调用 AkShare、TuShare、新闻源或其他外部 provider。
- 当已有数据不足或过期时，后端可以异步指挥 Search Agent / 数据刷新服务补齐；当前 HTTP 请求不阻塞等待。
- 新拿到的事实必须先进入主系统 Raw Item / Evidence / Market Snapshot，再由 Report Module 读取。
- 行情预警、概念热度、市场情绪都不是投资建议；进入主分析任务后必须通过 workflow 形成可追踪链路。
- 本节接口返回的行情、热度、预警必须来自 `MarketSnapshot` 或 Evidence 引用，不能把页面计算结果回写成 Evidence。

前端注解：

- 行情页可以直接使用本节接口。
- 如果响应里 `data_state=refreshing` 或 `stale`，页面应展示当前可用数据和刷新状态，不要假设这次请求已经拿到完整实时行情。
- 用户从行情或预警进入分析时，应创建或选择 `workflow_run`，不要把 market 响应当成最终分析依据。

## 2. 查询指数看板

```http
GET /api/v1/market/index-overview?refresh=stale
```

查询参数：

| 参数 | 必填 | 含义 |
| --- | --- | --- |
| `refresh` | 否 | `never`、`missing`、`stale`；默认 `stale`。允许后端在数据缺失或过期时异步触发刷新。 |

响应：

```json
{
  "data": {
    "report_run_id": "rpt_20260513_market_0001",
    "indices": [
      {
        "name": "上证指数",
        "code": "000001.SH",
        "value": 3120.55,
        "change_rate": 0.85,
        "is_up": true,
        "snapshot_id": "mkt_snap_20260513_000001_sh"
      }
    ],
    "market_sentiment": {
      "label": "中性偏多",
      "score": 62,
      "source": "market_snapshot_projection",
      "snapshot_ids": ["mkt_snap_20260513_index_sentiment"]
    },
    "data_state": "ready",
    "refresh_task_id": null,
    "updated_at": "2026-05-13T11:05:00+08:00"
  },
  "meta": {
    "request_id": "req_20260513_120001",
    "report_run_id": "rpt_20260513_market_0001"
  }
}
```

字段注解：

| 字段 | 说明 |
| --- | --- |
| `snapshot_id` | 主系统市场快照 ID，证明行情值来自已入库结果。 |
| `report_run_id` | Report Module 本次视图生成运行 ID，用于回查 `report_runs` 输入输出快照。 |
| `data_state` | `ready`、`stale`、`partial`、`refreshing`。 |
| `refresh_task_id` | 异步刷新任务 ID；只有后端触发刷新时返回。 |
| `market_sentiment` | 基于 MarketSnapshot 的市场情绪视图，不等于 Judge 结论。 |

前端注解：

- 旧字段 `changeRate/aiSentiment/updatedAt` 在本项目中统一改为 snake_case；`aiSentiment` 对应 `market_sentiment`，不保留 AI 投资判断语义。
- 如果复用旧前端组件，应在 API client 层做字段适配。

## 3. 查询指数日内走势

```http
GET /api/v1/market/index-intraday?code=000001.SH&refresh=stale
```

查询参数：

| 参数 | 必填 | 含义 |
| --- | --- | --- |
| `code` | 否 | 指数代码，默认 `000001.SH`。 |
| `refresh` | 否 | `never`、`missing`、`stale`；默认 `stale`。允许后端在数据缺失或过期时异步触发刷新。 |

响应：

```json
{
  "data": {
    "report_run_id": "rpt_20260513_index_intraday_0001",
    "code": "000001.SH",
    "name": "上证指数",
    "trade_date": "2026-05-13",
    "points": [
      {
        "time": "09:30",
        "timestamp": "2026-05-13T09:30:00+08:00",
        "value": 3120.55,
        "change": 1.23,
        "change_rate": 0.04,
        "volume": 12345600,
        "amount": 1234567890
      }
    ],
    "previous_close": 3119.32,
    "open": 3120.1,
    "high": 3130,
    "low": 3115.2,
    "snapshot_ids": ["mkt_snap_20260513_000001_intraday"],
    "data_state": "ready",
    "refresh_task_id": null,
    "updated_at": "2026-05-13T15:00:00+08:00"
  },
  "meta": {
    "request_id": "req_20260513_120005",
    "report_run_id": "rpt_20260513_index_intraday_0001"
  }
}
```

前端注解：

- 首页指数走势图必须使用本接口的 `points` 绘制，不能使用静态占位点。
- 本接口只投影已入库 `MarketSnapshot`。当 `data_state=pending_refresh` 或 `refreshing` 时，前端应展示空态或刷新状态，而不是伪造曲线。
- 日内点可以来自单个 `index_quote.metrics.intraday_points`，也可以来自多个 `index_quote` 快照按时间拼接。

## 4. 查询市场股票列表

```http
GET /api/v1/market/stocks?page=1&page_size=20&keyword={keyword}&refresh=stale
```

响应：

```json
{
  "data": {
    "report_run_id": "rpt_20260513_market_stocks_0001",
    "list": [
      {
        "stock_code": "002594.SZ",
        "ticker": "002594",
        "name": "比亚迪",
        "price": 218.5,
        "change_rate": 2.15,
        "is_up": true,
        "view_score": 78,
        "view_label": "关注度较高",
        "entity_id": "ent_company_002594",
        "snapshot_id": "mkt_snap_20260513_002594"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 1
    },
    "data_state": "ready",
    "refresh_task_id": null
  },
  "meta": {
    "request_id": "req_20260513_120010",
    "report_run_id": "rpt_20260513_market_stocks_0001"
  }
}
```

前端注解：

- 该接口保留 `page/page_size`，因为行情表格更适合页码分页。
- `view_score` 和 `view_label` 是基于 MarketSnapshot 的页面排序/展示字段，不是主链路投资建议。
- 点击“分析”时应跳转到创建或选择 `workflow_run` 的流程。

## 5. 查询概念雷达

```http
GET /api/v1/market/concept-radar?limit=20&refresh=stale
```

响应：

```json
{
  "data": [
    {
      "concept_name": "低空经济",
      "entity_id": "ent_concept_low_altitude_economy",
      "status": "升温",
      "heat_score": 86,
      "trend": "warming",
      "snapshot_ids": ["mkt_snap_20260513_concept_low_altitude"],
      "evidence_ids": []
    }
  ],
  "meta": {
    "request_id": "req_20260513_120020",
    "report_run_id": "rpt_20260513_concept_radar_0001",
    "data_state": "ready",
    "refresh_task_id": null
  }
}
```

前端注解：

- 概念雷达是市场热度视图，不等于投资建议。
- `evidence_ids` 为空时，说明它只是市场快照层的视图，还没有进入 Evidence 链路。
- 如果用户点进概念分析，应通过主 workflow 生成可追踪分析链路。

## 6. 查询市场预警

```http
GET /api/v1/market/warnings?limit=10&severity=notice&refresh=stale
```

响应：

```json
{
  "data": [
    {
      "warning_id": "warn_20260513_094500_001",
      "time": "09:45",
      "title": "异动预警",
      "content": "某板块出现放量上攻",
      "severity": "notice",
      "related_stock_codes": ["002594.SZ"],
      "related_entity_ids": ["ent_concept_low_altitude_economy"],
      "snapshot_ids": ["mkt_snap_20260513_warn_001"],
      "evidence_ids": []
    }
  ],
  "meta": {
    "request_id": "req_20260513_120030",
    "report_run_id": "rpt_20260513_market_warnings_0001",
    "data_state": "ready",
    "refresh_task_id": null
  }
}
```

前端注解：

- 预警是实时市场提示，不自动成为 Judge 结论；`severity` 只表达预警展示等级，不表达利多利空方向。
- 用户从预警进入分析页时，前端应创建或选择 `workflow_run`。
- 若预警需要作为分析证据，必须由主系统把相关原始信息转成 Raw Item / Evidence，Report Module 不能直接把 warning 文本当成证据写入。
