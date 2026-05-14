<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useWorkflowStore } from '../stores/workflow'

const route = useRoute()
const workflowStore = useWorkflowStore()
const workflowRunId = computed(() => route.params.workflowRunId as string)

onMounted(async () => {
  workflowStore.reset()
  await workflowStore.loadSnapshot(workflowRunId.value)
  workflowStore.connect(workflowRunId.value)
})

onBeforeUnmount(() => {
  workflowStore.disconnect()
})
</script>

<template>
  <section class="page two-column page-hero page-reveal">
    <div class="content-stack">
      <div class="page-header">
        <div>
          <p class="eyebrow">工作流实时视图</p>
          <h1>运行 {{ workflowRunId }}</h1>
          <p class="lede">状态与阶段保持分离，同时通过 SSE 事件流展示增量活动。</p>
        </div>
        <div class="header-actions">
          <RouterLink class="text-link" :to="`/workflow/${workflowRunId}`">总览</RouterLink>
          <RouterLink class="text-link" :to="`/workflow/${workflowRunId}/snapshot`">快照</RouterLink>
          <RouterLink class="text-link" :to="`/workflow/${workflowRunId}/trace`">追踪</RouterLink>
          <RouterLink class="text-link" :to="`/workflow/${workflowRunId}/judgment`">结论</RouterLink>
        </div>
      </div>

      <div class="summary-grid">
        <div class="panel metric-card">
          <span class="label">状态</span>
          <strong>{{ workflowStore.workflowRun?.status ?? 'unknown' }}</strong>
        </div>
        <div class="panel metric-card">
          <span class="label">阶段</span>
          <strong>{{ workflowStore.workflowRun?.stage ?? 'unknown' }}</strong>
        </div>
        <div class="panel metric-card">
          <span class="label">事件流</span>
          <strong>{{ workflowStore.isStreaming ? '已连接' : '未连接' }}</strong>
        </div>
        <div class="panel metric-card">
          <span class="label">最新序号</span>
          <strong>{{ workflowStore.lastSequence ?? 'n/a' }}</strong>
        </div>
      </div>

      <div class="panel page-reveal">
        <div class="panel-header">
          <h2>快照恢复状态</h2>
          <span class="badge">恢复来源</span>
        </div>
        <p class="muted">股票代码：{{ workflowStore.workflowRun?.ticker ?? '—' }}</p>
        <p class="muted">分析时间：{{ workflowStore.workflowRun?.analysis_time ?? '—' }}</p>
        <p class="muted">工作流配置：{{ workflowStore.workflowRun?.workflow_config_id ?? '—' }}</p>
        <p v-if="workflowStore.streamError" class="error-banner">{{ workflowStore.streamError }}</p>
      </div>
    </div>

    <aside class="panel rail-panel page-reveal">
      <div class="panel-header">
        <h2>事件流</h2>
        <span class="badge">/events SSE</span>
      </div>
      <ul v-if="workflowStore.events.length" class="event-list">
        <li v-for="event in workflowStore.events" :key="event.event_id">
          <div class="event-row">
            <span class="mono">#{{ event.sequence }}</span>
            <span>{{ event.event_type }}</span>
          </div>
          <p class="muted small">{{ event.created_at }}</p>
        </li>
      </ul>
      <p v-else class="muted">暂时还没有事件。此视图会等待 <code>/api/v1/workflow-runs/{workflow_run_id}/events</code> 的 SSE 更新。</p>
    </aside>
  </section>
</template>
