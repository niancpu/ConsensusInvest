# 通用内部接口协议

本文档定义所有内部模块接口共享的调用信封、返回包装、异步任务、事件和错误对象。它不定义模块职责，也不表示 HTTP 协议；它只约束跨模块接口调用时必须携带什么、如何返回状态、如何表达错误。

## 1. InternalCallEnvelope

所有内部接口调用都应携带：

```json
{
  "request_id": "req_20260513_000001",
  "correlation_id": "corr_20260513_000001",
  "workflow_run_id": null,
  "analysis_time": "2026-05-13T10:00:00+08:00",
  "requested_by": "workflow_orchestrator",
  "idempotency_key": "search_002594_20260513_missing_news",
  "trace_level": "standard"
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `request_id` | 是 | 单次调用 ID，用于日志定位。 |
| `correlation_id` | 是 | 一组跨模块调用的关联 ID，贯穿搜索、入库、推理、报告。 |
| `workflow_run_id` | 否 | 主链路 workflow ID；ZC 单独触发补齐时可为空。 |
| `analysis_time` | 是 | 业务分析时间；回测和信息可用性判断必须使用它。 |
| `requested_by` | 是 | 调用来源，如 `workflow_orchestrator`、`zc_module`、`evidence_maintenance`。 |
| `idempotency_key` | 视调用而定 | 创建类接口必须传；查询类接口可不传。 |
| `trace_level` | 否 | `minimal`、`standard`、`debug`；控制事件和日志粒度。 |

## 2. 同步返回包装

同步调用返回：

```json
{
  "ok": true,
  "request_id": "req_20260513_000001",
  "correlation_id": "corr_20260513_000001",
  "data": {},
  "warnings": []
}
```

失败返回：

```json
{
  "ok": false,
  "request_id": "req_20260513_000001",
  "correlation_id": "corr_20260513_000001",
  "error": {
    "code": "invalid_time_range",
    "message": "publish_time_lte must not be later than analysis_time",
    "retryable": false,
    "details": {
      "analysis_time": "2026-05-13T10:00:00+08:00"
    }
  }
}
```

## 3. 异步任务返回

创建异步任务时，只返回接收结果：

```json
{
  "task_id": "st_20260513_002594_0001",
  "status": "queued",
  "accepted_at": "2026-05-13T11:00:00+08:00",
  "idempotency_key": "search_002594_20260513_missing_news",
  "poll_after_ms": 1000
}
```

通用任务状态：

```text
queued
running
partial_completed
completed
failed
cancelled
```

约束：

- `partial_completed` 表示至少有部分结果可读取或已入库，不代表任务失败。
- 重复提交同一 `idempotency_key` 时，返回已有 `task_id` 和当前状态。
- 异步任务不得要求调用方同步等待完整结果；调用方应订阅事件或轮询状态。

## 4. 内部事件

内部事件用于模块间追踪和前端透明链路的上游材料。事件不是最终存储模型。

```json
{
  "event_id": "evt_20260513_000001",
  "event_type": "search.item_ingested",
  "occurred_at": "2026-05-13T11:00:12+08:00",
  "correlation_id": "corr_20260513_000001",
  "workflow_run_id": null,
  "producer": "evidence_store",
  "payload": {
    "task_id": "st_20260513_002594_0001",
    "raw_ref": "raw_20260513_002594_tavily_001",
    "evidence_id": "ev_20260513_002594_tavily_001"
  }
}
```

建议事件类型：

| 事件类型 | 生产方 | 说明 |
| --- | --- | --- |
| `search.task_queued` | Search Agent Pool | 搜索任务已接收。 |
| `search.item_found` | Search Agent Worker | 找到原始信息项，但还未入库。 |
| `search.item_ingested` | Evidence Store | 原始信息已产生 Raw/Evidence。 |
| `evidence.structure_saved` | Evidence Store | Evidence Structure 已保存。 |
| `agent.argument_saved` | Agent Swarm | Agent 论点已保存。 |
| `judge.tool_called` | Judge Runtime | Judge 回查了 Evidence/Raw。 |
| `judge.completed` | Judge Runtime | 最终判断完成。 |
| `report.refresh_requested` | Report/ZC Module | 页面聚合触发异步补齐。 |

## 5. 通用错误码

| code | retryable | 说明 |
| --- | --- | --- |
| `invalid_request` | false | 请求字段缺失或类型不合法。 |
| `invalid_time_range` | false | 请求违反 `analysis_time` / `publish_time` 约束。 |
| `duplicate_request` | true | 幂等键已存在，返回已有任务或结果。 |
| `source_unavailable` | true | 外部 source/provider 暂不可用。 |
| `partial_source_failure` | true | 多 source 任务部分失败。 |
| `not_found` | false | 请求的 task/evidence/raw/workflow 不存在。 |
| `insufficient_evidence` | true | 证据不足，需要 Orchestrator 决定是否补齐。 |
| `write_boundary_violation` | false | 调用方尝试写入不归它所有的数据对象。 |
| `internal_error` | true | 未分类内部错误。 |
