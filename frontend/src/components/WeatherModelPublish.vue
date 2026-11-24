<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import type { WeatherDeployment } from '../api/accounts'
import { gTrainingApi, type GJob, type SavedFieldModel } from '../api/weatherTraining'
import Card from './Card.vue'

const props = defineProps<{
  job: GJob
  operationKey: (jobId: string, name: string, fieldId: number) => string
}>()
const fields = ref<SavedFieldModel[]>([]), records = ref<WeatherDeployment[]>([])
const fieldId = ref<number | ''>(''), name = ref('')
const loading = ref(false), saving = ref(false), error = ref(''), message = ref('')
const loadFailed = ref(false)
const stateLabel = {DRAFT: '待发布', PUBLISHED: '已发布', DISABLED: '已停用'}
const existing = computed(() => records.value.find(row => row.name === name.value.trim() && row.model_id === fieldId.value))
let alive = true, generation = 0

async function load() {
  const mine = ++generation, id = props.job.id
  loading.value = true; error.value = ''; loadFailed.value = false
  try {
    const [models, publications] = await Promise.all([gTrainingApi.fieldModels(), gTrainingApi.deployments(id)])
    if (!alive || mine !== generation) return
    fields.value = models; records.value = publications
  } catch(e) { if (alive && mine === generation) {loadFailed.value = true; error.value = e instanceof Error ? e.message : '发布信息读取失败。'} }
  finally { if (alive && mine === generation) loading.value = false }
}
watch(() => props.job.id, () => {
  fieldId.value = ''; name.value = `${props.job.name} · 气象构场`.slice(0, 120)
  fields.value = []; records.value = []; message.value = ''; saving.value = false
  void load()
}, {immediate: true})
onUnmounted(() => { alive = false; ++generation })

async function publish() {
  if (saving.value || loading.value || loadFailed.value || !fieldId.value || !name.value.trim() || existing.value || props.job.state !== 'done') return
  const mine = generation, id = props.job.id
  const body = {name: name.value.trim(), field_model_id: fieldId.value}
  saving.value = true; error.value = ''; message.value = ''
  try {
    const result = await gTrainingApi.publish(id, body, props.operationKey(id, body.name, body.field_model_id))
    if (!alive || mine !== generation) return
    records.value = [{...result, field_model_name: fields.value.find(f => f.id === body.field_model_id)?.name}, ...records.value.filter(row => row.id !== result.id)]
    message.value = result.status === 'PUBLISHED' ? '气象模型已发布，可在棚体档案中选择配置。' : '已恢复原发布记录；如需使用，请在下方重新发布。'
  } catch(e) { if (alive && mine === generation) error.value = e instanceof Error ? e.message : '组合发布失败，请重试。' }
  finally { if (alive && mine === generation) saving.value = false }
}
async function setStatus(row: WeatherDeployment) {
  if (saving.value || loading.value) return
  const mine = generation
  saving.value = true; error.value = ''; message.value = ''
  try {
    const updated = await gTrainingApi.deploymentStatus(row.id, row.status === 'PUBLISHED' ? 'DISABLED' : 'PUBLISHED')
    if (!alive || mine !== generation) return
    records.value = records.value.map(item => item.id === row.id ? {...item, ...updated} : item)
    message.value = updated.status === 'PUBLISHED' ? '模型已发布，可用于后续构场。' : '模型已停用，已保存的历史温度场保留。'
  } catch(e) { if (alive && mine === generation) error.value = e instanceof Error ? e.message : '模型状态更新失败。' }
  finally { if (alive && mine === generation) saving.value = false }
}
</script>

<template>
  <Card class="weather-publish" aria-label="气象模型发布与配置">
    <div class="publish-heading"><h3>发布与配置</h3><button type="button" :disabled="loading || saving" @click="load">刷新发布记录</button></div>
    <p class="note">将本次 G 与已保存的构场模型 F 组合，发布后供棚体档案选择。单时刻版和一小时历史版一并发布，运行时按气象历史自动选择。</p>
    <p v-if="error" class="publish-alert" role="alert">{{ error }}</p>
    <p v-if="message" class="publish-message" role="status">{{ message }}</p>
    <p v-if="loading" class="note" role="status">正在读取可用成品与发布记录…</p>
    <form class="publish-form" @submit.prevent="publish">
      <fieldset :disabled="loading || saving">
        <label>气象模型名称<input v-model="name" maxlength="120" required /></label>
        <label>组合的构场模型 F<select v-model="fieldId" required><option value="">请选择已保存的 F 成品</option><option v-for="field in fields" :key="field.id" :value="field.id">{{ field.name }}（ID {{ field.id }}）</option></select></label>
      </fieldset>
      <p v-if="!loading && !error && !fields.length" class="note">暂无 F 成品，请先在“空间构场模型 F”中完成训练并保存到模型库。</p>
      <p v-if="existing" class="note">该组合已有发布记录（{{ stateLabel[existing.status] }}），请使用下方记录管理状态。</p>
      <div class="publish-actions"><button class="primary" type="submit" :disabled="loading || saving || loadFailed || !fieldId || !name.trim() || !!existing">{{ saving ? '处理中…' : '组合并发布' }}</button><RouterLink to="/admin/greenhouses">前往棚体档案配置</RouterLink></div>
    </form>
    <p class="note">发布复制现有训练成品，不重新训练，也不会自动替换棚体配置。这里的 G 成绩仍是独立阶段验证成绩。</p>
    <div v-if="records.length" class="publication-table"><table><thead><tr><th>气象模型</th><th>构场模型 F</th><th>外部输入</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="row in records" :key="row.id"><td>{{ row.name }}</td><td>{{ row.field_model_name || `F · ID ${row.model_id}` }}</td><td>{{ row.external_schema === 'two' ? '温度、光照' : '温度、湿度、光照' }}</td><td>{{ stateLabel[row.status] }}</td><td><button type="button" :disabled="loading || saving" @click="setStatus(row)">{{ row.status === 'PUBLISHED' ? '停用' : '发布' }}</button></td></tr></tbody></table></div>
    <p v-else-if="!loading" class="note">本次 G 尚无组合发布记录。</p>
  </Card>
</template>

<style scoped>
.publish-heading, .publish-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.publish-heading h3 { margin: 0; }
.weather-publish p { margin: 12px 0; }
.publish-form fieldset { border: 0; padding: 0; margin: 16px 0; display: grid; grid-template-columns: 1fr 1fr; gap: 14px; min-width: 0; }
.publish-form label { display: grid; gap: 6px; min-width: 0; }
.publish-form input, .publish-form select { padding: 8px; width: 100%; min-width: 0; border: var(--rule); border-radius: var(--radius); background: var(--card); color: var(--ink); font: inherit; }
.publish-actions { justify-content: flex-start; flex-wrap: wrap; }
.primary { background: var(--leaf); color: var(--paper); }
.publish-alert, .publish-message { padding: 10px; border-left: 3px solid var(--leaf); background: var(--leaf-soft); }
.publication-table { overflow: auto; margin-top: 16px; }.publication-table table { width: 100%; }.publication-table th,.publication-table td { padding: 10px; white-space: nowrap; }
@media(max-width: 700px) { .publish-form fieldset { grid-template-columns: minmax(0, 1fr); } .publish-heading { align-items: flex-start; } }
</style>
