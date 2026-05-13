# Migration And Cut Rules

本文档记录 `midterm-value-investor/fontWebUI` 旧接口接入本项目时的迁移、适配和裁切规则。

核心原则：旧模块必须适配当前主 API 定义，不能把旧项目的测试链路硬融合为本项目的新主链路。

## 迁移关系

| 旧接口 | 新协议处理 |
| --- | --- |
| `GET /api/v1/stocks/search` | 保留为 Report Module 正式视图接口；结果来自 Entity / Evidence Store / 已有股票索引。 |
| `GET /api/v1/stocks/{stockCode}/analysis` | 保留为个股研究聚合视图；不启动主工作流；不写主链路 Judgment。 |
| `GET /api/v1/stocks/{stockCode}/industry-details` | 保留为行业聚合视图；从 Entity Relations、Evidence、已有分析结果派生。 |
| `GET /api/v1/stocks/{stockCode}/event-impact-ranking` | 保留为事件影响排序视图；从 Evidence Structure / MarketSnapshot / 主链路 Trace 派生。 |
| `GET /api/v1/stocks/{stockCode}/benefits-risks` | 保留为利好风险视图；字符串数组升级为带引用 ID 的对象数组；无 `judgment_id` 时 `benefits` 为空。 |
| `GET /api/v1/market/index-overview` | 保留为市场看板视图；读取已有市场快照或触发刷新请求。 |
| `GET /api/v1/market/stocks` | 保留为市场股票列表视图；参数统一为 `page_size`。 |
| `GET /api/v1/market/concept-radar` | 保留为概念热度视图；不直接成为投资建议。 |
| `GET /api/v1/market/warnings` | 保留为市场预警视图；不自动写入 Judge 结论。 |
| `POST /api/v1/analysis/start` | 删除；这是旧项目测试 API，不作为兼容别名。 |
| `GET /api/v1/analysis/{run_id}/status` | 删除；这是旧项目测试 API，不作为兼容别名。 |
| `GET /api/v1/reports/{run_id}` | 删除；这是旧项目测试 API，不作为兼容别名。 |
| `GET /api/v1/reports/{run_id}/contradictions` | 删除；这是旧项目测试 API，不作为兼容别名。 |

## 删除旧 analysis/reports 的原因

旧 `analysis/*` 和 `reports/*` 与本项目 `workflow-runs + trace + judgment` 属于同一类能力。如果同时保留，会产生三类问题：

- 状态边界分裂：同一只股票可能同时存在 `run_id`、`workflow_run_id`、`report_id`，前端无法判断哪个是主状态。
- 推理链路断裂：旧报告接口倾向返回最终文本，不能稳定下钻到 Evidence、Agent Argument、Judge 依据。
- 长期演化冲突：后续异步任务、SSE 事件、证据引用、审计追踪都需要围绕主 workflow 模型演进。

因此旧测试接口直接裁切，不做迁移期别名。

## 适配要求

Report Module 接入时必须遵守：

- 搜索、行情、预警、聚合分析都先读取主系统已有数据。
- 数据不足时，只能请求主系统已有 Search Agent / 数据刷新能力异步补齐；Report Module 接口不能阻塞等待完整搜索完成。
- Search Agent 或行情刷新拿到的新事实必须进入 Raw Item / Evidence / Market Snapshot 等主系统数据层，Report Module 再读取结果。
- Report Module 只能做视图排序、摘录、模板填充和引用组织，不生成投资解读、分析结论、方向性判断或操作建议。
- Report Module 返回的字段必须带 `evidence_ids`、`market_snapshot_ids`、`entity_ids`、`workflow_run_id`、`judgment_id` 或 `report_run_id` 中至少一种可追踪引用。
- 报告视图 API 不保留独立运行 ID 字段，统一返回 `report_run_id`。
- `report_generation` 模式下 `workflow_run_id` 和 `judgment_id` 必须为空；后续升级完整分析必须新建 `workflow_run_id`。

前端注解：

- 新页面不要调用旧 `analysis/*` 和 `reports/*`。
- 旧页面如果还有这些调用，应直接改到 `docs/web_api` 的 `workflow-runs` 或本目录的 `stocks/*` 聚合视图。
- 如果 UI 只展示报告聚合结果，也要保留“查看依据”入口，否则会破坏金融 Agent 工具的透明性。
