# Stock Research View API

本文档定义 ZC 模块接入后的股票发现和个股研究聚合视图。

本节接口承接旧 `fontWebUI` 的 `stocks/*` 页面能力，但实现方式改为适配本项目主数据层：ZC 模块消费 Entity、Evidence Store、市场快照、主分析链路结果和模块内派生结果，不直接生产 Raw Item / Evidence。

## 1. 设计原则

- `stocks/search` 是正式保留接口，但搜索结果应来自 Entity / Evidence Store / 股票索引，而不是旧项目自有状态。
- `stocks/{stock_code}/analysis` 是个股研究聚合视图，不是新的 Agent 主流程入口。
- ZC 模块可以有自己的模块内 Agent，用于摘要、排序、视图解释；它与主链路 Agent 解离，不写入主链路 `agent_arguments`、`judgments`。
- 所有面向页面的解释性字段必须带可追踪引用，例如 `evidence_ids`、`entity_ids`、`workflow_run_id`、`judgment_id`、`zc_run_id`。
- 数据不足时，接口返回当前可用结果和 `data_state`；是否触发搜索/刷新由后端根据策略异步提交给已有 Search Agent，接口不阻塞等待完整搜索。

前端注解：

- 本节接口适合旧首页、轻量研究卡片和 ZC 模块页面。
- 如果页面要展示完整透明推理链路，仍应接入 `docs/web_api` 中的 workflow、trace、evidence、judgment。
- `summary`、`action`、`benefits`、`risks` 只是视图层字段，不等于主链路 Judge 的完整投资判断。

## 2. 搜索股票

```http
GET /api/v1/stocks/search?keyword={keyword}&limit=10
```

查询参数：

| 参数 | 必填 | 含义 |
| --- | --- | --- |
| `keyword` | 是 | 股票代码、简称、公司名、别名或自然语言关键词。 |
| `limit` | 否 | 返回数量，默认 `10`，最大值由后端限制。 |
| `include_evidence` | 否 | 是否返回命中的 Evidence 摘要，默认 `true`。 |

响应：

```json
{
  "data": [
    {
      "stock_code": "002594.SZ",
      "ticker": "002594",
      "exchange": "SZ",
      "name": "比亚迪",
      "market": "A_SHARE",
      "entity_id": "ent_company_002594",
      "aliases": ["BYD", "比亚迪股份"],
      "match": {
        "type": "entity_and_evidence",
        "score": 0.92,
        "matched_fields": ["ticker", "name", "evidence_title"]
      },
      "evidence_matches": [
        {
          "evidence_id": "ev_20260513_002594_report_001",
          "title": "比亚迪 2026Q1 财务数据",
          "objective_summary": "收入和利润保持增长。",
          "published_at": "2026-04-30T00:00:00+08:00",
          "source_quality": 0.9
        }
      ]
    }
  ],
  "meta": {
    "request_id": "req_20260513_110001",
    "data_state": "ready"
  }
}
```

字段注解：

| 字段 | 说明 |
| --- | --- |
| `entity_id` | 主系统实体 ID，用于跳转实体详情、关系网络或创建 workflow。 |
| `evidence_matches` | 从 Evidence Store 返回的相关证据摘要；这是搜索结果的一部分，不代表 ZC 模块生产了证据。 |
| `match.type` | 命中来源，例如 `entity`、`evidence`、`entity_and_evidence`。 |
| `data_state` | `ready` 表示已有数据足够；`partial` 表示只返回部分命中；`pending_refresh` 表示后端已异步触发搜索/刷新。 |

前端注解：

- 搜索框可以直接展示 `stock_code`、`name` 和 `evidence_matches` 的摘要。
- 创建主分析任务时，优先传 `entity_id` 或 `stock_code` 给 `POST /api/v1/workflow-runs`。
- 如果 `data_state=pending_refresh`，不要在当前请求里等待；展示当前结果，并允许用户稍后刷新。

## 3. 查询个股研究聚合视图

```http
GET /api/v1/stocks/{stock_code}/analysis?query={query}&workflow_run_id={workflow_run_id}&refresh=never
```

查询参数：

| 参数 | 必填 | 含义 |
| --- | --- | --- |
| `query` | 否 | 用户搜索词或自然语言补充问题，只影响视图聚合和模块内解释。 |
| `workflow_run_id` | 否 | 指定读取哪个主分析工作流的结果。 |
| `latest` | 否 | 未传 `workflow_run_id` 时是否读取最新完成任务，默认 `true`。 |
| `refresh` | 否 | `never`、`missing`、`stale`；默认 `never`。用于允许后端异步触发已有 Search Agent 补齐数据。 |

响应：

```json
{
  "data": {
    "stock_code": "002594.SZ",
    "ticker": "002594",
    "stock_name": "比亚迪",
    "entity_id": "ent_company_002594",
    "workflow_run_id": "wr_20260513_002594_000001",
    "judgment_id": "jdg_20260513_002594_001",
    "zc_run_id": "zc_20260513_002594_0001",
    "data_state": "ready",
    "action": {
      "label": "观望",
      "signal": "neutral",
      "reason": "等待价格确认基本面改善",
      "source": "main_judgment_summary"
    },
    "report": {
      "title": "个股研究聚合视图",
      "summary": "公司具备中期基本面支撑，但短期估值和现金流质量需要复核。",
      "key_evidence": [
        {
          "evidence_id": "ev_20260513_002594_report_001",
          "title": "2026Q1 财务数据",
          "objective_summary": "收入和利润保持增长。",
          "source_quality": 0.9,
          "relevance": 0.88
        }
      ],
      "risks": [
        {
          "text": "现金流质量下降",
          "evidence_ids": ["ev_20260513_002594_report_003"],
          "source": "zc_module_summary"
        }
      ]
    },
    "links": {
      "workflow_run": "/api/v1/workflow-runs/wr_20260513_002594_000001",
      "trace": "/api/v1/workflow-runs/wr_20260513_002594_000001/trace",
      "judgment": "/api/v1/judgments/jdg_20260513_002594_001",
      "entity": "/api/v1/entities/ent_company_002594"
    },
    "updated_at": "2026-05-13T11:00:00+08:00"
  },
  "meta": {
    "request_id": "req_20260513_110010"
  }
}
```

处理规则：

- 有 `workflow_run_id` 时，优先聚合该工作流的主链路结果。
- 无 `workflow_run_id` 时，可读取该股票最新可用的主链路 Judgment、Evidence、Entity 信息。
- 若主链路没有结果，接口仍可返回 Entity / Evidence / Market Snapshot 组成的轻量视图，但 `workflow_run_id` 和 `judgment_id` 为空。
- 若 `refresh=missing` 或 `refresh=stale` 且数据不足，后端可以异步提交搜索/刷新请求，并返回 `data_state=pending_refresh` 和 `refresh_task_id`。
- 该接口不启动 `workflow-runs`，也不生成主链路 Judgment。

前端注解：

- 页面可以用这个接口快速渲染旧项目首页结构。
- 若要生成新的完整分析，前端应调用 `POST /api/v1/workflow-runs`。
- `zc_run_id` 只代表 ZC 模块内视图生成或解释过程，不等于主链路 `workflow_run_id`。

## 4. 查询行业详情聚合视图

```http
GET /api/v1/stocks/{stock_code}/industry-details?workflow_run_id={workflow_run_id}
```

响应：

```json
{
  "data": {
    "stock_code": "002594.SZ",
    "ticker": "002594",
    "industry_entity_id": "ent_industry_new_energy_vehicle",
    "industry_name": "新能源汽车",
    "policy_support_level": "high",
    "policy_support_desc": "政策支持力度较强",
    "supply_demand_status": "供需紧平衡",
    "competition_landscape": "头部集中度提升",
    "referenced_evidence_ids": [
      "ev_20260513_002594_policy_001",
      "ev_20260513_002594_industry_002"
    ],
    "links": {
      "entity": "/api/v1/entities/ent_industry_new_energy_vehicle",
      "entity_relations": "/api/v1/entities/ent_industry_new_energy_vehicle/relations"
    },
    "updated_at": "2026-05-13T11:00:00+08:00"
  },
  "meta": {
    "request_id": "req_20260513_110020"
  }
}
```

前端注解：

- 这些字段来自 Entity Relations、Evidence 和已有分析结果的聚合。
- 不能把 `policy_support_desc`、`competition_landscape` 写成不可追踪的静态文案。

## 5. 查询事件影响排名

```http
GET /api/v1/stocks/{stock_code}/event-impact-ranking?workflow_run_id={workflow_run_id}&limit=10
```

响应：

```json
{
  "data": {
    "stock_code": "002594.SZ",
    "ticker": "002594",
    "ranker": "zc_event_impact_ranker_v1",
    "items": [
      {
        "event_name": "降息预期升温",
        "impact_score": 82,
        "impact_level": "high",
        "direction": "positive",
        "evidence_ids": ["ev_20260513_002594_macro_001"],
        "workflow_run_id": "wr_20260513_002594_000001",
        "judgment_id": "jdg_20260513_002594_001"
      }
    ],
    "updated_at": "2026-05-13T11:00:00+08:00"
  },
  "meta": {
    "request_id": "req_20260513_110030"
  }
}
```

前端注解：

- `impact_score` 是 ZC 模块排序分，不等于 Evidence 可信度，也不等于最终投资信号。
- `direction` 是视图解释方向；若要展示主链路 Bull/Bear 论证，应跳转到 workflow trace。

## 6. 查询利好与风险聚合视图

```http
GET /api/v1/stocks/{stock_code}/benefits-risks?workflow_run_id={workflow_run_id}
```

响应：

```json
{
  "data": {
    "stock_code": "002594.SZ",
    "ticker": "002594",
    "workflow_run_id": "wr_20260513_002594_000001",
    "zc_run_id": "zc_20260513_002594_0001",
    "benefits": [
      {
        "text": "订单能见度提升",
        "evidence_ids": ["ev_20260513_002594_order_001"],
        "source": "zc_module_summary"
      }
    ],
    "risks": [
      {
        "text": "现金流质量下降",
        "evidence_ids": ["ev_20260513_002594_report_003"],
        "source": "main_judgment_summary"
      }
    ],
    "updated_at": "2026-05-13T11:00:00+08:00"
  },
  "meta": {
    "request_id": "req_20260513_110040"
  }
}
```

前端注解：

- 旧项目返回字符串数组，本项目改为对象数组，是为了保留引用链路。
- UI 可以只展示 `text`，但详情跳转必须使用 `evidence_ids`、`workflow_run_id` 或 `zc_run_id`。

