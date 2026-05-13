# Agent Swarm / Judge Runtime 接口协议

本文档定义主链路 Agent 群和 Judge Runtime 的内部接口格式。Agent Swarm 消费已入库 Evidence，不接收 Search Agent 未入库结果。

## 1. run

```text
AgentSwarm.run(envelope: InternalCallEnvelope, input: AgentSwarmInput) -> AsyncTaskReceipt
```

请求：

```json
{
  "workflow_run_id": "wr_20260513_002594_000001",
  "ticker": "002594",
  "entity_id": "ent_company_002594",
  "workflow_config_id": "mvp_bull_judge_v1",
  "evidence_selection": {
    "evidence_ids": [
      "ev_20260513_002594_tavily_001",
      "ev_20260513_002594_tushare_001"
    ],
    "selection_strategy": "top_relevance_quality_v1"
  },
  "history": {
    "previous_judgment_ids": []
  }
}
```

字段注解：

| 字段 | 说明 |
| --- | --- |
| `workflow_run_id` | 主链路运行 ID，必须和 `envelope.workflow_run_id` 一致。 |
| `workflow_config_id` | 本轮启用的 Agent 编排配置。 |
| `evidence_selection.evidence_ids` | 必须来自 Evidence Store。 |
| `selection_strategy` | 选择 Evidence 的策略名，用于复现输入。 |
| `history.previous_judgment_ids` | 可选历史判断，用于连续研究。 |

约束：

- `evidence_ids` 为空或质量不足时，返回 `insufficient_evidence`，并给出 `EvidenceGap`。
- Agent Swarm 不直接调用 Search Agent；补齐动作由 Workflow Orchestrator 决定。

## 2. AgentArgumentDraft

Agent 单轮输出：

```json
{
  "agent_id": "bull_v1",
  "role": "bullish_interpreter",
  "round": 1,
  "argument": "从多头视角看，盈利改善和政策支持构成主要 thesis。",
  "confidence": 0.81,
  "referenced_evidence_ids": [
    "ev_20260513_002594_tushare_001"
  ],
  "counter_evidence_ids": [
    "ev_20260513_002594_news_003"
  ],
  "limitations": ["部分指标需要与历史口径核对"],
  "role_output": {
    "stance_interpretation": "该证据支持盈利改善 thesis。",
    "bullish_impact_assessment": 0.72
  }
}
```

写入要求：

| 字段 | 说明 |
| --- | --- |
| `argument` | 面向主链路保存的论证文本。 |
| `referenced_evidence_ids` | 支持当前论点的 Evidence ID。 |
| `counter_evidence_ids` | 当前论点主动承认或反驳的反向 Evidence ID。 |
| `limitations` | 论点限制条件，供 Judge 和前端透明链路展示。 |
| `role_output` | Agent 专属结构；运行时只要求外层字段稳定。 |

保存后应产生：

```json
{
  "agent_argument_id": "arg_20260513_bull_v1_r1_001",
  "saved_reference_count": 2
}
```

并调用：

```text
EvidenceStore.save_references(envelope, EvidenceReferenceBatch)
```

## 3. RoundSummaryDraft

```json
{
  "workflow_run_id": "wr_20260513_002594_000001",
  "round": 1,
  "summary": "第 1 轮形成盈利改善 thesis，同时保留现金流质量待核对。",
  "participants": ["bull_v1"],
  "agent_argument_ids": ["arg_20260513_bull_v1_r1_001"],
  "referenced_evidence_ids": ["ev_20260513_002594_tushare_001"],
  "disputed_evidence_ids": ["ev_20260513_002594_news_003"]
}
```

约束：

- `summary` 不得吞掉 `agent_argument_ids` 和 `evidence_ids`。
- Round Summary 只做导航和压缩，不作为新事实来源。

## 4. EvidenceGap

当证据不足时，Agent Swarm 返回结构化缺口：

```json
{
  "status": "insufficient_evidence",
  "gaps": [
    {
      "gap_type": "missing_industry_comparison",
      "description": "缺少与同业公司的毛利率对比。",
      "suggested_search": {
        "target_entity_ids": ["ent_company_002594"],
        "evidence_types": ["financial_report", "industry_news"],
        "lookback_days": 365,
        "keywords": ["比亚迪 毛利率 同业 对比"]
      }
    }
  ]
}
```

字段注解：

| 字段 | 说明 |
| --- | --- |
| `gap_type` | 机器可读缺口类型。 |
| `description` | 给 Orchestrator/Judge/前端看的缺口说明。 |
| `suggested_search` | 搜索建议，不是 SearchTask；是否执行由 Orchestrator 决定。 |

## 5. JudgeRuntime.run

```text
JudgeRuntime.run(envelope: InternalCallEnvelope, input: JudgeInput) -> AsyncTaskReceipt
```

请求：

```json
{
  "workflow_run_id": "wr_20260513_002594_000001",
  "round_summary_ids": ["rsum_20260513_002594_r1"],
  "agent_argument_ids": ["arg_20260513_bull_v1_r1_001"],
  "key_evidence_ids": ["ev_20260513_002594_tushare_001"],
  "tool_access": {
    "get_evidence_detail": true,
    "get_raw_item": true,
    "query_evidence_references": true
  }
}
```

Judge 工具调用记录：

```json
{
  "tool_call_id": "jtc_20260513_002594_001",
  "tool_name": "get_evidence_detail",
  "arguments": {
    "evidence_id": "ev_20260513_002594_tushare_001"
  },
  "result_ref": {
    "evidence_id": "ev_20260513_002594_tushare_001",
    "raw_ref": "raw_20260513_002594_tushare_001"
  },
  "used_for": "verify_profit_growth_claim"
}
```

Judge 输出：

```json
{
  "judgment_id": "jdg_20260513_002594_001",
  "workflow_run_id": "wr_20260513_002594_000001",
  "conclusion": "watch",
  "confidence": 0.74,
  "summary": "中期基本面有支撑，但现金流和估值仍需复核。",
  "key_evidence_ids": ["ev_20260513_002594_tushare_001"],
  "major_risks": [
    {
      "text": "现金流质量低于利润增速。",
      "evidence_ids": ["ev_20260513_002594_report_003"]
    }
  ],
  "limitations": ["缺少最新同行横向估值对比"]
}
```

## 6. 事件

| event_type | payload |
| --- | --- |
| `agent.run_started` | `workflow_run_id`、`agent_id`、`round` |
| `agent.argument_saved` | `agent_argument_id`、`referenced_evidence_ids` |
| `agent.evidence_gap_found` | `workflow_run_id`、`gaps` |
| `round.summary_saved` | `round_summary_id`、`agent_argument_ids` |
| `judge.tool_called` | `tool_call_id`、`tool_name`、`result_ref` |
| `judge.completed` | `judgment_id`、`key_evidence_ids` |
