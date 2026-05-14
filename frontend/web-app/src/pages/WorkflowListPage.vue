<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ApiError } from '../api/http'
import { fetchWorkflowRuns } from '../api/workflow'
import type { WorkflowRunSummary } from '../types/workflow'

const workflowRuns = ref<WorkflowRunSummary[]>([])
const nextCursor = ref<string | null>(null)
const errorMessage = ref('')
const isLoading = ref(false)
const isLoadingMore = ref(false)

async function loadWorkflowRuns(cursor?: string) {
  if (cursor) {
    isLoadingMore.value = true
  } else {
    isLoading.value = true
    errorMessage.value = ''
  }

  try {
    const response = await fetchWorkflowRuns(cursor)
    workflowRuns.value = cursor ? [...workflowRuns.value, ...response.items] : response.items
    nextCursor.value = response.next_cursor ?? null
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? `${error.code}: ${error.message}` : '加载工作流列表失败。'
  } finally {
    isLoading.value = false
    isLoadingMore.value = false
  }
}

onMounted(() => {
  void loadWorkflowRuns()
})
</script>

<template>
  <section class="page page-hero page-reveal">
    <div class="page-header">
      <div>
        <p class="eyebrow">工作流历史</p>
        <h1>浏览工作流运行记录。</h1>
        <p class="lede">
          查看来自 <code>/api/v1/workflow-runs</code> 的历史工作流运行，并进入稳定的总览页面继续下钻分析。
        </p>
      </div>
      <div class="header-actions">
        <RouterLink class="text-link" to="/workflow/new">新建工作流</RouterLink>
      </div>
    </div>

    <div v-if="isLoading" class="panel loading-state">
      <span class="badge subtle">加载中</span>
      <div class="status-copy">
        <strong>正在加载工作流列表…</strong>
        <p class="muted">准备历史工作流记录与可继续下钻的入口。</p>
      </div>
    </div>
    <p v-else-if="errorMessage" class="error-banner">{{ errorMessage }}</p>
    <div v-else-if="workflowRuns.length === 0" class="panel empty-state">
      <h2>暂无工作流运行记录</h2>
      <p class="muted">先创建一个工作流，才能看到历史记录和可路由的下钻详情页面。</p>
    </div>
    <div v-else class="panel">
      <div class="panel-header">
        <h2>工作流运行列表</h2>
        <span class="badge">已加载 {{ workflowRuns.length }} 条</span>
      </div>

      <ul class="card-list">
        <li v-for="run in workflowRuns" :key="run.workflow_run_id" class="run-card">
          <div class="event-row align-start">
            <div>
              <div class="card-title-row">
                <RouterLink class="resource-link" :to="`/workflow/${run.workflow_run_id}`">{{ run.ticker }}</RouterLink>
                <span class="badge subtle">{{ run.workflow_run_id }}</span>
              </div>
              <p class="muted small">创建时间 {{ run.created_at }}</p>
            </div>
            <div class="badge-row wrap-end">
              <span class="badge subtle">状态 {{ run.status }}</span>
              <span class="badge subtle">阶段 {{ run.stage ?? '—' }}</span>
              <span v-if="run.final_signal" class="badge signal">{{ run.final_signal }}</span>
            </div>
          </div>

          <div class="metric-row compact-metrics">
            <span>分析时间 {{ run.analysis_time }}</span>
            <span>配置 {{ run.workflow_config_id }}</span>
            <span>置信度 {{ run.confidence ?? '—' }}</span>
            <span>完成时间 {{ run.completed_at ?? '—' }}</span>
          </div>

          <div class="header-actions">
            <RouterLink class="text-link" :to="`/workflow/${run.workflow_run_id}`">总览</RouterLink>
            <RouterLink class="text-link" :to="`/workflow/${run.workflow_run_id}/live`">实时</RouterLink>
            <RouterLink class="text-link" :to="`/workflow/${run.workflow_run_id}/snapshot`">快照</RouterLink>
            <RouterLink class="text-link" :to="`/workflow/${run.workflow_run_id}/trace`">追踪</RouterLink>
            <RouterLink class="text-link" :to="`/workflow/${run.workflow_run_id}/judgment`">结论</RouterLink>
          </div>
        </li>
      </ul>

      <div v-if="nextCursor" class="actions">
        <button :disabled="isLoadingMore" type="button" @click="loadWorkflowRuns(nextCursor ?? undefined)">
          {{ isLoadingMore ? '正在加载更多…' : '加载更多' }}
        </button>
      </div>
    </div>
  </section>
</template>
