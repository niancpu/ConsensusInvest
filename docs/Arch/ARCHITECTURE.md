# ConsensusInvest 架构设计

## 1. 项目定位

ConsensusInvest 是一个“证据驱动”的投资研究框架。

它的核心目标不是做一个固定的“选股 Agent”，而是构建一套可以完成以下工作的系统：

- 从多个信息源采集原始市场信息；
- 将原始信息统一整理为可追踪的 Evidence；
- 对每条 Evidence 的来源质量、相关性、时效性和客观内容进行结构化整理；
- 让可插拔 Agent 从不同角度解释这些 Evidence；
- 基于明确引用的 Evidence 进行多轮辩论或复核；
- 最后由 Judge Agent 结合 Evidence、辩论历史和系统提示词生成最终判断。

本项目定位为面向 A 股的投资研究框架。Source Connector、Evidence 类型、信息源权重和回测约束均以 A 股市场为前提设计：Evidence schema 使用 `ticker` 标识股票代码，信息源选型聚焦 AkShare / TuShare / 主流财经媒体，来源权重默认值反映 A 股信息生态。架构在 Agent 接口和 Evidence 模型上保持抽象，便于未来在 Connector 层和权重表上做增量扩展，但其他市场不在当前路线图中。

## 2. 项目名称

当前项目名：`ConsensusInvest`

含义：

- `Consensus`：最终判断来自多源证据和多个 Agent 的讨论，而不是单个模型的一次性回答。
- `Invest`：项目领域是投资研究和决策支持。

曾考虑过的备选名：

- `AlphaEvidence`
- `EvidenceAlpha`
- `AlphaDebate`
- `AlphaJury`
- `MarketEvidence`

如果项目重点是多 Agent 形成共识和最终裁决，`ConsensusInvest` 合适。  
如果后续更偏向“证据平台”，`AlphaEvidence` 也可以作为备选。

## 3. 设计原则

### 3.1 Evidence First

Agent 不应该直接基于大量非结构化原始文本推理。只要能先构建结构化证据层，就应该先把原始信息转成 Evidence。

所有原始数据在进入解释、辩论、裁决之前，都应先转成 Evidence 对象。

### 3.2 Agent 与项目解耦

Agent 必须和项目工作流解耦。

核心运行时不应把 `bull_agent`、`bear_agent`、`technical_agent` 写死成特殊逻辑。每个 Agent 都应遵守统一接口，并通过配置加载。

这样后续可以做到：

- 把多头 Agent 替换成技术专家 Agent；
- 增加基本面专家；
- 增加政策专家；
- 移除辩论，只运行单 Agent 复核；
- 修改 Judge Prompt，而不用改证据采集逻辑。

### 3.3 可追踪推理

Agent 做出的每个重要判断，都必须引用一个或多个 Evidence ID。

最终结果应能追踪：

- 哪个信息源产生了这条 Evidence；
- 哪些 Evidence 影响了每个 Agent；
- 每轮辩论引用了哪些 Evidence；
- 哪些 Evidence 对最终判断影响最大。

### 3.4 工作流可配置

工作流应由配置定义，而不是写死在代码路径里。

示例：

```yaml
workflow:
  collectors:
    - akshare
    - tushare
    - tavily
    - exa
  evidence_processors:
    - evidence_structurer_v1
  debate_agents:
    - bull_v1
  judge:
    - judge_v1
  debate_rounds: 3
```

MVP 阶段可以只实现一个辩论侧 Agent，例如 `bull_v1`，但运行时设计必须允许后续继续加入其他 Agent。

## 4. 总体架构

```text
Source Connectors
  Exa / Tavily / AkShare / TuShare
        |
        v
Raw Information Store
        |
        v
Evidence Normalizer
        |
        v
Evidence Store
        |
        v
Evidence Structuring Agent
        |
        v
Perspective Agents
  MVP: 只实现 Bull Agent
  后续: Bear / Technical / Fundamental / Policy / Risk Agents
        |
        v
Debate Runtime
        |
        v
Round Summary Agent
        |
        v
Judge Agent
  可通过引用关系回查 Evidence Store / Raw Information Store
        |
        v
Final Investment Judgment
```

## 5. 核心模块

### 5.1 Source Connectors

Source Connector 负责从外部供应商抓取原始信息。

第一阶段计划支持：

- `AkShare`：A 股行情、财务指标、东方财富新闻、宏观和市场数据；
- `TuShare`：A 股结构化数据、公司基础信息、财务数据、公告、指数数据；
- `Tavily`：网页搜索、新闻搜索、页面正文抽取，适合 Agent 检索；
- `Exa`：语义搜索、深度网页发现、行业文章、长文上下文。

Connector 只负责采集和轻量解析，不负责投资判断。

Connector 输出示例：

```json
{
  "source": "tavily",
  "source_type": "web_news",
  "ticker": "000001",
  "title": "...",
  "content": "...",
  "url": "...",
  "publish_time": "2026-05-13 09:30:00",
  "fetched_at": "2026-05-13 10:00:00",
  "raw": {}
}
```

### 5.2 Raw Information Store

Raw Information Store 保存外部信息源返回的原始数据。

要求：

- 保留原始 payload；
- 支持按信息源调试；
- 避免在归一化过程中丢失信息；
- 支持后续回测和审计复盘。

### 5.3 Evidence Normalizer

Evidence Normalizer 把原始信息转换成统一的 Evidence 结构。

职责：

- 字段归一化；
- 相似信息去重；
- 解析并校验发布时间；
- 分类信息类型；
- 标记来源元数据；
- 剔除或标记低质量记录。

信息类型可以包括：

- `price`
- `volume`
- `financial_report`
- `announcement`
- `regulatory_event`
- `company_news`
- `industry_news`
- `macro_news`
- `analyst_report`
- `social_signal`

### 5.4 Evidence Store

Evidence Store 保存结构化 Evidence，并支持按以下条件检索：

- 股票代码；
- 日期范围；
- 信息源；
- Evidence 类型；
- 来源质量；
- 相关性；
- 被哪一轮辩论引用。

Evidence Store 是系统中心。

MVP 阶段使用 SQLite 作为本地 Evidence Store。表分为数据主体和两类关联表。

数据主体表：

- `raw_items`：保存外部信息源返回的原始 payload；
- `evidence_items`：保存归一化后的 Evidence 主体字段；
- `evidence_structures`：保存客观摘要、关键事实、claims、质量标记；
- `workflow_runs`：保存一次分析任务的股票代码、分析时间、查询参数和运行配置；
- `agent_runs`：保存每个 Agent 的运行记录；
- `agent_arguments`：保存辩论者 Agent 每轮输出；
- `judgments`：保存最终判断。

推理链路关联（结构化、闭集合、查询模板固定）：

- `evidence_references`：保存 Agent / Round Summary / Judge 对 Evidence 的引用关系。字段建议包含 `source_type`（agent_argument / round_summary / judgment）、`source_id`、`evidence_id`、`reference_role`（supports / counters / cited / refuted）、`round`。前端"从最终判断逐层下钻到原始记录"的所有反查都走这张表。

实体语义关联（开放集合、跨 workflow_run 共享、需要多跳遍历）：

- `entities`：保存公司、行业、政策、事件等实体；
- `evidence_entities`：保存 Evidence 与实体的多对多关系；
- `entity_relations`：保存实体之间的关系（属于行业、上下游、同业、同一政策影响等）。

这两类关联表不能合并到同一张表。推理链路的边在一次 workflow_run 内闭合、语义固定；实体关联的边跨 run 共享、语义开放、关系类型会持续增加。混在一张表会退化为"什么边都能放"的弱 schema，丢失约束和索引价值。

MVP 数据量级下，实体关联的多跳查询用 SQLite 递归 CTE 可以胜任。下列任一条件触发时，再评估迁移到 Postgres + AGE 或专用图数据库：

- 实体跨多次 workflow_run 累积到 10 万级以上；
- 关系类型超过十几种、需要按权重做路径排序；
- 前端要做"自由探索式关系图谱"这种 4-5 跳实时可视化。

SQLite 是 MVP 的工程选择，不是长期架构锁定。后续如果出现多人并发、服务化部署、复杂全文检索或跨资产大规模回测，再评估迁移到 Postgres 或专用检索组件。

Evidence Store 是系统中心，含义不是所有模块都只读 Evidence 摘要，而是系统保留从 Agent 输出、Round Summary、Judge 结论回溯到 Evidence，并继续回溯到 Raw Information Store 的能力。Summary 用于降低上下文读取成本，但不应切断证据链。

## 6. Evidence 模型

建议结构：

```json
{
  "id": "ev_20260513_000001_tushare_001",
  "ticker": "000001",
  "source": "tushare",
  "source_type": "announcement",
  "evidence_type": "company_announcement",
  "title": "...",
  "content": "...",
  "url": "...",
  "publish_time": "2026-05-13 09:30:00",
  "fetched_at": "2026-05-13 10:00:00",
  "entities": ["平安银行"],
  "tags": ["业绩", "银行", "公告"],
  "objective_summary": "平安银行发布 2026 年一季度报告，营业收入、归母净利润、不良贷款率等关键指标如下...",
  "key_facts": [
    {
      "name": "归母净利润",
      "value": "...",
      "unit": "亿元",
      "period": "2026Q1"
    }
  ],
  "claims": [
    {
      "claim": "公司一季度归母净利润同比增长...",
      "evidence_span": "...",
      "claim_type": "reported_fact"
    }
  ],
  "source_quality": 0.9,
  "relevance": 0.86,
  "freshness": 0.95,
  "structuring_confidence": 0.81,
  "quality_notes": ["公告来源可信，但部分指标需要与历史口径核对"],
  "raw_ref": "raw_20260513_000001_tushare_001"
}
```

字段说明：

- `source_quality`：来源身份、采集方式和内容完整性的综合质量评分；
- `relevance`：这条 Evidence 和目标股票的相关程度；
- `freshness`：对当前分析日期来说是否足够新；
- `objective_summary`：对原始记录的客观摘要，不包含投资立场；
- `key_facts`：可被辩论者消费的事实、指标、时间周期和单位；
- `claims`：从原文抽取出的可引用陈述，并保留对应原文片段；
- `structuring_confidence`：对本次结构化抽取是否准确的置信度。

Evidence 模型不保存 `bull_impact`、`bear_impact`、`net_impact` 这类立场解释字段。  
这些字段属于 Bull、Bear、Technical、Fundamental 等辩论者 Agent 的输出，而不是原始证据层的属性。

更严格地说，事实提取层只描述“原始记录说了什么、质量如何、和目标对象是否相关”。它不负责判断事件的市场含义。即使在 Agent 层，`bull_impact`、`bear_impact`、`net_impact` 也不应成为所有 Agent 的通用字段，只能出现在明确承担对应立场解释职责的 Agent 输出里。例如 `bull_v1` 可以输出 `bullish_impact_assessment`，`bear_v1` 可以输出 `bearish_impact_assessment`，但 `round_summary_v1`、`news_verifier_v1`、`evidence_structurer_v1` 不应输出这类方向性字段。

## 7. Evidence Structuring Agent

Evidence Structuring Agent 接收归一化后的 Evidence，并把原始记录整理成辩论者可消费的客观结构。

它负责做：

- 生成客观摘要；
- 抽取关键事实、指标、实体、时间周期和单位；
- 抽取原文中的明确 claim，并保留引用片段；
- 标记来源质量、相关性、时效性和结构化置信度；
- 标记信息缺口、口径不一致、疑似重复或低质量内容。

它不负责做：

- 判断这条 Evidence 是利多还是利空；
- 给出 `bull_impact`、`bear_impact` 或 `net_impact`；
- 替 Bull / Bear / Technical / Fundamental Agent 解释投资含义；
- 生成最终投资结论。

输出示例：

```json
{
  "evidence_id": "ev_001",
  "objective_summary": "公司发布一季度报告，披露收入、利润、资产质量等指标变化。",
  "key_facts": [
    {
      "name": "归母净利润",
      "value": "...",
      "unit": "亿元",
      "period": "2026Q1"
    }
  ],
  "claims": [
    {
      "claim": "归母净利润同比增长...",
      "evidence_span": "...",
      "claim_type": "reported_fact"
    }
  ],
  "source_quality": 0.9,
  "relevance": 0.86,
  "freshness": 0.95,
  "structuring_confidence": 0.82,
  "quality_notes": ["部分指标需与历史口径核对"]
}
```

这个 Agent 是数据处理层，不是解释层。它只负责为后续辩论者 Agent 准备可引用、可复核、可消费的证据结构。

重要规则：

低置信度或低质量 Evidence 不应被隐藏，而应明确标记问题原因。

## 8. Agent Runtime

### 8.1 统一 Agent 接口

所有 Agent 应使用统一接口。

概念示例：

```python
class Agent:
    id: str
    role: str
    capabilities: list[str]

    def run(self, context, evidence, history):
        ...
```

所有 Agent 输出应保留统一的可追踪外壳：

```json
{
  "agent_id": "bull_v1",
  "role": "bullish_interpreter",
  "round": 1,
  "referenced_evidence_ids": ["ev_001", "ev_008"],
  "argument": "...",
  "confidence": 0.81,
  "counter_evidence_ids": ["ev_003"],
  "limitations": ["..."]
}
```

立场解释和影响强度属于具体 Agent 的 `role_output`，不属于通用 Agent 接口：

```json
{
  "agent_id": "bull_v1",
  "role": "bullish_interpreter",
  "round": 1,
  "referenced_evidence_ids": ["ev_001", "ev_008"],
  "argument": "...",
  "confidence": 0.81,
  "counter_evidence_ids": ["ev_003"],
  "limitations": ["..."],
  "role_output": {
    "stance_interpretation": "从多头视角看，ev_001 和 ev_008 支持盈利改善 thesis。",
    "bullish_impact_assessment": 0.72
  }
}
```

不同 Agent 可以有不同 `role_output` schema。核心运行时只要求引用 Evidence、记录论点、保存置信度和限制条件，不解释字段含义。

### 8.2 MVP Agent 集合

MVP 阶段只实现：

- `evidence_structurer_v1`
- `bull_v1`
- `round_summary_v1`
- `judge_v1`

这样可以在保持系统较小的同时，验证 Evidence 驱动工作流是否成立。

### 8.3 后续 Agent 集合

后续可以增加：

- `bear_v1`：关注下行风险和负面证据；
- `technical_expert_v1`：关注价格行为、趋势、成交量、波动率；
- `fundamental_expert_v1`：关注财务质量和估值；
- `policy_expert_v1`：关注监管和政策影响；
- `risk_expert_v1`：关注回撤、流动性、仓位控制；
- `news_verifier_v1`：检查来源冲突和重复报道。

这些 Agent 应通过配置添加，而不是重写工作流核心。

### 8.4 Prompt 管理

MVP 阶段，Agent 的 System Prompt 与 Agent 代码同包维护，不引入独立 Prompt 存储或运行时加载。Agent 标识中的 `v1` 后缀同时指代代码版本和 Prompt 版本，二者一并演进。后续如出现频繁调整 Prompt 不希望发版、或需要 A/B 比较多版 Prompt 的需求，再评估是否独立 Prompt 仓库。

## 9. Debate 设计

### 9.1 MVP Debate

由于第一版只实现多头 Agent，MVP 的辩论可以先做成单边证据复核：

```text
第 1 轮：
  Bull Agent 选择最强利多 Evidence，并解释上涨逻辑。

第 2 轮：
  Bull Agent 从结构化 Evidence 中主动审视可能削弱多头 thesis 的事实和缺口。

第 3 轮：
  Bull Agent 根据混合证据更新看多置信度。

Judge：
  总结多头 thesis 是否足够强。
```

即使没有 Bear Agent，每轮也必须引用 Evidence ID。

### 9.2 完整多 Agent Debate

后续完整辩论可以是：

```text
第 1 轮：
  Bull 展示最强利多证据。
  Bear 展示最强利空证据。

第 2 轮：
  Bull 基于证据反驳 Bear。
  Bear 基于证据反驳 Bull。

第 3 轮：
  技术专家或基本面专家评论双方有争议的论点。

Round Summary Agent：
  总结每轮辩论并记录引用的 Evidence。
  Summary 是给 Judge 快速获取上下文的导航层，不是新的事实来源。

Judge Agent：
  根据 Evidence、辩论历史和系统提示词生成最终判断。
```

辩论规则：

没有 Evidence 引用的论点，应被视为低置信度论点。

Round Summary 不应吞掉分歧细节。每条 summary item 至少要保留：

- 对应 round；
- 参与 Agent；
- 关键论点；
- 被引用的 Evidence ID；
- 被反驳或存在争议的 Evidence ID；
- 可回查的 agent_argument_id。

Judge 可以优先读取 Round Summary。系统应提供通过 `agent_argument_id` 和 `evidence_id` 回查 Agent 输出、结构化 Evidence 和原始记录的工具；是否调用由 Judge Prompt 控制，主要用于关键分歧点、证据含义不清或上下文不足的情况。

## 10. Judge Agent

Judge Agent 不应把所有原始信息一次性塞进上下文。系统应提供回查原始数据和 Evidence 的工具，允许 Judge 在需要核对关键事实时选择性调用。

输入应包括：

- Top 结构化 Evidence；
- Evidence Structuring Agent 生成的客观摘要、关键事实和质量标记；
- 辩论者 Agent 对 Evidence 的立场解释和影响判断；
- Debate 历史；
- 每轮 Summary；
- Evidence / Raw 回查工具或等价检索接口；
- 最终系统提示词；
- 如有需要，也可以加入组合和风控上下文。

输出示例：

```json
{
  "final_signal": "bullish",
  "confidence": 0.74,
  "time_horizon": "short_to_mid_term",
  "key_positive_evidence_ids": ["ev_001", "ev_006"],
  "key_negative_evidence_ids": ["ev_003"],
  "reasoning": "...",
  "risk_notes": ["..."],
  "suggested_next_checks": ["..."]
}
```

最终判断应来自：

```text
系统提示词
+ Evidence 摘要
+ 多轮辩论 transcript
+ 每轮 summary
+ 可选回查到的结构化 Evidence 和原始记录
```

约束：

- Judge 默认消费 Round Summary、关键 Evidence 摘要和辩论 transcript；
- 当关键论点存在冲突、summary 过度压缩或 Evidence 质量较低时，Judge 可以通过工具回查原始 Evidence；
- Judge 对最终判断引用的关键证据，必须保存 Evidence ID；
- 如果最终判断依赖原始文本中的细节，应额外保存 raw_ref 或原文片段引用。

## 11. 信息源权重

建议默认来源可信度：

```text
交易所公告 / 公司公告：0.95
TuShare 结构化财务数据：0.90
AkShare 结构化行情 / 财务数据：0.80
主流财经媒体：0.70
Tavily 抽取网页正文：0.65
Exa 语义搜索结果：0.60
仅搜索摘要：0.30
未知来源 / 自媒体：0.20
```

这些只是默认值。Evidence Structuring Agent 可以根据具体来源身份、采集方式和内容质量调整来源质量评分。

## 12. 回测安全

回测时，所有 Evidence 必须满足：

```text
publish_time <= analysis_time
fetched_at 可以晚于 analysis_time，但 publish_time 必须在历史上有效
```

任何 Agent 都不应使用 `datetime.now()` 判断历史窗口。

每次 workflow run 应保存：

- 股票代码；
- 分析时间；
- 信息源查询参数；
- Evidence ID 列表；
- Agent 输出；
- 最终判断。

## 13. 运行入口

### 13.1 触发与执行

一次分析任务由前端页面调用后端 API 触发。后端职责：

- 接收请求载荷：股票代码、分析时间、所用 workflow 配置 ID；
- 创建 `workflow_runs` 记录并分配 `workflow_run_id`；
- 异步执行 Source Connectors → Evidence Normalizer → Evidence Structuring Agent → Debate Runtime → Judge Agent 流水线；
- 通过流式接口持续推送各阶段结果，并提供按 `workflow_run_id` 的查询接口供前端补拉历史和明细。

### 13.2 前端返回原则

本系统是集成 Agent 的金融研究工具，用户对结论的信任度直接依赖可解释性。后端返回设计遵循以下原则：

- **透明可追溯**：返回内容应充分暴露推理路径——每个 Agent 引用的 Evidence ID、客观摘要、关键事实、置信度、限制条件、被反驳证据都应包含在响应中，使用户可以从最终判断逐层回溯到原始记录。
- **流式注入**：Source Connector 的抓取进度、新归一化的 Evidence、Structuring Agent 的结构化输出、Agent 的逐段论证、Round Summary、Judge 的推理过程应以流式方式持续推送，而不是等全流程结束后一次性返回。每个阶段产生新内容即刻下发。
- **链式思考透明化**：Agent 的中间论证、对反向证据的主动审视、置信度的调整过程作为独立片段返回，而不是只暴露最终结论。Judge Agent 调用工具回查 Evidence / Raw 的过程也应可见，包括调用了哪些工具、回查了哪些记录、如何影响最终判断。
- **可溯源的交互**：前端可基于 `evidence_id`、`agent_argument_id`、`raw_ref`、`workflow_run_id` 在任意层级反查——客观摘要可下钻到原始 payload，最终判断可回溯到引用的 Evidence、辩论 transcript 和具体论证。
- **默认全量、按需裁剪**：前端尚未定型，后端默认返回各阶段尽可能完整的结构化内容（包括质量标记、置信度、限制条件、被反驳证据等"次要"字段）。后续如出现带宽、延迟或成本压力，再讨论裁剪和分页策略。

具体协议形态（HTTP + SSE / WebSocket / JSON Lines 等）、字段命名、版本协商、鉴权、错误码、任务队列、流量控制属于接口工程实现，由接口文档单独定义。

## 14. 当前 MVP 路线

### Phase 1：架构骨架

- 定义 Evidence schema；
- 定义 Agent interface；
- 定义 workflow config；
- 创建本地 Evidence Store；
- 优先实现 AkShare connector。

### Phase 2：Evidence 结构化

- 实现 Evidence Normalizer；
- 实现 Evidence Structuring Agent；
- 保存客观摘要、关键事实、claim、来源质量、相关性、时效性和结构化置信度；
- 展示所有 Evidence 及其客观结构化结果。

### Phase 3：多头单边推理

- 实现 `bull_v1`；
- 由 `bull_v1` 基于结构化 Evidence 选择最能支持多头 thesis 的证据；
- 在 `bull_v1` 输出中保存多头解释、影响判断和置信度；
- 生成引用 Evidence 的多头 thesis；
- 加入对反向事实、缺口和不确定性的审视。

### Phase 4：Judge Agent

- 实现 Round Summary Agent；
- 实现 Judge Agent；
- 最终输出使用系统提示词、每轮 Summary 和辩论 transcript。

### Phase 5：多源扩展

- 增加 TuShare；
- 增加 Tavily；
- 增加 Exa；
- 增加去重和来源冲突处理。

### Phase 6：完整辩论

- 增加 Bear Agent；
- 增加 Technical Expert Agent；
- 增加多轮 Debate Runtime；
- 增加每轮引用 Evidence 展示。

## 15. MVP 非目标

MVP 阶段不做：

- 自动实盘交易；
- 组合执行；
- 复杂前端大屏；
- 高频信号；
- 完美信息源覆盖；
- 一开始就实现完整多空专家辩论。

第一目标是验证：Evidence 能否被采集、结构化、引用，并被可替换 Agent 从不同立场解释。

## 16. 文档范围

本架构文档定义证据驱动工作流的概念结构、Agent 角色边界、Evidence 模型和运行时约束。下列内容属于实现层规范或服务层工程设计，由相应规范单独定义，不在本文档展开：

- LLM Provider 抽象、模型分配、token 预算、重试与降级策略；
- Agent 输出 JSON 的解析、Schema 校验和容错处理；
- Judge Agent 工具回查的 Tool Use 接口实现；
- 前端调用接口的具体协议形态、字段命名、鉴权、错误码、任务队列、流量控制；
- API key 与 secrets 的加载和管理；
- 数据库迁移、Schema 演进和备份恢复；
- 日志、追踪、metrics 等可观测性方案。


