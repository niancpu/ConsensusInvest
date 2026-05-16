# Workflow API

本文档定义异步分析任务、任务快照、推理链路总览和 SSE 事件流。

## 4. Workflow Runs

### 4.1 创建分析任务

```http
POST /api/v1/workflow-runs
Content-Type: application/json
```

请求：

```json
{
  "ticker": "000001",
  "analysis_time": "2026-05-13T10:00:00+08:00",
  "workflow_config_id": "mvp_bull_judge_v1",
  "query": {
    "lookback_days": 30,
    "sources": ["tavily", "exa", "akshare"]
  },
  "options": {
    "stream": true,
    "include_raw_payload": false
  }
}
```

响应：`202 Accepted`

```json
{
  "data": {
    "workflow_run_id": "wr_20260513_000001_000001",
    "status": "queued",
    "ticker": "000001",
    "analysis_time": "2026-05-13T10:00:00+08:00",
    "workflow_config_id": "mvp_bull_judge_v1",
    "created_at": "2026-05-13T10:00:01+08:00",
    "events_url": "/api/v1/workflow-runs/wr_20260513_000001_000001/events",
    "snapshot_url": "/api/v1/workflow-runs/wr_20260513_000001_000001/snapshot"
  },
  "meta": {
    "request_id": "req_20260513_100001"
  }
}
```

前端注解：

- 这个接口只创建任务，不等待分析完成。
- 前端拿到 `workflow_run_id` 后应立即订阅 `events_url`，同时可以定时或断线后调用 `snapshot_url`。
- `analysis_time` 是分析基准时间。回测时不得用当前时间替代。
- `include_raw_payload=false` 只影响创建后的默认快照体积，不影响后续通过 Raw Item 接口下钻。
- 创建任务时，后端会把 `ticker` / `stock_code` / `entity_id` 登记为最小 Company Entity；若 `stock_code` 只传 6 位 A 股代码，后端按代码前缀规范化为 `.SH` 或 `.SZ`。这保证后续 Report Module 可以按 `/api/v1/stocks/{stock_code}/...` 查到同一标的，但不代表已补齐公司简称、行业关系等实体资料。

### 4.2 查询任务列表

```http
GET /api/v1/workflow-runs?ticker=000001&status=completed&limit=20&offset=0
```

响应：

```json
{
  "data": [
    {
      "workflow_run_id": "wr_20260513_000001_000001",
      "ticker": "000001",
      "status": "completed",
      "analysis_time": "2026-05-13T10:00:00+08:00",
      "workflow_config_id": "mvp_bull_judge_v1",
      "created_at": "2026-05-13T10:00:01+08:00",
      "completed_at": "2026-05-13T10:03:42+08:00",
      "judgment_id": "jdg_20260513_000001_001",
      "final_signal": "bullish",
      "confidence": 0.74
    }
  ],
  "pagination": {
    "limit": 20,
    "offset": 0,
    "total": 1,
    "has_more": false
  },
  "meta": {
    "request_id": "req_20260513_100010"
  }
}
```

前端注解：

- 这个接口用于历史任务列表，不承担完整推理链展示。
- 列表里只放摘要字段，完整链路走 `snapshot` 或 `trace`。

### 4.3 查询任务详情

```http
GET /api/v1/workflow-runs/{workflow_run_id}
```

响应：

```json
{
  "data": {
    "workflow_run_id": "wr_20260513_000001_000001",
    "ticker": "000001",
    "status": "running",
    "stage": "debate",
    "analysis_time": "2026-05-13T10:00:00+08:00",
    "workflow_config_id": "mvp_bull_judge_v1",
    "created_at": "2026-05-13T10:00:01+08:00",
    "started_at": "2026-05-13T10:00:03+08:00",
    "completed_at": null,
    "progress": {
      "raw_items_collected": 42,
      "evidence_items_normalized": 31,
      "evidence_items_structured": 26,
      "agent_arguments_completed": 2
    },
    "links": {
      "events": "/api/v1/workflow-runs/wr_20260513_000001_000001/events",
      "snapshot": "/api/v1/workflow-runs/wr_20260513_000001_000001/snapshot",
      "trace": "/api/v1/workflow-runs/wr_20260513_000001_000001/trace",
      "evidence": "/api/v1/workflow-runs/wr_20260513_000001_000001/evidence",
      "judgment": "/api/v1/workflow-runs/wr_20260513_000001_000001/judgment"
    }
  },
  "meta": {
    "request_id": "req_20260513_100020"
  }
}
```

前端注解：

- `stage` 用于显示当前执行阶段，不等于最终状态。
- `progress` 是展示辅助信息，不应作为数据完整性的唯一判断依据。

### 4.4 查询任务快照

```http
GET /api/v1/workflow-runs/{workflow_run_id}/snapshot
```

查询参数：

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `include_raw_payload` | `false` | 是否内联 Raw Item 的原始 payload |
| `include_events` | `false` | 是否内联近期事件 |
| `max_evidence` | `100` | 内联 Evidence 数量上限 |
| `max_arguments` | `100` | 内联 Agent Argument 数量上限 |

响应：

```json
{
  "data": {
    "workflow_run": {
      "workflow_run_id": "wr_20260513_000001_000001",
      "ticker": "000001",
      "status": "running",
      "stage": "judge"
    },
    "evidence_items": [],
    "agent_runs": [],
    "agent_arguments": [],
    "round_summaries": [],
    "judgment": null,
    "last_event_sequence": 87
  },
  "meta": {
    "request_id": "req_20260513_100030"
  }
}
```

前端注解：

- `snapshot` 是断线恢复、刷新页面和历史回放的主接口。
- 它不是实时接口。实时增量走 SSE。
- 如果 `last_event_sequence` 小于前端本地最后事件序号，说明本地事件更新，不要用旧快照覆盖新状态。

### 4.5 查询完整推理链路

```http
GET /api/v1/workflow-runs/{workflow_run_id}/trace
```

响应：

```json
{
  "data": {
    "workflow_run_id": "wr_20260513_000001_000001",
    "judgment_id": "jdg_20260513_000001_001",
    "trace_nodes": [
      {
        "node_type": "judgment",
        "node_id": "jdg_20260513_000001_001",
        "title": "Final judgment",
        "summary": "多头 thesis 有一定证据支持，但仍需关注资产质量指标。"
      },
      {
        "node_type": "agent_argument",
        "node_id": "arg_20260513_bull_v1_r1_001",
        "title": "Bull round 1",
        "summary": "盈利改善和行业政策支持构成主要多头论据。"
      },
      {
        "node_type": "evidence",
        "node_id": "ev_20260513_000001_tushare_001",
        "title": "2026Q1 财务数据",
        "summary": "归母净利润同比增长。"
      },
      {
        "node_type": "raw_item",
        "node_id": "raw_20260513_000001_tushare_001",
        "title": "TuShare financial payload",
        "summary": "原始结构化财务记录。"
      }
    ],
    "trace_edges": [
      {
        "from_node_id": "jdg_20260513_000001_001",
        "to_node_id": "arg_20260513_bull_v1_r1_001",
        "edge_type": "uses_argument"
      },
      {
        "from_node_id": "arg_20260513_bull_v1_r1_001",
        "to_node_id": "ev_20260513_000001_tushare_001",
        "edge_type": "supports"
      },
      {
        "from_node_id": "ev_20260513_000001_tushare_001",
        "to_node_id": "raw_20260513_000001_tushare_001",
        "edge_type": "derived_from"
      }
    ]
  },
  "meta": {
    "request_id": "req_20260513_100040"
  }
}
```

前端注解：

- `trace` 用于展示“结论为什么这么来”的总览图。
- 详情仍通过各资源详情接口查询，不建议把所有原文都塞进 trace。


## 5. SSE Events

### 5.1 订阅任务事件流

```http
GET /api/v1/workflow-runs/{workflow_run_id}/events
Accept: text/event-stream
```

可选查询参数：

| 参数 | 含义 |
| --- | --- |
| `after_sequence` | 从指定 sequence 之后继续推送 |
| `include_snapshot` | 首条事件是否附带轻量快照 |

SSE 格式：

```text
id: evt_20260513_000001_000012
event: evidence_structured
data: {"event_id":"evt_20260513_000001_000012","workflow_run_id":"wr_20260513_000001_000001","sequence":12,"event_type":"evidence_structured","created_at":"2026-05-13T10:00:18+08:00","payload":{}}
```

统一事件外壳：

```json
{
  "event_id": "evt_20260513_000001_000012",
  "workflow_run_id": "wr_20260513_000001_000001",
  "sequence": 12,
  "event_type": "evidence_structured",
  "created_at": "2026-05-13T10:00:18+08:00",
  "payload": {}
}
```

前端注解：

- 前端应按 `sequence` 做幂等处理，避免断线重连后重复插入。
- `event_type` 决定 `payload` schema。
- SSE 事件是运行日志和增量结果，不等价于最终数据库完整状态。完整状态以资源查询接口为准。

### 5.2 事件类型

Workflow SSE 只覆盖有 `workflow_run_id` 的主分析链路事件。`report_generation` 报告生成和无 workflow 的异步补齐不能挂到本接口；这类状态通过报告视图响应中的 `data_state`、`refresh_task_id` 或后续独立 report 事件入口暴露。

| event_type | 含义 |
| --- | --- |
| `workflow_queued` | 任务已进入队列 |
| `workflow_started` | 任务开始执行 |
| `connector_started` | 某个 Source Connector 开始采集 |
| `connector_progress` | Connector 采集进度 |
| `raw_item_collected` | 新 Raw Item 已入库 |
| `evidence_normalized` | 新 Evidence 已归一化 |
| `evidence_structuring_started` | Evidence Structuring Agent 开始处理 |
| `evidence_structured` | Evidence 结构化结果已生成 |
| `agent_run_started` | 某个 Agent 开始运行 |
| `agent_argument_delta` | Agent 论证片段增量 |
| `agent_argument_completed` | Agent 单轮论证完成 |
| `round_summary_delta` | Round Summary 增量 |
| `round_summary_completed` | Round Summary 完成 |
| `judge_started` | Judge Agent 开始运行 |
| `judge_tool_call_started` | Judge 开始回查 Evidence / Raw |
| `judge_tool_call_completed` | Judge 回查完成 |
| `judgment_delta` | 最终判断文本或结构增量 |
| `judgment_completed` | 最终判断完成 |
| `workflow_completed` | 整个任务完成 |
| `workflow_failed` | 整个任务失败 |

前端注解：

- `agent_argument_delta` 和 `judgment_delta` 用于实时展示，但最终保存应以 `completed` 事件或详情接口返回为准。
- `judge_tool_call_started/completed` 是透明链路的重要组成，不要只展示最终结论。

### 5.2.1 内部事件映射

后端内部事件使用 dotted style，例如 `agent.argument_saved`；Web SSE 使用 snake_case。公开 API 只承诺本节 `event_type`，不暴露内部事件名。

| 内部事件 | Web SSE event_type |
| --- | --- |
| `search.task_queued` | `connector_progress` |
| `search.source_started` | `connector_started` |
| `search.item_found` | `connector_progress` |
| `search.source_failed` | `connector_progress` |
| `search.task_completed` | `connector_progress` |
| `evidence.raw_saved` | `raw_item_collected` |
| `evidence.item_saved` | `evidence_normalized` |
| `evidence.structure_saved` | `evidence_structured` |
| `agent.argument_saved` | `agent_argument_completed` |
| `round.summary_saved` | `round_summary_completed` |
| `judge.tool_called` | `judge_tool_call_completed` |
| `judge.completed` | `judgment_completed` |

前端注解：

- 映射事件只是运行过程提示，不替代资源详情接口。
- 如果实现保留内部事件日志，前端仍只依赖 Web SSE 的 `event_type`。

### 5.3 Agent Argument Delta 示例

```json
{
  "event_id": "evt_20260513_000001_000051",
  "workflow_run_id": "wr_20260513_000001_000001",
  "sequence": 51,
  "event_type": "agent_argument_delta",
  "created_at": "2026-05-13T10:01:12+08:00",
  "payload": {
    "agent_run_id": "arun_20260513_bull_v1_001",
    "agent_argument_id": "arg_20260513_bull_v1_r1_001",
    "agent_id": "bull_v1",
    "round": 1,
    "delta": "ev_001 支持盈利改善 thesis，原因是...",
    "referenced_evidence_ids": ["ev_20260513_000001_tushare_001"]
  }
}
```

前端注解：

- `delta` 可以拼接展示，但不要把 delta 拼接结果当成最终结构化字段。
- 完整论证字段以 `agent_argument_completed` 或 `GET /agent-arguments/{id}` 为准。

### 5.4 Judge Tool Call 示例

```json
{
  "event_id": "evt_20260513_000001_000072",
  "workflow_run_id": "wr_20260513_000001_000001",
  "sequence": 72,
  "event_type": "judge_tool_call_completed",
  "created_at": "2026-05-13T10:02:30+08:00",
  "payload": {
    "judgment_id": "jdg_20260513_000001_001",
    "tool_name": "get_evidence_detail",
    "input": {
      "evidence_id": "ev_20260513_000001_tushare_001"
    },
    "output_summary": "该 Evidence 来自 TuShare 财务数据，source_quality=0.9，structuring_confidence=0.82。",
    "affected_fields": ["confidence", "risk_notes"]
  }
}
```

前端注解：

- 这里暴露的是可审计的工具回查过程，不是模型私有思考。
- 如果 Judge 的最终判断依赖某次回查，前端应允许用户从该事件跳转到 Evidence 详情。

