<script setup lang="ts">
import { computed, onDeactivated, reactive, ref, watch } from 'vue'
import { session } from '../api/session'
import type { VolumePayload } from '../api/types'
import { warningsApi } from '../api/warnings'
import { tempStops, valueToColor } from '../charts/scale'
import Card from './Card.vue'
import GaugeDial from './GaugeDial.vue'
import Icon from './Icon.vue'
import ModalDialog from './ModalDialog.vue'

const props = defineProps<{ field: VolumePayload | null; humidity: number | null }>()
type Limits = { low: number; high: number }
type AlertLimits = { temperature: Limits | null; humidity: Limits | null }
type Tone = 'hot' | 'cold' | 'normal' | 'muted'

const unconfigured = { text: '未设阈值', tone: 'muted' } as const
const unavailable = { text: '暂无数据', tone: 'muted' } as const
const normal = { text: '正常', tone: 'normal' } as const
const limits = ref<AlertLimits>({ temperature: null, humidity: null })
const open = ref(false)
const error = ref('')
const loading = ref(false)
const saving = ref(false)
const syncError = ref('')
const draft = reactive<{ tempLow: number | ''; tempHigh: number | ''; rhLow: number | ''; rhHigh: number | '' }>({
  tempLow: '', tempHigh: '', rhLow: '', rhHigh: '',
})
const storageKey = () => session.user.value ? `tfield.environment-alerts.v1.${session.user.value.id}` : null

function validRange(value: unknown, humidity = false): value is Limits {
  if (!value || typeof value !== 'object') return false
  const { low, high } = value as Partial<Limits>
  return typeof low === 'number' && Number.isFinite(low) && typeof high === 'number' && Number.isFinite(high)
    && low < high && (!humidity || (low >= 0 && high <= 100))
}
watch(() => session.user.value?.id, async (owner) => {
  open.value = false
  saving.value = false
  loading.value = !!owner
  syncError.value = ''
  limits.value = { temperature: null, humidity: null }
  let localTemperature: Limits | null = null
  try {
    const key = storageKey()
    const stored = (key ? JSON.parse(localStorage.getItem(key) ?? 'null') : null) as Partial<AlertLimits> | null
    if (validRange(stored?.temperature)) localTemperature = stored.temperature
    if (validRange(stored?.humidity, true)) limits.value.humidity = stored.humidity
  } catch { /* Settings are optional when browser storage is unavailable. */ }
  if (!owner) return
  try {
    let result = await warningsApi.settings()
    if (owner !== session.user.value?.id) return
    if (!result.saved && localTemperature) result = await warningsApi.saveSettings(localTemperature, true)
    if (owner === session.user.value?.id) limits.value.temperature = result.temperature ?? null
  } catch {
    if (owner === session.user.value?.id) syncError.value = '温度阈值读取失败，可重新保存。'
  } finally {
    if (owner === session.user.value?.id) loading.value = false
  }
}, { immediate: true })
onDeactivated(() => { open.value = false })

function editLimits() {
  const { temperature, humidity } = limits.value
  Object.assign(draft, {
    tempLow: temperature?.low ?? '', tempHigh: temperature?.high ?? '',
    rhLow: humidity?.low ?? '', rhHigh: humidity?.high ?? '',
  })
  error.value = ''
  open.value = true
}
async function saveLimits() {
  if (saving.value || loading.value) return
  const temperature = draft.tempLow === '' && draft.tempHigh === '' ? null : { low: draft.tempLow, high: draft.tempHigh }
  const humidity = draft.rhLow === '' && draft.rhHigh === '' ? null : { low: draft.rhLow, high: draft.rhHigh }
  if (temperature && !validRange(temperature)) {
    error.value = '请填写温度上下限，下限须小于上限。'
    return
  }
  if (humidity && !validRange(humidity, true)) {
    error.value = '请填写 0–100% 的湿度上下限，下限须小于上限。'
    return
  }
  const owner = session.user.value?.id
  error.value = ''
  saving.value = true
  try {
    const saved = await warningsApi.saveSettings(temperature)
    if (owner !== session.user.value?.id) return
    const next: AlertLimits = { temperature: saved.temperature ?? null, humidity }
    limits.value = next
    syncError.value = ''
    const key = storageKey()
    try { if (key) localStorage.setItem(key, JSON.stringify({ humidity })) }
    catch { /* The outdoor humidity range remains usable in the current page. */ }
    open.value = false
  } catch (cause) {
    if (owner === session.user.value?.id) error.value = cause instanceof Error ? cause.message : '温度阈值保存失败。'
  } finally {
    if (owner === session.user.value?.id) saving.value = false
  }
}

const mean = computed(() => {
  const value = props.field?.mean
  return typeof value === 'number' && Number.isFinite(value) ? value : null
})
const meanText = computed(() => mean.value !== null ? `${mean.value.toFixed(1)} °C` : props.field ? '不报数' : '暂无')
const meanFraction = computed(() => {
  const field = props.field
  if (!field || mean.value === null || !(field.vmax > field.vmin)) return 0
  return Math.min(1, Math.max(0, (mean.value - field.vmin) / (field.vmax - field.vmin)))
})
const meanColor = computed(() => {
  const field = props.field
  if (!field || mean.value === null) return ''
  const [r, g, b] = valueToColor(mean.value, field.vmin, field.vmax, tempStops())
  return `rgb(${r}, ${g}, ${b})`
})

const temperatureAlerts = computed<{ text: string; tone: Tone }[]>(() => {
  const range = limits.value.temperature
  const field = props.field
  if (!range) return [unconfigured]
  if (!field) return [unavailable]
  const excluded = new Map<number, Set<number>>()
  for (const [x, z] of field.stripes) {
    let columns = excluded.get(z)
    if (!columns) excluded.set(z, columns = new Set())
    columns.add(x)
  }
  let hasReading = false
  let high = false
  let low = false
  // Compare the model's valid grid values directly. The color scale can extend beyond the readings.
  for (const { values } of field.planes) {
    for (const [z, row] of values.entries()) {
      const blocked = excluded.get(z)
      for (const [x, value] of row.entries()) {
        if (value === null || !Number.isFinite(value) || blocked?.has(x)) continue
        hasReading = true
        high ||= value >= range.high
        low ||= value <= range.low
        if (high && low) return [{ text: '高温预警', tone: 'hot' }, { text: '低温预警', tone: 'cold' }]
      }
    }
  }
  if (high) return [{ text: '高温预警', tone: 'hot' }]
  if (low) return [{ text: '低温预警', tone: 'cold' }]
  return [hasReading ? normal : unavailable]
})
const humidity = computed(() => typeof props.humidity === 'number' && Number.isFinite(props.humidity)
  && props.humidity >= 0 && props.humidity <= 100 ? props.humidity : null)
const humidityText = computed(() => humidity.value === null ? '暂无' : `${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(humidity.value)}%`)
const humidityAlert = computed<{ text: string; tone: Tone }>(() => {
  const range = limits.value.humidity
  if (!range) return unconfigured
  if (humidity.value === null) return unavailable
  if (humidity.value >= range.high) return { text: '偏湿', tone: 'cold' }
  if (humidity.value <= range.low) return { text: '偏干', tone: 'hot' }
  return normal
})
</script>

<template>
  <Card class="env-card">
    <div class="alerts-heading">
      <Icon name="thermometer" />
      <h3>环境监测预警</h3>
      <button type="button" aria-haspopup="dialog" :disabled="loading" @click="editLimits"><Icon name="gear" />预警阈值</button>
    </div>
    <div class="alerts-grid">
      <GaugeDial :frac="meanFraction" :value-text="meanText" :arc-color="meanColor" label="棚内平均温度" :size="96" technical />
      <div class="alert-box temperature-alerts">
        <h4><Icon name="alert" />温度预警</h4>
        <div class="alert-labels" role="status">
          <span v-for="alert in temperatureAlerts" :key="alert.text" class="alert-badge" :data-tone="alert.tone">{{ alert.text }}</span>
        </div>
        <p>{{ syncError || '棚内模型估温' }}</p>
      </div>
      <div class="alert-box">
        <h4><Icon name="humidity" />湿度预警</h4>
        <div class="alert-labels" role="status">
          <span class="alert-badge" :data-tone="humidityAlert.tone">{{ humidityAlert.text }}</span>
        </div>
        <p>棚外相对湿度 <strong class="num">{{ humidityText }}</strong></p>
      </div>
    </div>
    <ModalDialog v-if="open" label="环境预警阈值" :busy="saving" @close="open = false">
      <form class="alert-settings" @submit.prevent="saveLimits">
        <h3>环境预警阈值</h3>
        <p>数值达到上限或下限时触发预警。每组留空可关闭该项预警。</p>
        <fieldset>
          <legend>棚内估算温度</legend>
          <label>低温下限 / °C<input v-model="draft.tempLow" type="number" step="any" /></label>
          <label>高温上限 / °C<input v-model="draft.tempHigh" type="number" step="any" /></label>
        </fieldset>
        <fieldset>
          <legend>棚外相对湿度</legend>
          <label>偏干下限 / %<input v-model="draft.rhLow" type="number" min="0" max="100" step="any" /></label>
          <label>偏湿上限 / %<input v-model="draft.rhHigh" type="number" min="0" max="100" step="any" /></label>
        </fieldset>
        <p class="settings-note">温度阈值保存在当前账号，新构场会据此记录预警。湿度阈值保存在当前浏览器。</p>
        <p v-if="error" class="settings-error" role="alert">{{ error }}</p>
        <footer>
          <button type="button" :disabled="saving" @click="open = false">取消</button>
          <button type="submit" :disabled="saving">{{ saving ? '正在保存…' : '保存阈值' }}</button>
        </footer>
      </form>
    </ModalDialog>
  </Card>
</template>

<style scoped>
.env-card { container-type: inline-size; min-width: 0; padding: 10px 12px; border: 1px solid var(--interact); display: flex; flex-direction: column; }
.alerts-heading { display: flex; align-items: center; gap: 7px; margin-bottom: 6px; padding-bottom: 6px; border-bottom: var(--rule); }
.alerts-heading > .icon { --icon-size: 21px; color: var(--edge); }
.alerts-heading h3 { margin: 0; font-size: var(--size-h3); }
.alerts-heading button { display: flex; align-items: center; gap: 4px; margin-inline-start: auto; border: 0; padding: 3px; background: transparent; color: var(--ink-muted); font: inherit; font-size: 12px; white-space: nowrap; cursor: pointer; }
.alerts-heading button .icon { --icon-size: 14px; }
.alerts-heading button:hover { color: var(--edge); }
.alerts-grid { display: grid; grid-template-columns: auto repeat(2, minmax(0, 1fr)); align-items: stretch; gap: 8px; flex: 1 1 auto; }
.alerts-grid :deep(.dial) { align-self: center; }
.alert-box { display: flex; min-width: 0; min-height: 84px; flex-direction: column; justify-content: center; gap: 5px; padding: 7px 8px; border: 1px solid var(--interact); border-radius: var(--radius); background: var(--card-2); }
.alert-box h4 { display: flex; align-items: center; gap: 4px; margin: 0; font-size: 13px; }
.alert-box h4 .icon { --icon-size: 15px; color: var(--edge); }
.temperature-alerts h4 .icon { color: var(--bar); }
.alert-box p { margin: 0; color: var(--ink-muted); font-size: 11px; }
.alert-box strong { color: var(--edge); white-space: nowrap; }
.alert-labels { display: flex; flex-wrap: wrap; gap: 4px; }
.alert-badge { --alert-color: var(--ink-muted); padding: 2px 5px; border: 1px solid color-mix(in srgb, var(--alert-color) 55%, var(--steel)); border-radius: 4px; background: color-mix(in srgb, var(--alert-color) 12%, var(--card)); color: var(--alert-color); font-size: 12px; font-weight: var(--w-strong); white-space: nowrap; }
.alert-badge[data-tone=hot] { --alert-color: var(--bar); }
.alert-badge[data-tone=cold] { --alert-color: color-mix(in srgb, var(--interact) 65%, var(--ink)); }
.alert-badge[data-tone=normal] { --alert-color: var(--ok); }
.alert-settings h3 { margin: 0 0 12px; }
.alert-settings p { color: var(--ink-muted); font-size: 13px; }
.alert-settings fieldset { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 12px 0; padding: 10px; border: var(--rule); border-radius: var(--radius); }
.alert-settings label { display: grid; gap: 5px; font-size: 13px; }
.alert-settings input,.alert-settings button { min-width: 0; padding: 7px 9px; border: var(--rule); border-radius: var(--radius); background: var(--card-2); color: var(--ink); font: inherit; }
.alert-settings button { cursor: pointer; }
.alert-settings button[type=submit] { border-color: var(--edge); color: var(--edge); }
.alert-settings footer { display: flex; justify-content: flex-end; gap: 8px; }
.alert-settings .settings-error { color: var(--bar); }
@container (max-width: 380px) {
  .alerts-grid { gap: 5px; }
  .alert-box { padding: 5px; }
  .alerts-grid :deep(.dial) { --dial-size: 78px !important; }
  .alerts-grid :deep(.dial svg) { width: 78px; height: 78px; }
}
</style>
