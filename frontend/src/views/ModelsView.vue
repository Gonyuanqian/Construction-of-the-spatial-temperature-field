<script setup lang="ts">
/** 模型库管理保存记录；构场使用的模型在构场页面选择。 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { deleteModels, fetchModelDetail, fetchModels, renameModel } from '../api/models'
import type { ModelRowPayload, ParamValue } from '../api/types'
import Card from '../components/Card.vue'
import Icon from '../components/Icon.vue'
import ModalDialog from '../components/ModalDialog.vue'
import TrainingModelLibrary from '../components/TrainingModelLibrary.vue'
import { emptyModelFilters, filterModels, modelListCsv } from './modelLibrary'
import { useAsync } from '../composables/useAsync'
import { MODELS } from '../design/copy'
import { fmtTime } from '../design/format'

const route = useRoute()
const router = useRouter()
const models = useAsync(fetchModels)
const selectedId = ref<number | null>(null)
const detail = useAsync(() => fetchModelDetail(selectedId.value!))
const tabs = [
  { key: 'overview', label: '概览' },
  { key: 'metrics', label: '评估结果' },
  { key: 'parameters', label: '参数' },
] as const
type DetailTab = typeof tabs[number]['key']
const activeTab = ref<DetailTab>('overview')
const actionMessage = ref('')
const routeId = computed(() => {
  if (route.name !== 'model-detail') return null
  const id = Number(route.params.id)
  return Number.isSafeInteger(id) && id > 0 ? id : null
})
const invalidRoute = computed(() => route.name === 'model-detail' && routeId.value === null)
const rows = computed(() => models.data.value?.rows ?? [])
const selectedRow = computed(() => rows.value.find(row => row.id === selectedId.value) ?? null)
// 防止切换期间把上一模型的响应显示在新模型标题下。
const record = computed(() => detail.data.value?.id === selectedId.value ? detail.data.value : null)
const metricRows = computed(() => record.value?.metrics ?? [])
const trendParameters = computed(() => Object.entries(record.value?.trend_params ?? {}))

async function refreshModels(): Promise<void> {
  await models.run()
  if (!models.error.value) checkedIds.value = checkedIds.value.filter(id => rows.value.some(row => row.id === id))
}
watch(routeId, id => {
  selectedId.value = id
}, { immediate: true })
watch(selectedId, id => {
  activeTab.value = 'overview'
  actionMessage.value = ''
  if (id !== null) void detail.run()
}, { immediate: true })
onMounted(() => { void refreshModels() })

const filters = reactive(emptyModelFilters())
const appliedFilters = ref(emptyModelFilters())
const filterError = ref('')
const sources = computed(() => [...new Set(rows.value.map(row => row.data_file))])
const filteredRows = computed(() => filterModels(rows.value, appliedFilters.value))
const page = ref(1)
const pageSize = ref(10)
const pages = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / pageSize.value)))
const pageRows = computed(() => filteredRows.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const checkedIds = ref<number[]>([])
const allPageChecked = computed(() => pageRows.value.length > 0 && pageRows.value.every(row => checkedIds.value.includes(row.id)))
const somePageChecked = computed(() => pageRows.value.some(row => checkedIds.value.includes(row.id)) && !allPageChecked.value)
watch([filteredRows, pageSize], () => { page.value = Math.min(page.value, pages.value) })
function search(): void {
  if (filters.start && filters.end && filters.start > filters.end) { filterError.value = '开始日期不能晚于结束日期。'; return }
  filterError.value = ''
  appliedFilters.value = { ...filters }
  page.value = 1
  checkedIds.value = []
}
function resetFilters(): void { Object.assign(filters, emptyModelFilters()); search() }
function togglePage(checked: boolean): void {
  const ids = new Set(checkedIds.value)
  pageRows.value.forEach(row => checked ? ids.add(row.id) : ids.delete(row.id))
  checkedIds.value = [...ids]
}
const columns = [
  { key: 'source', label: '训练来源' }, { key: 'type', label: '模型类型' },
  { key: 'status', label: '成品状态' }, { key: 'mae', label: 'MAE / ℃' }, { key: 'saved', label: '保存时间' },
] as const
const visibleColumns = ref<string[]>(columns.map(column => column.key))
const columnVisible = (key: string) => visibleColumns.value.includes(key)
const editingRow = ref<ModelRowPayload | null>(null)
const editingName = ref('')
const savingEdit = ref(false)
const deleteRows = ref<ModelRowPayload[]>([])
const deleting = ref(false)
const managementError = ref('')
const mutating = computed(() => savingEdit.value || deleting.value)
function edit(row: ModelRowPayload): void { editingRow.value = row; editingName.value = row.name; managementError.value = '' }
function askDelete(items: ModelRowPayload[]): void { deleteRows.value = items; managementError.value = '' }
async function saveRename(): Promise<void> {
  if (!editingRow.value || savingEdit.value || !editingName.value.trim()) return
  savingEdit.value = true
  managementError.value = ''
  try {
    const row = editingRow.value
    await renameModel(row.id, editingName.value.trim())
    if (detail.data.value?.id === row.id) detail.data.value = { ...detail.data.value, name: editingName.value.trim() }
    editingRow.value = null
    actionMessage.value = '模型名称已更新。'
    await refreshModels()
  } catch (error) { managementError.value = error instanceof Error ? error.message : String(error) }
  finally { savingEdit.value = false }
}
async function confirmDelete(): Promise<void> {
  if (!deleteRows.value.length || deleting.value) return
  deleting.value = true
  managementError.value = ''
  try {
    const ids = deleteRows.value.map(row => row.id)
    await deleteModels(ids)
    deleteRows.value = []
    checkedIds.value = checkedIds.value.filter(id => !ids.includes(id))
    if (selectedId.value !== null && ids.includes(selectedId.value)) await router.replace('/models')
    actionMessage.value = `已删除 ${ids.length} 个模型。`
    await refreshModels()
  } catch (error) { managementError.value = error instanceof Error ? error.message : String(error) }
  finally { deleting.value = false }
}
function exportList(): void {
  const items = checkedIds.value.length ? filteredRows.value.filter(row => checkedIds.value.includes(row.id)) : filteredRows.value
  const url = URL.createObjectURL(new Blob([modelListCsv(items)], { type: 'text/csv;charset=utf-8;' }))
  const link = document.createElement('a')
  link.href = url; link.download = '模型库列表.csv'; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

function num(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? '无值' : value.toFixed(4)
}
function when(value: string | null | undefined): string { return value ? fmtTime(value) : '未记录' }
const featureLabels: Record<string, string> = {
  coord: '空间坐标', zbasis: '高度基函数', meteo: '背景气象', interaction: '交互特征',
}
const parameterLabels: Record<string, string> = {
  'metric.power': '距离权重幂次', 'metric.lx': '横向距离尺度',
  'metric.ly': '沿棚距离尺度', 'metric.lz': '高度距离尺度', cross_shed: '跨棚修正',
  'trend.max_depth': '树的最大深度', 'trend.learning_rate': '学习率',
  'trend.n_estimators': '树的数量', 'trend.min_child_weight': '最小子节点权重',
  'trend.subsample': '样本采样比例', 'trend.colsample_bytree': '特征采样比例',
  'trend.reg_lambda': 'L2 正则强度', 'trend.objective': '目标函数',
  'trend.random_state': '随机种子', 'trend.n_jobs': '计算线程数',
  'trend.tree_method': '树构建方法', 'trend.verbosity': '日志级别',
}
function parameterLabel(key: string): string { return parameterLabels[key] ?? key }
function parameterValue(value: ParamValue): string {
  return typeof value === 'boolean' ? (value ? '开启' : '关闭') : String(value)
}
function modelKind(kind: string): string { return kind === 'xgboost' ? 'XGBoost' : kind }
function spatialGroup(group: string): string {
  if (group === 'A') return '空间选参组'
  if (group === 'B') return '空间留出组'
  return group && group !== 'None' && group !== 'nan' ? group : '不分组'
}
function foldKind(kind: string): string {
  return ({ position: '测点留出', section: '断面留出', region: '区域留出' } as Record<string, string>)[kind] ?? kind
}
function tabKeydown(event: KeyboardEvent): void {
  const index = tabs.findIndex(tab => tab.key === activeTab.value)
  let next = index
  if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
  else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = tabs.length - 1
  else return
  const tab = tabs[next]
  if (!tab) return
  event.preventDefault()
  activeTab.value = tab.key
  const container = event.currentTarget as HTMLElement
  container.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus()
}
</script>

<template>
  <section class="models" aria-labelledby="models-title">
    <header class="models-heading">
      <div><p class="breadcrumb">工作空间 / 模型库</p><h2 id="models-title">{{ MODELS.title }}</h2><p class="note">查询与管理模型、训练记录及评估结果</p></div>
      <div class="heading-actions">
        <span v-if="models.data.value" class="note">旧版模型 {{ rows.length }} 条</span>
      </div>
    </header>
    <TrainingModelLibrary />
    <Card v-if="models.error.value" class="library-error">
      <p class="err" role="alert">{{ models.error.value }}</p>
      <p v-if="models.data.value" class="note">以下保留上次读取的列表，可点击刷新重试。</p>
      <button v-else type="button" :disabled="models.loading.value" @click="refreshModels">重新加载</button>
    </Card>
    <form class="filter-panel" aria-label="模型筛选" @submit.prevent="search">
      <div class="filter-grid">
        <label>模型名称<input v-model="filters.name" type="search" placeholder="请输入模型名称"></label>
        <label>训练来源<select v-model="filters.source"><option value="">全部数据集</option><option v-for="source in sources" :key="source" :value="source">{{ source }}</option></select></label>
        <label>成品状态<select v-model="filters.artifact"><option value="">全部状态</option><option value="ready">已保存成品</option><option value="parameters">仅保存参数</option></select></label>
        <label>数据适配<select v-model="filters.fit"><option value="">全部</option><option value="native">当前数据适配</option><option value="borrowed">训练来源不同</option><option value="unavailable">当前配置不可用</option></select></label>
        <div class="date-filter"><span>保存时间</span><div><input v-model="filters.start" type="date" aria-label="保存开始日期"><span>至</span><input v-model="filters.end" type="date" aria-label="保存结束日期"></div></div>
      </div>
      <div class="filter-actions"><p v-if="filterError" role="alert" class="err">{{ filterError }}</p><button class="primary" type="submit"><Icon name="search" />查询</button><button type="button" @click="resetFilters">重置</button></div>
    </form>
    <div class="management-toolbar">
      <div class="toolbar-group">
        <RouterLink class="button-link primary-link" to="/train"><Icon name="plus" />新增模型</RouterLink>
        <span title="外部模型文件导入尚未开放"><button type="button" disabled aria-describedby="import-status"><Icon name="upload" />导入模型</button></span>
        <button type="button" class="danger-outline" :disabled="!checkedIds.length || checkedIds.length > 100 || mutating" @click="askDelete(rows.filter(row => checkedIds.includes(row.id)))"><Icon name="trash" />批量删除</button>
        <button type="button" :disabled="!filteredRows.length" :title="checkedIds.length ? '导出已选中的模型管理信息' : '导出当前筛选结果的模型管理信息'" @click="exportList"><Icon name="download" />导出列表</button>
      </div>
      <div class="toolbar-group"><button type="button" class="icon-button" :disabled="models.loading.value || mutating" @click="refreshModels"><Icon name="reset" />{{ models.loading.value ? '读取中' : '刷新' }}</button><details class="column-settings"><summary><Icon name="columns" />列设置</summary><div><label v-for="column in columns" :key="column.key"><input v-model="visibleColumns" type="checkbox" :value="column.key">{{ column.label }}</label></div></details></div>
    </div>
    <p v-if="actionMessage" role="status" class="action-success action-feedback">{{ actionMessage }}</p>
    <div class="library-table-panel" :aria-busy="models.loading.value">
      <div class="table-scroll">
        <table class="model-table" aria-label="模型列表">
          <thead><tr><th class="check-column" scope="col"><input type="checkbox" aria-label="选择本页模型" :checked="allPageChecked" :indeterminate="somePageChecked" :disabled="!pageRows.length || mutating" @change="togglePage(($event.target as HTMLInputElement).checked)"></th><th scope="col">模型名称</th><th v-if="columnVisible('source')" scope="col">训练来源</th><th v-if="columnVisible('type')" scope="col">模型类型</th><th v-if="columnVisible('status')" scope="col">成品状态</th><th v-if="columnVisible('mae')" scope="col">MAE / ℃</th><th v-if="columnVisible('saved')" scope="col">保存时间</th><th class="operations-column" scope="col">操作</th></tr></thead>
          <tbody><tr v-for="row in pageRows" :key="row.id" :class="{ 'is-selected': checkedIds.includes(row.id) }">
            <td class="check-column"><input v-model="checkedIds" type="checkbox" :value="row.id" :aria-label="`选择模型 ${row.name}`" :disabled="mutating"></td>
            <td class="name-column"><RouterLink :to="`/models/${row.id}`" class="model-name">{{ row.name }}</RouterLink><div class="row-meta"><span class="note">ID {{ String(row.id).padStart(3, '0') }}</span></div></td>
            <td v-if="columnVisible('source')"><span class="source-name" :title="row.data_file">{{ row.data_file }}</span></td><td v-if="columnVisible('type')" class="model-kind">趋势模型 + IDW</td>
            <td v-if="columnVisible('status')"><span class="status" :class="{ ready: row.has_artifact }">{{ row.has_artifact ? MODELS.artifactReady : MODELS.notSolid }}</span><span class="state-caption" :title="row.why">{{ !row.compatible ? '当前配置不可用' : row.borrowed ? MODELS.differentSource : '当前数据适配' }}</span></td>
            <td v-if="columnVisible('mae')" class="numeric">{{ row.mae == null ? '—' : num(row.mae) }}</td><td v-if="columnVisible('saved')" class="saved-column">{{ when(row.saved_at) }}</td>
            <td><div class="row-actions"><RouterLink :to="`/models/${row.id}`">查看</RouterLink><button type="button" :disabled="mutating" @click="edit(row)">编辑</button><button type="button" class="danger-text" :disabled="mutating || row.is_current" :title="row.is_current ? '该模型正用于构场，请先在构场页面选择其他模型并开始构场' : '删除模型'" @click="askDelete([row])">删除</button></div></td>
          </tr><tr v-if="!pageRows.length"><td :colspan="3 + visibleColumns.length" class="empty-cell"><Icon name="database" /><strong>{{ models.loading.value ? '正在读取模型库…' : models.error.value ? '模型列表读取失败' : rows.length ? '没有符合筛选条件的模型' : MODELS.empty }}</strong><p>{{ rows.length ? '请调整查询条件后重试。' : MODELS.emptyWhy }}</p><button v-if="rows.length" type="button" @click="resetFilters">清空筛选</button></td></tr></tbody>
        </table>
      </div>
      <p class="list-caption">点击“查看”打开模型详情。构场时，请在“空间温度场的构建”页面选择模型并开始构场。</p>
      <div class="pagination"><div>已选 <strong>{{ checkedIds.length }}</strong> 项<span>共 {{ filteredRows.length }} 条记录</span></div><nav aria-label="模型分页"><label><select v-model.number="pageSize" aria-label="每页模型数量" @change="page = 1"><option :value="10">10 条/页</option><option :value="20">20 条/页</option><option :value="50">50 条/页</option></select></label><button type="button" aria-label="上一页" :disabled="page <= 1" @click="page--">‹</button><span class="page-number">{{ page }}</span><button type="button" aria-label="下一页" :disabled="page >= pages" @click="page++">›</button><span>/ {{ pages }} 页</span></nav></div>
    </div>
    <p id="import-status" class="import-status note">新增模型需先完成训练；外部模型文件导入暂未开放。导出列表包含模型管理信息。</p>

    <ModalDialog v-if="route.name === 'model-detail'" label="模型详情" drawer @close="router.replace('/models')">
      <div class="drawer-top"><h2>模型详情</h2><button type="button" aria-label="关闭模型详情" @click="router.replace('/models')">×</button></div>
      <div class="model-detail-panel" :aria-busy="detail.loading.value">
        <template v-if="invalidRoute"><h3>模型编号无效</h3><p class="note">请选择左侧模型记录。</p><RouterLink to="/models">返回模型列表</RouterLink></template>
        <template v-else-if="selectedId !== null">
          <div class="detail-heading"><div><p class="note detail-eyebrow">模型详情 <span class="num">ID {{ selectedId }}</span></p><h3>{{ selectedRow?.name ?? record?.name ?? '正在读取模型…' }}</h3></div></div>
          <div class="detail-tabs" role="tablist" aria-label="模型详情分类" @keydown="tabKeydown">
            <button v-for="tab in tabs" :id="`model-tab-${tab.key}`" :key="tab.key" type="button" role="tab" :aria-selected="activeTab === tab.key" :aria-controls="`model-panel-${tab.key}`" :tabindex="activeTab === tab.key ? 0 : -1" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">{{ tab.label }}</button>
          </div>
          <div v-if="detail.loading.value" class="detail-loading" role="status">正在读取模型详情…</div>
          <div v-else-if="detail.error.value" class="detail-error"><p class="err" role="alert">{{ detail.error.value }}</p><button type="button" @click="detail.run">重新读取详情</button></div>
          <template v-else-if="record">
            <div :id="`model-panel-${activeTab}`" role="tabpanel" :aria-labelledby="`model-tab-${activeTab}`">
              <template v-if="activeTab === 'overview'">
                <dl class="model-facts">
                  <dt>训练来源</dt><dd>{{ record.data_file }}</dd>
                  <dt>训练时段</dt><dd>{{ when(record.data_start) }}<br>至 {{ when(record.data_end) }}</dd>
                  <dt>模型类型</dt><dd>{{ modelKind(record.trend_kind) }} 趋势与 IDW 残差修正</dd>
                  <dt>输入特征</dt><dd><span class="feature-list"><span v-for="group in record.feature_groups" :key="group" class="feature" :title="group">{{ featureLabels[group] ?? group }}</span></span></dd>
                  <dt>成品状态</dt><dd>{{ record.has_artifact ? MODELS.artifactReady : MODELS.notSolid }}</dd>
                  <dt>保存时间</dt><dd>{{ when(record.saved_at) }}</dd>
                </dl>
                <div v-if="selectedRow && !selectedRow.compatible" class="context-note" role="note"><strong>当前配置不可用</strong><p>{{ selectedRow.why }}</p></div>
                <div v-else-if="selectedRow?.borrowed" class="context-note" role="note"><strong>{{ MODELS.differentSource }}</strong><p>{{ selectedRow.why }}</p></div>
                <p v-if="!record.has_artifact" class="note artifact-note">{{ MODELS.notSolidWhy }}</p>
                <section class="summary-section" aria-labelledby="model-spatial-summary">
                  <div class="section-heading"><h3 id="model-spatial-summary">空间留出验证</h3><button type="button" class="text-button" @click="activeTab = 'metrics'">查看明细</button></div>
                  <p class="note">保存记录中的空间留出组成绩</p>
                  <dl class="metric-grid"><div><dt>MAE <span>℃</span></dt><dd class="num">{{ num(record.mae) }}</dd></div><div><dt>RMSE <span>℃</span></dt><dd class="num">{{ num(record.rmse) }}</dd></div><div><dt>R²</dt><dd class="num">{{ num(record.r2) }}</dd></div></dl>
                </section>
                <section class="generalization-summary" aria-labelledby="model-generalization-title">
                  <h3 id="model-generalization-title">跨时段泛化评估</h3>
                  <div><span>B 数据集验证</span><span class="note">暂无记录</span></div><div><span>C 数据集最终测试</span><span class="note">暂无记录</span></div>
                  <p class="note">空间留出成绩不代表在其他时段数据上的重建效果。</p>
                </section>
              </template>

              <template v-else-if="activeTab === 'metrics'">
                <h3 class="tab-section-title">空间留出验证结果</h3>
                <dl class="metric-grid"><div><dt>MAE <span>℃</span></dt><dd class="num">{{ num(record.mae) }}</dd></div><div><dt>RMSE <span>℃</span></dt><dd class="num">{{ num(record.rmse) }}</dd></div><div><dt>R²</dt><dd class="num">{{ num(record.r2) }}</dd></div></dl>
                <p class="note metric-hint">{{ MODELS.listHint }}</p>
                <dl class="comparison-list"><div><dt>空间选参组 MAE / ℃</dt><dd class="num">{{ num(record.ab?.mae_a) }}</dd></div><div><dt>空间留出组 MAE / ℃</dt><dd class="num">{{ num(record.ab?.mae_b) }}</dd></div><div><dt>MAE 差值（选参减留出）/ ℃</dt><dd class="num">{{ num(record.ab?.gap) }}</dd></div></dl>
                <p class="note">这里的分组是空间验证分组，与 A／B／C 时间数据集划分不同。</p>
                <details class="advanced-details">
                  <summary>查看逐折结果（{{ metricRows.length }} 条）</summary>
                  <div v-if="metricRows.length" class="table-scroll" role="region" aria-label="逐折验证结果" tabindex="0">
                    <table class="fold-table"><thead><tr><th scope="col">留出方式</th><th scope="col">区域与分组</th><th scope="col">样本数</th><th scope="col">MAE / ℃</th><th scope="col">RMSE / ℃</th><th scope="col">R²</th></tr></thead>
                      <tbody><tr v-for="(metric, index) in metricRows" :key="`${metric.fold}:${metric.tag}:${index}`"><td>{{ foldKind(metric.fold_kind) }}<span class="note fold-name">{{ metric.fold }}</span></td><td>{{ metric.region }}<span class="note fold-name">{{ spatialGroup(metric.group) }}</span></td><td class="num">{{ metric.n }}</td><td class="num">{{ num(metric.mae) }}</td><td class="num">{{ num(metric.rmse) }}</td><td class="num">{{ num(metric.r2) }}</td></tr></tbody>
                    </table>
                  </div><p v-else class="note">这份记录未包含逐折结果。</p>
                </details>
                <div class="context-note"><strong>跨时段评估暂无记录</strong><p>后续需固定模型版本，在独立目标数据与留出测点上计算误差。</p></div>
              </template>

              <template v-else>
                <h3 class="tab-section-title">模型配置</h3>
                <dl class="model-facts"><dt>趋势模型</dt><dd>{{ modelKind(record.trend_kind) }}</dd><dt>输入特征</dt><dd><span class="feature-list"><span v-for="group in record.feature_groups" :key="group" class="feature" :title="group">{{ featureLabels[group] ?? group }}</span></span></dd><dt>跨棚修正</dt><dd>{{ record.cross_shed ? '开启' : '关闭' }}</dd></dl>
                <h3 class="tab-section-title">残差修正参数</h3>
                <dl class="parameter-grid"><div><dt>距离权重幂次</dt><dd class="num">{{ record.metric.power }}</dd></div><div><dt>横向距离尺度</dt><dd class="num">{{ record.metric.lx }}</dd></div><div><dt>沿棚距离尺度</dt><dd class="num">{{ record.metric.ly }}</dd></div><div><dt>高度距离尺度</dt><dd class="num">{{ record.metric.lz }}</dd></div></dl>
                <details class="advanced-details">
                  <summary>趋势模型参数（{{ trendParameters.length }} 项）</summary>
                  <table v-if="trendParameters.length" class="parameter-table"><thead><tr><th scope="col">参数</th><th scope="col">保存值</th></tr></thead><tbody><tr v-for="[key, value] in trendParameters" :key="key"><td>{{ parameterLabel(`trend.${key}`) }}<code class="note technical-key">{{ key }}</code></td><td class="num">{{ parameterValue(value) }}</td></tr></tbody></table><p v-else class="note">这份记录未包含趋势模型参数。</p>
                </details>
                <details class="advanced-details">
                  <summary>参数搜索与可接受区间</summary><p class="note">搜索 {{ record.n_trials }} 次试验，随机种子 <span class="num">{{ record.seed }}</span>。</p>
                  <p v-if="record.tuned_keys.length" class="note">搜索维度：{{ record.tuned_keys.map(parameterLabel).join('、') }}。</p>
                  <table v-if="record.plateau.length" class="parameter-table"><thead><tr><th scope="col">参数</th><th scope="col">下界</th><th scope="col">上界</th></tr></thead><tbody><tr v-for="item in record.plateau" :key="item.dim"><td>{{ parameterLabel(item.dim) }}</td><td class="num">{{ item.lo }}</td><td class="num">{{ item.hi }}</td></tr></tbody></table><p v-else class="note">这份记录未包含可接受区间。</p>
                </details>
                <details class="advanced-details"><summary>来源与版本信息</summary><dl class="model-facts version-facts"><dt>记录编号</dt><dd class="num">{{ record.id }}</dd><dt>标定完成</dt><dd>{{ when(record.created_at) }}</dd><dt>保存时间</dt><dd>{{ when(record.saved_at) }}</dd><dt>计算版本</dt><dd>{{ record.tool_version || '未记录' }}</dd><dt>数据签名</dt><dd><code>{{ record.dataset_sig }}</code></dd><dt>特征签名</dt><dd><code>{{ record.groups_sig }}</code></dd></dl></details>
              </template>
            </div>
            <footer class="detail-actions">
              <div class="action-buttons">
                <button type="button" disabled aria-describedby="model-evaluation-status" :title="record.has_artifact ? '跨时段评估入口暂未开放' : '需先保存训练好的模型成品'">创建评估</button>
              </div>
              <p id="model-evaluation-status" class="note">{{ record.has_artifact ? '跨时段评估入口暂未开放，当前仅展示保存的空间验证结果。' : '此记录仅有参数，固定模型评估需先训练并保存成品。' }}</p>
              <p v-if="actionMessage" class="action-success" role="status">{{ actionMessage }}</p>
            </footer>
          </template>
        </template>
        <template v-else><h3>选择一个模型</h3><p class="note">查看它的训练来源、成品状态和评估结果。</p></template>
      </div>
    </ModalDialog>
    <ModalDialog v-if="editingRow" label="编辑模型" :busy="savingEdit" @close="editingRow = null">
      <form class="management-form" @submit.prevent="saveRename"><div class="drawer-top"><h2>编辑模型</h2><button type="button" aria-label="关闭编辑" :disabled="savingEdit" @click="editingRow = null">×</button></div><p class="note">修改模型名称，训练参数和成品由训练流程管理。</p><label>模型名称<input v-model="editingName" required maxlength="120" autofocus></label><p class="note">ID {{ editingRow.id }} · {{ editingRow.data_file }}</p><p v-if="managementError" role="alert" class="err">{{ managementError }}</p><footer><button type="button" :disabled="savingEdit" @click="editingRow = null">取消</button><button type="submit" class="primary" :disabled="savingEdit || !editingName.trim()">{{ savingEdit ? '保存中…' : '保存修改' }}</button></footer></form>
    </ModalDialog>
    <ModalDialog v-if="deleteRows.length" label="删除模型" :busy="deleting" @close="deleteRows = []">
      <div class="management-form"><div class="drawer-top"><h2>删除模型</h2><button type="button" aria-label="关闭删除确认" :disabled="deleting" @click="deleteRows = []">×</button></div><p>确认删除以下 {{ deleteRows.length }} 个模型？</p><ul class="delete-list"><li v-for="row in deleteRows" :key="row.id">{{ row.name }} <span class="note">ID {{ row.id }}</span></li></ul><p class="note">删除后无法从模型库恢复。被构场配置、实时会话或气象构场引用的模型不能删除。</p><p v-if="managementError" role="alert" class="err">{{ managementError }}</p><footer><button type="button" :disabled="deleting" @click="deleteRows = []">取消</button><button type="button" class="danger-fill" :disabled="deleting || deleteRows.some(row => row.is_current)" @click="confirmDelete">{{ deleting ? '删除中…' : '确认删除' }}</button></footer></div>
    </ModalDialog>
  </section>
</template>

<style scoped>
.models { display: flex; flex-direction: column; gap: 16px; padding: 8px 0 24px; }
.models-heading, .heading-actions, .panel-heading, .detail-heading, .section-heading { display: flex; align-items: center; justify-content: space-between; gap: var(--gap-s); }
.models-heading { align-items: flex-end; flex-wrap: wrap; padding-bottom: 2px; }
.models-heading h2 { margin-bottom: 4px; font-size: 26px; }
.breadcrumb { margin: 0 0 12px; color: var(--ink-muted); font-size: 14px; }
.models-heading p, .detail-actions p { margin-bottom: 0; }
.heading-actions { flex-wrap: wrap; }
.icon-button, .panel-heading h3 { display: inline-flex; align-items: center; gap: var(--gap-s); }
.row-meta, .feature-list, .action-buttons { display: flex; align-items: center; flex-wrap: wrap; gap: var(--gap-s); }
.session-note { margin-top: 4px; }
.status { display: inline-block; flex: none; padding: 1px 7px; border: 1px solid var(--steel); border-radius: var(--radius); color: var(--ink-muted); font-size: var(--size-note); line-height: 1.5; white-space: nowrap; }
.status { background: var(--training-warning-soft); color: var(--training-warning); border-color: color-mix(in srgb, var(--training-warning) 20%, var(--card)); }
.status.ready { background: var(--management-success-soft); border-color: color-mix(in srgb, var(--management-success) 20%, var(--card)); color: var(--management-success); }
.filter-panel { padding: 20px; border: 1px solid var(--management-line); border-radius: 5px; background: var(--management-tint); }
.filter-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px 28px; }
.filter-grid > label, .date-filter { display: grid; grid-template-columns: 74px minmax(0, 1fr); align-items: center; gap: 10px; font-size: 14px; }
.models input:not([type='checkbox']), .models select, .management-form input { width: 100%; min-width: 0; height: 38px; padding: 7px 10px; border: 1px solid var(--steel); border-radius: 4px; background: var(--card); color: var(--ink); font: inherit; font-size: 14px; }
.models input::placeholder { color: var(--ink-muted); }
.date-filter { grid-column: span 2; }
.date-filter > div { display: flex; align-items: center; gap: 6px; }
.date-filter input { padding: 6px; }
.date-filter > div > span { color: var(--ink-muted); }
.filter-actions { display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin-top: 16px; }
.filter-actions .err { margin-right: auto; }
.filter-actions button, .column-settings summary { display: inline-flex; align-items: center; gap: 6px; }
.models button, .management-form button { min-height: 36px; padding: 6px 14px; font-size: 14px; border-radius: 4px; }
.primary, .primary-link { background: var(--management-primary); color: var(--card); border-color: var(--management-primary); }
.management-toolbar, .toolbar-group { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.management-toolbar { justify-content: space-between; gap: 12px 24px; }
.toolbar-group button, .toolbar-group .button-link { display: inline-flex; align-items: center; justify-content: center; gap: 6px; }
.toolbar-group .button-link { min-height: 38px; padding: 6px 16px; font-size: 14px; }
.danger-outline { color: var(--management-danger); border-color: color-mix(in srgb, var(--management-danger) 50%, var(--steel)); }
.danger-fill { background: var(--management-danger); color: var(--card); border-color: var(--management-danger); }
.column-settings { position: relative; }
.column-settings summary { list-style: none; padding: 6px 14px; min-height: 36px; border: var(--rule); border-radius: 4px; background: var(--card); font-size: 14px; cursor: pointer; }
.column-settings > div { position: absolute; right: 0; top: calc(100% + 6px); z-index: 3; min-width: 160px; display: grid; gap: 10px; padding: 16px; border: var(--rule); border-radius: 4px; background: var(--card); box-shadow: var(--shadow); }
.column-settings label { display: flex; gap: 8px; align-items: center; font-size: 14px; }
input[type='checkbox'] { width: 16px; height: 16px; accent-color: var(--management-primary); cursor: pointer; }
.library-table-panel { border: 1px solid var(--management-line); border-radius: 5px; overflow: hidden; background: var(--card); }
.model-table { min-width: 1100px; table-layout: auto; }
.model-table th { padding: 12px 14px; font-size: 14px; color: var(--ink); background: var(--management-tint); border-bottom-color: var(--management-line); vertical-align: middle; }
.model-table td { padding: 16px 14px; font-size: 14px; vertical-align: middle; }
.model-table tbody tr.is-selected { background: var(--management-tint); }
.model-table tbody tr:hover { background: var(--management-tint); }
.model-table .check-column { width: 42px; padding-right: 8px; }
.model-table .name-column { min-width: 170px; max-width: 260px; }
.model-name { color: var(--management-primary); font-weight: var(--w-strong); text-decoration: none; overflow-wrap: anywhere; }
.model-name:hover, .row-actions a:hover { text-decoration: underline; }
.row-meta { margin-top: 4px; gap: 5px 10px; }
.source-name { display: block; max-width: 245px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.model-kind, .saved-column, .numeric { white-space: nowrap; }
.numeric { font-variant-numeric: tabular-nums; }
.state-caption { display: block; margin-top: 4px; color: var(--ink-muted); font-size: 13px; }
.operations-column { min-width: 150px; }
.row-actions { display: flex; align-items: center; flex-wrap: nowrap; gap: 14px; }
.row-actions a, .row-actions button { color: var(--management-primary); font: inherit; text-decoration: none; background: transparent; border: 0; padding: 0; min-height: 24px; white-space: nowrap; }
.row-actions button.danger-text { color: var(--management-danger); }
.row-actions button:disabled { color: var(--ink-muted); opacity: .6; }
.list-caption { margin: 0; padding: 12px 16px; color: var(--ink-muted); font-size: 13px; border-bottom: 1px solid var(--management-line); }
.pagination { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; padding: 14px 16px; font-size: 14px; }
.pagination > div > span { margin-left: 20px; }
.pagination strong { color: var(--management-primary); }
.pagination nav { display: flex; align-items: center; gap: 10px; }
.pagination select { width: auto; }
.pagination button { padding: 2px 10px; font-size: 22px; }
.page-number { display: grid; place-items: center; min-width: 34px; height: 34px; color: var(--card); background: var(--management-primary); border-radius: 4px; }
.import-status { margin: 0; font-size: 12px; }
.model-table .empty-cell { padding: 60px 20px; text-align: center; }
.empty-cell .icon { margin: 0 auto 14px; --icon-size: 36px; color: var(--ink-muted); }
.empty-cell strong { display: block; margin-bottom: 8px; font-size: 16px; }
.empty-cell p { color: var(--ink-muted); }
.action-feedback { margin: 0; padding: 10px 14px; background: var(--card); border: var(--rule); border-radius: 4px; }
.drawer-top { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
.drawer-top h2 { font-size: 22px; }
.drawer-top button { width: 32px; height: 32px; padding: 0; font-size: 24px; border: 0; background: transparent; color: var(--ink-muted); }
.management-form > label { display: grid; gap: 8px; margin: 20px 0 8px; font-size: 14px; font-weight: var(--w-strong); }
.management-form footer { display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px; }
.delete-list { max-height: 180px; overflow: auto; margin: 16px 0; padding-left: 22px; }
.model-detail-panel { min-width: 0; }
.detail-heading { align-items: flex-start; margin-bottom: var(--gap-m); }
.detail-heading > div { min-width: 0; }
.detail-heading h3 { overflow-wrap: anywhere; }
.detail-eyebrow { display: flex; align-items: center; gap: var(--gap-s); margin-bottom: 4px; }
.detail-tabs { display: flex; gap: var(--gap-s); flex-wrap: wrap; padding-bottom: var(--gap-m); margin-bottom: var(--gap-m); border-bottom: var(--rule); }
.detail-tabs button { font-size: var(--size-label); }
.detail-tabs button.active { color: var(--leaf); background: var(--leaf-soft); border-color: var(--leaf); }
.model-facts { display: grid; grid-template-columns: 78px minmax(0, 1fr); gap: 12px var(--gap-m); margin: 0; font-size: var(--size-label); }
.model-facts dt { color: var(--ink-muted); }
.model-facts dd { margin: 0; overflow-wrap: anywhere; }
.feature-list { gap: 4px var(--gap-s); }
.feature { color: var(--ink); border-bottom: 1px solid var(--steel); }
.context-note { border-left: 2px solid var(--leaf); background: var(--leaf-soft); margin-top: var(--gap-m); padding: 10px 12px; font-size: var(--size-note); overflow-wrap: anywhere; }
.context-note strong { display: block; font-weight: var(--w-strong); margin-bottom: 4px; }
.context-note p { margin: 0; }
.artifact-note { margin: var(--gap-m) 0 0; }
.summary-section { margin-top: var(--gap-l); }
.section-heading { margin-bottom: 4px; }
.text-button { color: var(--leaf); border: 0; padding: 3px 0; background: transparent; font-size: var(--size-note); white-space: nowrap; }
.metric-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--gap-s); margin: var(--gap-m) 0; }
.metric-grid > div { padding: var(--gap-s); background: var(--paper); min-width: 0; }
.metric-grid dt { color: var(--ink-muted); font-size: var(--size-note); }
.metric-grid dt span { margin-left: 3px; }
.metric-grid dd { margin: 4px 0 0; font-size: var(--size-h); overflow-wrap: anywhere; }
.generalization-summary { margin-top: var(--gap-m); }
.generalization-summary h3 { margin-bottom: var(--gap-s); }
.generalization-summary > div, .comparison-list > div { display: flex; justify-content: space-between; gap: var(--gap-m); padding: var(--gap-s) 0; border-bottom: var(--rule); font-size: var(--size-label); }
.generalization-summary p { margin: var(--gap-s) 0 0; }
.tab-section-title { margin-bottom: var(--gap-m); }
.metric-hint { margin: var(--gap-m) 0; }
.comparison-list { margin: 0 0 var(--gap-m); }
.comparison-list dt { color: var(--ink-muted); }
.comparison-list dd { margin: 0; flex: none; }
.advanced-details { margin-top: var(--gap-m); padding-top: var(--gap-m); border-top: var(--rule); }
.advanced-details summary { cursor: pointer; font-size: var(--size-label); font-weight: var(--w-strong); overflow-wrap: anywhere; }
.advanced-details[open] summary { margin-bottom: var(--gap-m); }
.table-scroll { overflow-x: auto; max-width: 100%; }
.fold-table { min-width: 610px; font-size: var(--size-note); }
.fold-table th, .fold-table td { padding: 8px 10px 8px 0; }
.fold-name, .technical-key { display: block; overflow-wrap: anywhere; }
.fold-name { font-size: var(--size-note); }
.parameter-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--gap-m); margin: 0; }
.parameter-grid > div { border-bottom: var(--rule); padding-bottom: var(--gap-s); }
.parameter-grid dt { color: var(--ink-muted); font-size: var(--size-note); }
.parameter-grid dd { margin: 4px 0 0; font-size: var(--size-h3); }
.model-facts + .tab-section-title { margin-top: var(--gap-l); }
.parameter-table { table-layout: fixed; font-size: var(--size-label); }
.parameter-table td, .parameter-table th { padding: 8px 10px 8px 0; overflow-wrap: anywhere; white-space: normal; }
.technical-key { font-family: var(--font-num); }
.version-facts code { font-family: var(--font-num); font-size: var(--size-note); }
.detail-actions { margin-top: var(--gap-l); padding-top: var(--gap-m); border-top: var(--rule); }
.action-buttons { margin-bottom: var(--gap-s); }
.action-buttons button { font-size: var(--size-label); }
.action-success { color: var(--leaf); margin-top: var(--gap-s); }
.detail-actions .err { margin-top: var(--gap-s); }
.err { color: var(--management-danger); overflow-wrap: anywhere; }
.library-error .err { margin-bottom: var(--gap-s); }
.detail-error, .detail-loading { padding: var(--gap-m) 0; min-height: 160px; }
.detail-error p { margin-bottom: var(--gap-m); }
.empty-library { display: flex; flex-direction: column; align-items: center; text-align: center; gap: var(--gap-m); padding: var(--gap-xl); }
.empty-library > .icon { --icon-size: 32px; color: var(--leaf); }
.empty-library p { margin-bottom: 0; }
.button-link { display: inline-flex; padding: 6px 12px; border-radius: var(--radius); border: 1px solid var(--steel); text-decoration: none; }
.primary-link { color: var(--card); background: var(--management-primary); border-color: var(--management-primary); }
@media (max-width: 1199px) { .filter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; } }
@media (max-width: 599px) {
  .date-filter { grid-column: auto; }
  .filter-grid { grid-template-columns: minmax(0, 1fr); }
  .filter-panel { padding: 14px; }
  .pagination nav { flex-wrap: wrap; }
  .model-facts { grid-template-columns: 65px minmax(0, 1fr); gap: var(--gap-s); }
  .metric-grid { gap: 4px; } .metric-grid > div { padding: 6px; } .metric-grid dd { font-size: var(--size-h3); }
  .detail-heading { flex-wrap: wrap; } .comparison-list > div { flex-wrap: wrap; gap: 4px var(--gap-s); }
}
</style>
