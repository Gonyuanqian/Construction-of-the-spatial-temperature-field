<script setup lang="ts">
import { computed, onMounted } from 'vue'
import type { EChartsOption } from 'echarts'
import { getJson } from '../api/client'
import type { DatasetPayload, TimeseriesPayload } from '../api/types'
import EChart from '../charts/EChart.vue'
import Card from '../components/Card.vue'
import StatCard from '../components/StatCard.vue'
import StatRow from '../components/StatRow.vue'
import { useAsync } from '../composables/useAsync'
import { readPalette } from '../design/palette'
import { tempStops } from '../charts/scale'
import { makeOverviewDemo } from '../demo/overview'

const props = withDefaults(defineProps<{ demo?: boolean }>(), { demo: false })
const demoData = props.demo ? makeOverviewDemo() : null

const ds = useAsync(() => demoData ? Promise.resolve(demoData.dataset) : getJson<DatasetPayload>('/api/dataset'))
const ts = useAsync(() => demoData ? Promise.resolve(demoData.timeseries) : getJson<TimeseriesPayload>('/api/dataset/timeseries'))
const p = readPalette()
onMounted(async () => { await ds.run(); if (ds.data.value) void ts.run() })
const checks = computed(() => ds.data.value?.checks ?? [])
// 日历只标记后端给出的采集日期覆盖，不推断逐日告警。
const calendar = computed(() => {
  const data = ds.data.value
  const end = data?.time_end?.slice(0, 10)
  if (!end || !/^\d{4}-\d{2}-\d{2}$/.test(end)) return null
  const date = new Date(`${end}T00:00:00`)
  if (!Number.isFinite(date.getTime())) return null
  const year = date.getFullYear(), month = date.getMonth()
  const offset = (new Date(year, month, 1).getDay() + 6) % 7
  const count = new Date(year, month + 1, 0).getDate()
  return { label: end.slice(0, 7), days: Array.from({ length: 42 }, (_, i) => {
    const day = i - offset + 1
    const iso = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    return { day: day > 0 && day <= count ? day : null, covered: iso >= (data?.time_start?.slice(0, 10) ?? '') && iso <= end }
  }) }
})
const chartBase = { backgroundColor: 'transparent', textStyle: { color: p.inkMuted, fontSize: p.chartAxis }, animationDuration: 320, animationDurationUpdate: 600 }
const ring = computed<EChartsOption>(() => ({
  ...chartBase, tooltip: { trigger: 'item' }, legend: { bottom: 0, textStyle: { color: p.inkMuted } },
  series: [{ type: 'pie', showEmptyCircle: false, radius: ['64%', '82%'], center: ['50%', '43%'], label: { show: false },
    data: checks.value.map(c => ({ name: c.name, value: 1, itemStyle: { color: c.status === 'ok' ? p.leaf : p.bar } })) }],
  graphic: [{ type: 'text', left: 'center', top: '34%', style: { text: ds.data.value ? '数据检查' : '等待数据', fill: p.ink, fontSize: 18 } }],
}))
const line = computed<EChartsOption>(() => ({
  ...chartBase, color: [p.leaf, p.layerMid, p.layerLow, p.layerTop], tooltip: { trigger: 'axis' },
  grid: { top: 35, left: 45, right: 20, bottom: 42 }, legend: { top: 0, textStyle: { color: p.inkMuted } },
  xAxis: { type: 'category', data: ts.data.value?.time ?? [], axisLabel: { color: p.inkMuted, formatter: (v: string) => v.slice(5, 16).replace('T', ' ') }, axisLine: { lineStyle: { color: p.steel } } },
  yAxis: { type: 'value', name: '°C', scale: true, axisLabel: { color: p.inkMuted }, splitLine: { lineStyle: { color: p.steel, type: 'dashed' } } },
  series: Object.entries(ts.data.value?.shed_mean ?? {}).map(([name, data]) => ({ type: 'line', name, data, smooth: true, showSymbol: false, connectNulls: false, lineStyle: { width: 2 }, areaStyle: { opacity: .06 } })),
}))
const heat = computed<EChartsOption>(() => {
  const data = ds.data.value
  const sheds = Object.keys(data?.sheds ?? {})
  const positions = data?.positions?.map(x => x.id) ?? []
  const temperatures = (data?.temperature ?? []).flatMap(t => t.mean !== null && Number.isFinite(t.mean) ? [t.mean] : [])
  const low = temperatures.length ? Math.floor(Math.min(...temperatures)) : 0
  const high = temperatures.length ? Math.max(low + 1, Math.ceil(Math.max(...temperatures))) : 50
  return { ...chartBase, tooltip: { position: 'top' }, grid: { top: 10, left: 65, right: 20, bottom: 80 },
    xAxis: { type: 'category', data: positions.map(id => data?.point_codes[id] ?? id), axisLabel: { color: p.inkMuted } },
    yAxis: { type: 'category', data: sheds, axisLabel: { color: p.inkMuted } },
    visualMap: { type: 'continuous', min: low, max: high, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, text: [`${high}°C`, `${low}°C`], textStyle: { color: p.inkMuted }, inRange: { color: tempStops() } },
    series: [{ type: 'heatmap', data: (data?.temperature ?? []).filter(t => t.mean !== null).map(t => [positions.indexOf(t.position), sheds.indexOf(t.shed), t.mean]), itemStyle: { borderWidth: 3, borderColor: p.paper }, emphasis: { itemStyle: { borderColor: p.leaf } } }],
  }
})
const bars = computed<EChartsOption>(() => ({
  ...chartBase, tooltip: { trigger: 'axis' }, grid: { top: 10, bottom: 25, left: 75, right: 30 },
  xAxis: { type: 'value', minInterval: 1, axisLabel: { color: p.inkMuted }, splitLine: { lineStyle: { color: p.steel } } },
  yAxis: { type: 'category', data: Object.keys(ds.data.value?.sheds ?? {}), axisLabel: { color: p.inkMuted } },
  series: [{ type: 'bar', barWidth: 12, data: Object.values(ds.data.value?.sheds ?? {}), itemStyle: { color: p.leaf, borderRadius: 6 }, label: { show: true, position: 'right', color: p.ink } }],
}))
</script>

<template>
  <section class="overview">
    <div class="overview-heading"><div><p class="eyebrow">SPATIAL THERMAL FIELD / MISSION CONTROL</p><h2>温度场作战总览</h2></div><RouterLink class="live-entry" to="/live">进入实时监测 ↗</RouterLink></div>
    <div v-if="demo" class="demo-banner" role="status"><div><strong>演示数据预览</strong><span>当前指标、温度曲线和检查结果均为模拟数据，仅用于查看 UI 效果。</span></div><RouterLink to="/overview">切换真实数据</RouterLink></div>
    <div v-else class="preview-actions"><RouterLink class="live-entry" to="/overview?demo=1">查看有数据的演示界面</RouterLink></div>
    <p v-if="ds.error.value" class="note" role="status">总览暂未取得数据，请确认后端已启动，并在数据导入页上传数据集。</p>
    <StatRow>
      <StatCard label="采集样本 / SAMPLES" :value="ds.data.value ? String(ds.data.value.n_times) : '—'" />
      <StatCard label="数据维度 / CHANNELS" :value="ds.data.value ? String(ds.data.value.n_columns) : '—'" />
      <StatCard label="缺失样本 / MISSING" :value="ds.data.value ? String(ds.data.value.n_missing ?? '—') : '—'" />
      <StatCard label="重复时刻 / DUPLICATES" :value="ds.data.value ? String(ds.data.value.n_dup_times ?? '—') : '—'" />
    </StatRow>
    <div class="dashboard-grid">
      <Card class="integrity"><h3>01 / 数据检查状态</h3><EChart :option="ring" height="230px" /><p class="note">每个扇区对应一项检查，蓝色通过；异常项显示在风险面板。</p></Card>
      <Card class="thermal"><h3>02 / 测点温度热力矩阵</h3><p class="note">各棚、各测点的全时段均温（°C）</p><EChart v-if="ds.data.value" :option="heat" height="240px" /><div v-else class="chart-empty">◇<span>等待测点数据接入</span></div></Card>
      <Card class="coverage"><h3>03 / 各棚测点覆盖</h3><EChart v-if="ds.data.value" :option="bars" height="230px" /><div v-else class="chart-empty">▥<span>等待测点覆盖数据</span></div><p class="note">按数据集中的棚分组展示测点数量。</p></Card>
      <Card class="stream"><div class="panel-heading"><h3>04 / 温度数据流</h3><span class="note">历史采集序列</span></div><EChart v-if="ts.data.value" :option="line" height="275px" /><div v-else class="chart-empty">⌁<span>等待温度采集序列</span></div><p v-if="ts.error.value" class="note" role="status">温度序列暂不可用。</p></Card>
      <Card class="risks"><h3>05 / 风险与采集日历</h3><div class="date-window"><span class="note">数据覆盖时间</span><strong>{{ ds.data.value?.time_start?.slice(0, 10) ?? '—' }}</strong><span class="date-line" /><strong>{{ ds.data.value?.time_end?.slice(0, 10) ?? '—' }}</strong></div><div v-if="calendar" class="calendar"><div class="calendar-title">{{ calendar.label }}<span class="note">采集覆盖</span></div><div class="calendar-grid"><span v-for="day in ['一','二','三','四','五','六','日']" :key="day" class="weekday">{{ day }}</span><span v-for="(cell, i) in calendar.days" :key="i" :class="{ covered: cell.day && cell.covered }" :title="cell.day && cell.covered ? '数据采集日期范围内，未提供逐日告警' : ''">{{ cell.day ?? '' }}</span></div></div><div v-for="c in checks" :key="c.no" class="check-row" :class="{ 'check-warning': c.status === 'warn' }"><span>{{ c.name }}</span><span>{{ c.status === 'ok' ? '已通过' : '需关注' }}</span></div><p class="note">{{ checks.length ? (demo ? '模拟检查结果，日历高亮为模拟采集日期。' : '逐日风险记录暂未提供，当前展示数据检查状态。') : '等待数据集接入后显示检查结果。' }}</p><RouterLink to="/data">查看数据与检查详情</RouterLink></Card>
    </div>
  </section>
</template>
<style scoped>
.demo-banner { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin: 0 0 20px; padding: 12px 16px; border: var(--rule); border-left: 3px solid var(--leaf); border-radius: var(--radius); background: var(--leaf-soft); font-size: 13px; }
.demo-banner strong { color: var(--leaf); margin-right: 14px; }
.demo-banner span { color: var(--ink-muted); }
.demo-banner a { white-space: nowrap; }
.preview-actions { margin-bottom: 24px; }
.preview-actions a { display: inline-flex; font-size: 13px; }
.overview-heading, .panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.eyebrow { font: 11px var(--font-num); color: var(--leaf); letter-spacing: .16em; margin-bottom: 12px; }
.live-entry { border: var(--rule); padding: 10px 18px; border-radius: var(--radius); text-decoration: none; background: var(--glass); white-space: nowrap; }
.dashboard-grid { display: grid; grid-template-columns: minmax(220px, .85fr) minmax(320px, 1.5fr) minmax(220px, .85fr); gap: 18px; }
h3 { margin-bottom: 16px; font-size: 14px; letter-spacing: .05em; }
.stream { grid-column: span 2; }
.date-window { display: flex; flex-direction: column; gap: 8px; margin: 22px 0; font-family: var(--font-num); }
.date-line { width: 1px; height: 18px; background: var(--leaf); margin-left: 4px; opacity: .4; }
.check-row { display: flex; justify-content: space-between; gap: 8px; border-bottom: var(--rule); padding: 10px 0; font-size: 13px; }
.check-row span:last-child { color: var(--leaf); }
.check-warning span:last-child { color: var(--bar); }
.calendar { margin: 16px 0; border-top: var(--rule); padding-top: 12px; }
.calendar-title { display: flex; justify-content: space-between; margin-bottom: 10px; font-family: var(--font-num); }
.calendar-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 4px; text-align: center; font: 11px var(--font-num); }
.calendar-grid > span { padding: 5px 0; }
.weekday { color: var(--ink-muted); }
.covered { background: var(--leaf-soft); color: var(--leaf); border-radius: 4px; }
.chart-empty { height: 240px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18px; color: var(--steel); font-size: 48px; background: radial-gradient(ellipse, var(--grid), transparent 70%); }
.chart-empty span { color: var(--ink-muted); font-size: 13px; }
.risks > .note { margin: 16px 0; }
@media (max-width: 1250px) { .dashboard-grid { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } .thermal { grid-column: 2; } .stream { grid-column: span 2; } .risks { grid-column: 2; grid-row: 2; } }
@media (max-width: 850px) { .dashboard-grid { grid-template-columns: minmax(0, 1fr); } .dashboard-grid > * { grid-column: 1; grid-row: auto; } .overview-heading { flex-wrap: wrap; margin-bottom: 18px; } }
</style>
