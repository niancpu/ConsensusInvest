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
- Agent Swarm 不直接调用 Search Agent；补齐动作由 Workflow Orchestrator 通过 `EvidenceAcquisitionService` 决定。
- Agent Swarm 可以暴露受控 `request_search` / `search_intent` 工具；该工具只能生成 `EvidenceGap.suggested_search`，不能直接调用 provider。
- Agent Swarm 可以返回 `suggested_search`，但它不是 `SearchTask`，不能要求当前 Agent 同步等待补齐完成，也不能携带未入库搜索结果。

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

`suggested_search` 约束：

- 只能描述建议补齐的信息类型、关键词、实体和时间范围。
- 不能指定 provider 私有参数、不能覆盖 workflow source 白名单、不能绕过预算。
- 不能包含未入库搜索结果，也不能被 Agent Swarm / Judge 直接消费为 Evidence。
- Orchestrator 可以丢弃、合并、降级或改写建议，再交给 `EvidenceAcquisitionService` 生成正式 `SearchTask`。
- SearchResult 必须经 SearchAgentPool 回调写入 Evidence Store；后续 Debate/Judge 只能通过新的 `evidence_ids` 消费补齐结果。

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
    "query_evidence_references": true,
    "request_search": true
  }
}
```

`request_search` 是受控搜索意图工具。它的输出必须是 `EvidenceGap.suggested_search`，由 Orchestrator 后续处理；它不是直接 provider 调用，也不能返回 SearchResult。

Judge 工具调用记录：

```json
{
  "tool_call_id": "jtc_20260513_002594_001",
  "judgment_id": "jdg_20260513_002594_001",
  "tool_name": "get_evidence_detail",
  "input": {
    "evidence_id": "ev_20260513_002594_tushare_001"
  },
  "result_ref": {
    "evidence_id": "ev_20260513_002594_tushare_001",
    "raw_ref": "raw_20260513_002594_tushare_001"
  },
  "output_summary": "source_quality=0.9，structuring_confidence=0.82。",
  "referenced_evidence_ids": ["ev_20260513_002594_tushare_001"],
  "used_for": "verify_profit_growth_claim"
}
```

公开 API 投影：

- `input`、`output_summary`、`referenced_evidence_ids` 直接投影到 `GET /api/v1/judgments/{judgment_id}/tool-calls`。
- `result_ref` 用于内部回查和 trace 构建，公开接口可以按权限裁剪，但不能删除工具调用记录本身。

Judge 输出：

```json
{
  "judgment_id": "jdg_20260513_002594_001",
  "workflow_run_id": "wr_20260513_002594_000001",
  "final_signal": "neutral",
  "confidence": 0.74,
  "time_horizon": "short_to_mid_term",
  "key_positive_evidence_ids": ["ev_20260513_002594_tushare_001"],
  "key_negative_evidence_ids": ["ev_20260513_002594_report_003"],
  "reasoning": "中期基本面有支撑，但现金流和估值仍需复核。",
  "risk_notes": ["现金流质量低于利润增速。"],
  "suggested_next_checks": ["补充最新同行横向估值对比"],
  "referenced_agent_argument_ids": ["arg_20260513_bull_v1_r1_001"],
  "limitations": ["缺少最新同行横向估值对比"]
}
```

字段约束：

| 字段 | 说明 |
| --- | --- |
| `final_signal` | Judge Runtime 的最终信号字段；Web API 直接投影该字段。 |
| `confidence` | Judge 对最终判断可靠性的估计，不是 Evidence 质量分，也不是 Report Module 字段。 |
| `reasoning` | 可审计判断摘要，必须能通过 `referenced_agent_argument_ids` 和 Evidence References 回查。 |
| `risk_notes` | Judge 形成的风险说明，不能写回 Evidence。 |
| `suggested_next_checks` | 后续核对建议，不等同于自动 SearchTask；是否补齐由 Orchestrator 决定。 |

Judge 若发现关键 Evidence 不足，应输出 `suggested_next_checks` 或 EvidenceGap 等结构化建议。Judge 不得直接调用 Search Agent，也不得把未入库搜索结果写入 Judgment。

Judge 返回 `EvidenceGap.suggested_search` 时，Orchestrator 拥有执行和恢复 workflow 的控制权：

- 校验 source allowlist、预算、重试上限和 workflow 状态。
- 将搜索意图转换为正式 `SearchTask`。
- 等 SearchResult 入 Evidence Store 后，重新选择 Evidence 并继续 Judge 或必要的 Debate 阶段。
- 如果补齐失败或预算耗尽，再将 workflow 标记为信息不足。

## 6. 事件

| event_type | payload |
| --- | --- |
| `agent.run_started` | `workflow_run_id`、`agent_id`、`round` |
| `agent.argument_saved` | `agent_argument_id`、`referenced_evidence_ids` |
| `agent.evidence_gap_found` | `workflow_run_id`、`gaps` |
| `round.summary_saved` | `round_summary_id`、`agent_argument_ids` |
| `judge.tool_called` | `tool_call_id`、`tool_name`、`result_ref` |
| `judge.completed` | `judgment_id`、`key_evidence_ids` |
