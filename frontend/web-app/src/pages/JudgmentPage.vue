<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ApiError } from '../api/http'
import { fetchJudgmentReferences, fetchJudgmentToolCalls, fetchWorkflowJudgment } from '../api/workflow'
import type { Judgment, JudgmentReference, JudgeToolCall } from '../types/workflow'

const route = useRoute()
const workflowRunId = computed(() => route.params.workflowRunId as string)
const judgment = ref<Judgment | null>(null)
const references = ref<JudgmentReference[]>([])
const toolCalls = ref<JudgeToolCall[]>([])
const errorMessage = ref('')
const isLoading = ref(false)

onMounted(async () => {
  isLoading.value = true
  try {
    const nextJudgment = await fetchWorkflowJudgment(workflowRunId.value)
    judgment.value = nextJudgment
    references.value = await fetchJudgmentReferences(nextJudgment.judgment_id)
    toolCalls.value = await fetchJudgmentToolCalls(nextJudgment.judgment_id)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? `${error.code}: ${error.message}` : '加载结论失败。'
  } finally {
    isLoading.value = false
  }
})
</script>

<template>
  <section class="page page-hero page-reveal">
    <div class="page-header">
      <div>
        <p class="eyebrow">工作流结论</p>
        <h1>{{ workflowRunId }} 的结论</h1>
        <p class="lede">最终结论始终与证据引用、论点以及裁决工具调用透明度保持连接。</p>
      </div>
    </div>

    <div v-if="isLoading" class="panel loading-state">
      <span class="badge subtle">加载中</span>
      <div class="status-copy">
        <strong>正在加载结论…</strong>
        <p class="muted">读取最终信号、证据引用和裁决工具透明度信息。</p>
      </div>
    </div>
    <p v-else-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <div v-else-if="judgment" class="detail-grid">
      <div class="panel">
        <div class="panel-header">
          <h2>结论</h2>
          <span class="badge signal">{{ judgment.final_signal }}</span>
        </div>
        <p class="metric-large">置信度 {{ judgment.confidence }}</p>
        <p>{{ judgment.reasoning }}</p>
        <div class="stack-top">
          <h3>引用论点</h3>
          <ul v-if="judgment.referenced_agent_argument_ids.length" class="card-list compact">
            <li v-for="argumentId in judgment.referenced_agent_argument_ids" :key="argumentId">
              <RouterLink class="resource-link mono" :to="`/agent-arguments/${argumentId}`">{{ argumentId }}</RouterLink>
            </li>
          </ul>
          <p v-else class="muted">暂无引用论点 ID。</p>
        </div>
        <div class="stack-top">
          <h3>风险说明</h3>
          <ul class="card-list compact">
            <li v-for="note in judgment.risk_notes" :key="note">{{ note }}</li>
          </ul>
        </div>
        <div class="stack-top">
          <h3>建议后续检查</h3>
          <ul class="card-list compact">
            <li v-for="item in judgment.suggested_next_checks" :key="item">{{ item }}</li>
          </ul>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2>证据引用</h2>
          <span class="badge">{{ references.length }} 条引用</span>
        </div>
        <ul class="card-list">
          <li v-for="reference in references" :key="reference.reference_id">
            <div class="event-row align-start">
              <span class="badge subtle">{{ reference.reference_role }}</span>
              <RouterLink class="resource-link mono" :to="`/evidence/${reference.evidence_id}`">{{ reference.evidence_id }}</RouterLink>
            </div>
            <p class="muted small">来源：{{ reference.source_type }} · 轮次：{{ reference.round ?? 'n/a' }}</p>
            <p v-if="reference.source_type.toLowerCase().includes('argument')" class="muted small">
              来源 ID：
              <RouterLink class="resource-link mono" :to="`/agent-arguments/${reference.source_id}`">{{ reference.source_id }}</RouterLink>
            </p>
            <p v-else class="muted small">来源 ID：<span class="mono">{{ reference.source_id }}</span></p>
          </li>
        </ul>
      </div>

      <div class="panel full-span">
        <div class="panel-header">
          <h2>裁决工具调用</h2>
          <span class="badge">{{ toolCalls.length }} 次调用</span>
        </div>
        <ul class="card-list">
          <li v-for="call in toolCalls" :key="`${call.created_at}-${call.tool_name}`">
            <div class="event-row">
              <strong>{{ call.tool_name }}</strong>
              <span class="mono small">{{ call.created_at }}</span>
            </div>
            <p class="muted small">{{ call.output_summary }}</p>
            <div v-if="call.referenced_evidence_ids?.length" class="stack-top">
              <p class="muted small">引用的证据</p>
              <div class="header-actions">
                <RouterLink
                  v-for="evidenceId in call.referenced_evidence_ids"
                  :key="evidenceId"
                  class="resource-link mono"
                  :to="`/evidence/${evidenceId}`"
                >
                  {{ evidenceId }}
                </RouterLink>
              </div>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
