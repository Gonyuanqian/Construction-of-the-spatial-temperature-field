<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { assistantApi, type AnalysisSnapshot } from '../api/assistant'
const VolumeView = defineAsyncComponent(() => import('../scene/VolumeView.vue'))
const route = useRoute()
const snapshot = ref<AnalysisSnapshot | null>(null)
const error = ref('')
const identifier = computed(() => String(route.params.snapshotId))
const position = computed(() => {
  if (!['x','y','z'].every(k => typeof route.query[k] === 'string' && Number.isFinite(Number(route.query[k])))) return undefined
  return { x:Number(route.query.x), y:Number(route.query.y), z:Number(route.query.z) }
})
let requestSequence = 0
watch(identifier,async (id) => {
  const mine=++requestSequence; snapshot.value=null; error.value=''
  try { const out=await assistantApi.snapshotInfo(id); if(mine===requestSequence) snapshot.value=out }
  catch (e) { if(mine===requestSequence) error.value = e instanceof Error ? e.message : '无法读取分析快照' }
},{immediate:true})
</script>
<template>
  <section class="frozen-field">
    <header><h1>查看回答依据的温度场</h1><RouterLink to="/assistant">返回智能助手</RouterLink></header>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="snapshot">固定回放时刻：{{ snapshot.source_time }} · 模型 #{{ snapshot.model_id }}。本页不改变实时播放。</p>
    <VolumeView v-if="snapshot" :key="identifier" :t-index="snapshot.frame_index" :clock-time="snapshot.source_time"
      :frozen-snapshot-id="identifier" :initial-position="position" :show-clock="true" :show-view-controls="true" panels="shell" :stretch="true" />
  </section>
</template>
<style scoped>
.frozen-field { display:flex; flex:1; flex-direction:column; min-height:0; gap:var(--gap-m); }
header { display:flex; justify-content:space-between; align-items:center; gap:var(--gap-m); }
h1 { font-size:21px; color:var(--title-ink); } p { color:var(--ink-muted); } a { color:var(--leaf); }
</style>
