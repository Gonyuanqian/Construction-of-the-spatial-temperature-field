<script setup lang="ts">
import { computed, defineAsyncComponent, reactive, ref, watch } from 'vue'
import { warningsApi, type WarningCategory, type WarningEvent } from '../api/warnings'
import Card from '../components/Card.vue'
import Icon from '../components/Icon.vue'
import ModalDialog from '../components/ModalDialog.vue'
import { useAsync } from '../composables/useAsync'

const VolumeView = defineAsyncComponent(() => import('../scene/VolumeView.vue').then(module => module.default))
const categories = { all: '全部记录', temperature: '温度预警', device: '设备告警' } as const
const types = { high: '高温预警', low: '低温预警', expired: '任务过期', skipped: '任务跳过', failed: '执行失败' } as const
const origins: Record<string, string> = { manual: '用户操作', agriseek: 'AgriSeek', scheduler: '定时调度', system: '系统' }
const operations: Record<string, string> = { task_run: '执行任务', start: '启动设备', stop: '停止设备', auto_stop: '到时停止' }
const filters = reactive({ category: 'all' as WarningCategory | 'all', greenhouse: '', confirmation: 'all', days: '7' })
const page = ref(1)
const pageSize = 20
const selected = ref<WarningEvent | null>(null)
const snapshot = ref<WarningEvent | null>(null)
const acknowledging = ref(false)
const actionError = ref('')
const { data, loading, error, run } = useAsync(() => warningsApi.list({
  ...filters, limit: String(pageSize), offset: String((page.value - 1) * pageSize),
}))
const rows = computed(() => data.value?.items ?? [])
const greenhouses = computed(() => data.value?.greenhouses ?? [])
const pages = computed(() => Math.max(1, Math.ceil((data.value?.total ?? 0) / pageSize)))
const canOpenControl = computed(() => greenhouses.value.some(g => g.id === selected.value?.design_id && !g.archived))
const dateTime = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})
const when = (time: string | null) => time ? dateTime.format(new Date(time)) : '暂无'
const degrees = (number: number | null) => number === null ? '暂无' : `${number.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} °C`
const state = (event: WarningEvent) => event.end_reason === 'recovered' ? '已恢复'
  : event.end_reason === 'rule_changed' ? '阈值已变更' : '异常中'
const reason = (event: WarningEvent) => event.result?.detail || event.result?.reason || '暂无原因记录'
const same = (a: WarningEvent | null, b: WarningEvent) => a?.id === b.id && a.category === b.category

async function refresh() {
  await run()
  if (!error.value && page.value > pages.value) page.value = pages.value
}
watch(filters, () => { page.value = 1; selected.value = null; actionError.value = '' }, { flush: 'sync' })
watch([filters, page], refresh, { immediate: true })
watch(rows, items => {
  const current = selected.value
  selected.value = (current ? items.find(item => same(current, item)) : items[0]) ?? null
})

function reset() {
  Object.assign(filters, { category: 'all', greenhouse: '', confirmation: 'all', days: '7' })
}
function select(item: WarningEvent) {
  selected.value = item
  actionError.value = ''
}
async function acknowledge() {
  const item = selected.value
  if (!item || item.acknowledged_at || acknowledging.value) return
  acknowledging.value = true
  actionError.value = ''
  try {
    const result = await warningsApi.acknowledge(item)
    if (same(selected.value, item)) selected.value = result
    await refresh()
  } catch (cause) {
    actionError.value = cause instanceof Error ? cause.message : '确认失败，请重试。'
  } finally {
    acknowledging.value = false
  }
}
</script>

<template>
  <section class="alerts-log">
    <header class="log-header">
      <h1>预警日志</h1>
      <button type="button" class="log-button" :disabled="loading" @click="refresh"><Icon name="reset" />刷新</button>
    </header>
    <div class="category-tabs" role="group" aria-label="预警来源">
      <button v-for="(label, key) in categories" :key="key" type="button" :aria-pressed="filters.category === key"
              @click="filters.category = key">{{ label }}</button>
    </div>
    <div class="filters">
      <label>时间
        <select v-model="filters.days"><option value="1">今天</option><option value="7">最近 7 天</option><option value="30">最近 30 天</option><option value="0">全部时间</option></select>
      </label>
      <label>棚体
        <select v-model="filters.greenhouse">
          <option value="">全部棚体</option>
          <option v-for="house in greenhouses" :key="house.id" :value="house.id">{{ house.name }}{{ house.archived ? '（已删除）' : '' }}</option>
          <option value="custom">自定义棚体</option>
        </select>
      </label>
      <label>确认状态
        <select v-model="filters.confirmation"><option value="all">全部状态</option><option value="pending">待确认</option><option value="confirmed">已确认</option></select>
      </label>
      <button type="button" class="reset-button" @click="reset">重置</button>
    </div>
    <p v-if="error" role="alert" class="log-error">{{ error }}</p>
    <p v-if="actionError" role="alert" class="log-error">{{ actionError }}</p>
    <div class="log-columns" :class="{ 'has-detail': selected }">
      <Card class="event-card">
        <div class="table-scroll">
          <table :aria-busy="loading" aria-label="预警记录">
            <thead><tr><th>触发时间</th><th>棚体 / 设备</th><th>预警类型</th><th>事件概况</th><th>确认状态</th></tr></thead>
            <tbody>
              <tr v-for="item in rows" :key="`${item.category}-${item.id}`" :class="{ selected: same(selected, item) }" @click="select(item)">
                <td><button type="button" class="row-link num" :aria-label="`查看 ${item.greenhouse_name} ${types[item.alert_type]} 详情`"
                            :aria-current="same(selected, item) ? 'true' : undefined" @click.stop="select(item)">{{ when(item.event_time) }}</button></td>
                <td class="object-cell">{{ item.greenhouse_name }}<span v-if="item.device_name">{{ item.device_name }}</span></td>
                <td><span class="log-badge" :class="item.alert_type">{{ types[item.alert_type] }}</span></td>
                <td>{{ item.category === 'temperature' ? `${degrees(item.trigger_value)} · ${state(item)}` : reason(item) }}</td>
                <td><span class="log-badge" :class="{ pending: !item.acknowledged_at }">{{ item.acknowledged_at ? '已确认' : '待确认' }}</span></td>
              </tr>
              <tr v-if="!rows.length"><td colspan="5" class="empty-row">{{ loading ? '正在读取记录…' : error ? '记录读取失败' : '当前筛选条件下暂无预警记录' }}</td></tr>
            </tbody>
          </table>
        </div>
        <footer class="table-footer">
          <span>共 {{ data?.total ?? 0 }} 条记录</span>
          <span class="pagination"><button class="log-button" type="button" :disabled="page <= 1 || loading" @click="page--">上一页</button>
            <span class="num">{{ page }} / {{ pages }}</span>
            <button class="log-button" type="button" :disabled="page >= pages || loading" @click="page++">下一页</button></span>
        </footer>
      </Card>

      <Card v-if="selected" class="detail-card">
        <header><h2>预警详情</h2><button type="button" class="reset-button" aria-label="关闭预警详情" @click="selected = null">×</button></header>
        <div class="detail-summary"><h3>{{ types[selected.alert_type] }}</h3>
          <span class="log-badge" :class="selected.alert_type">{{ selected.category === 'temperature' ? state(selected) : '模拟设备' }}</span>
        </div>
        <dl>
          <div><dt>棚体</dt><dd>{{ selected.greenhouse_name }}</dd></div>
          <div><dt>来源</dt><dd>{{ selected.category === 'temperature' ? '实时监测 · 模型估温' : `温室控制 · ${origins[selected.source] ?? selected.source}` }}</dd></div>
          <div><dt>首次触发</dt><dd class="num">{{ when(selected.event_time) }}</dd></div>
          <template v-if="selected.category === 'temperature'">
            <div><dt>触发温度</dt><dd class="num">{{ degrees(selected.trigger_value) }}</dd></div>
            <div><dt>触发阈值</dt><dd class="num">{{ selected.alert_type === 'high' ? '≥' : '≤' }} {{ degrees(selected.threshold_value) }}</dd></div>
            <div><dt>期间极值</dt><dd class="num">{{ degrees(selected.extreme_value) }}</dd></div>
            <div v-if="selected.ended_at"><dt>{{ selected.end_reason === 'recovered' ? '恢复时间' : '结束时间' }}</dt><dd class="num">{{ when(selected.ended_at) }}</dd></div>
            <div v-else><dt>最近超限</dt><dd class="num">{{ when(selected.last_seen_at) }}</dd></div>
          </template>
          <template v-else>
            <div><dt>设备</dt><dd>{{ selected.device_name || '全棚' }}</dd></div>
            <div v-if="selected.operation"><dt>操作</dt><dd>{{ operations[selected.operation] ?? selected.operation }}</dd></div>
            <div v-if="selected.result?.task_id"><dt>任务编号</dt><dd class="num">{{ selected.result.task_id }}</dd></div>
            <div><dt>原因</dt><dd>{{ reason(selected) }}</dd></div>
          </template>
          <div v-if="selected.acknowledged_at"><dt>已阅</dt><dd>{{ selected.acknowledged_by }}<br>{{ when(selected.acknowledged_at) }}</dd></div>
        </dl>
        <footer>
          <button v-if="selected.trigger_frame_id" type="button" class="log-button" @click="snapshot = selected">查看构场</button>
          <RouterLink v-else-if="canOpenControl" class="log-button" :to="{ name: 'greenhouse-control', query: { greenhouse: selected.design_id, tab: 'alarms' } }">查看温室控制</RouterLink>
          <button v-if="!selected.acknowledged_at" type="button" class="log-button primary" :disabled="acknowledging" @click="acknowledge">{{ acknowledging ? '确认中…' : '确认已阅' }}</button>
        </footer>
      </Card>
    </div>
    <ModalDialog v-if="snapshot" label="预警触发时的温度场" wide @close="snapshot = null">
      <div class="snapshot-panel">
        <header><div><h2>预警触发时的温度场</h2><p>{{ snapshot.greenhouse_name }} · {{ when(snapshot.event_time) }}</p></div>
          <button type="button" class="log-button" @click="snapshot = null">关闭</button></header>
        <VolumeView :key="snapshot.trigger_frame_id!" source="live" :session-id="snapshot.trigger_frame_id!" :t-index="0"
                    clock-time="" :show-clock="true" :show-notes="false" />
      </div>
    </ModalDialog>
  </section>
</template>

<style scoped>
.alerts-log { display: grid; align-content: start; gap: 14px; padding-bottom: 22px; min-width: 0; }
.log-header,.detail-card header,.snapshot-panel header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.log-header h1 { margin: 0; font-size: 27px; }
.category-tabs { display: flex; gap: 17px; border-bottom: var(--rule); }
.category-tabs button { padding: 8px 10px; color: var(--ink-muted); background: none; border: 0; border-bottom: 2px solid transparent; font: inherit; cursor: pointer; }
.category-tabs button[aria-pressed=true] { border-color: var(--edge); color: var(--ink); font-weight: var(--w-strong); }
.filters { display: flex; align-items: end; gap: 10px; flex-wrap: wrap; }
.filters label { display: grid; gap: 4px; color: var(--ink-muted); font-size: 12px; min-width: 126px; }
.filters select,.log-button { min-height: 34px; padding: 5px 9px; border: 1px solid var(--steel); border-radius: var(--radius); background: var(--card); color: var(--ink); font: inherit; font-size: 13px; }
.filters select { max-width: min(80vw, 230px); }
.log-button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; text-decoration: none; white-space: nowrap; cursor: pointer; }
.log-button:hover { border-color: var(--edge); }
.log-button:disabled { opacity: .55; cursor: default; }
.log-button .icon { --icon-size: 15px; }
.reset-button { border: 0; background: transparent; color: var(--edge); padding: 6px; font: inherit; cursor: pointer; }
.log-columns { display: grid; grid-template-columns: minmax(0, 1fr); align-items: start; gap: 12px; }
.log-columns.has-detail { grid-template-columns: minmax(0, 2.25fr) minmax(260px, 1fr); }
.event-card,.detail-card { min-width: 0; padding: 0; border: var(--rule); overflow: hidden; }
.table-scroll { overflow: auto; min-height: 260px; }
table { width: 100%; min-width: 580px; border-collapse: collapse; text-align: left; font-size: 13px; }
th,td { padding: 11px 10px; border-bottom: var(--rule); }
th { background: var(--card-2); color: var(--ink-muted); white-space: nowrap; }
tbody tr:not(:has(.empty-row)) { cursor: pointer; }
tbody tr.selected { background: color-mix(in srgb, var(--interact) 19%, var(--card)); }
tbody tr:hover { background: color-mix(in srgb, var(--interact) 12%, var(--card)); }
.row-link { padding: 0; border: 0; background: transparent; color: var(--ink); font: inherit; cursor: pointer; text-align: left; }
.row-link:hover { color: var(--edge); }
.object-cell span { display: block; color: var(--ink-muted); }
.log-badge { display: inline-block; padding: 3px 7px; border-radius: 4px; background: var(--card-2); color: var(--ink-muted); white-space: nowrap; font-size: 12px; font-weight: var(--w-strong); }
.log-badge.high,.log-badge.pending,.log-badge.expired,.log-badge.skipped,.log-badge.failed { color: var(--bar); background: color-mix(in srgb, var(--bar) 14%, var(--card)); }
.log-badge.low { color: var(--edge); background: color-mix(in srgb, var(--edge) 12%, var(--card)); }
.empty-row { text-align: center; color: var(--ink-muted); padding: 24px 12px; }
.table-footer,.detail-card footer { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; padding: 10px 12px; border-top: var(--rule); font-size: 13px; color: var(--ink-muted); }
.pagination { display: flex; gap: 8px; align-items: center; }
.detail-card header { background: var(--card-2); padding: 10px 13px; border-bottom: var(--rule); }
.detail-card h2,.snapshot-panel h2 { font-size: 17px; margin: 0; }
.detail-summary { display: flex; align-items: center; gap: 8px; padding: 12px 13px 2px; }
.detail-summary h3 { margin: 0; font-size: 16px; }
.detail-card dl { margin: 8px 13px 12px; font-size: 13px; }
.detail-card dl div { display: grid; grid-template-columns: 5em minmax(0, 1fr); gap: 7px; padding-block: 8px; border-bottom: var(--rule); }
.detail-card dt,.snapshot-panel p { color: var(--ink-muted); }
.detail-card dd { margin: 0; overflow-wrap: anywhere; }
.detail-card footer { justify-content: flex-end; }
.primary { background: var(--interact); color: var(--on-face); border-color: var(--interact); }
.log-error { margin: 0; color: var(--bar); }
.snapshot-panel p { margin: 4px 0 0; }
@media (max-width: 1020px) { .log-columns.has-detail { grid-template-columns: minmax(0, 1fr); } }
</style>
