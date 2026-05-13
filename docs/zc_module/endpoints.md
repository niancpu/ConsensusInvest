# ZC Module API Endpoints

本文档是 `midterm-value-investor/fontWebUI` 模块接入本项目后的 API 索引。

这里不定义主分析链路，也不把旧项目接口硬并入 `docs/web_api`。ZC 模块作为独立功能模块接入：消费主系统已经沉淀的数据、Evidence、实体和市场快照，输出面向页面的聚合视图。

## 阅读顺序

1. [Stock Research View API](./stock_research.md)：股票搜索、个股研究聚合视图、行业详情、事件影响、利好风险。
2. [Market API](./market.md)：指数看板、市场股票列表、概念雷达、市场预警。
3. [Migration And Cut Rules](./compatibility.md)：旧 `fontWebUI` 接口迁移、裁切和删除规则。

## 融合边界

ZC 模块的定位：

- 适配当前主 API 和数据模型，不反向要求主系统兼容旧项目状态模型。
- 消费已有信息，包括 Entity、Evidence Store、市场快照、主分析链路产出的 Judgment / Trace。
- 可以调用或指挥已有 Search Agent / 数据刷新能力，但不自己生产 Raw Item / Evidence。
- 可以运行自己的模块内 Agent，但该 Agent 与主链路 Perspective Agents / Judge Agent 解离，不写入主链路 `agent_arguments` 和 `judgments`。
- 返回页面聚合视图时必须保留可追踪 ID，不能只返回孤立文案。

ZC 模块不负责：

- 不新增第二套投资分析主入口。
- 不新增第二套 Evidence Store。
- 不新增第二套 Report Store。
- 不保留旧 `analysis/*` 和 `reports/*` 测试 API。

## 与其他文档的关系

| 目录 | 职责 |
| --- | --- |
| `docs/web_api` | 前端与主系统通信协议，包含 workflow、SSE、trace、evidence、judgment。 |
| `docs/zc_module` | ZC 模块接入后的视图 API、迁移规则、裁切边界。 |
| `docs/internal_contracts` | 主程序模块之间的内部接口协议；当前不在本文档补内容。 |

前端注解：

- 需要透明推理链路时，使用 `docs/web_api` 的 `workflow-runs`、`events`、`snapshot`、`trace`、`evidence`、`judgment`。
- 需要承接旧页面、行情页、轻量个股卡片时，使用本目录接口。
- 本目录接口返回的 `summary`、`benefits`、`risks`、`event ranking` 都是视图层结果；点击下钻必须能回到 Evidence、Entity、Workflow 或主链路 Judgment。
