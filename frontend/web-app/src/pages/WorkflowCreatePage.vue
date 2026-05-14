<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError } from '../api/http'
import { createWorkflowRun, fetchWorkflowConfigs } from '../api/workflow'
import type { WorkflowConfig } from '../types/workflow'

const router = useRouter()
const configs = ref<WorkflowConfig[]>([])
const isLoading = ref(false)
const isSubmitting = ref(false)
const errorMessage = ref('')
const ticker = ref('000001')
const analysisTime = ref(new Date().toISOString().slice(0, 16))
const workflowConfigId = ref('')
const lookbackDays = ref(30)
const sources = ref('akshare,tushare,tavily,exa')

const enabledConfigs = computed(() => configs.value.filter((item) => item.enabled))

onMounted(async () => {
  isLoading.value = true
  errorMessage.value = ''
  try {
    configs.value = await fetchWorkflowConfigs()
    workflowConfigId.value = enabledConfigs.value[0]?.workflow_config_id ?? ''
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.code : '加载工作流配置失败。'
  } finally {
    isLoading.value = false
  }
})

async function submitForm() {
  isSubmitting.value = true
  errorMessage.value = ''

  try {
    const created = await createWorkflowRun({
      ticker: ticker.value.trim(),
      analysis_time: new Date(analysisTime.value).toISOString(),
      workflow_config_id: workflowConfigId.value,
      query: {
        lookback_days: lookbackDays.value,
        sources: sources.value
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
      },
      options: {
        stream: true,
        include_raw_payload: false,
      },
    })

    await router.push(`/workflow/${created.workflow_run_id}/live`)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? `${error.code}: ${error.message}` : '创建工作流失败。'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">工作流创建</p>
        <h1>新建分析工作流。</h1>
        <p class="lede">
          使用后端提供的 <code>workflow_config_id</code> 创建可审计的工作流运行，配置来自 <code>/api/v1/workflow-configs</code>。
        </p>
      </div>
    </div>

    <div class="panel form-panel">
      <div class="panel-header">
        <h2>运行配置</h2>
        <span class="badge">202 接受流程</span>
      </div>

      <p v-if="isLoading" class="muted">正在加载工作流配置…</p>
      <p v-else-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

      <form v-else class="form-grid" @submit.prevent="submitForm">
        <label>
          <span>股票代码</span>
          <input v-model="ticker" name="ticker" placeholder="000001" required />
        </label>

        <label>
          <span>分析时间</span>
          <input v-model="analysisTime" name="analysisTime" type="datetime-local" required />
        </label>

        <label class="full-width">
          <span>工作流配置</span>
          <select v-model="workflowConfigId" name="workflowConfigId" required>
            <option disabled value="">请选择工作流配置</option>
            <option v-for="config in enabledConfigs" :key="config.workflow_config_id" :value="config.workflow_config_id">
              {{ config.name }} · {{ config.workflow_config_id }}
            </option>
          </select>
        </label>

        <label>
          <span>回看天数</span>
          <input v-model.number="lookbackDays" min="1" name="lookbackDays" type="number" />
        </label>

        <label>
          <span>数据源</span>
          <input v-model="sources" name="sources" placeholder="akshare,tushare,tavily,exa" />
        </label>

        <div class="full-width actions">
          <button :disabled="isSubmitting || !workflowConfigId" type="submit">
            {{ isSubmitting ? '正在创建工作流…' : '创建工作流运行' }}
          </button>
        </div>
      </form>
    </div>
  </section>
</template>
