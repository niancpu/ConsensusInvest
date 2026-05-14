<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ApiError } from '../api/http'
import { fetchWorkflowTrace } from '../api/workflow'
import type { WorkflowTrace } from '../types/workflow'

const route = useRoute()
const workflowRunId = computed(() => route.params.workflowRunId as string)
const trace = ref<WorkflowTrace | null>(null)
const errorMessage = ref('')
const isLoading = ref(false)

function isEvidenceNode(nodeType: string) {
  return nodeType.toLowerCase().includes('evidence')
}

function isAgentArgumentNode(nodeType: string) {
  return nodeType.toLowerCase().includes('argument')
}

onMounted(async () => {
  isLoading.value = true
  try {
    trace.value = await fetchWorkflowTrace(workflowRunId.value)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? `${error.code}: ${error.message}` : '加载追踪数据失败。'
  } finally {
    isLoading.value = false
  }
})
</script>

<template>
  <section class="page page-hero page-reveal">
    <div class="page-header">
      <div>
        <p class="eyebrow">工作流追踪</p>
        <h1>{{ workflowRunId }} 的追踪图</h1>
        <p class="lede">从结论到论点、证据和原始来源，提供一个可读的分层视图。</p>
      </div>
    </div>

    <div v-if="isLoading" class="panel loading-state">
      <span class="badge subtle">加载中</span>
      <div class="status-copy">
        <strong>正在加载追踪数据…</strong>
        <p class="muted">整理结论到论点、证据与来源的可读追踪关系。</p>
      </div>
    </div>
    <p v-else-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <div v-else-if="trace" class="detail-grid">
      <div class="panel">
        <div class="panel-header">
          <h2>追踪节点</h2>
          <span class="badge">{{ trace.trace_nodes.length }} 个节点</span>
        </div>
        <ul class="card-list">
          <li v-for="node in trace.trace_nodes" :key="node.node_id" class="trace-node">
            <div class="trace-node-top">
              <span class="badge subtle">{{ node.node_type }}</span>
              <span class="mono">{{ node.node_id }}</span>
            </div>
            <strong>{{ node.title }}</strong>
            <p class="muted small">{{ node.summary }}</p>
            <div v-if="isEvidenceNode(node.node_type) || isAgentArgumentNode(node.node_type)" class="stack-top">
              <RouterLink v-if="isEvidenceNode(node.node_type)" class="resource-link mono" :to="`/evidence/${node.node_id}`">
                打开证据详情
              </RouterLink>
              <RouterLink
                v-else-if="isAgentArgumentNode(node.node_type)"
                class="resource-link mono"
                :to="`/agent-arguments/${node.node_id}`"
              >
                打开智能体论点详情
              </RouterLink>
            </div>
          </li>
        </ul>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2>追踪边</h2>
          <span class="badge">{{ trace.trace_edges.length }} 条边</span>
        </div>
        <ul class="card-list">
          <li v-for="edge in trace.trace_edges" :key="`${edge.from_node_id}-${edge.to_node_id}-${edge.edge_type}`">
            <p class="mono small">{{ edge.from_node_id }} → {{ edge.to_node_id }}</p>
            <strong>{{ edge.edge_type }}</strong>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
