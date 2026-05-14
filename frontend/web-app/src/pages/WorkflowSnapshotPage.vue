<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ApiError } from '../api/http'
import { fetchWorkflowSnapshot } from '../api/workflow'
import type { WorkflowSnapshot } from '../types/workflow'

const route = useRoute()
const workflowRunId = computed(() => route.params.workflowRunId as string)
const snapshot = ref<WorkflowSnapshot | null>(null)
const errorMessage = ref('')
const isLoading = ref(false)

onMounted(async () => {
  isLoading.value = true
  try {
    snapshot.value = await fetchWorkflowSnapshot(workflowRunId.value)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? `${error.code}: ${error.message}` : '加载快照失败。'
  } finally {
    isLoading.value = false
  }
})
</script>

<template>
  <section class="page page-hero page-reveal">
    <div class="page-header">
      <div>
        <p class="eyebrow">工作流快照</p>
        <h1>{{ workflowRunId }} 的快照恢复</h1>
        <p class="lede">此页面将快照视为恢复与状态补水机制，而不是实时事件传输通道。</p>
      </div>
    </div>

    <div v-if="isLoading" class="panel loading-state">
      <span class="badge subtle">加载中</span>
      <div class="status-copy">
        <strong>正在加载快照…</strong>
        <p class="muted">恢复工作流状态、证据和论点补水载荷。</p>
      </div>
    </div>
    <p v-else-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <div v-else-if="snapshot" class="detail-grid">
      <div class="panel">
        <div class="panel-header">
          <h2>工作流状态</h2>
          <span class="badge">last_event_sequence {{ snapshot.last_event_sequence }}</span>
        </div>
        <dl class="detail-list">
          <div><dt>状态</dt><dd>{{ snapshot.workflow_run.status }}</dd></div>
          <div><dt>阶段</dt><dd>{{ snapshot.workflow_run.stage ?? '—' }}</dd></div>
          <div><dt>股票代码</dt><dd>{{ snapshot.workflow_run.ticker }}</dd></div>
          <div><dt>是否有结论</dt><dd>{{ snapshot.judgment ? '是' : '否' }}</dd></div>
        </dl>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2>已恢复资源</h2>
          <span class="badge">快照载荷</span>
        </div>
        <dl class="detail-list">
          <div><dt>证据条目</dt><dd>{{ snapshot.evidence_items.length }}</dd></div>
          <div><dt>智能体论点</dt><dd>{{ snapshot.agent_arguments.length }}</dd></div>
          <div><dt>轮次总结</dt><dd>{{ snapshot.round_summaries.length }}</dd></div>
          <div><dt>智能体运行</dt><dd>{{ snapshot.agent_runs.length }}</dd></div>
        </dl>
      </div>

      <div v-if="snapshot.evidence_items.length" class="panel full-span">
        <div class="panel-header">
          <h2>证据条目</h2>
          <span class="badge">{{ snapshot.evidence_items.length }} 条</span>
        </div>
        <ul class="card-list">
          <li v-for="item in snapshot.evidence_items" :key="item.evidence_id" class="evidence-card">
            <div class="event-row align-start">
              <strong>{{ item.title }}</strong>
              <RouterLink class="resource-link mono" :to="`/evidence/${item.evidence_id}`">{{ item.evidence_id }}</RouterLink>
            </div>
            <p class="muted small">{{ item.objective_summary }}</p>
          </li>
        </ul>
      </div>

      <div v-if="snapshot.agent_arguments.length" class="panel full-span">
        <div class="panel-header">
          <h2>智能体论点</h2>
          <span class="badge">{{ snapshot.agent_arguments.length }} 条</span>
        </div>
        <ul class="card-list">
          <li v-for="argument in snapshot.agent_arguments" :key="argument.agent_argument_id">
            <div class="event-row align-start">
              <strong>{{ argument.agent_id }} · 第 {{ argument.round }} 轮</strong>
              <RouterLink class="resource-link mono" :to="`/agent-arguments/${argument.agent_argument_id}`">
                {{ argument.agent_argument_id }}
              </RouterLink>
            </div>
            <p class="muted small">{{ argument.argument }}</p>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
