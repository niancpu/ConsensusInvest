<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ApiError } from '../api/http'
import { fetchWorkflowRun } from '../api/workflow'
import type { WorkflowRunDetail } from '../types/workflow'

const route = useRoute()
const workflowRunId = computed(() => route.params.workflowRunId as string)
const workflowRun = ref<WorkflowRunDetail | null>(null)
const errorMessage = ref('')
const isLoading = ref(false)

onMounted(async () => {
  isLoading.value = true
  errorMessage.value = ''

  try {
    workflowRun.value = await fetchWorkflowRun(workflowRunId.value)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? `${error.code}: ${error.message}` : '加载工作流运行详情失败。'
  } finally {
    isLoading.value = false
  }
})
</script>

<template>
  <section class="page page-hero page-reveal">
    <div class="page-header">
      <div>
        <p class="eyebrow">工作流总览</p>
        <h1>工作流 {{ workflowRun?.ticker ?? workflowRunId }}</h1>
        <p class="lede">
          这个稳定的总览页将生命周期 <code>status</code> 与执行阶段 <code>stage</code> 分开展示，并连接到实时、快照、追踪和结论视图。
        </p>
      </div>
      <div class="header-actions">
        <RouterLink class="text-link" to="/workflows">工作流历史</RouterLink>
        <RouterLink class="text-link" :to="`/workflow/${workflowRunId}/live`">实时</RouterLink>
      </div>
    </div>

    <div v-if="isLoading" class="panel loading-state">
      <span class="badge subtle">加载中</span>
      <div class="status-copy">
        <strong>正在加载工作流详情…</strong>
        <p class="muted">同步运行元信息、阶段进度与可进入视图。</p>
      </div>
    </div>
    <p v-else-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <div v-else-if="workflowRun" class="detail-grid">
      <div class="panel full-span">
        <div class="panel-header">
          <h2>工作流概览</h2>
          <span class="badge subtle">{{ workflowRun.workflow_run_id }}</span>
        </div>
        <div class="summary-grid">
          <div class="metric-card">
            <span class="label">状态</span>
            <strong>{{ workflowRun.status }}</strong>
          </div>
          <div class="metric-card">
            <span class="label">阶段</span>
            <strong>{{ workflowRun.stage ?? '—' }}</strong>
          </div>
          <div class="metric-card">
            <span class="label">最终信号</span>
            <strong>{{ workflowRun.final_signal ?? '—' }}</strong>
          </div>
          <div class="metric-card">
            <span class="label">置信度</span>
            <strong>{{ workflowRun.confidence ?? '—' }}</strong>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2>运行元信息</h2>
          <span class="badge">详情</span>
        </div>
        <dl class="detail-list">
          <div><dt>股票代码</dt><dd>{{ workflowRun.ticker }}</dd></div>
          <div><dt>分析时间</dt><dd>{{ workflowRun.analysis_time }}</dd></div>
          <div><dt>工作流配置</dt><dd>{{ workflowRun.workflow_config_id }}</dd></div>
          <div><dt>创建时间</dt><dd>{{ workflowRun.created_at }}</dd></div>
          <div><dt>开始时间</dt><dd>{{ workflowRun.started_at ?? '—' }}</dd></div>
          <div><dt>完成时间</dt><dd>{{ workflowRun.completed_at ?? '—' }}</dd></div>
          <div><dt>结论 ID</dt><dd>{{ workflowRun.judgment_id ?? '—' }}</dd></div>
        </dl>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2>执行进度</h2>
          <span class="badge">计数</span>
        </div>
        <dl class="detail-list">
          <div><dt>原始资料采集数</dt><dd>{{ workflowRun.progress?.raw_items_collected ?? '—' }}</dd></div>
          <div><dt>已规范化证据数</dt><dd>{{ workflowRun.progress?.evidence_items_normalized ?? '—' }}</dd></div>
          <div><dt>已结构化证据数</dt><dd>{{ workflowRun.progress?.evidence_items_structured ?? '—' }}</dd></div>
          <div><dt>已完成论点数</dt><dd>{{ workflowRun.progress?.agent_arguments_completed ?? '—' }}</dd></div>
        </dl>
      </div>

      <div class="panel full-span">
        <div class="panel-header">
          <h2>可进入视图</h2>
          <span class="badge">导航</span>
        </div>
        <div class="header-actions">
          <RouterLink class="text-link" :to="`/workflow/${workflowRunId}/live`">实时 SSE</RouterLink>
          <RouterLink class="text-link" :to="`/workflow/${workflowRunId}/snapshot`">快照</RouterLink>
          <RouterLink class="text-link" :to="`/workflow/${workflowRunId}/trace`">追踪</RouterLink>
          <RouterLink class="text-link" :to="`/workflow/${workflowRunId}/judgment`">结论</RouterLink>
        </div>
      </div>
    </div>
  </section>
</template>
