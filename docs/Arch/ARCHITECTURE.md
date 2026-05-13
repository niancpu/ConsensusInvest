# ConsensusInvest 架构总览

本文档是架构入口，只保留项目定位、模块地图、关键边界和运行模式。模块细节拆到同目录下的独立设计文档；接口字段、方法签名和错误码见 `docs/internal_contracts`。

## 1. 项目定位

ConsensusInvest 是面向 A 股投资研究的证据驱动系统。系统目标不是让单个 Agent 直接给结论，而是先构建可追踪 Evidence，再让不同 Agent 基于 Evidence 解释、复核、辩论，最后由 Judge 或报告模块输出可追溯结果。

当前市场范围以 A 股为主。`ticker`、信息源选择、回测时间约束、来源质量权重均按 A 股信息生态设计；未来扩展其他市场时，应从 Source/Search、Evidence 类型和权重表开始扩展，不能让 Report Module 或 Agent Swarm 自行绕过事实层。

## 2. 文档地图

| 文档 | 内容 |
| --- | --- |
| [principles.md](./principles.md) | Evidence First、可追踪、异步非阻塞、判断区原则。 |
| [runtime_modes.md](./runtime_modes.md) | 主 workflow、报告生成、异步补齐三种运行模式。 |
| [search_agent.md](./search_agent.md) | Search Agent Pool 的架构定位、状态归属和边界。 |
| [evidence_store.md](./evidence_store.md) | Raw/Evidence/Structure/Reference 的事实层设计。 |
| [agent_swarm.md](./agent_swarm.md) | Agent Swarm、Debate Runtime、Judge Runtime 的推理链路设计。 |
| [report_module.md](./report_module.md) | Report Module 的报告生成设计和补齐边界。 |
| [data_model.md](./data_model.md) | 主要数据对象和表归属。 |
| [mvp_roadmap.md](./mvp_roadmap.md) | MVP 阶段、非目标和后续扩展触发条件。 |

## 3. 总体模块图

```text
Search Agent Pool
  Tavily / Exa / AkShare / TuShare / future providers
        |
        | SearchResultPackage
        v
Evidence Store
  Raw Items / Evidence Items / Evidence Structures / References
        |
        +--------------------+
        |                    |
        v                    v
Agent Swarm / Judge      Report Module
  arguments / judgment     reports / report runs
        |                    |
        +----------+---------+
                   v
          Web API / Frontend Views
```

主 workflow 中存在两个横切层：

- `AgentRuntime`：通用运行层，只管理 Agent 类任务的生命周期、状态、事件、预算、错误和 trace。它不是通用业务 Agent 基类，不定义 Search、Debate、Judge 的输入输出语义。
- `EvidenceAcquisitionService`：Workflow Orchestrator 内部补齐服务，负责把 `EvidenceGap` / `suggested_search` 转换成 `SearchTask`，并调用 Search Agent Pool。它不生产 Raw/Evidence，也不允许推理 Agent 直接绕过它调用 provider。

## 4. 核心运行模式

| 模式 | 是否创建 `workflow_run_id` | 是否运行 Agent Swarm/Judge | 输出 |
| --- | --- | --- | --- |
| 主 workflow | 是 | 是 | `agent_arguments`、`round_summaries`、`judgment`、可下钻 Evidence/Raw。 |
| 报告生成 | 否 | 否 | `report_run_id`、报告视图、Evidence/Raw/MarketSnapshot 引用、限制说明。 |
| 异步补齐 | 可选 | 否 | SearchTask、入库后的 Raw/Evidence；由后续查询消费。 |

`workflow_run_id` 不是所有模块调用的全局必填字段。它只表示一次主分析 workflow。跨模块追踪默认使用 `correlation_id`；只有进入主链路分析时才创建 `workflow_run_id`。

## 5. 已定边界

- Search Agent 只发现、抓取和整理原始信息，返回 `SearchResultPackage`，不生产 Evidence，不输出投资判断。
- Search Agent 可以在同一 `SearchTask` 内做受约束的低判断区扩展，例如抓原文、翻页、跟随官方来源、同事件跨源核对；不能自主开启新的研究方向。
- Evidence Store 是事实层写入入口，负责 Raw、Evidence、Structure、Reference 的持久化和回查。
- Agent Swarm / Judge 只消费已入库 Evidence，不直接消费 Search Agent 原始结果。
- Agent Swarm / Judge 不能直接调用 Search Agent；只能输出 `EvidenceGap` 或 `suggested_search`，由 Orchestrator 决定是否补齐。
- Report Module 是报告生成模块，可以只读 Evidence Store 生成报告视图；缺数据时只能异步提交 SearchTask，不能自己抓 provider。
- Report Module 只负责编排、格式化、引用组织和限制说明，不负责解读、分析或生成投资建议。
- 主 workflow 的 Judgment 和报告视图不是同一种对象，不能用 `report_run_id` 冒充 `workflow_run_id`。
- `MarketSnapshot` 第一版由 Evidence Store 管理，但作为独立事实类型存在，不混成 `EvidenceItem`。

## 6. 高判断区

已定：

- 保持 Evidence First，避免 Agent 或 Report 直接基于未入库搜索结果形成系统结论。
- 主 workflow 和报告生成分离，避免客户只要报告时被迫运行完整推理链路。
- 搜索补齐异步非阻塞，避免页面请求被外部 provider 延迟拖死。
- 搜索补齐的决策权归 Orchestrator；推理 Agent 只能提出缺口，Search Agent 只能在任务约束内扩展采集。
- 通用 Agent 抽象只放在运行层，不把 Search、Debate、Judge 伪装成同一种业务接口。
- 推理链路引用关系和实体语义关系分表，避免关系模型变成无约束弱 schema。
- Evidence 不足时默认自动重试研究补齐；只有 Research/Search Agent 明确无法补齐时，才报告信息不足。
- Report Module 不产生解读、分析或投资建议字段，正式投资判断只属于 Judge Runtime。
- MarketSnapshot 由 Evidence Store 管理为独立事实类型。

未决：

- Search Task 第一版使用 SQLite 任务表还是独立任务队列。
- Report Module 的 `report_runs` 第一版是否持久化完整输入输出，还是只做视图缓存。

## 7. 协议入口

架构文档不定义字段级接口协议。对应文档见：

- `docs/internal_contracts`：内部模块间接口协议。
- `docs/web_api`：后端与前端通信协议。
- Report Module HTTP 视图接口由对外接口文档维护；架构文档只定义模块边界。
