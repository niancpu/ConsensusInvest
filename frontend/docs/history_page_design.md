# 历史页面设计

本文档描述 `frontend/src/features/history/HistoryPage.tsx` 的页面结构、数据流和已知缺口。

## 1. 页面定位

历史页面用于回看已完成 / 运行中的 workflow。当前实现是**最小可用列表 + 摘要详情**，不在页内复现 Trace 图。

可以做：

- 查看最近 20 条 workflow 的 `ticker / status / workflow_config_id`；
- 点击某条记录看摘要详情（`Status / Config / Judgment / Signal`）；
- 用「回到分析」按钮跳到 `#analysis?ticker=...&run=...`，由分析页恢复快照和 Trace。

不在历史页做：

- 重新启动 workflow；
- 展示 Trace / Evidence / Argument 详情；
- 修改或删除任务。

## 2. 布局

```text
┌──────────────────────────────────────────────────────────┐
│ GlobalNav                                                │
├────────────────────┬────────────────────────────────────┤
│ History List       │ History Detail                     │
│                    │                                    │
│ 标题 + 说明         │ ticker 大标题                       │
│ workflow 列表       │ workflow_run_id                    │
│  - ticker          │ Status / Config / Judgment / Signal│
│  - status          │ 回到分析按钮                        │
│  - config_id        │                                    │
│ 错误 banner         │                                    │
└────────────────────┴────────────────────────────────────┘
```

## 3. 数据入口

```ts
// mount
listWorkflowRuns()        // GET /api/v1/workflow-runs?limit=20&offset=0

// 点击一条
getWorkflowRun(workflowRunId)  // GET /api/v1/workflow-runs/{id}
```

列表返回的 `WorkflowRunListItemView` 摘要字段：

- `workflow_run_id / ticker / status / analysis_time / workflow_config_id`
- `created_at / completed_at`
- `judgment_id / final_signal / confidence`

两个接口共用 `data + pagination` 外壳，错误走 `formatApiError`。

## 4. 列表

- 每行 `history-row`：`ticker（粗）+ status + workflow_config_id（小字）`；
- 点击行调用 `handlePickRun(workflow_run_id)`，重新拉详情写入 `selectedRun`；
- 没有筛选、没有分页控件（只取前 20 条）；
- 错误 banner 显示在列表底部。

## 5. 详情

- 标题 = `ticker`，副标题 = 完整 `workflow_run_id`；
- `<dl>` 渲染 4 项：`Status / Config / Judgment / Signal`，`judgment_id` / `final_signal` 为空时显示 `-`；
- 主按钮「回到分析」=> `#analysis?ticker={ticker}&run={workflow_run_id}`。

## 6. 边界与已知缺口

- 详情区只展示列表里的摘要字段，**没有调用 `snapshot` / `trace` / `judgment`**。如果要在历史页内复现「当时如何得到这个判断」，需要：
  1. 增加 `getWorkflowSnapshot` + `getWorkflowTrace` 调用；
  2. 把 `AnalysisPage` 的 Trace 渲染抽成可复用组件；
  3. 处理只读态（不再订阅 SSE）。
- 没有按 `status` 过滤；当前列表里既会出现 `completed`，也会出现 `running / failed`。
- 默认按后端排序，前端没有重排。
- 点击行后没有把 `workflow_run_id` 写到历史页 URL；刷新历史页会回到列表首项，但从详情进入分析页后可通过 `run` 参数恢复完整分析状态。
