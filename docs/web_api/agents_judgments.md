# Agent And Judgment API

本文档定义 Agent Run、Agent Argument、Round Summary、Judgment 和 Judge Tool Calls。

## 8. Agent Runs And Arguments

### 8.1 查询 Agent Run 列表

```http
GET /api/v1/workflow-runs/{workflow_run_id}/agent-runs
```

响应：

```json
{
  "data": [
    {
      "agent_run_id": "arun_20260513_bull_v1_001",
      "workflow_run_id": "wr_20260513_000001_000001",
      "agent_id": "bull_v1",
      "role": "bullish_interpreter",
      "status": "completed",
      "started_at": "2026-05-13T10:01:00+08:00",
      "completed_at": "2026-05-13T10:01:40+08:00",
      "rounds": [1, 2, 3]
    }
  ],
  "meta": {
    "request_id": "req_20260513_100300"
  }
}
```

前端注解：

- Agent Run 是运行记录，Agent Argument 才是用户可阅读的论证内容。

### 8.2 查询 Agent Argument 列表

```http
GET /api/v1/workflow-runs/{workflow_run_id}/agent-arguments?agent_id=bull_v1&round=1
```

响应：

```json
{
  "data": [
    {
      "agent_argument_id": "arg_20260513_bull_v1_r1_001",
      "agent_run_id": "arun_20260513_bull_v1_001",
      "workflow_run_id": "wr_20260513_000001_000001",
      "agent_id": "bull_v1",
      "role": "bullish_interpreter",
      "round": 1,
      "argument": "从多头视角看，盈利改善和政策支持构成主要 thesis。",
      "confidence": 0.81,
      "referenced_evidence_ids": ["ev_20260513_000001_tushare_001"],
      "counter_evidence_ids": ["ev_20260513_000001_news_003"],
      "limitations": ["部分指标需要与历史口径核对"],
      "role_output": {
        "stance_interpretation": "该证据支持盈利改善 thesis。",
        "bullish_impact_assessment": 0.72
      },
      "created_at": "2026-05-13T10:01:40+08:00"
    }
  ],
  "meta": {
    "request_id": "req_20260513_100310"
  }
}
```

前端注解：

- `role_output` 是 Agent 角色专属字段，不同 Agent 可能不同。
- 通用展示应优先使用 `argument/confidence/referenced_evidence_ids/counter_evidence_ids/limitations`。

### 8.3 查询 Agent Argument 详情

```http
GET /api/v1/agent-arguments/{agent_argument_id}
```

响应同单条 Agent Argument。

前端注解：

- 从 Round Summary、Judgment 或 Trace 点击某条论证时，用这个接口下钻。

### 8.4 查询 Agent Argument 引用

```http
GET /api/v1/agent-arguments/{agent_argument_id}/references
```

响应：

```json
{
  "data": [
    {
      "reference_id": "eref_20260513_000001_001",
      "source_type": "agent_argument",
      "source_id": "arg_20260513_bull_v1_r1_001",
      "evidence_id": "ev_20260513_000001_tushare_001",
      "reference_role": "supports",
      "round": 1
    }
  ],
  "meta": {
    "request_id": "req_20260513_100320"
  }
}
```

前端注解：

- 这个接口用于在论证详情页高亮所有被引用或反驳的 Evidence。


## 9. Round Summaries

### 9.1 查询 Round Summary 列表

```http
GET /api/v1/workflow-runs/{workflow_run_id}/round-summaries
```

响应：

```json
{
  "data": [
    {
      "round_summary_id": "rsum_20260513_000001_r1",
      "workflow_run_id": "wr_20260513_000001_000001",
      "round": 1,
      "summary": "第 1 轮主要形成盈利改善 thesis，同时保留资产质量指标待核对。",
      "participants": ["bull_v1"],
      "agent_argument_ids": ["arg_20260513_bull_v1_r1_001"],
      "referenced_evidence_ids": ["ev_20260513_000001_tushare_001"],
      "disputed_evidence_ids": ["ev_20260513_000001_news_003"],
      "created_at": "2026-05-13T10:02:00+08:00"
    }
  ],
  "meta": {
    "request_id": "req_20260513_100400"
  }
}
```

前端注解：

- Round Summary 是导航层，不是新事实来源。
- 如果 Summary 和 Agent Argument 有冲突，详情以 Agent Argument 和 Evidence 为准。

### 9.2 查询 Round Summary 详情

```http
GET /api/v1/round-summaries/{round_summary_id}
```

响应同单条 Round Summary。


## 10. Judgments

### 10.1 查询任务最终判断

```http
GET /api/v1/workflow-runs/{workflow_run_id}/judgment
```

响应：

```json
{
  "data": {
    "judgment_id": "jdg_20260513_000001_001",
    "workflow_run_id": "wr_20260513_000001_000001",
    "final_signal": "bullish",
    "confidence": 0.74,
    "time_horizon": "short_to_mid_term",
    "key_positive_evidence_ids": ["ev_20260513_000001_tushare_001"],
    "key_negative_evidence_ids": ["ev_20260513_000001_news_003"],
    "reasoning": "盈利改善证据和行业政策支持形成较强多头 thesis，但资产质量指标仍需复核。",
    "risk_notes": ["资产质量指标需要继续核对", "市场整体风险偏好可能影响短期表现"],
    "suggested_next_checks": ["核对历史财报口径", "补充行业同业对比"],
    "referenced_agent_argument_ids": ["arg_20260513_bull_v1_r1_001"],
    "tool_call_count": 2,
    "created_at": "2026-05-13T10:03:42+08:00",
    "links": {
      "references": "/api/v1/judgments/jdg_20260513_000001_001/references",
      "trace": "/api/v1/workflow-runs/wr_20260513_000001_000001/trace"
    }
  },
  "meta": {
    "request_id": "req_20260513_100500"
  }
}
```

前端注解：

- Judgment 是最终判断，但不是孤立结论。
- 页面展示最终判断时，必须提供跳转到关键 Evidence、Agent Argument 和 Trace 的入口。

### 10.2 查询 Judgment 详情

```http
GET /api/v1/judgments/{judgment_id}
```

响应同单条 Judgment。

### 10.3 查询 Judgment 引用

```http
GET /api/v1/judgments/{judgment_id}/references
```

响应：

```json
{
  "data": [
    {
      "reference_id": "eref_20260513_000001_021",
      "source_type": "judgment",
      "source_id": "jdg_20260513_000001_001",
      "evidence_id": "ev_20260513_000001_tushare_001",
      "reference_role": "supports",
      "round": null
    },
    {
      "reference_id": "eref_20260513_000001_022",
      "source_type": "judgment",
      "source_id": "jdg_20260513_000001_001",
      "evidence_id": "ev_20260513_000001_news_003",
      "reference_role": "counters",
      "round": null
    }
  ],
  "meta": {
    "request_id": "req_20260513_100510"
  }
}
```

前端注解：

- 这个接口用于最终判断页展示“支持证据”和“反向证据”。
- `reference_role` 是 Judge 对证据使用方式的记录。

### 10.4 查询 Judge Tool Calls

```http
GET /api/v1/judgments/{judgment_id}/tool-calls
```

响应：

```json
{
  "data": [
    {
      "tool_call_id": "tcall_20260513_judge_001",
      "judgment_id": "jdg_20260513_000001_001",
      "tool_name": "get_evidence_detail",
      "input": {
        "evidence_id": "ev_20260513_000001_tushare_001"
      },
      "output_summary": "source_quality=0.9，structuring_confidence=0.82。",
      "referenced_evidence_ids": ["ev_20260513_000001_tushare_001"],
      "created_at": "2026-05-13T10:02:30+08:00"
    }
  ],
  "meta": {
    "request_id": "req_20260513_100520"
  }
}
```

前端注解：

- 这是透明回查链路，不是展示模型私有思考。
- 如果未来出于安全或合规原因需要裁剪，也应裁剪输出内容，而不是删除工具调用记录。

