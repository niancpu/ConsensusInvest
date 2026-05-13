# 模块间接口协议

本文档定义后端内部模块之间的接口契约：方法签名、请求/响应 DTO、异步任务、事件、错误和幂等规则。

这里的“接口”是模块边界，不是 HTTP endpoint，也不要求跨进程调用。MVP 默认按同进程 Port/Adapter 实现；只有出现独立部署、独立扩缩容或跨语言调用需求时，才在 Adapter 层增加 HTTP/gRPC/MQ 实现。

模块为什么这样拆、事实层为什么归 Evidence Store 等架构判断，见 `docs/Arch/ARCHITECTURE.md`，这里不重复展开。

## 文档边界

- `docs/internal_contracts`：主程序内部模块间接口协议。
- `docs/web_api`：后端和前端的 HTTP/SSE 协议。
- `docs/zc_module`：Report/ZC 模块对外视图接口和兼容说明。

## 文件列表

1. [common_protocol.md](./common_protocol.md)：通用调用信封、返回包装、异步任务、事件、错误对象、幂等规则。
2. [search_agent.md](./search_agent.md)：Search Agent Pool 的任务提交、状态查询、结果包接口。
3. [evidence_store.md](./evidence_store.md)：SearchResultPackage 入库、Evidence 查询、Raw 回查、引用写入接口。
4. [agent_swarm.md](./agent_swarm.md)：Agent Swarm / Judge Runtime 的运行输入、论证输出、证据缺口返回接口。
5. [report_module.md](./report_module.md)：Report/ZC 模块读取主数据、构建聚合视图、触发异步补齐的内部接口。

## 接口表达约定

接口签名统一写成：

```text
ModulePort.method(envelope: InternalCallEnvelope, request: RequestDto) -> ResultDto
```

约定：

- `ModulePort` 表示被依赖模块暴露给其他模块的接口，不等同于具体 class。
- `InternalCallEnvelope` 承载追踪、业务分析时间、调用来源和幂等键。
- DTO 名称用于约束字段和语义，具体语言实现可以是 dataclass、Pydantic model、TypeScript type 或其他等价结构。
- 返回值只表达接口契约，不规定持久化表结构。
- 同步/异步表示业务语义，不表示线程模型；异步接口只返回任务接收结果。

## 内部接口清单

| 调用方 | 被调用方 | 方法 | 同步/异步 | 说明 |
| --- | --- | --- | --- | --- |
| Workflow Orchestrator | Search Agent Pool | `submit(SearchTask)` | 异步 | 创建搜索/刷新任务，立即返回 `SearchTaskReceipt`。 |
| Workflow Orchestrator | Search Agent Pool | `get_status(task_id)` | 同步 | 查询搜索任务状态和已入库数量。 |
| Search Agent Worker | Evidence Store | `ingest_search_result(SearchResultPackage)` | 同步提交，可批量 | 提交原始信息包；Store 返回 Raw/Evidence 写入结果。 |
| Workflow Orchestrator | Evidence Store | `query_evidence(EvidenceQuery)` | 同步 | 选择主链路要消费的 Evidence。 |
| Agent Swarm | Evidence Store | `get_evidence(evidence_id)` / `get_raw(raw_ref)` | 同步 | Agent/Judge 回查证据和原始材料。 |
| Agent Swarm | Evidence Store | `save_references(EvidenceReferenceBatch)` | 同步 | 保存 Agent 论点、Round Summary、Judgment 对 Evidence 的引用关系。 |
| Workflow Orchestrator | Agent Swarm | `run(AgentSwarmInput)` | 异步或长任务 | 启动主链路 Agent 论证。 |
| Workflow Orchestrator | Judge Runtime | `run(JudgeInput)` | 异步或长任务 | 生成最终判断并记录回查过程。 |
| Report/ZC Module | Evidence Store | `query_evidence` / `get_evidence` / `get_raw` | 同步 | 构建页面聚合视图时读取已入库数据。 |
| Report/ZC Module | Main Runtime Query | `get_workflow_trace(workflow_run_id)` | 同步 | 读取主链路 Trace、Agent Argument、Judgment。 |
| Report/ZC Module | Search Agent Pool | `submit(SearchTask)` | 异步 | 数据缺失或过期时触发补齐，不阻塞当前页面响应。 |

## 统一约定

- 所有内部请求必须带 `InternalCallEnvelope`；字段见 [common_protocol.md](./common_protocol.md)。
- 异步调用只返回任务接收结果，不等待全链路完成。
- Search Agent 返回的是 `SearchResultPackage`，包含原信息、URL、发布时间、来源、正文/摘要、raw payload 等；它不是 Evidence。
- Evidence Store 入库后才会产生 `raw_ref`、`evidence_id`、质量标记和引用关系。
- Agent Swarm、Judge Runtime、Report/ZC 模块只能引用 `evidence_id` / `raw_ref`，不能直接引用 Search Agent 的未入库结果。
- 协议示例里的 ID 格式是约定样例，不要求实现完全照抄，但必须保持全局可追踪、可日志检索。

## 实现边界

- 当前实现优先使用同进程接口调用，避免为了模块化强行 HTTP 化。
- Orchestrator 只依赖各模块 Port，不直接访问其他模块内部表或私有方法。
- Adapter 可以替换，但不能改变本目录定义的请求/响应语义。
- 网络化、消息队列化、独立服务化属于部署边界调整；需要另写架构设计，不在本接口协议中默认决定。
