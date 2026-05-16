# 详情介绍页设计

本文档描述 `frontend/src/features/details/DetailsPage.tsx`。

## 1. 页面定位

`DetailsPage` 是 `HomePage` 「了解更多」按钮的目标页，对应 hash `#details`。

当前实现是**纯静态介绍页**：解释「资讯报告」「分析」「历史」三个页面入口分别承担什么职责。不依赖任何 API。

## 2. 布局

```text
┌──────────────────────────────────────────────────────────┐
│ GlobalNav（无 active 高亮）                                │
├─────────────────────────────────┬───────────────────────┤
│ details-hero                    │ details-panel          │
│  h1: 多 Agent 证据链投研          │ 页面入口列表           │
│  正文段落                        │  - 资讯报告           │
│  「开始分析」「查看资讯报告」按钮   │  - 分析                │
│                                 │  - 历史                │
└─────────────────────────────────┴───────────────────────┘
```

## 3. 内容来源

文本硬编码在 `DetailsPage.tsx` 内，没有 i18n 字典也没有 CMS。

`details-panel` 三个条目：

| 入口 | 说明 |
| --- | --- |
| 资讯报告 | Report Module：stocks/* 与 market/* 视图 |
| 分析 | Workflow：任务、SSE、snapshot、trace |
| 历史 | 保留入口，等历史列表协议完成后接入 |

注：第三条文案是早期占位，与现状（`HistoryPage` 已接入 `listWorkflowRuns`）不完全一致，下一次内容更新时需要同步。

## 4. 边界

- `GlobalNav` 没有 `details` 这个 key，所以详情页在导航条上不会高亮任何项。
- 页面没有动态数据，不会出错，也不会有 loading 态。
- 如果要把这一页升级成产品说明 / changelog / 帮助中心，需要先决定内容是 markdown 化加载还是继续硬编码；当前两种方式都未规划。
