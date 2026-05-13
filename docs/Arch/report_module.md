# Report Module 设计

Report Module 来源是待融合的 `midterm-value-investor/fontWebUI/api.md` 中的个股研究、市场看板、事件、风险等报告视图能力。旧目录名只代表迁移来源，不作为当前系统模块名。

它是报告生成模块，只负责编排、格式化、引用组织和限制说明；不是事实生产模块，也不是主 workflow 推理模块，不负责解读、分析或生成投资建议。

## 1. 两种报告路径

| 路径 | 输入 | 输出 | 是否有主 workflow |
| --- | --- | --- | --- |
| `with_workflow_trace` | Evidence、Judgment、Trace、MarketSnapshot | 带主判断链路的报告视图 | 是 |
| `report_generation` | Evidence、Structure、MarketSnapshot | 只有报告视图和引用 | 否 |

## 2. 报告生成模式

客户只想要报告时，不创建 `workflow_run_id`。

系统创建：

- `report_run_id`
- `report_mode=report_generation`
- `trace_refs.evidence_ids`
- `trace_refs.market_snapshot_ids`
- `limitations`

必须为空：

- `workflow_run_id`
- `judgment_id`

后果：

- 可以展示已有摘要、事实列表、风险事项、事件时间线和引用。
- 不能宣称已经完成主链路投资判断。
- 不能输出解读、分析或投资建议字段。
- 没有 Agent Swarm 论证链和 Judge 最终裁决。
- 后续升级完整分析时，应新建 workflow，但可以复用已有 Evidence。

ID 约束：

- 内部长期模型只使用 `report_run_id`。
- 报告视图 API 不保留独立运行 ID 字段，统一返回 `report_run_id`。

## 3. 数据读取

Report Module 默认读取：

- Evidence Store；
- Evidence Structure；
- Entity；
- MarketSnapshot；
- 主 workflow Trace；
- Judgment。

它不直接读取外部 provider，不保存 SearchResultPackage。

## 4. 异步补齐

当数据缺失或过期，并且 `refresh_policy` 允许时，Report Module 可以提交 SearchTask。

流程：

```text
Report Module detects missing data
  -> submit SearchTask
  -> return current view with data_state / refresh_task_id
  -> Search Agent ingests to Evidence Store
  -> later Report Module query reads new Evidence
```

边界：

- 不同步等待 Search 完成。
- 不直接调用 AkShare、TuShare、Tavily、Exa。
- 不把补齐结果存在 Report 私有事实库。

## 5. 报告视图生成

Report Module 可以做报告视图生成，例如：

- 选择报告模板；
- 按已有结构填充章节；
- 按时间、来源或预定义字段排列事件；
- 展示已有摘要、事实、风险事项和限制条件；
- 组织 Evidence、Judgment、Workflow、MarketSnapshot 引用。

这些输出只归 Report Module。Report Module 不能生成新的解释性文本、方向性归纳或分析结论；报告中的摘要必须来自 Evidence Structure，解释、风险判断或主链路结论必须来自 Agent/Judge 输出或已有 workflow，并保留 Evidence/Judgment/Workflow/MarketSnapshot 引用。报告生成模式下至少保留 Evidence 或 MarketSnapshot 引用。

如果这些引用需要持久化，Report Module 只能通过 Evidence Store 的引用接口写入 `source_type=report_view`，不能直接写 `evidence_references` 表。

Report Module 禁止输出解读、分析或投资建议字段。正式投资判断只属于 Judge Runtime。

## 6. 高判断区

已定：

- 报告视图不等于主链路 Judgment。
- 报告生成是一等路径，不是异常降级。
- Report Module 可以触发搜索补齐，但不能拥有事实生产权。
- Report Module 不负责解读、分析或投资建议字段。

未决：

- `report_runs` 是否持久化完整输入输出。
