<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ApiError } from '../api/http'
import { fetchEntity, fetchEntityEvidence } from '../api/entities'
import type { Entity, EvidenceItem } from '../types/workflow'

const route = useRoute()
const entityId = computed(() => route.params.entityId as string)
const entity = ref<Entity | null>(null)
const evidenceItems = ref<EvidenceItem[]>([])
const errorMessage = ref('')
const isLoading = ref(false)

onMounted(async () => {
  isLoading.value = true
  try {
    entity.value = await fetchEntity(entityId.value)
    evidenceItems.value = await fetchEntityEvidence(entityId.value)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? `${error.code}: ${error.message}` : '加载实体证据失败。'
  } finally {
    isLoading.value = false
  }
})
</script>

<template>
  <section class="page page-hero page-reveal">
    <div class="page-header">
      <div>
        <p class="eyebrow">实体证据</p>
        <h1>{{ entity?.name ?? entityId }} 的证据</h1>
        <p class="lede">此页面使用跨工作流的实体边界接口 <code>/api/v1/entities/{entity_id}/evidence</code>。</p>
      </div>
    </div>

    <div v-if="isLoading" class="panel loading-state">
      <span class="badge subtle">加载中</span>
      <div class="status-copy">
        <strong>正在加载实体证据…</strong>
        <p class="muted">准备跨工作流实体资料与证据结果列表。</p>
      </div>
    </div>
    <p v-else-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <div v-else class="detail-grid">
      <div class="panel">
        <div class="panel-header">
          <h2>实体资料</h2>
          <span class="badge">{{ entity?.entity_type ?? 'entity' }}</span>
        </div>
        <p class="muted">ID：<span class="mono">{{ entity?.entity_id ?? entityId }}</span></p>
        <p>{{ entity?.description ?? '暂无描述信息。' }}</p>
      </div>

      <div class="panel full-span">
        <div class="panel-header">
          <h2>证据结果</h2>
          <span class="badge">{{ evidenceItems.length }} 条</span>
        </div>
        <ul class="card-list">
          <li v-for="item in evidenceItems" :key="item.evidence_id" class="evidence-card">
            <div class="event-row align-start">
              <strong>{{ item.title }}</strong>
              <RouterLink class="resource-link mono" :to="`/evidence/${item.evidence_id}`">{{ item.evidence_id }}</RouterLink>
            </div>
            <p class="muted small">{{ item.objective_summary }}</p>
            <div class="metric-row">
              <span>source_quality {{ item.source_quality ?? '—' }}</span>
              <span>relevance {{ item.relevance ?? '—' }}</span>
              <span>freshness {{ item.freshness ?? '—' }}</span>
              <span>structuring_confidence {{ item.structuring_confidence ?? '—' }}</span>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
