<script setup lang="ts">
/**
 * 实时模式那一屏：把模型没见过的 144 帧一帧一帧演出来。
 *
 * **这一页不做任何计算**（硬约束 1）：温度、帧号、时间戳、分级文案全部来自
 * 后端，这里的每一个数都是某条接口原样给的。
 *
 * ⚠️ 2026-10-09 第二轮（用户按参考图重做这一屏）：**这里也不做任何计算**那条
 * 仍然成立 —— 新加的「棚内均温」是后端给的（`VolumePayload.mean`，
 * 口径见 `routes/field.py::_mean_in_arch`），前端一个温度都不重算。
 * 三个坑（拱外是 NaN、z 高于 1.10 m 那一条是外推、平均要在软单调投影之后取）
 * 都在后端那一处，前端连碰都不碰。
 *
 * `cursor` 是**服务端**给的（`GET /api/live/status` 的纯读），不是本地推的 ——
 * 时钟在服务端，是 `(started_at, now)` 的纯函数。本地再维护一个「第几帧」
 * 迟早与服务端漂开，而这一屏最不能错的就是「现在演的是第几帧」。
 *
 * ⚠️ **「实时模式」与图章的 `live` 不是一回事**：前者是这一屏的名字，
 * 后者说的是「这个数是这次请求现算的」。
 * （原先那排四张指标卡都挂 `live` 图章 —— 2026-10-09 按用户裁定撤了，
 * 这一屏上就再没有挂图章的格子了，但两个词的区别仍然成立：
 * 断面那张卡里的读数也是 `/api/live/frame/{n}` 现算的。）
 *
 * 控件**在页内**，不走 `Teleport to="#rail-extra"` —— 实时模式收起导航
 * （`App.vue` 的 `route.meta.rail`），而 `#rail-extra` 由 `NavRail` 渲染，
 * 导航不在时那个落点根本不存在。
 *
 * 三维那一块**不在这里**：规格书 §「前端形态」写的是懒加载 `scene/VolumeView.vue`
 * —— 页③ 那一整块搬过来，只把取数口换成实时那条（`:source="'live'"`）。
 * 判定、文案、吸附、坐标查询因此仍然只有一处。
 */
import { computed, defineAsyncComponent, h, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {requestedDesign,requireMonitoringConfig} from '../live/designSelection'

defineOptions({ name: 'LiveView' })

import type { LiveFramePayload, LiveStatus, VolumePayload } from '../api/types'
import { getJson } from '../api/client'
import { weatherApi } from '../api/weather'
import { session } from '../api/session'
import { designsApi, type DesignRecord } from '../api/greenhouseDesigns'
import EChart from '../charts/EChart.vue'
import { buildLiveMeanCurveOption, MEAN_CURVE_TITLE } from '../charts/options/liveMeanCurve'
import { buildSectionFieldOption, shedOfSeries } from '../charts/options/sectionField'
import { interpretPick, pickText } from '../charts/pick'
import Card from '../components/Card.vue'
import LiveWeatherOverview from '../components/LiveWeatherOverview.vue'
import LiveEnvironmentAlerts from '../components/LiveEnvironmentAlerts.vue'
import LiveGreenhouseDialog from '../components/LiveGreenhouseDialog.vue'
import MonitoringLocationDialog from '../components/MonitoringLocationDialog.vue'
import { useMonitoringLocation } from '../composables/useMonitoringLocation'
import { useHouseDimensions } from '../composables/useHouseDimensions'
import {sameDimensions,validDimensions} from '../live/houseDimensions'
import { useSingleWeatherQuery } from '../composables/useSingleWeatherQuery'
import { useAutomaticField } from '../composables/useAutomaticField'
import { useTimedMonitoring } from '../composables/useTimedMonitoring'
import { fieldMatchesQuery, savedSingleMatchesLocation, savedSingleQuery, savedSingleLocation } from '../live/weatherQuery'
import { sameRegion, type MonitoringLocation } from '../live/monitoringLocation'
import SectionAsk from '../components/SectionAsk.vue'
import LiveFieldPlaceholder from '../components/LiveFieldPlaceholder.vue'
import AgronomyAdvice from '../components/AgronomyAdvice.vue'
import { useAsync } from '../composables/useAsync'
import { useRetainedTeleport } from '../composables/useRetainedTeleport'
import { calibratedLabel } from '../design/copy'
import { readPalette } from '../design/palette'
import { snapIndex } from '../scene/hover'
import { ALL_TEMPERATURE_LAYERS, type TemperatureLayerCuts, type TemperatureLayerVisibility } from '../scene/volumeView'

// 三维整块懒加载，`FieldView` 同款写法。占位用 `h()` 不用字符串模板：
// 打包出来的 `vue` 是 runtime-only 的，`template:` 字符串在真跑时会抛，
// 而 vitest 走 `index.mjs`（带编译器）所以测试里看不出来。
const VolumeView = defineAsyncComponent({
  loader: () => import('../scene/VolumeView.vue'),
  loadingComponent: {
    name: 'LiveVolumeLoading',
    render: () => h('p', { class: 'note' }, '正在加载三维模块…'),
  },
  delay: 0,
})

const palette = readPalette()
const { target: sidebarTarget, disabled: sidebarSuspended } = useRetainedTeleport('#shell-side')
const { target: navTarget, disabled: navSuspended } = useRetainedTeleport('#rail-extra')

/* 用户视图只读取公开棚体档案和本账号气象结果，不访问开发者模型库。 */
const catalog = useAsync(weatherApi.houses)
const prototypeInfo=useAsync(weatherApi.prototype)
const hasModel = computed(() => status.value?.state === 'ready' || !!prototypeInfo.data.value?.ready || !!catalog.data.value?.some(h => h.ready))
const catalogLoaded = computed(() => catalog.data.value !== null)

/* ── 状态与三个控件 ─────────────────────────────────────── */

const status = ref<LiveStatus | null>(null)
const layerCuts = ref<TemperatureLayerCuts>([0.5, 1.5])
const layerVisibility = ref<TemperatureLayerVisibility>(ALL_TEMPERATURE_LAYERS)
const designRoute=useRoute(),designRouter=useRouter()
const weatherOpen = ref(false)
const greenhouseOpen=ref(false),designApplying=ref(false),designError=ref(''),designLinkError=ref('')
const { selected: monitoringLocation, save: saveMonitoringLocation } = useMonitoringLocation()
const {selected:houseDimensions,customized:dimensionsCustomized,save:saveDimensions}=useHouseDimensions()
const weatherQueryActive = ref(!designRoute?.query.applyDesign)
const automaticWeather = useSingleWeatherQuery(monitoringLocation, weatherQueryActive)
const constructionAllowed=ref(true),shotRequested=ref(false),restoredSession=ref<string|null>(null)
const automaticField = useAutomaticField(automaticWeather.data, constructionAllowed,houseDimensions)
const preferredSession = computed(() => automaticField.data.value?.live.session_id ?? restoredSession.value)
const statusError = ref('')
const refreshing = ref(false)
const updateBusy=computed(()=>designApplying.value || refreshing.value || automaticWeather.loading.value || automaticField.loading.value)
const timedMonitoring=useTimedMonitoring({
  run:async()=>{const failure=await refreshDashboard();if(failure)throw new Error(failure)},
  busy:updateBusy,active:weatherQueryActive,location:computed(()=>monitoringLocation.value?{...monitoringLocation.value,dimensions:houseDimensions.value}:null),
  userId:computed(()=>session.user.value?.id??null),
})
const monitoringState=computed(()=>({enabled:timedMonitoring.enabled.value,intervalMinutes:timedMonitoring.intervalMinutes.value,
  nextAt:timedMonitoring.nextAt.value,paused:timedMonitoring.paused.value,error:timedMonitoring.error.value}))
let alive = true
let active = true
let statusSeq = 0

async function refreshStatus() {
  const mine = ++statusSeq
  const expected=preferredSession.value
  try {
    const fresh = await getJson<LiveStatus>(`/api/live/status${expected ? `?session_id=${encodeURIComponent(expected)}` : ''}`)
    if (!alive || !active || mine !== statusSeq || expected!==preferredSession.value) return
    if (fresh.session_id !== status.value?.session_id || fresh.state !== 'ready') {
      frame.data.value = null
      summary.data.value = null
    }
    status.value = fresh
    if(!dimensionsCustomized.value && fresh.prototype && validDimensions(fresh.dimensions) && !sameDimensions(fresh.dimensions,houseDimensions.value))saveDimensions(fresh.dimensions)
    const savedPoint=!monitoringLocation.value?savedSingleLocation(fresh):null
    if(savedPoint)saveMonitoringLocation(savedPoint)
    if(!shotRequested.value&&monitoringLocation.value&&savedSingleMatchesLocation(fresh,monitoringLocation.value))restoredSession.value=fresh.session_id??null
    statusError.value = ''
  } catch (e) {
    if (!alive || !active || mine !== statusSeq) return
    statusError.value = (e as Error).message
  }
}

async function refreshDashboard() {
  if (updateBusy.value) return
  refreshing.value = true
  shotRequested.value=true;restoredSession.value=null
  try {
    await Promise.all([catalog.run(), prototypeInfo.run(), refreshStatus(), automaticWeather.refresh()])
    await automaticField.settled()
    if (alive && active && ready.value) refetch()
    return automaticWeather.error.value || automaticField.error.value || automaticField.blocked.value
  } finally { refreshing.value = false }
}

function locationConfirmed(location: MonitoringLocation) {
  statusSeq++
  designLinkError.value=''
  saveMonitoringLocation(location)
  shotRequested.value=true;restoredSession.value=null
  weatherOpen.value = false
  frame.data.value = null
  summary.data.value = null
  return automaticWeather.refresh()
}
function applyMonitoringConfig(config:ReturnType<typeof requireMonitoringConfig>){
  saveDimensions(config.dimensions)
  return locationConfirmed(config.location)
}
function openGreenhousePicker(){
  designError.value=''
  greenhouseOpen.value=true
}
async function applyDesign(plan:DesignRecord){
  if(updateBusy.value||!weatherQueryActive.value)return
  const mine=activationSeq,owner=session.user.value?.id
  const current=()=>alive&&active&&mine===activationSeq&&owner===session.user.value?.id
  designApplying.value=true;designError.value=''
  try{
    const selected=await designsApi.activate(plan.id,plan.revision)
    if(!current())return
    const config=requireMonitoringConfig(selected.spec)
    greenhouseOpen.value=false
    await applyMonitoringConfig(config)
  }catch(e){
    if(current())designError.value=e instanceof Error?e.message:'温室方案暂时无法应用。'
  }finally{
    if(current())designApplying.value=false
  }
}

/* ── 当前这一帧 ─────────────────────────────────────────── */

const ready = computed(() => {
  const saved=status.value
  if(saved?.state!=='ready')return false
  if((saved.prototype || dimensionsCustomized.value) && !sameDimensions(saved.dimensions,houseDimensions.value))return false
  if(saved.weather_source?.data_kind==='forecast')return false
  if(!monitoringLocation.value)return true
  if(!sameRegion(monitoringLocation.value,saved.location))return false
  // A newly queried forecast must not relabel an old temperature field as current.
  if(automaticWeather.data.value)return fieldMatchesQuery(saved,automaticWeather.data.value)
  return !shotRequested.value&&savedSingleMatchesLocation(saved,monitoringLocation.value)
})
const displayWeatherQuery=computed(()=>automaticWeather.data.value??(ready.value?savedSingleQuery(status.value):null))
function sessionQuery(separator = '?'): string {
  const id = status.value?.session_id
  return id ? `${separator}session_id=${encodeURIComponent(id)}` : ''
}

const frame = useAsync(async () => {
  const s = status.value
  if (!s || s.state !== 'ready') throw new Error('实时源还没准备好')
  return getJson<LiveFramePayload>(`/api/live/frame/${s.cursor}${sessionQuery()}`)
})

/**
 * 摘要那一份体网格。指标行的「棚内均温」与底栏那条沿棚均温曲线都要它。
 *
 * ⚠️ **它与三维那一块不是同一次请求，也不该合成一次。** 三维要的是 37 片的
 * 精细体网格（约 1.2 s），摘要要的是「沿棚长方向的走势」——`y_step = 3.0`
 * 七片就够，约四分之一秒。合成一次的话摘要要为三维的分辨率付钱；反过来更糟，
 * 把三维降到 3 m 一片是另一件事。
 *
 * ⚠️ 两条请求打的是**同一个**实时源，`advance_to(n)` 是幂等的
 * （`test_api_live.py::test_同一帧走两条路由不重复接帧` 钉着），
 * 所以多打一次不会把同一帧接两遍。
 */
const SUMMARY_Y_STEP = 3.0

const summary = useAsync(async () => {
  const s = status.value
  if (!s || s.state !== 'ready') throw new Error('实时源还没准备好')
  return getJson<VolumePayload>(`/api/live/volume/${s.cursor}?y_step=${SUMMARY_Y_STEP}${sessionQuery('&')}`)
})

/**
 * 帧与摘要一起重取。**必须一起** —— 它们说的是同一帧，分开取迟早指着两帧：
 * 屏上左边写着 12:00、右边那条曲线却是 11:55 的，而两边都不报错。
 */
function refetch(): void {
  void frame.run()
  void summary.run()
}
watch(automaticField.data,saved=>{
  if(!saved || !alive || !active || !fieldMatchesQuery(saved.live,automaticWeather.data.value))return
  statusSeq++
  const changed=status.value?.session_id!==saved.live.session_id
  status.value=saved.live;statusError.value=''
  shotRequested.value=false
  if(changed){frame.data.value=null;summary.data.value=null}
  if(ready.value)refetch()
})

/**
 * 轮询对表。**帧号变了才重取** —— 同一帧重取一次，图上什么都没变，
 * 白等一次构场（断面那一半是秒级的，三维那一半约 1.2 s）。
 *
 * 三维那一块自己跟着 `t-index` 重取（`VolumeView` 里防抖），这里不催它。
 */
const POLL_MS = 5000
let timer: ReturnType<typeof setInterval> | undefined
let pollingStatus = false
let activationSeq = 0

async function activate(initial: boolean): Promise<void> {
  const mine = ++activationSeq
  if(designRoute?.query.applyDesign){
    let selected:Awaited<ReturnType<typeof requestedDesign>>|undefined
    try{
      selected=await requestedDesign(designRoute.query.applyDesign,designRoute.query.designRevision)
    }catch(e){
      if(alive&&active&&mine===activationSeq)designLinkError.value=e instanceof Error?e.message:'无法应用温室方案。'
    }
    if(!alive||!active||mine!==activationSeq)return
    const query={...designRoute.query};delete query.applyDesign;delete query.designRevision
    await designRouter.replace({path:'/live',query})
    if(!alive||!active||mine!==activationSeq)return
    weatherQueryActive.value=true
    if(selected)await applyMonitoringConfig(selected)
    if(!alive||!active||mine!==activationSeq)return
  }
  const before = status.value
  // 档案用于空态说明；状态始终读取，档案失效也不挡住个人已有保存结果。
  await Promise.all([catalog.run(),prototypeInfo.run()])
  if (!alive || !active || mine !== activationSeq) return
  await refreshStatus()
  if (!alive || !active || mine !== activationSeq) return
  if (ready.value && (initial || status.value?.cursor !== before?.cursor
      || status.value?.session_id !== before?.session_id || before?.state !== 'ready')) refetch()
  if (timer) clearInterval(timer)
  timer = setInterval(async () => {
    // idle 状态也轮询：后台配置完成并产生新结果后，无需重载整个页面。
    if (!active || pollingStatus) return
    // 暂停时也轻量核对会话，及时发现服务重启；同一会话同一帧不重新构场。
    pollingStatus = true
    const before = status.value
    try {
      await refreshStatus()
      if (ready.value && (status.value?.cursor !== before?.cursor
          || status.value?.session_id !== before?.session_id || before?.state !== 'ready')) refetch()
    } finally { pollingStatus = false }
  }, POLL_MS)
}

onMounted(() => { void activate(true) })
// KeepAlive 保留三维画布；离页不再轮询，回来只在会话或帧号变化时取新场。
onDeactivated(() => {
  weatherQueryActive.value = false
  weatherOpen.value = false
  greenhouseOpen.value=false
  designApplying.value=false
  active = false
  activationSeq += 1
  statusSeq += 1
  if (timer) clearInterval(timer)
  timer = undefined
})
onActivated(() => {
  if (active) return // 首次挂载已由 onMounted 启动
  active = true
  weatherQueryActive.value = !designRoute?.query.applyDesign
  void activate(false)
})
onUnmounted(() => {
  constructionAllowed.value=false
  alive = false
  active = false
  activationSeq += 1
  statusSeq += 1
  if (timer) clearInterval(timer)
})

/* ── 文案 ───────────────────────────────────────────────── */

/** `null` 就是后端说的「不报数」—— 不翻成 0，也不留空。 */
const show = (v: number | null): string => (v === null ? '不报数' : v.toFixed(1))

/* ── 指标行与底栏的文案 ─────────────────────────────────── */

/** 棚内均温。`null` 是后端说的「这一卷一个可用格子都没有」—— 不翻成 0。 */
const alertField = computed(() => {
  const volume = summary.data.value
  const current = status.value
  return ready.value && current && volume?.live?.session_id === current.session_id
    && volume?.frame?.n === current.cursor ? volume : null
})

// 接入信息必须属于当前帧；新观测加载中不沿用上一观测或状态响应的读数。
const displayedFrame = computed(() => {
  const current = frame.data.value
  return ready.value && current?.live.session_id === status.value?.session_id
    && current?.frame.n === status.value?.cursor ? current : null
})
const weatherObservation = computed(() =>
  displayWeatherQuery.value?.weather ?? (monitoringLocation.value ? null : displayedFrame.value?.live.weather)
)
const alertHumidity = computed(() => displayWeatherQuery.value?.data_kind === 'forecast' ? null : weatherObservation.value?.bg_rh ?? null)

const emptyMessage = computed(() => {
  if (automaticField.blocked.value) return automaticField.blocked.value
  if (automaticField.error.value) return `自动构场失败：${automaticField.error.value} 点击上方刷新重试。`
  if (automaticField.loading.value) return '气象已接入，正在自动构建三维温度场…'
  if (statusError.value || catalog.error.value) return '暂时无法读取构场状态，请检查连接后重试。'
  if (!catalogLoaded.value || !status.value) return '正在检查构场状态…'
  if (!hasModel.value) return '尚未配置可用的棚体结构与气象模型，请联系管理员完成配置。'
  if (monitoringLocation.value && automaticWeather.loading.value) return '正在查询监测地点的气象数据…'
  if (monitoringLocation.value && automaticWeather.error.value) return '气象查询失败，请点击上方刷新重试。'
  if (monitoringLocation.value && automaticWeather.data.value && !ready.value) return '正在读取该地点的温度场…'
  if (monitoringLocation.value && status.value.state === 'ready' && !ready.value) return '已切换监测地点，等待该地点的气象构场结果。'
  return '尚无已保存的气象构场；请选择监测地点，接入该地点的气象后显示温度场。'
})

/**
 * 均温那句口径里要报的那个高度上限（米）。
 *
 * ⚠️ 读载荷里的 `max_measured_z`，**不要**在前端另写一个常量。后端那个字段
 * 就是 `float(C.MAX_MEASURED_Z)`（`field.py:355`）—— 转发过来的同一个数，
 * 与均温那个掩膜用的截断值天然一致。前端再存一份，就是把后端的一条规则
 * 实现了第二遍（那条硬规矩的原话在 `field.py:359` 上面）。改常量的那天，
 * 两处会不一致，而屏上没有任何提示。
 *
 * 兜底那个 `'1.10'` 只在载荷还没到的一瞬露脸（那句说明不等取数就挂在页面上）。
 * 它与后端当前的值一致，但**不是**它的来源 —— 来源永远是载荷。
 * （测试替身里 `max_measured_z` 是 `2`，与真实常量不同；那不是错，
 * 替身只需要形状对，别照着它去改这句话。）
 */
const zLimitText = computed(() => (
  summary.data.value ? summary.data.value.max_measured_z.toFixed(2) : '1.10'
))

/** 底栏那条曲线。摘要还没到时是 null，模板那一支会说明在等什么。 */
const vCurve = computed(() => (
  ready.value && summary.data.value ? buildLiveMeanCurveOption(summary.data.value, palette) : null
))

/* ── 断面 + 点选 ────────────────────────────────────────── */

/**
 * 看哪一块。**默认落在三维**（2026-10-09 用户裁定）：进这一屏先看棚体的样子，
 * 不必先点一下。与页③ 相反 —— 那一页的入口是断面，它要读的是具体某一片。
 */
const view = ref<'section' | 'volume'>('volume')
const picked = ref<{ shed: string; ix: number; iz: number } | null>(null)

const v5 = computed(() =>
  frame.data.value ? buildSectionFieldOption(frame.data.value, palette) : null)

/** 点选**只从已经拿到的载荷里读**，不再打接口 —— 与页③ 同一个口径。 */
function onPick(ev: { seriesIndex: number; value: unknown }) {
  const f = frame.data.value
  if (!f) return
  const shed = shedOfSeries(f, ev.seriesIndex)
  if (!shed || !Array.isArray(ev.value) || ev.value.length < 2) return
  picked.value = { shed, ix: Number(ev.value[0]), iz: Number(ev.value[1]) }
}

/** 判定与文案都在 `charts/pick.ts`（全前端唯一那处），这一页不新造第四档。 */
const readout = computed(() => {
  const f = frame.data.value
  const p = picked.value
  if (!f || !p) return null
  return {
    where: `${p.shed}　x ${f.x[p.ix].toFixed(2)} m　z ${f.z[p.iz].toFixed(2)} m`,
    text: pickText(interpretPick(f, p.shed, p.ix, p.iz), f.max_measured_z),
  }
})

/* ── 右栏：断面那一档的问数（2026-10-12 规格书 §三 D8） ─────────────── */

/**
 * 断面查询的答案。走的是与三维那边**同一套判定**：吸附 `snapIndex`、
 * 回答 `interpretPick` / `pickText`（两处都是全前端唯一那处）。
 *
 * ⚠️ 断面的 y 不是连续轴，是**三个棚位**。所以 `snapIndex` 喂的是
 * `frame.sheds` 的 y 列表，要的就是「最近的那个棚位」。
 */
const askAnswer = ref<{ where: string; text: string } | null>(null)
const askError = ref('')

/** 这一档能问的范围。拼的是载荷自己报的两个端点，不是这里算出来的界。 */
const askRange = computed(() => {
  const f = frame.data.value
  if (!f) return '这一帧还没到，坐标范围暂时说不了。'
  return `可用范围：x ${f.x[0].toFixed(2)} 至 ${f.x[f.x.length - 1].toFixed(2)} m，`
    + `z ${f.z[0].toFixed(2)} 至 ${f.z[f.z.length - 1].toFixed(2)} m。`
})

function runAsk(q: { x: number; y: number; z: number }): void {
  const f = frame.data.value
  if (!f) return
  const si = snapIndex(f.sheds.map((sh) => sh.y), q.y)
  const ix = snapIndex(f.x, q.x)
  const iz = snapIndex(f.z, q.z)
  if (si === null || ix === null || iz === null) {
    // **绝不从范围外吸进来**：吸到最近的边上格点，屏幕上写的还是「最近格点」，
    // 而用户以为自己问的是 100 米处 —— 一个不是他问的答案，看起来却完全正常。
    askAnswer.value = null
    askError.value = `坐标超出这一帧的范围，没有可吸附的格点。${askRange.value}`
    return
  }
  askError.value = ''
  const shed = f.sheds[si]!
  askAnswer.value = {
    where: `${shed.shed}　x ${f.x[ix]!.toFixed(2)} m　z ${f.z[iz]!.toFixed(2)} m`,
    text: pickText(interpretPick(f, shed.shed, ix, iz), f.max_measured_z),
  }
}
</script>

<template>
  <!-- ⚠️ 2026-10-16：根这一层带 `class="live"`，为的是 `.live` / `.stage`
       那两条竖排弹性列的规则（见本文件末尾那一段样式）。`App.vue` 在实时
       那一档把中栏也摆成了一条 flex 列 —— 两头接上，三维那一块才有高度可分。

       ⚠️ 这段注释里**不许出现那个样式的标签名**（`style`）：`prose.test.ts`
       用 `indexOf` 找它来切模板段，注释里写一个就把扫描段截在这儿，
       于是那条守卫会以「一个 p.note 都没有」报红 —— 而它其实是被饿着了。
       这一条已经踩过一次（2026-10-16）。 -->
  <section class="live">
    <MonitoringLocationDialog :open="weatherOpen" :model-value="monitoringLocation ?? displayedFrame?.live.location" @close="weatherOpen = false" @confirm="locationConfirmed" />
    <LiveGreenhouseDialog v-if="greenhouseOpen" :location="monitoringLocation" :dimensions="houseDimensions"
      :busy="updateBusy||!weatherQueryActive" :applying="designApplying" :error="designError"
      @close="greenhouseOpen=false" @apply="applyDesign" @clear-error="designError=''" />
    <p v-if="designLinkError" role="alert" class="alert">{{ designLinkError }}</p>
    <p v-if="statusError" role="alert" class="alert">{{ statusError }}</p>
    <p v-if="ready && automaticField.error.value" role="alert" class="alert">自动更新温度场失败：{{ automaticField.error.value }} 当前保留已保存结果。</p>
    <Card v-if="catalog.error.value" class="catalog-error">
      <p class="err" role="alert">{{ catalog.error.value }}</p>
    </Card>
    <p v-if="frame.error.value" role="alert" class="alert">{{ frame.error.value }}</p>
    <LiveWeatherOverview
      :greenhouse-open="greenhouseOpen" @select-greenhouse="openGreenhousePicker"
      :observation="weatherObservation" :location="monitoringLocation ?? displayedFrame?.live.location"
      :query="displayWeatherQuery" :querying="automaticWeather.loading.value" :query-error="automaticWeather.error.value"
      :refreshing="updateBusy" :monitoring="monitoringState" @select-region="weatherOpen = true" @refresh="refreshDashboard"
      @monitor-start="timedMonitoring.start" @monitor-stop="timedMonitoring.stop" @monitor-interval="timedMonitoring.setIntervalMinutes"
    />

      <!-- ⚠️ 两块**互斥**、共用一个位子（2026-10-09 第一轮用户裁定）：
           原先断面那张卡没有 `v-if` 拦着，切到三维就成了上下两条。
           页③ 一直是 `v-if` / `v-else`，只有实时这一屏漏了。 -->
      <template v-if="ready && view === 'section'">
        <Card v-if="frame.data.value" class="block section-stage">
          <div class="row head">
            <!-- ⚠️ 头不再是「第 N 帧」（2026-10-09 第二轮）：帧号是不报的那几个
                 数之一。这一块画的是三个断面，头就写它是什么。 -->
            <h3>断面温度场</h3>
            <span class="tag">
              {{ calibratedLabel(frame.data.value) }}
            </span>
          </div>
          <p class="note reading">
            这一帧的 24 个预测点温度（次序：p1 的 8 个位置，然后 p2、p3）：
            <span class="num">{{ (frame.data.value.frame.predicted_sensor_temps ?? []).map(show).join('、') || '暂无' }}</span>
          </p>

          <EChart v-if="v5" :option="v5" height="100%" class="section-chart" @pick="onPick" />
          <p v-else class="note state">正在构这一帧的场…</p>

        </Card>
        <p v-else-if="frame.loading.value" class="note state">正在取这一帧…</p>
      </template>

      <!-- 三维那一块就是页③ 的那一块，取数口换成实时这条。切过去才懒加载它。
           ⚠️ 2026-10-12 起它还多带一个 `panels="shell"`：**只渲染中栏**，
           问数 / 几何与剖切 / 视图控制三张卡投进外壳右栏
           （`App.vue` 渲染的 `<aside id="shell-side">`）。
           ⚠️ **画布角上那一组视角按钮这一屏不再打开** —— 它搬到右栏那张卡里
           （`ViewControls`，与页③ 同一份实现），同一组按钮印两处迟早有一处是旧的。
           ⚠️ `clock-time` **仍然要传**：它是 `VolumeView` 的必填 prop，
           而且不走那枚钟也仍然读它（「正在构体…」括号里的时刻、
           以及「画面仍是 X 的场」那句说的都是它）。
           ⚠️ `show-notes` 仍然关掉（2026-10-09 用户裁定）：那两行口径说明
           撤下来之后，顶住规格书 §5.3 那条要求的是右栏那个滑块的标题与读数。 -->
      <!-- ⚠️ 2026-10-16：三维那一块包进 `.stage` —— 它是这一屏**唯一**
           会长会缩的那一格。`stretch` 让 `VolumeView` 把高度交给外面分配
           （逐层 `flex` 传到画布，见那两个文件末尾的样式）。
           ⚠️ 传的是 `stretch` 而不是一个高度：高度由窗口算，不由这里编一个
           常数 —— 编出来的那个数在有人往这一屏加一块时会**悄悄**过期，
           而屏上只表现为「三维矮了」，不报错。 -->
      <div v-show="!ready || view === 'volume'" class="stage">
        <KeepAlive :max="1">
          <VolumeView
            v-if="ready && view === 'volume'"
            :key="status?.session_id ?? 'legacy'"
            :session-id="status?.session_id ?? undefined"
            source="live" :t-index="status?.cursor ?? 0"
            panels="shell" :show-notes="false" stretch
            :clock-time="displayedFrame?.frame.time ?? ''"
            v-model:layer-cuts="layerCuts"
            v-model:layer-visibility="layerVisibility"
          />
        </KeepAlive>
        <LiveFieldPlaceholder v-if="!ready" :message="emptyMessage" />
      </div>

      <!-- 右栏（2026-10-12 规格书 §三 D8）。**三档都在的只有三维那一支**：
           `VolumeView` 自己把三张卡投进 `#shell-side`；断面这一档缓存三维组件并收回其右栏，
           所以那一段由这里补上 —— 只有一张问数卡（几何与剖切、视图控制
           服务的是三维，断面档上没有它们的事）。
           ⚠️ **落点不在文档里时 Vue 静默不挂**：这一块会整块消失而不报错。
           `LiveView.test.ts` 自己造落点，正是防这一手。 -->
      <Teleport v-if="ready && view === 'section'" :to="sidebarTarget" :disabled="sidebarSuspended">
        <Card class="side-card">
          <fieldset class="rail-box">
            <legend>问数</legend>
            <table v-if="readout">
              <tbody>
                <tr><th>位置</th><td class="num">{{ readout.where }}</td></tr>
                <tr><th>回答</th><td>{{ readout.text }}</td></tr>
              </tbody>
            </table>
            <p v-else class="note state">点一个格子看它的读数。</p>
          </fieldset>

          <fieldset class="rail-box">
            <legend>查一个坐标</legend>
            <SectionAsk
              :answer="askAnswer" :error="askError" :note="askRange"
              @query="runAsk"
            />
          </fieldset>
        </Card>
      </Teleport>
      <Teleport :to="sidebarTarget" :disabled="!ready || view !== 'section' || sidebarSuspended">
      <div class="foot" :class="{ 'section-foot': ready && view === 'section' }">
        <LiveEnvironmentAlerts :field="alertField" :humidity="alertHumidity" />

        <Card class="temperature-overview">
          <div class="temperature-overview-heading"><h3><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="currentColor"><path d="M3 13h4v8H3zM10 7h4v14h-4zM17 2h4v19h-4z" /></svg>{{ MEAN_CURVE_TITLE }}</h3><span class="note" title="曲线表示各高度的有效网格均温，颜色表示均温相对高低">垂直均温：蓝低，橙高</span></div>
          <!-- 与底栏卡片同高，断面视图随侧栏伸展。 -->
          <EChart v-if="vCurve" :option="vCurve" height="100%" class="overview-chart" />
          <!-- ⚠️ 这一格**不印后端的原话**：它是底栏的次要一块，把一条接口错误
               原样摊在这里会盖过温度场。而 `routes.smoke.test.ts` 那条禁字形
               扫描是逐页扫整页文本的，一句来路不明的错误文案正是最容易带进
               禁字形的地方。 -->
          <p v-else class="note state curve-placeholder">{{ ready ? summary.error.value ? '垂直温度分布暂时无法读取，请刷新重试。' : '正在取这一帧的垂直温度分布…' : '构场后显示垂直温度分布' }}</p>
          <!-- ⚠️ 这一格原来压着一句口径说明，2026-10-16 第二回连同左块那一句
               一起撤进页脚的「口径与出处」了：这一屏要三块同屏不滚动，
               而底栏是全屏最高的那一块，两句话就是将近五十像素。 -->
        </Card>
      </div>
      </Teleport>

    <!-- 口径与出处：一页最多一处（spec §八）。收起来，但内容始终在 DOM 里。 -->
    <Teleport :to="sidebarTarget" :disabled="sidebarSuspended">
      <AgronomyAdvice :session-id="ready ? status?.session_id ?? null : null" :active="weatherQueryActive" />
    </Teleport>
    <Teleport v-if="ready" :to="navTarget" :disabled="navSuspended">
    <details class="why">
      <summary>口径与出处</summary>
      <!-- ⚠️ 分级句**原先常驻在屏上**（`data-grading`），2026-10-09 用户裁定
           撤下来折进这里（用户的原话：「这两句也不要」）。
           这不是一条普通的排版裁定，是**有意推翻规格书**：那一句在 §6.2、
           §十二.7、页⑤ 规格书 §306 / §308 / §415 被点过五次名，原话是
           「实时是一帧一帧刷过去的，观众只会记住『它在动』；分级看不见，
           就等于把『混合出来的』渲染成『测出来的』」。
           处置是**降级不是删除**：话一个字不丢，但从「常驻」变成「点一下」。
           再往下删之前，先回到那五处看一眼。
           `data-grading` 留着当路标 —— 它是这一句的身份，也让
           `LiveView.test.ts` 钉得住「它在折叠里、且全屏只有一处」。 -->
      <p class="note" data-grading>
        图上一个格子只有三种回答：拱外无定义、无测量带里不报数、以及一个带出处的模型推算值。
      </p>
      <!-- ⚠️ 均温那一句**原先常驻在概览条底下**，2026-10-16 用户裁定撤下来。
           与原先把分级句折进这里是同一条处置：**降级不是删除** —— 话一个字
           不丢，从「常驻」变成「点一下」。它撤得掉的理由是这一屏最容易看错的
           那个数（均温）在下面那张环上、以及那一块的标题里都还标着是什么。
           `LiveView.test.ts` 里断「都不进平均」的那一条**照样绿** ——
           `<details>` 收起来，内容仍然在 DOM 里。 -->
      <p class="note">
        均温只算拱形以内、z 不高于 {{ zLimitText }} m 的那些格子。拱外没有定义，
        再往上那一条是按外推补出来的，都不进平均。
      </p>
      <p class="note">
        温度分布概览的横坐标为距地高度，纵坐标为该高度沿棚宽、棚长的有效网格均温。
        统计使用当前帧的网格，沿棚长每 3 m 采一片，包含上部已有的模型预测温度；拱外与缺失值不计入，缺数高度留空。
      </p>
      <p class="note">
        显示当前账号最近一次保存的气象构场。G 预测棚内点位，冻结 F 构建空间温度场，
        棚内点位不是现场传感器实测。
      </p>
      <!-- 原先挂在顶部那条状态句上。整句说的都是帧数，跟着指标卡一起撤了，
           但这一句不是帧数、是**用户该知道的口径**：重启服务这一屏就从头演。 -->
      <p class="note">
        气象输入与模型配置快照随结果保存。提交新的外部气象后更新当前画布，服务重启后仍可读取已保存结果。
      </p>
      <!-- 正在用的那一份包不是为当前这份数据标的时的那句话。**逐字来自后端**
           （`deps._BORROWED_NOTE` → 载荷的 `mismatch_note`），前端不另写一句
           —— 与页③ 同一句，同一个来源。对得上时它是空串，这一格不印。

           ⚠️ 2026-10-16 起这一格在页⑤ 上**恒不印**：页⑤ 的轴换成了
           `configs/live/train.xlsx`（规格书 2026-10-16），它不是「当前数据集
           切出来的训练段」，与包上那个逐机指纹**不可能**相同 —— 那句话对它
           永远为真、也就零信息。后端 `LiveSource.prepare()` 已经把它抹成空串。
           这一格留着不删：它是**载荷的形状**（同一个 `sections_payload`），
           页③ 也用它；哪天页⑤ 的轴再变，它就自动又活了。 -->
      <p v-if="frame.data.value?.mismatch_note" class="note">
        {{ frame.data.value.mismatch_note }}
      </p>
      <!-- ⚠️ 页⑤ 有 `frame` 与 `volume` 两个载荷，后端两处都带这一格（同一句）。
           只印 `frame` 那一份：一帧只有一个结论，印两遍是同一个数字说两次。
           ⚠️ 与上面那句**各是一个格**：合成一句会让一份本地的模型自称
           「借来的」（`copy.ts` 的 `calibratedLabel` 就是拿那一格判的）。 -->
      <p v-if="frame.data.value?.artifact_note" class="note">
        {{ frame.data.value.artifact_note }}
      </p>
    </details>
    </Teleport>
  </section>
</template>

<style scoped>
.live-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.live-heading h2 { margin: 0; }
.section-stage { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.live .section-stage { margin-bottom: 0; margin-top: var(--gap-m); }
.section-stage .section-chart { flex: 1 1 auto; min-height: 260px; }
.foot.section-foot { display: grid; grid-template-columns: minmax(0, 1fr); grid-template-rows: auto minmax(220px, 1fr); margin-top: 0; gap: 12px; flex: 1 0 auto; order: 1; }
.section-foot .temperature-overview { display: flex; flex-direction: column; min-height: 220px; }
.section-foot .overview-chart { flex: 1 1 0; min-height: 165px; }
.side-card { flex-shrink: 0; }
.section-foot .temperature-overview-heading { flex-wrap: wrap; gap: 3px; }
.section-foot .temperature-overview-heading > .note { font-size: 10px; }
.side-card { padding: 12px; }
.side-card :deep(fieldset) { min-inline-size: 0; margin: 0 0 8px; padding: 6px 8px; }
.side-card :deep(.ask .row) { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.side-card :deep(.ask .row label) { min-width: 0; }
.side-card :deep(.ask input) { width: 100%; min-width: 0; }
.side-card :deep(.ask .note) { font-size: 11px; line-height: 1.5; }

.temperature-overview { position: relative; border: 1px solid var(--interact); }
.temperature-overview::before, .temperature-overview::after { content: ''; position: absolute; width: 13px; height: 13px; pointer-events: none; }
.temperature-overview::before { top: -1px; left: -1px; border-top: 2px solid var(--edge); border-left: 2px solid var(--edge); }
.temperature-overview::after { bottom: -1px; right: -1px; border-bottom: 2px solid var(--edge); border-right: 2px solid var(--edge); }
.temperature-overview-heading { display: flex; align-items: center; justify-content: space-between; gap: var(--gap-s); padding-bottom: 6px; margin-bottom: 2px; border-bottom: var(--rule); }
.temperature-overview-heading h3 { display: flex; align-items: center; gap: var(--gap-s); }
.temperature-overview-heading svg { color: var(--edge); flex: none; }
/* ── 一屏装三块（2026-10-16 用户裁定） ─────────────────────────────────
   用户报的：「棚体三维温度场、环境参数、沿栅均温这三个模块应该都能同时
   显现出来，而现在后两块必须下滑才能显示。」

   做法是一条**竖排的弹性列**：`App.vue` 在实时那一档把中栏（`.page`）也
   摆成 flex 列，这里接上；`.stage`（三维那一块）是**唯一**那一格会长会缩的
   成员，其余各块按自己的内容高。

   ⚠️ `.live` 必须允许 `flex-shrink`：否则它会坚持内容的自然高度，
   `.page` 只能滚动，底下的环境参数与均温曲线就被推到首屏以外。
   `.stage` 保持弹性，按窗口余量伸缩；画布高度上下限在 `VolumeScene.vue` 统一控制。

   ⚠️ 没有 `.stage { min-height: … }`：下限写在**画布**那一层
   （`VolumeScene.vue` 的 `.scene-wrap.stretch > .scene`），一条链只写一处。
   在这里再写一个数，两个数迟早对不上，而屏上只是「三维的高度看着不对」。 */
.live { display: flex; flex-direction: column; flex: 1 1 0; min-height: 0; }
.stage { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; }
.empty-status { gap: 10px; margin-bottom: var(--gap-s); }
.empty-status > .note { flex: 1 1 280px; }
.empty-status a { color: var(--edge); white-space: nowrap; }
.empty-status button { padding: 3px 10px; font-size: var(--size-note); }
.curve-placeholder { min-height: min(120px, 13vh); display: flex; align-items: center; justify-content: center; margin: 0; }

.block { margin-bottom: var(--gap-xl); }
.row { display: flex; flex-wrap: wrap; gap: var(--gap-s); align-items: center; }
.live-model { max-width: 18em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.head { justify-content: space-between; }
.alert { color: var(--leaf); border-left: 3px solid var(--leaf); padding-left: var(--gap-s); }
.tag { font-size: var(--size-note); color: var(--ink-muted); }
.rail-box {
  border: var(--rule); padding: var(--gap-s);
  margin: 0 0 var(--gap-s); font-size: var(--size-note);
}
/* 开关那一块：外框去掉，描边交给里面的分段控件（spec §九）。
   ⚠️ 没有 `> legend` 那一条了 —— 2026-10-09 用户裁定把「看哪一块」那行标签
   整个删掉。`fieldset` 留着（`fieldset.rail-box .seg` 是两页共用的钩子），
   只是这一支不再有 legend。 */
.rail-switch { border: 0; padding: 0; margin: 0 0 var(--gap-m); }
/* 底栏两块。左边窄、右边宽 —— 气象是三个数，曲线要的是横向地方。 */
.foot > .temperature-overview { padding: 10px 12px; }
.foot {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.5fr);
  gap: var(--gap-m);
  margin-top: var(--gap-m);
}
.foot:not(.section-foot) > .temperature-overview { display: flex; flex-direction: column; }
.foot:not(.section-foot) .overview-chart { flex: 1 1 0; min-height: 140px; }
@media (min-width: 1200px) {
  .foot:not(.section-foot) { min-height: 260px; flex: 0 0 auto; }
}
/* 窄屏上摞起来：两条轨并排时每块只剩三百来像素，曲线读不出形状。 */
@media (max-width: 1100px) { .foot { grid-template-columns: minmax(0, 1fr); } }
.seg {
  display: flex;
  align-items: stretch;
  /* ⚠️ `margin-top` 原先是「与上面那行 legend 拉开」用的。legend 撤了
     （2026-10-09 用户裁定）这一条**不能跟着删** —— 它现在拉的是上面那一排
     播放控件（`.row` 自己没有下边距），删了分段控件就贴到按钮底下。 */
  margin-top: var(--gap-s);
  border: 1px solid var(--steel);
  border-radius: var(--radius);
  background: var(--card);
}
.seg button {
  flex: 1 1 auto;
  font: inherit; cursor: pointer;
  background: transparent;
  border: 0; border-radius: 0;
  padding: 3px 10px;
  color: var(--ink-muted);
}
/* 圆角由首末两个按钮自己收，不用 `overflow: hidden`（会裁掉焦点环，终审 M-8）。 */
.seg button:first-child { border-radius: var(--radius) 0 0 var(--radius); }
.seg button:last-child { border-radius: 0 var(--radius) var(--radius) 0; }
.seg button + button { border-left: 1px solid var(--steel); }
/* 选中项是**交互态**（2026-10-12），同 `ModeSwitch.vue` 那一处。 */
.seg button.on { background: var(--interact); color: var(--on-face); }
.seg button:disabled { cursor: not-allowed; }
/* 2026-10-16 第二回：上边距从 `--gap-l`（28）收到 `--gap-m`（16）。
   这一屏的每一像素都在「三块同屏」那张账上，而这一条与上面那块只差 12px
   的呼吸 —— 收掉它看得出来才怪。 */
.why { margin-top: var(--gap-s); padding: 0 var(--gap-m) var(--gap-m); overflow-wrap: anywhere; }
.why summary { font-size: var(--size-label); color: var(--ink-muted); cursor: pointer; }
.why > p { margin-top: var(--gap-s); }
/* 右栏那张卡：它是 `<Teleport>` 投出去的那个落点里的一块，落点的 `gap`
   管卡片间距，这里只管卡片内部两组之间的间距。 */
.side-card { display: flex; flex-direction: column; }
</style>
