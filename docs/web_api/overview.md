# API Overview

本文档定义 API 总原则、协议形态、通用响应和通用 ID。

## 1. 文档定位

本文档定义后端暴露给前端的 API 协议。它不是前端页面接口清单，也不是只覆盖首屏需要的最小接口。

后端接口设计原则：

- 后端已有的核心资源应尽量提供查询入口，前端按需消费；
- 一次分析任务必须异步非阻塞执行；
- 运行过程必须可流式展示；
- 最终判断必须能回溯到 Agent 论证、Evidence、Evidence Structure 和 Raw Item；
- 低质量、低置信度或存在冲突的信息不隐藏，而是以结构化字段暴露；
- Evidence 层只保存客观事实和质量标记，不保存 Bull / Bear 等立场解释；
- Agent / Judge 输出必须保留 Evidence 引用，不能只返回无法审计的自然语言结论。

前端注解：

- 前端不需要一次性接入所有接口，但不要把 API 理解成“只为某个页面服务”。
- 推荐前端先接入 `workflow-runs`、`events`、`snapshot`、`trace`、`evidence`、`judgment`。
- 被融合模块的 `stocks/*`、`market/*` 适配规则放在 `docs/zc_module`。
- `docs/web_api` 里的核心链路优先级高于被融合模块的聚合视图；透明推理链路仍以 `workflow-runs`、`trace`、`evidence`、`judgment` 为准。
- 旧 `analysis/*`、`reports/*` 是被融合模块的测试 API，不在主协议中保留。


## 2. 协议形态

MVP 默认使用：

- `HTTP JSON`：创建任务、查询状态、查询资源详情、补拉历史；
- `SSE`：订阅单个 workflow run 的实时运行事件。

暂不默认使用 WebSocket。

取舍说明：

- 当前系统主要是后端向前端持续推送执行过程，SSE 已满足异步非阻塞和透明链路展示；
- WebSocket 适合后续需要双向实时控制、多人协作、在线暂停/恢复任务时再引入；
- SSE 断线后，前端用 `Last-Event-ID` 或 `after_sequence` 补拉事件，并用 `snapshot` 恢复完整状态。


## 3. 通用约定

### 3.1 Base URL

```text
/api/v1
```

### 3.2 时间格式

所有 API 返回时间统一使用 ISO 8601，带时区。

```text
2026-05-13T10:00:00+08:00
```

如果是回测场景，`analysis_time` 是业务时间，不等于服务器当前时间。

### 3.3 通用响应外壳

成功响应：

```json
{
  "data": {},
  "meta": {
    "request_id": "req_20260513_000001"
  }
}
```

列表响应：

```json
{
  "data": [],
  "pagination": {
    "limit": 50,
    "offset": 0,
    "total": 128,
    "has_more": true
  },
  "meta": {
    "request_id": "req_20260513_000002"
  }
}
```

错误响应：

```json
{
  "error": {
    "code": "EVIDENCE_NOT_FOUND",
    "message": "Evidence not found.",
    "details": {
      "evidence_id": "ev_20260513_000001_tushare_001"
    }
  },
  "meta": {
    "request_id": "req_20260513_000003"
  }
}
```

前端注解：

- `message` 可以直接用于开发态提示，但正式 UI 建议按 `code` 做本地化文案。
- `details` 是调试和定位用字段，不保证适合直接展示给终端用户。

### 3.4 通用 ID

| 字段 | 含义 |
| --- | --- |
| `stock_code` | 前端展示和路由使用的股票代码，建议带交易所后缀，例如 `002594.SZ` |
| `ticker` | 系统内部分析使用的股票标识，架构文档示例为 `000001` |
| `workflow_run_id` | 一次完整分析任务 |
| `raw_ref` | 原始数据记录 ID |
| `evidence_id` | 归一化后的证据 ID |
| `evidence_structure_id` | Evidence 的客观结构化结果 ID |
| `agent_run_id` | 某个 Agent 的一次运行记录 |
| `agent_argument_id` | 某个 Agent 在某一轮输出的论证片段 |
| `round_summary_id` | 某一轮辩论摘要 |
| `judgment_id` | Judge 的最终判断 |
| `entity_id` | 公司、行业、政策、事件等实体 |

前端注解：

- 页面内跳转和下钻应优先使用这些 ID，不要依赖标题、股票名称或数组下标。
- `raw_ref` 和 `evidence_id` 不是同一个概念。Raw Item 是原始输入，Evidence 是归一化后的证据。
- `stock_code` 面向路由和展示，`ticker` 面向工作流和数据检索。后端必须接受常见 A 股代码格式并在响应中返回规范化结果。

### 3.5 被融合模块边界

`midterm-value-investor/fontWebUI` 原接口使用：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

主前端协议统一使用：

```json
{
  "data": {},
  "meta": {
    "request_id": "req_..."
  }
}
```

取舍：

- `docs/web_api` 中的新接口和核心接口统一使用本项目响应外壳；
- `docs/web_api` 不为同一个业务接口维护两套响应 schema；
- ZC 模块接口也应适配 `data/meta/error`，不把 `code/message/data` 扩散回主协议；
- 旧 `analysis/*`、`reports/*` 测试 API 直接裁切，不在主协议中做兼容别名；
- 错误码统一走本文档第 17 节，不继续扩展旧模块的 `5010` 语义。

前端注解：

- 新前端直接消费 `data/meta/error`。
- 如果复用旧 `fontWebUI/src/api/http.js`，需要先改响应拦截逻辑。
- 被融合模块的具体接口见 `docs/zc_module`；主协议只暴露 workflow、trace、evidence、agent、judgment、entity 等核心资源。

