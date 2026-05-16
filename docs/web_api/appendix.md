# API Appendix

本文档定义 Workflow Config、错误码、状态枚举、MVP 取舍与未决项。

## 16. Configs

### 16.1 查询 Workflow Config 列表

```http
GET /api/v1/workflow-configs
```

响应：

```json
{
  "data": [
    {
      "workflow_config_id": "mvp_bull_judge_v1",
      "name": "MVP Bull + Judge",
      "description": "Tavily/Exa/AkShare/TuShare + Evidence Structurer + Bull Agent + Round Summary + Judge",
      "collectors": ["tavily", "exa", "akshare", "tushare"],
      "agents": ["evidence_structurer_v1", "bull_v1", "round_summary_v1", "judge_v1"],
      "debate_rounds": 3,
      "enabled": true
    }
  ],
  "meta": {
    "request_id": "req_20260513_100800"
  }
}
```

前端注解：

- 前端创建任务时应使用后端返回的 `workflow_config_id`。
- 不要在前端硬编码 Agent 列表作为真实执行依据。


## 17. Error Codes

| code | HTTP 状态 | 含义 |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | 请求字段缺失、格式错误或参数非法 |
| `UNAUTHORIZED` | 401 | 未认证 |
| `FORBIDDEN` | 403 | 无权限访问该资源 |
| `STOCK_NOT_FOUND` | 404 | 股票不存在或无法规范化 |
| `WORKFLOW_NOT_FOUND` | 404 | workflow run 不存在 |
| `RAW_ITEM_NOT_FOUND` | 404 | Raw Item 不存在 |
| `EVIDENCE_NOT_FOUND` | 404 | Evidence 不存在 |
| `AGENT_ARGUMENT_NOT_FOUND` | 404 | Agent Argument 不存在 |
| `JUDGMENT_NOT_FOUND` | 404 | Judgment 不存在 |
| `REPORT_RUN_NOT_FOUND` | 404 | Report Module 视图运行不存在 |
| `MARKET_SNAPSHOT_NOT_FOUND` | 404 | MarketSnapshot 不存在 |
| `WORKFLOW_ALREADY_RUNNING` | 409 | 同一约束下已有运行中的任务 |
| `BOUNDARY_VIOLATION` | 409 | 请求试图跨越模块边界，例如用 report view 写推理关系 |
| `CONNECTOR_FAILED` | 502 | 外部信息源采集失败 |
| `AGENT_FAILED` | 500 | Agent 执行失败 |
| `JUDGE_FAILED` | 500 | Judge 执行失败 |
| `INTERNAL_ERROR` | 500 | 未分类内部错误 |

前端注解：

- `CONNECTOR_FAILED` 不一定意味着整个 workflow 失败。后端可以继续处理其他来源，并在 Evidence 质量或 Workflow 状态中暴露部分失败。
- `workflow_failed` SSE 事件才表示整个任务失败。


## 18. 状态枚举

### 18.1 Workflow Status

```text
queued
running
waiting
partial_completed
completed
failed
cancelled
```

前端注解：

- `waiting` 表示任务在等待外部 provider、子任务、预算窗口或调度条件，仍属于非终态。
- `partial_completed` 表示已有部分可用产物，同时仍存在失败来源或未完成步骤；前端应展示可用结果和限制说明，不要当作整体失败。

### 18.2 Workflow Stage

```text
queued
collecting_raw_items
normalizing_evidence
structuring_evidence
debate
round_summary
judge
completed
failed
```

### 18.3 Reference Role

```text
supports
counters
cited
refuted
```

### 18.4 Report Mode

```text
report_generation
with_workflow_trace
```

### 18.5 Data State

```text
ready
partial
missing
refreshing
stale
failed
```

前端注解：

- `status` 是任务生命周期状态。
- `stage` 是当前执行阶段。
- `reference_role` 是引用关系，不是 Evidence 自身属性。
- `report_generation` 不创建 `workflow_run_id`，也不产生 `judgment_id`。
- `refreshing` 只表示后端已提交异步补齐，不表示当前响应包含新数据。


## 19. MVP 取舍与未决项

### 19.1 已定取舍

- 创建任务必须异步返回 `202 Accepted`；
- 实时运行过程使用 SSE；
- 查询和下钻使用 HTTP JSON；
- Evidence、Agent Argument、Round Summary、Judgment 都提供独立查询入口；
- 最终判断必须能通过 `trace` 和 `references` 回查证据链；
- 低质量 Evidence 不隐藏，只标记质量问题；
- Agent 角色解释放在 `role_output`，不写入 Evidence。
- 旧 `analysis/*`、`reports/*` 测试 API 不作为迁移期别名，直接裁切。
- `stocks/*`、`market/*` 属于 Report Module 视图接口，规则见 `docs/report_module`；主协议不重复维护这些 endpoint。
- Report Module 可以消费主系统已有 Entity、Evidence、市场快照和 workflow 结果，但不能替代主 workflow。
- Report Module 的 `report_generation` 模式必须返回 `report_run_id`，且 `workflow_run_id` / `judgment_id` 为空。
- Report View 对 Evidence 的引用只能使用 `reference_role=cited`。

### 19.2 未决项

- 鉴权方式：当前协议保留 `Authorization` 扩展空间，MVP 可先按本地单用户处理；
- 取消任务：如需要，可增加 `POST /api/v1/workflow-runs/{workflow_run_id}/cancel`；
- 任务重试：如需要，可增加 `POST /api/v1/workflow-runs/{workflow_run_id}/retry`；
- WebSocket：等出现双向实时控制需求后再评估；
- 大规模分页策略：MVP 使用 `limit/offset`，后续数据量增大时可切到 cursor；
- Raw Payload 裁剪：如供应商 payload 过大或含敏感字段，需要增加字段级裁剪策略。

前端注解：

- 未决项不要在前端写死假设。
- 对取消、重试、权限等能力，先按“后端未承诺”处理。

