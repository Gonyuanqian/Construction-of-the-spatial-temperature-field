<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { greenhouseApi, type Greenhouse, type GreenhouseEdit, type WeatherDeployment } from '../api/accounts'
import Card from '../components/Card.vue'

const houses = ref<Greenhouse[]>([]), models = ref<WeatherDeployment[]>([])
const selected = ref<Greenhouse | null>(null), binding = ref('')
const loading = ref(false), saving = ref(false), error = ref(''), message = ref('')
const form = reactive({ name: '', enabled: true, length_m: 18, width_m: 2.1, height_m: 1.3017 })
const published = computed(() => models.value.filter(m => m.status === 'PUBLISHED'))
let alive = true
async function load() {
  loading.value = true; error.value = ''
  try {
    const [list, deployments] = await Promise.all([greenhouseApi.list(), greenhouseApi.models()])
    if (!alive) return
    houses.value = list; models.value = deployments
    if (selected.value) choose(list.find(h => h.id === selected.value?.id) ?? null)
  } catch (e) { if (alive) error.value = e instanceof Error ? e.message : '棚体档案读取失败。' }
  finally { if (alive) loading.value = false }
}
function choose(house: Greenhouse | null) {
  selected.value = house
  Object.assign(form, { name: house?.name ?? '', enabled: house?.enabled ?? true, length_m: house?.length_m ?? 18, width_m: house?.width_m ?? 2.1, height_m: house?.height_m ?? 1.3017 })
  binding.value = house?.weather_model_id ?? ''; message.value = ''; error.value = ''
}
async function action(run: () => Promise<void>) {
  if (saving.value) return
  saving.value = true; error.value = ''; message.value = ''
  try { await run() }
  catch (e) { if (alive) error.value = e instanceof Error ? e.message : '操作失败，请重试。' }
  finally { if (alive) saving.value = false }
}
async function save() {
  await action(async () => {
    const body: GreenhouseEdit = { ...form, name: form.name.trim() }
    const house = selected.value ? await greenhouseApi.update(selected.value.id, body) : await greenhouseApi.create(body)
    if (!alive) return
    houses.value = [house, ...houses.value.filter(h => h.id !== house.id)]
    choose(house); message.value = '棚体配置已保存，模型选用不受气象地区限制。'
  })
}
async function bind() {
  if (!selected.value || !binding.value) return
  const id = selected.value.id
  await action(async () => {
    const updated = await greenhouseApi.bind(id, binding.value)
    if (!alive) return
    houses.value = houses.value.map(h => h.id === updated.id ? updated : h)
    selected.value = updated; message.value = '已保存模型配置，后续构场使用此版本。'
  })
}
onMounted(() => { void load() })
onUnmounted(() => { alive = false })
</script>
<template>
  <section class="workspace-page">
    <header class="workspace-heading"><div><h2>棚体档案管理</h2><p class="note">维护棚体结构、尺寸与模型配置。地区只标识气象来源，不用于绑定或筛选模型。</p></div><div class="workspace-actions"><button type="button" :disabled="loading || saving" @click="load">刷新</button><button type="button" class="primary" :disabled="saving" @click="choose(null)">新增档案</button></div></header>
    <p v-if="error" role="alert" class="form-message error">{{ error }}</p><p v-if="message" role="status" class="form-message">{{ message }}</p>
    <div class="management-grid">
      <div class="stacked-panels">
        <Card><div class="panel-title"><h3>棚体配置库 <span class="note">{{ houses.length }} 份</span></h3></div>
          <p v-if="loading" role="status" class="note">正在读取档案…</p><div v-else-if="!houses.length" class="empty-panel">暂无棚体档案，请在右侧创建。</div>
          <div v-else class="management-table"><table><thead><tr><th>棚体配置</th><th>尺寸 / m</th><th>模型配置</th><th>启用状态</th><th>操作</th></tr></thead><tbody><tr v-for="house in houses" :key="house.id" :class="{ selected: selected?.id === house.id }"><td><strong>{{ house.name }}</strong><p class="note">拱形棚体</p></td><td class="dimensions">{{ house.length_m ?? '—' }} × {{ house.width_m ?? '—' }} × {{ house.height_m ?? '—' }}<p class="note">长 × 宽 × 高</p></td><td>{{ house.weather_model_name || '尚未配置' }}</td><td><span class="status-chip" :class="{ muted: !house.ready }">{{ house.ready ? '可用于构场' : house.enabled ? '待完善' : '已停用' }}</span><p v-if="!house.ready" class="note">{{ house.unavailable_reason }}</p></td><td><button type="button" :aria-label="`编辑档案 ${house.name}`" :disabled="saving" @click="choose(house)">编辑</button></td></tr></tbody></table></div>
        </Card>
        <Card><h3 class="panel-title">模型选用规则</h3><div class="matching-steps"><div><strong>01 选择棚体</strong><p class="note">按棚体结构与尺寸选择配置，不按省市区县筛选。</p></div><div><strong>02 配置模型</strong><p class="note">为棚体选择已发布的 G/F 组合，同一组合可供多份配置使用。</p></div><div><strong>03 接入气象</strong><p class="note">地区只用于获取和记录气象；各账号独立保存构场结果。</p></div></div><p class="note">只有一份启用配置时自动选用；有多份时由用户明确选择，避免任取模型。</p></Card>
      </div>
      <div class="stacked-panels"><Card><h3 class="panel-title">{{ selected ? '编辑棚体档案' : '新增棚体档案' }}</h3><form class="form-stack archive-form" @submit.prevent="save">
        <label>档案名称<input v-model="form.name" maxlength="120" required :disabled="saving" placeholder="例如：标准人参拱棚"></label>
        <div class="dimension-fields"><label>长 / m<input v-model.number="form.length_m" type="number" min="0.0001" max="100000" step="any" required :disabled="saving"></label><label>宽 / m<input v-model.number="form.width_m" type="number" min="0.0001" max="100000" step="any" required :disabled="saving"></label><label>高 / m<input v-model.number="form.height_m" type="number" min="0.0001" max="100000" step="any" required :disabled="saving"></label></div>
        <p class="note">当前固定构场模板范围为 18 × 2.1 × 1.3017 m。可记录其他尺寸，但需适配模型后才能构场；示意长度不代表缩放模型。</p>
        <label class="check-label"><input v-model="form.enabled" type="checkbox" :disabled="saving">启用棚体配置</label>
        <button class="primary" type="submit" :disabled="saving || !form.name.trim()">{{ saving ? '正在保存…' : '保存档案' }}</button>
      </form></Card>
      <Card v-if="selected"><h3 class="panel-title">模型配置</h3><p v-if="!published.length" class="note">暂无已发布的气象模型。请到<a href="/train">模型训练</a>的“气象映射模型 G”中选择已完成的训练，与 F 成品组合发布，再刷新本页。</p><form v-else class="form-stack" @submit.prevent="bind"><label>已发布模型<select v-model="binding" :disabled="saving" required><option value="">请选择气象模型</option><option v-if="selected.weather_model_id && !published.some(m => m.id === selected?.weather_model_id)" :value="selected.weather_model_id" disabled>当前模型不可用</option><option v-for="model in published" :key="model.id" :value="model.id">{{ model.name }}（{{ model.external_schema === 'two' ? '温度、光照' : '温度、湿度、光照' }}）</option></select></label><p class="note">历史结果保留当时的地区、尺寸和模型快照。切换配置只影响后续构场。</p><button type="submit" :disabled="saving || !binding || !published.some(m => m.id === binding)">保存模型配置</button></form></Card></div>
    </div>
  </section>
</template>
<style scoped>
.management-table button { white-space: nowrap; }.management-table th,.management-table td { padding: 12px 8px; }.management-table td:first-child { min-width: 132px; }.management-table td:nth-child(4) { min-width: 140px; max-width: 200px; }
.management-grid { grid-template-columns: minmax(0, 1fr) 380px; }.management-table p { margin: 4px 0 0; }.dimensions { white-space: nowrap; }.catalog-filter { display: flex; gap: 8px; align-items: center; font-size: var(--size-note); }.catalog-filter select { padding: 7px; border: var(--rule); border-radius: var(--radius); color: var(--ink); background: var(--card); }.matching-steps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; margin-bottom: 18px; }.matching-steps strong { font-size: var(--size-label); }.dimension-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }@media(max-width: 1200px) { .management-grid { grid-template-columns: minmax(0, 1fr); } }@media(max-width: 600px) { .matching-steps { grid-template-columns: minmax(0, 1fr); } }
</style>
