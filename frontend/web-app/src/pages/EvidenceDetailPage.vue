<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ApiError } from '../api/http'
import { fetchEvidence } from '../api/workflow'
import type { EvidenceItem } from '../types/workflow'

const route = useRoute()
const evidenceId = computed(() => route.params.evidenceId as string)
const evidence = ref<EvidenceItem | null>(null)
const errorMessage = ref('')
const isLoading = ref(false)

onMounted(async () => {
  isLoading.value = true
  errorMessage.value = ''

  try {
    evidence.value = await fetchEvidence(evidenceId.value)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? `${error.code}: ${error.message}` : '加载证据详情失败。'
  } finally {
    isLoading.value = false
  }
})
</script>

<template>
  <section class="page page-hero page-reveal">
    <div class="page-header">
      <div>
        <p class="eyebrow">证据详情</p>
        <h1>证据 {{ evidence?.title ?? evidenceId }}</h1>
        <p class="lede">这里的证据页面保持客观性，只展示来源事实、提取质量和溯源信息，不承载解释性立场。</p>
      </div>
      <div class="header-actions">
        <RouterLink v-if="evidence?.workflow_run_id" class="text-link" :to="`/workflow/${evidence.workflow_run_id}`">工作流总览</RouterLink>
      </div>
    </div>

    <div v-if="isLoading" class="panel loading-state">
      <span class="badge subtle">加载中</span>
      <div class="status-copy">
        <strong>正在加载证据…</strong>
        <p class="muted">同步来源事实、质量信号和溯源信息。</p>
      </div>
    </div>
    <p v-else-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <div v-else-if="evidence" class="detail-grid">
      <div class="panel full-span">
        <div class="panel-header">
          <h2>客观摘要</h2>
          <span class="badge subtle">{{ evidence.evidence_id }}</span>
        </div>
        <p>{{ evidence.objective_summary }}</p>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2>来源信息</h2>
          <span class="badge">来源</span>
        </div>
        <dl class="detail-list">
          <div><dt>标题</dt><dd>{{ evidence.title }}</dd></div>
          <div><dt>来源</dt><dd>{{ evidence.source }}</dd></div>
          <div><dt>来源类型</dt><dd>{{ evidence.source_type }}</dd></div>
          <div><dt>证据类型</dt><dd>{{ evidence.evidence_type ?? '—' }}</dd></div>
          <div><dt>发布时间</dt><dd>{{ evidence.publish_time ?? '—' }}</dd></div>
          <div><dt>抓取时间</dt><dd>{{ evidence.fetched_at ?? '—' }}</dd></div>
          <div><dt>工作流运行</dt><dd>{{ evidence.workflow_run_id ?? '—' }}</dd></div>
          <div><dt>股票代码</dt><dd>{{ evidence.ticker ?? '—' }}</dd></div>
        </dl>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2>质量信号</h2>
          <span class="badge">客观</span>
        </div>
        <dl class="detail-list">
          <div><dt>来源质量</dt><dd>{{ evidence.source_quality ?? '—' }}</dd></div>
          <div><dt>相关性</dt><dd>{{ evidence.relevance ?? '—' }}</dd></div>
          <div><dt>时效性</dt><dd>{{ evidence.freshness ?? '—' }}</dd></div>
          <div><dt>结构化置信度</dt><dd>{{ evidence.structuring_confidence ?? '—' }}</dd></div>
          <div><dt>原始引用</dt><dd class="mono wrap-anywhere">{{ evidence.raw_ref ?? '—' }}</dd></div>
        </dl>
      </div>

      <div v-if="evidence.quality_notes?.length" class="panel full-span">
        <div class="panel-header">
          <h2>质量说明</h2>
          <span class="badge">{{ evidence.quality_notes.length }} 条</span>
        </div>
        <ul class="card-list compact">
          <li v-for="note in evidence.quality_notes" :key="note">{{ note }}</li>
        </ul>
      </div>
    </div>
  </section>
</template>
