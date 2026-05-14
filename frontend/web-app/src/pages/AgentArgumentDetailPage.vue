<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ApiError } from '../api/http'
import { fetchAgentArgument } from '../api/workflow'
import type { AgentArgument } from '../types/workflow'

const route = useRoute()
const agentArgumentId = computed(() => route.params.agentArgumentId as string)
const agentArgument = ref<AgentArgument | null>(null)
const errorMessage = ref('')
const isLoading = ref(false)

onMounted(async () => {
  isLoading.value = true
  errorMessage.value = ''

  try {
    agentArgument.value = await fetchAgentArgument(agentArgumentId.value)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? `${error.code}: ${error.message}` : '加载智能体论点失败。'
  } finally {
    isLoading.value = false
  }
})
</script>

<template>
  <section class="page page-hero page-reveal">
    <div class="page-header">
      <div>
        <p class="eyebrow">智能体论点详情</p>
        <h1>论点 {{ agentArgument?.agent_id ?? agentArgumentId }}</h1>
        <p class="lede">解释性内容保留在论点层，并通过明确的证据引用支持审计和下钻导航。</p>
      </div>
      <div class="header-actions">
        <RouterLink v-if="agentArgument" class="text-link" :to="`/workflow/${agentArgument.workflow_run_id}`">工作流总览</RouterLink>
      </div>
    </div>

    <div v-if="isLoading" class="panel loading-state">
      <span class="badge subtle">加载中</span>
      <div class="status-copy">
        <strong>正在加载智能体论点…</strong>
        <p class="muted">准备解释性内容与证据引用下钻信息。</p>
      </div>
    </div>
    <p v-else-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <div v-else-if="agentArgument" class="detail-grid">
      <div class="panel full-span">
        <div class="panel-header">
          <h2>论点内容</h2>
          <span class="badge subtle">{{ agentArgument.agent_argument_id }}</span>
        </div>
        <p>{{ agentArgument.argument }}</p>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2>论点元信息</h2>
          <span class="badge">详情</span>
        </div>
        <dl class="detail-list">
          <div><dt>工作流运行</dt><dd>{{ agentArgument.workflow_run_id }}</dd></div>
          <div><dt>智能体运行</dt><dd>{{ agentArgument.agent_run_id }}</dd></div>
          <div><dt>智能体</dt><dd>{{ agentArgument.agent_id }}</dd></div>
          <div><dt>角色</dt><dd>{{ agentArgument.role }}</dd></div>
          <div><dt>轮次</dt><dd>{{ agentArgument.round }}</dd></div>
          <div><dt>置信度</dt><dd>{{ agentArgument.confidence }}</dd></div>
          <div><dt>创建时间</dt><dd>{{ agentArgument.created_at }}</dd></div>
          <div><dt>更新时间</dt><dd>{{ agentArgument.updated_at ?? '—' }}</dd></div>
        </dl>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2>局限性</h2>
          <span class="badge">{{ agentArgument.limitations.length }} 条</span>
        </div>
        <ul v-if="agentArgument.limitations.length" class="card-list compact">
          <li v-for="item in agentArgument.limitations" :key="item">{{ item }}</li>
        </ul>
        <p v-else class="muted">暂无局限性记录。</p>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2>引用证据</h2>
          <span class="badge">{{ agentArgument.referenced_evidence_ids.length }} 条</span>
        </div>
        <ul v-if="agentArgument.referenced_evidence_ids.length" class="card-list compact">
          <li v-for="evidenceId in agentArgument.referenced_evidence_ids" :key="evidenceId">
            <RouterLink class="resource-link mono" :to="`/evidence/${evidenceId}`">{{ evidenceId }}</RouterLink>
          </li>
        </ul>
        <p v-else class="muted">暂无引用证据 ID。</p>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2>反证证据</h2>
          <span class="badge">{{ agentArgument.counter_evidence_ids.length }} 条</span>
        </div>
        <ul v-if="agentArgument.counter_evidence_ids.length" class="card-list compact">
          <li v-for="evidenceId in agentArgument.counter_evidence_ids" :key="evidenceId">
            <RouterLink class="resource-link mono" :to="`/evidence/${evidenceId}`">{{ evidenceId }}</RouterLink>
          </li>
        </ul>
        <p v-else class="muted">暂无反证证据 ID。</p>
      </div>
    </div>
  </section>
</template>
