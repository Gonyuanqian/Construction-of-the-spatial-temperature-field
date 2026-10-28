<script setup lang="ts">
/** 列表与详情同屏；查看由路由确定，选用模型单独提交。 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchModelDetail, fetchModels, setCurrentModel } from '../api/models'
import type { ModelRowPayload, ParamValue } from '../api/types'
import Card from '../components/Card.vue'
import Icon from '../components/Icon.vue'
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
const selectingId = ref<number | null>(null)
const actionError = ref('')
const actionMessage = ref('')
const routeId = computed(() => {
  if (route.name !== 'model-detail') return null
  const id = Number(route.params.id)
  return Number.isSafeInteger(id) && id > 0 ? id : null
})
const invalidRoute = computed(() => route.name === 'model-detail' && routeId.value === null)
const rows = computed(() => models.data.value?.rows ?? [])
const selectedRow = computed(() => rows.value.find(row => row.id === selectedId.value) ?? null)
const currentRow = computed(() => rows.value.find(row => row.id === models.data.value?.current_id) ?? null)
// 防止切换期间把上一模型的响应显示在新模型标题下。
const record = computed(() => detail.data.value?.id === selectedId.value ? detail.data.value : null)
const metricRows = computed(() => record.value?.metrics ?? [])
const trendParameters = computed(() => Object.entries(record.value?.trend_params ?? {}))
const currentIsViewed = computed(() => selectedRow.value !== null && selectedRow.value.id === currentRow.value?.id)

function chooseDefault(): void {
  if (route.name === 'model-detail') return
  if (rows.value.some(row => row.id === selectedId.value)) return
  selectedId.value = currentRow.value?.id ?? rows.value[0]?.id ?? null
}
async function refreshModels(): Promise<void> {
  await models.run()
  if (!models.error.value) chooseDefault()
}
watch(routeId, id => {
  if (route.name === 'model-detail') selectedId.value = id
  else chooseDefault()
}, { immediate: true })
watch(selectedId, id => {
  activeTab.value = 'overview'
  actionError.value = ''
  actionMessage.value = ''
  if (id !== null) void detail.run()
}, { immediate: true })
onMounted(() => { void refreshModels() })

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
async function selectCurrent(row: ModelRowPayload, openField = false): Promise<void> {
  if (!row.compatible || selectingId.value !== null || (row.is_current && !openField)) return
  selectingId.value = row.id
  actionError.value = ''
  actionMessage.value = ''
  try {
    // 显式选用保存记录，同时解除未保存训练结果的优先使用。
    await setCurrentModel(row.id)
    const payload = models.data.value
    if (payload) models.data.value = {
      ...payload, current_id: row.id,
      rows: payload.rows.map(item => ({ ...item, is_current: item.id === row.id })),
    }
    actionMessage.value = `已将「${row.name}」设为工作区模型。`
    await refreshModels()
    if (openField) await router.push('/field')
  } catch (error) {
    actionError.value = `选用「${row.name}」失败：${error instanceof Error ? error.message : String(error)}`
  } finally { selectingId.value = null }
}
</script>

<template>
  <section class="models" aria-labelledby="models-title">
    <header class="models-heading">
      <div><h2 id="models-title">{{ MODELS.title }}</h2><p class="note">查看训练来源、管理模型成品与评估结果</p></div>
      <div class="heading-actions">
        <span v-if="models.data.value" class="note">共 {{ rows.length }} 个模型</span>
        <button type="button" class="icon-button" :disabled="models.loading.value || selectingId !== null" @click="refreshModels"><Icon name="reset" />{{ models.loading.value ? '读取中' : '刷新列表' }}</button>
      </div>
    </header>
    <Card v-if="models.error.value" class="library-error">
      <p class="err" role="alert">{{ models.error.value }}</p>
      <p v-if="models.data.value" class="note">以下保留上次读取的列表，可点击刷新重试。</p>
      <button v-else type="button" :disabled="models.loading.value" @click="refreshModels">重新加载</button>
    </Card>
    <Card v-if="models.data.value" class="workspace-card">
      <div class="workspace-current"><span class="note">当前工作区模型</span>
        <template v-if="currentRow"><strong>{{ currentRow.name }}</strong><span class="status" :class="{ ready: currentRow.has_artifact }">{{ currentRow.has_artifact ? MODELS.artifactReady : MODELS.notSolid }}</span></template>
        <span v-else>尚未选用模型</span>
      </div>
      <p class="note session-note">查看详情不会切换模型；已有实时会话继续使用其绑定的模型。</p>
    </Card>
    <Card v-if="models.loading.value && !models.data.value" class="loading-card" role="status">正在读取模型库…</Card>
    <Card v-else-if="models.data.value && rows.length === 0 && route.name !== 'model-detail'" class="empty-library">
      <Icon name="cube" /><h3>{{ MODELS.empty }}</h3><p class="note">{{ MODELS.emptyWhy }}</p>
      <RouterLink class="button-link primary-link" to="/train">前往模型训练</RouterLink>
    </Card>

    <div v-if="rows.length > 0 || route.name === 'model-detail'" class="model-workbench">
      <Card class="model-list-panel" :aria-busy="models.loading.value">
        <div class="panel-heading"><h3><Icon name="cube" />已保存的模型</h3><span class="note">选择一项查看详情</span></div>
        <table v-if="rows.length" class="model-table" aria-label="模型列表">
          <colgroup><col class="name-column"><col class="source-column"><col class="state-column"></colgroup>
          <thead><tr><th scope="col">模型名称</th><th scope="col">训练来源</th><th scope="col">成品与状态</th></tr></thead>
          <tbody><tr v-for="row in rows" :key="row.id" :class="{ 'is-selected': row.id === selectedId }">
            <td>
              <RouterLink :to="`/models/${row.id}`" class="model-name" :aria-current="row.id === selectedId ? 'true' : undefined" @click="activeTab = 'overview'">{{ row.name }}</RouterLink>
              <div class="row-meta"><span class="note">ID <span class="num">{{ row.id }}</span></span><span v-if="row.is_current" class="status current-status">{{ MODELS.current }}</span></div>
              <p class="note saved-at">保存于 {{ when(row.saved_at) }}</p>
            </td>
            <td><span class="source-name">{{ row.data_file }}</span><span class="note data-period">{{ when(row.data_start) }}<br>至 {{ when(row.data_end) }}</span></td>
            <td>
              <span class="status" :class="{ ready: row.has_artifact }">{{ row.has_artifact ? MODELS.artifactReady : MODELS.notSolid }}</span>
              <span v-if="!row.compatible" class="state-caption" :title="row.why">当前配置不可用</span>
              <span v-else-if="row.borrowed" class="state-caption" :title="row.why">{{ MODELS.differentSource }}</span>
              <span v-else class="state-caption">当前数据适配</span>
            </td>
          </tr></tbody>
        </table>
        <p v-else class="note list-placeholder">{{ models.loading.value ? '正在读取模型列表…' : '暂无可显示的模型记录。' }}</p>
        <p class="note list-caption">左侧选中项用于查看，工作区模型由“{{ MODELS.setCurrent }}”操作确定。</p>
      </Card>

      <Card class="model-detail-panel" :aria-busy="detail.loading.value" aria-label="模型详情">
        <template v-if="invalidRoute"><h3>模型编号无效</h3><p class="note">请选择左侧模型记录。</p><RouterLink to="/models">返回模型列表</RouterLink></template>
        <template v-else-if="selectedId !== null">
          <div class="detail-heading"><div><p class="note detail-eyebrow">模型详情 <span class="num">ID {{ selectedId }}</span></p><h3>{{ selectedRow?.name ?? record?.name ?? '正在读取模型…' }}</h3></div><span v-if="selectedRow?.is_current" class="status current-status">{{ MODELS.current }}</span></div>
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
                <button type="button" class="on" :disabled="!selectedRow?.compatible || selectingId !== null" @click="selectedRow && selectCurrent(selectedRow, true)">{{ selectingId === selectedId ? '正在选用…' : '用于构场' }}</button>
                <button type="button" :disabled="!selectedRow?.compatible || currentIsViewed || selectingId !== null" @click="selectedRow && selectCurrent(selectedRow)">{{ currentIsViewed ? '工作区已选用' : MODELS.setCurrent }}</button>
                <button type="button" disabled aria-describedby="model-evaluation-status" :title="record.has_artifact ? '跨时段评估入口暂未开放' : '需先保存训练好的模型成品'">创建评估</button>
              </div>
              <p id="model-evaluation-status" class="note">{{ record.has_artifact ? '跨时段评估入口暂未开放，当前仅展示保存的空间验证结果。' : '此记录仅有参数，固定模型评估需先训练并保存成品。' }}</p>
              <p v-if="actionError" class="err" role="alert">{{ actionError }}</p><p v-else-if="actionMessage" class="action-success" role="status">{{ actionMessage }}</p>
            </footer>
          </template>
        </template>
        <template v-else><h3>选择一个模型</h3><p class="note">查看它的训练来源、成品状态和评估结果。</p></template>
      </Card>
    </div>
  </section>
</template>

<style scoped>
.models { display: flex; flex-direction: column; gap: var(--gap-m); padding-bottom: var(--gap-m); }
.models-heading, .heading-actions, .panel-heading, .detail-heading, .section-heading { display: flex; align-items: center; justify-content: space-between; gap: var(--gap-s); }
.models-heading { align-items: flex-start; flex-wrap: wrap; }
.models-heading h2 { margin-bottom: 4px; }
.models-heading p, .workspace-card p, .detail-actions p { margin-bottom: 0; }
.heading-actions { flex-wrap: wrap; }
.icon-button, .panel-heading h3 { display: inline-flex; align-items: center; gap: var(--gap-s); }
.workspace-current, .row-meta, .feature-list, .action-buttons { display: flex; align-items: center; flex-wrap: wrap; gap: var(--gap-s); }
.workspace-current strong { font-weight: var(--w-strong); overflow-wrap: anywhere; }
.session-note { margin-top: 4px; }
.status { display: inline-block; flex: none; padding: 1px 7px; border: 1px solid var(--steel); border-radius: var(--radius); color: var(--ink-muted); font-size: var(--size-note); line-height: 1.5; white-space: nowrap; }
.status.ready, .current-status { background: var(--leaf-soft); border-color: var(--leaf-soft); color: var(--leaf); }
.model-workbench { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); align-items: start; gap: var(--gap-m); min-width: 0; }
.model-list-panel, .model-detail-panel { min-width: 0; }
.model-list-panel { position: sticky; top: 0; }
.panel-heading { margin-bottom: var(--gap-m); flex-wrap: wrap; }
.model-table { table-layout: fixed; }
.model-table .name-column { width: 32%; }
.model-table .source-column { width: 44%; }
.model-table .state-column { width: 24%; }
.model-table th { padding: 8px; color: var(--ink-muted); font-size: var(--size-label); background: var(--paper); white-space: normal; }
.model-table td { padding: 14px 8px; font-size: var(--size-label); }
.model-table tr.is-selected td { background: var(--leaf-soft); }
.model-name { color: var(--leaf); font-weight: var(--w-strong); text-decoration-thickness: 1px; text-underline-offset: 3px; overflow-wrap: anywhere; }
.row-meta { margin-top: var(--gap-s); gap: 4px var(--gap-s); }
.row-meta .status { font-size: var(--size-note); }
.saved-at { margin: 6px 0 0; }
.source-name { display: block; overflow-wrap: anywhere; }
.data-period { display: block; margin-top: var(--gap-s); }
.state-caption { display: block; margin-top: var(--gap-s); color: var(--ink-muted); font-size: var(--size-note); overflow-wrap: anywhere; }
.list-caption { margin: var(--gap-m) 0 0; }
.list-placeholder { padding: var(--gap-m) 0; }
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
.err { color: var(--ink); overflow-wrap: anywhere; }
.library-error .err { margin-bottom: var(--gap-s); }
.detail-error, .detail-loading { padding: var(--gap-m) 0; min-height: 160px; }
.detail-error p { margin-bottom: var(--gap-m); }
.empty-library { display: flex; flex-direction: column; align-items: center; text-align: center; gap: var(--gap-m); padding: var(--gap-xl); }
.empty-library > .icon { --icon-size: 32px; color: var(--leaf); }
.empty-library p { margin-bottom: 0; }
.button-link { display: inline-flex; padding: 6px 12px; border-radius: var(--radius); border: 1px solid var(--steel); text-decoration: none; }
.primary-link { color: var(--on-face); background: var(--interact); border-color: var(--interact); }
@media (max-width: 1199px) { .model-workbench { grid-template-columns: minmax(0, 1fr); } .model-list-panel { position: static; } }
@media (max-width: 599px) {
  .model-table .name-column { width: 31%; } .model-table .source-column { width: 40%; } .model-table .state-column { width: 29%; }
  .model-table th, .model-table td { padding: 8px 4px; font-size: var(--size-note); }
  .model-table .status { white-space: normal; }
  .model-facts { grid-template-columns: 65px minmax(0, 1fr); gap: var(--gap-s); }
  .metric-grid { gap: 4px; } .metric-grid > div { padding: 6px; } .metric-grid dd { font-size: var(--size-h3); }
  .detail-heading { flex-wrap: wrap; } .comparison-list > div { flex-wrap: wrap; gap: 4px var(--gap-s); }
}
</style>
