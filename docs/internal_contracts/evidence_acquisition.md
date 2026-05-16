# Evidence Acquisition Service 接口协议

Evidence Acquisition Service 是 Workflow Orchestrator 内部的补齐服务。它负责把 `EvidenceGap` / `suggested_search` 转换成正式 `SearchTask`，并调用 Search Agent Pool。

它不是 Evidence Store，不生产 Raw/Evidence；也不是 Search Agent，不直接抓 provider。

Debate/Judge 暴露的是受控 `request_search` / `search_intent` 工具。该工具只表达搜索意图，不能直接调用 provider，也不能把 SearchResult 交回 Debate/Judge。所有 SearchResult 必须先经 SearchAgentPool 回调写入 Evidence Store；Orchestrator 再重新选择 Evidence 并决定继续 workflow 或进入信息不足状态。

## 1. request_gap_fill

```text
EvidenceAcquisitionService.request_gap_fill(envelope: InternalCallEnvelope, request: EvidenceGapFillRequest) -> AsyncTaskReceipt
```

请求：

```json
{
  "workflow_run_id": "wr_20260513_002594_000001",
  "gap": {
    "gap_type": "missing_financial_report",
    "description": "缺少 2026Q1 现金流数据。",
    "suggested_search": {
      "target_entity_ids": ["ent_company_002594"],
      "evidence_types": ["financial_report"],
      "lookback_days": 90,
      "keywords": ["002594 2026 一季报 现金流"]
    }
  },
  "target": {
    "ticker": "002594",
    "stock_code": "002594.SZ",
    "entity_id": "ent_company_002594",
    "keywords": ["比亚迪", "BYD"]
  },
  "policy": {
    "source_allowlist": ["tavily", "exa", "akshare", "tushare"],
    "max_retry_rounds": 2,
    "max_retry_per_gap_type": 1,
    "default_lookback_days": 30,
    "max_results": 50,
    "expansion_policy": {
      "allowed": true,
      "max_depth": 1,
      "allowed_actions": [
        "fetch_original_url",
        "follow_official_source",
        "provider_pagination",
        "same_event_cross_source"
      ]
    },
    "budget": {
      "max_provider_calls": 20,
      "max_runtime_ms": 60000
    }
  }
}
```

字段注解：

| 字段 | 说明 |
| --- | --- |
| `gap` | Agent Swarm / Judge 发现的证据缺口。 |
| `gap.suggested_search` | 搜索建议，不是 `SearchTask`；服务可以合并、降级或改写。 |
| `target` | Orchestrator 确认后的目标实体。 |
| `policy.source_allowlist` | 当前 workflow 允许使用的 source；不得被 `suggested_search` 覆盖。 |
| `policy.max_retry_rounds` | workflow 级补齐轮数上限。 |
| `policy.max_retry_per_gap_type` | 同一 `gap_type` 的补齐次数上限。 |
| `policy.expansion_policy` | 传递给 `SearchTask.constraints.expansion_policy` 的自主扩展约束。 |
| `policy.budget` | 传递给 `SearchTask.constraints.budget` 的资源预算。 |

内部行为：

1. 校验 `envelope.workflow_run_id`、`gap_type`、重试预算和 source allowlist。
2. 将 `EvidenceGap` / `suggested_search` 转换成 `SearchTask`。
3. 生成或复用 `idempotency_key`，避免同一缺口重复提交。
4. 调用 `SearchAgentPool.submit(envelope, SearchTask)`。
5. 返回 `AsyncTaskReceipt`；是否等待或轮询由 Orchestrator 决定。
6. SearchTask 完成后，SearchAgentPool 必须把 SearchResult 写入 Evidence Store，不能把未入库结果直接返回给 Debate/Judge。
7. Orchestrator 重新执行 evidence selection，并从上次中断的 Debate/Judge 控制点继续；补齐失败或预算耗尽时才标记信息不足。

## 2. build_search_task

```text
EvidenceAcquisitionService.build_search_task(envelope: InternalCallEnvelope, request: EvidenceGapFillRequest) -> SearchTask
```

该接口可作为纯函数能力在测试或 Orchestrator 内部使用。它只负责生成任务草案，不提交 Search Agent。

约束：

- 输出的 `SearchTask.callback.ingest_target` 必须是 `evidence_store`。
- 输出的 `SearchTask.callback.workflow_run_id` 必须来自 `envelope.workflow_run_id` 或请求中的 `workflow_run_id`。
- `scope.sources` 必须来自 `policy.source_allowlist`，不能来自 Agent 建议直接覆盖。
- `scope.evidence_types`、`scope.lookback_days`、`target.keywords` 可以吸收 `suggested_search`，但必须经过 Orchestrator 策略裁剪。

## 3. 边界

- Agent Swarm / Judge 不能直接调用本服务；调用方是 Workflow Orchestrator。
- 本服务不调用外部 provider。
- 本服务不保存 Raw/Evidence。
- 本服务不改变 EvidenceGap 的业务含义，只把可执行的补齐请求变成受约束的 `SearchTask`。
- 本服务不能接受 Agent 指定的 provider 私有参数，也不能让 `suggested_search` 覆盖 workflow source allowlist。
- 本服务不能把 SearchResultPackage 或 provider 原始响应返回给 Debate/Judge；它只能通过 SearchAgentPool 与 Evidence Store 完成入库链路。
- 如果预算耗尽或缺口不可补齐，应返回失败的内部错误对象或不可补齐原因，由 Orchestrator 决定 workflow 是否进入信息不足状态。
