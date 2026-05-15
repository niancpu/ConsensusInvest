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
| `workflow_run_id` | 否 | 主链路 workflow ID；Report Module 单独触发补齐时可为空。 |
| `analysis_time` | 是 | 业务分析时间；回测和信息可用性判断必须使用它。 |
| `requested_by` | 是 | 调用来源，如 `workflow_orchestrator`、`report_module`、`evidence_maintenance`。 |
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
waiting
partial_completed
completed
failed
cancelled
```

约束：

- `waiting` 表示任务已持久化且正在等待外部 provider、子任务、预算窗口或调度条件。
- `partial_completed` 表示至少有部分结果可读取或已入库，不代表任务失败。
- 重复提交同一 `idempotency_key` 时，返回已有 `task_id` 和当前状态。
- 异步任务不得要求调用方同步等待完整结果；调用方应订阅事件或轮询状态。

## 4. 内部事件

内部事件用于模块间追踪和前端透明链路的上游材料。事件不是最终存储模型，也不直接等同于 Web SSE 事件；对前端暴露时由 Runtime Event Projector 转成 `docs/web_api/workflow.md` 定义的 snake_case 事件。

```json
{
  "event_id": "evt_20260513_000001",
  "event_type": "evidence.item_saved",
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
| `evidence.raw_saved` | Evidence Store | 原始信息已持久化为 Raw Item。 |
| `evidence.item_saved` | Evidence Store | Raw Item 已归一化为 Evidence。 |
| `evidence.structure_saved` | Evidence Store | Evidence Structure 已保存。 |
| `agent.argument_saved` | Agent Swarm | Agent 论点已保存。 |
| `judge.tool_called` | Judge Runtime | Judge 回查了 Evidence/Raw。 |
| `judge.completed` | Judge Runtime | 最终判断完成。 |
| `report.refresh_requested` | Report Module | 页面聚合触发异步补齐。 |

内部事件到 Web SSE 的投影规则：

| 内部事件 | Web SSE event_type | 说明 |
| --- | --- | --- |
| `search.task_queued` | `connector_progress` | 仅主 workflow 内搜索投影到 workflow SSE；无 `workflow_run_id` 的补齐不挂到 workflow SSE。 |
| `search.source_started` | `connector_started` | 主 workflow 内某个 source 开始采集。 |
| `search.item_found` | `connector_progress` | 仅表示 Search Agent 找到候选原始项；未入库前不能投影成 Raw Item。 |
| `search.source_failed` | `connector_progress` | 单个 source 失败不等于 workflow 失败；失败细节放在 payload。 |
| `search.task_completed` | `connector_progress` | 搜索任务阶段状态提示；最终资源状态以查询接口为准。 |
| `evidence.raw_saved` | `raw_item_collected` | Evidence Store 保存 Raw Item 后才能对外暴露 `raw_ref`。 |
| `evidence.item_saved` | `evidence_normalized` | Evidence Store 生成 Evidence 后才能对外暴露 `evidence_id`。 |
| `evidence.structure_saved` | `evidence_structured` | 结构化结果保存后投影。 |
| `agent.argument_saved` | `agent_argument_completed` | Agent 论点持久化后投影；实时 delta 由运行时另行产生。 |
| `round.summary_saved` | `round_summary_completed` | Round Summary 持久化后投影。 |
| `judge.tool_called` | `judge_tool_call_completed` | 只暴露工具名、输入摘要、结果引用，不暴露模型私有思考。 |
| `judge.completed` | `judgment_completed` | Judgment 持久化后投影。 |
| `report.view_built` | 不投影到 workflow SSE | Report Module 事件通过报告视图响应或后续独立 report 事件入口消费。 |
| `report.refresh_requested` | 不投影到 workflow SSE | Report Module 已提交异步补齐任务；当前响应使用 `data_state=refreshing` 和 `refresh_task_id` 表达。 |

投影约束：

- Web SSE 事件必须带 `correlation_id`；主 workflow 事件还必须带 `workflow_run_id`。
- `workflow_run_id` 为空的 `report_generation` 或异步补齐事件不能挂到 `/workflow-runs/{workflow_run_id}/events` 下；应由报告视图查询或后续独立 report 事件入口消费。
- 事件 payload 只承载增量提示和跳转 ID，不承载完整事实对象。

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
