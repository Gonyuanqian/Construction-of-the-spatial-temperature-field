<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, getJson } from './api/client'

interface DatasetSummary {
  file: string
  n_times: number
  n_columns: number
  signature: string
}

const health = ref<string>('检查中…')
const dataset = ref<DatasetSummary | null>(null)
const failure = ref<string>('')

onMounted(async () => {
  try {
    health.value = (await getJson<{ status: string }>('/api/health')).status
    dataset.value = await getJson<DatasetSummary>('/api/dataset')
  } catch (e) {
    failure.value = e instanceof ApiError ? e.message : String(e)
    health.value = '不可用'
  }
})
</script>

<template>
  <main>
    <h1>人参棚空间温度场重建系统</h1>
    <p>后端：{{ health }}</p>
    <p v-if="dataset">
      数据集 {{ dataset.file }} —— {{ dataset.n_times }} 个时刻 × {{ dataset.n_columns }} 列
    </p>
    <p v-if="failure" role="alert">{{ failure }}</p>
  </main>
</template>
