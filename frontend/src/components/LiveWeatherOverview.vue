<script setup lang="ts">
import { computed } from 'vue'
import type { ExternalWeatherObservation } from '../api/types'
import type { RegionInfo } from '../api/regions'
import type { WeatherQueryResult } from '../api/weather'
import Icon from './Icon.vue'
import TimedMonitoringControl from './TimedMonitoringControl.vue'

const props = defineProps<{
  observation?: ExternalWeatherObservation | null
  location?: RegionInfo | null
  refreshing?: boolean
  query?: WeatherQueryResult | null
  querying?: boolean
  queryError?: string
  greenhouseOpen?: boolean
  monitoring?: { enabled: boolean; intervalMinutes: number; nextAt: number | null; paused: boolean; error: string }
}>()
const emit = defineEmits<{ 'select-region': []; 'select-greenhouse': []; refresh: []; 'monitor-start': []; 'monitor-stop': []; 'monitor-interval': [minutes: number] }>()
const value = (n: number | null | undefined, unit = '') =>
  typeof n === 'number' && Number.isFinite(n) ? `${n.toFixed(1)}${unit}` : '暂无'
const lightValue = (n: number | null | undefined) =>
  typeof n === 'number' && Number.isFinite(n) ? new Intl.NumberFormat('zh-CN', {maximumFractionDigits: 1}).format(n) : '暂无'
const regionText = computed(() => [props.location?.province_name, props.location?.city_name]
  .filter(v => typeof v === 'string' && v.trim()).join(' · ') || '选择省市地区')
const currentObservation=computed(()=>props.query?.data_kind==='forecast'?null:props.observation)
const overview = computed(() => [
  {key: 'temperature', icon: 'thermometer', label: '外部温度', value: value(currentObservation.value?.bg_temp, ' °C')},
  {key: 'humidity', icon: 'humidity', label: '相对湿度', value: currentObservation.value && currentObservation.value.bg_rh == null ? '未提供' : value(currentObservation.value?.bg_rh, ' %')},
  {key: 'light', icon: 'sunlight', label: '光照强度', value: lightValue(currentObservation.value?.bg_light), sub: props.query ? props.query.construction_ready?'lux · 预报近似':'光照暂不可用' : '源数据单位'},
] as const)
const updateText=computed(()=>props.monitoring?.enabled?`每 ${props.monitoring.intervalMinutes} 分钟自动更新，可随时暂停。`:'本次结果保持不变，点击重新构场更新。')
const queryTitle=computed(()=>props.queryError || (props.query ? updateText.value : '选择地点后查询一次并构场。'))
</script>

<template>
  <section class="weather-overview strip" aria-label="接入的外部气象环境">
    <div class="cell region-cell">
      <Icon name="location" class="region-pin" />
      <div class="region-copy">
        <div class="region-actions">
        <div class="location-actions">
        <button type="button" class="region-selector" aria-label="选择监测地点" :title="regionText" @click="emit('select-region')">
          <span class="region-value">{{ regionText }}</span><span class="chevron" aria-hidden="true" />
        </button>
        <p class="api-state" :class="{received:query?.construction_ready&&!queryError,failed:!!queryError}" :title="queryTitle" role="status"><i aria-hidden="true"/><span v-if="querying">正在查询气象…</span><span v-else-if="queryError">查询失败，请重新构场</span><template v-else-if="query?.data_kind==='current'"><a href="https://www.qweather.com" target="_blank" rel="noopener noreferrer">和风天气</a><span>{{monitoring?.enabled ? `· 每 ${monitoring.intervalMinutes} 分钟` : '· 单次构场'}}</span></template><span v-else>{{query?'等待实况气象':observation?'已保存气象数据':'选择地点后单次构场'}}</span></p>
        </div>
        <div class="monitor-actions">
        <TimedMonitoringControl :enabled="monitoring?.enabled ?? false" :interval-minutes="monitoring?.intervalMinutes ?? 15" :next-at="monitoring?.nextAt ?? null" :paused="monitoring?.paused" :error="monitoring?.error" :busy="refreshing" :available="!!location && !!monitoring" @start="emit('monitor-start')" @stop="emit('monitor-stop')" @interval="emit('monitor-interval', $event)" />
        <button type="button" class="greenhouse-trigger" aria-label="温室棚体" aria-haspopup="dialog" :aria-expanded="greenhouseOpen" @click="emit('select-greenhouse')"><Icon name="cube" /><span>温室棚体</span></button>
        </div>
        </div>
      </div>
    </div>
    <div v-for="cell in overview" :key="cell.key" class="cell weather-cell">
      <Icon :name="cell.icon" class="weather-icon" />
      <div class="cell-copy"><p class="label">{{ cell.label }}</p><p class="value num">{{ cell.value }}</p><p v-if="'sub' in cell" class="sub note">{{ cell.sub }}</p></div>
    </div>
    <button type="button" class="ribbon-refresh" aria-label="重新构场" title="获取气象并重新构场（单次）" :disabled="refreshing" @click="emit('refresh')"><Icon name="reset" /><span class="refresh-label">{{refreshing?'处理中':query?'重新构场':'构场'}}</span></button>
  </section>
</template>

<style scoped>
.location-actions{min-width:0;flex:1;}.monitor-actions{display:flex;flex-direction:column;gap:6px;flex:none;}.monitor-actions :deep(.timed-trigger){width:100%;justify-content:center;}
.greenhouse-trigger{display:flex;align-items:center;justify-content:center;gap:5px;min-height:32px;width:100%;padding:6px 8px;white-space:nowrap;border:1px solid var(--interact);border-radius:var(--radius);background:var(--card);color:var(--ink-muted);font:inherit;font-size:12px;cursor:pointer}
.greenhouse-trigger :deep(.icon){--icon-size:15px}
.greenhouse-trigger:hover,.greenhouse-trigger[aria-expanded=true]{color:var(--edge);border-color:var(--edge)}
.greenhouse-trigger:focus-visible{outline:2px solid var(--edge);outline-offset:3px}
.weather-overview { container-type: inline-size; position: relative; display: grid; grid-template-columns: minmax(290px, 1.6fr) repeat(3, minmax(0, 1fr)) 54px; align-items: stretch; min-height: 102px; padding: 16px 12px 16px 18px; border: 1px solid var(--interact); border-radius: var(--radius); background: linear-gradient(110deg, color-mix(in srgb, var(--interact) 9%, var(--card)), var(--card)); box-shadow: inset 0 0 24px color-mix(in srgb, var(--edge) 4%, transparent); }
.weather-overview::before,.weather-overview::after { content: ''; position: absolute; width: 14px; height: 14px; pointer-events: none; filter: var(--panel-corner-glow); }
.weather-overview::before { top: -1px; left: -1px; border-top: 2px solid var(--edge); border-left: 2px solid var(--edge); }.weather-overview::after { bottom: -1px; right: -1px; border-bottom: 2px solid var(--edge); border-right: 2px solid var(--edge); }
.cell { position: relative; display: flex; align-items: center; min-width: 0; gap: 12px; }
.weather-cell { padding: 0 18px; }.weather-cell::before { content: ''; position: absolute; left: 0; top: 6%; bottom: 6%; width: 1px; background: linear-gradient(transparent, var(--edge), transparent); opacity: .7; }
.region-cell { padding-right: 18px; gap: 10px; }.region-pin { --icon-size: 26px; flex: 0 0 26px; color: var(--edge); }.region-copy,.cell-copy { min-width: 0; }
.region-actions{display:flex;align-items:center;gap:8px;}.region-copy{flex:1;}.region-selector{min-width:0;}
.region-selector { display: flex; align-items: center; gap: 10px; max-width: 100%; min-height: 32px; padding: 6px 10px; border: 1px solid var(--interact); border-radius: var(--radius); background: var(--card); color: var(--ink); font-size: 14px; font-weight: var(--w-strong); cursor: pointer; }
.region-value { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }.chevron { flex: 0 0 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid currentColor; }
.api-state { display: flex; align-items: center; gap: 6px; margin: 8px 0 0; color: var(--ink-muted); font-size: 11px; white-space: nowrap; }.api-state i { width: 6px; height: 6px; border-radius: 50%; background: var(--bar); box-shadow: 0 0 7px color-mix(in srgb, var(--bar) 65%, transparent); }
.api-state.received i{background:var(--ok);}.api-state a{color:inherit;text-decoration:none;}.api-state.failed{color:var(--bar);}
.weather-icon { --icon-size: 34px; flex: 0 0 34px; color: var(--edge); }.label { margin: 0; color: var(--ink-muted); font-size: 13px; }.value { margin: 6px 0 0; color: var(--edge); font-size: 23px; font-weight: var(--w-strong); line-height: 1.2; white-space: nowrap; }.sub { margin: 5px 0 0; font-size: 11px; }
.ribbon-refresh { align-self: center; display: flex; flex-direction:column; gap:4px; align-items: center; justify-content: center; width: 52px; min-height:48px; padding: 4px; border: 0; background: transparent; color: var(--ink-muted); cursor: pointer; }.refresh-label{font-size:11px;white-space:nowrap;}.ribbon-refresh :deep(.icon) { --icon-size: 20px; }.ribbon-refresh:hover { color: var(--edge); }.region-selector:focus-visible,.ribbon-refresh:focus-visible { outline: 2px solid var(--edge); outline-offset: 3px; }
@media (max-width: 1350px) {
  .weather-overview { grid-template-columns: minmax(270px, 1.6fr) repeat(3, minmax(0, 1fr)) 54px; padding: 14px 10px 14px 14px; min-height: 94px; }.weather-cell { padding: 0 8px; gap: 6px; }.region-cell { padding-right: 12px; gap: 7px; }.region-pin { --icon-size: 22px; flex-basis: 22px; }.region-selector { font-size: 13px; padding-inline: 8px; }.weather-icon { --icon-size: 22px; flex-basis: 22px; }.value { font-size: 20px; }.label { font-size: 12px; }
}
@container (max-width: 900px) { .weather-icon{display:none;}.weather-cell{padding-inline:8px;}.value{font-size:18px;}.region-actions{gap:6px;} }
@media (max-width: 900px) { .weather-icon { display: none; }.weather-cell { padding: 0 10px; }.value { font-size: 18px; } }
@media (max-width: 640px) { .weather-overview { grid-template-columns: repeat(3, minmax(0, 1fr)) 54px; gap: 12px 0; }.region-cell { grid-column: 1 / -1; padding-bottom: 12px; border-bottom: 1px solid var(--interact); }.weather-cell:first-of-type::before { display: none; } }
</style>
