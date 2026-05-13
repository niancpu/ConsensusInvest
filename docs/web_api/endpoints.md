# ConsensusInvest API Endpoints

本文档是 API 文档索引。详细协议已按资源拆分，避免单文件过长。

## 阅读顺序

1. [API Overview](./overview.md)：协议总则、响应外壳、通用 ID。
2. [Workflow API](./workflow.md)：异步分析任务、SSE 事件流、快照和 trace。
3. [Evidence API](./evidence.md)：Raw Item、Evidence、Evidence Structure、Evidence References。
4. [Agent And Judgment API](./agents_judgments.md)：Agent Run、Agent Argument、Round Summary、Judgment、Judge Tool Calls。
5. [Entity API](./entities.md)：实体、实体关联 Evidence、实体关系。
6. [API Appendix](./appendix.md)：Workflow Config、错误码、状态枚举、MVP 取舍与未决项。

报告视图接口单独放在 [Report Module API](../report_module/endpoints.md)，包括 `stocks/*`、`market/*` 的视图接口，以及旧 `analysis/*`、`reports/*` 测试接口的删除规则。

## 核心边界

- 真正的 Agent 金融分析主流程统一走 `POST /api/v1/workflow-runs`。
- 实时运行过程统一走 `GET /api/v1/workflow-runs/{workflow_run_id}/events` SSE。
- 最终判断必须能通过 `trace`、`references`、`evidence`、`raw-items` 回溯。
- `docs/web_api` 只记录本项目和前端通信的核心协议，不承载被融合模块的完整接口清单。
- `stocks/*`、`market/*` 的报告视图适配规则放在 `docs/report_module`。
- 旧 `analysis/*`、`reports/*` 是被融合模块的测试接口，主协议不提供兼容别名。
