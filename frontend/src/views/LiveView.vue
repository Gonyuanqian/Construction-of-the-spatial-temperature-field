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
import { computed, defineAsyncComponent, h, onMounted, onUnmounted, ref } from 'vue'

import type { LiveFramePayload, LiveStatus, PrepareResult, VolumePayload } from '../api/types'
import { ApiError, getJson, postJson } from '../api/client'
import { fetchModels, usableModels } from '../api/models'
import EChart from '../charts/EChart.vue'
import { buildLiveMeanCurveOption, MEAN_CURVE_TITLE } from '../charts/options/liveMeanCurve'
import { buildSectionFieldOption, shedOfSeries } from '../charts/options/sectionField'
import { interpretPick, pickText } from '../charts/pick'
import { tempStops, valueToColor } from '../charts/scale'
import Card from '../components/Card.vue'
import GaugeDial from '../components/GaugeDial.vue'
import Icon from '../components/Icon.vue'
import OverviewStrip from '../components/OverviewStrip.vue'
import SectionAsk from '../components/SectionAsk.vue'
import { useAsync } from '../composables/useAsync'
import { calibratedLabel, FIELD_MODEL, FIELD_VIEWS } from '../design/copy'
import { fmtTime } from '../design/format'
import { readPalette } from '../design/palette'
import { snapIndex } from '../scene/hover'

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

/* ── 模型库：这一屏能不能算，由它定 ─────────────────────── */

const models = useAsync(fetchModels)

/**
 * 有没有一条能用的模型。**与页③ 读同一个出口**（`api/models.ts` 的
 * `usableModels`）—— 各判一次不会报错，只会漂成「页③ 有场、页⑤ 说没模型」，
 * 而两页看的是同一个训练段、同一份库。
 *
 * ⚠️ 名字**不能**叫 `ready` —— 下面已经有一个
 * `const ready = computed(() => status.value?.state === 'ready')`（实时源准备好没）。
 * 一个说的是「源备好了」，一个说的是「有模型可算」，两件事两个名字。
 */
const hasModel = computed(() => usableModels(models.data.value).length > 0)

/** 取数**回来了**。用它把「还不知道」与「知道没有」分开 —— 见模板那一支。 */
const modelsLoaded = computed(() => models.data.value !== null)

/* ── 状态与三个控件 ─────────────────────────────────────── */

const status = ref<LiveStatus | null>(null)
const busy = ref(false)
const error = ref('')
let alive = true
let statusSeq = 0
let pendingAction: { scope: string; key: string } | null = null

async function refreshStatus() {
  const mine = ++statusSeq
  try {
    const fresh = await getJson<LiveStatus>('/api/live/status')
    if (!alive || mine !== statusSeq) return
    if (fresh.session_id !== status.value?.session_id || fresh.state !== 'ready') {
      frame.data.value = null
      summary.data.value = null
    }
    status.value = fresh
  } catch (e) {
    if (!alive || mine !== statusSeq) return
    error.value = (e as Error).message
  }
}

async function act(name: 'prepare' | 'start' | 'pause' | 'next' | 'new') {
  if (busy.value) return
  busy.value = true
  const expected = status.value?.session_id ?? 'none'
  const scope = `${expected}:${name}`
  if (pendingAction?.scope !== scope) pendingAction = { scope, key: globalThis.crypto.randomUUID() }
  try {
    // ⚠️ 回执**不拿来当状态用**。`prepare` 回的是 `{state, seconds}`（规格书 §五），
    // 不是一份 `LiveStatus` —— 把回执赋给 `status` 会让状态条渲染出空的帧号，
    // 还会让下面 `frame` 拼出 `/frame/undefined`（真后端 422），而这是实时模式
    // 唯一的入口动作。所以四个动作一律**问完再重新问一次状态**：
    // 再查询服务端确认的状态；状态查询不构建管线，依赖不可用时显示恢复提示。
    await postJson<LiveStatus | PrepareResult>(`/api/live/${name === 'new' ? 'sessions' : name}`, undefined,
      { 'Idempotency-Key': pendingAction.key, 'X-TField-Expected-Session': expected })
    pendingAction = null
    if (!alive) return
    error.value = ''
    await refreshStatus()
    if (ready.value) refetch()
  } catch (e) {
    if (e instanceof ApiError && e.status >= 400 && e.status < 500) pendingAction = null
    if (!alive) return
    error.value = (e as Error).message
    await refreshStatus()
  } finally {
    busy.value = false
  }
}

/* ── 当前这一帧 ─────────────────────────────────────────── */

const ready = computed(() => status.value?.state === 'ready')
const preparing = computed(() => busy.value || !!status.value?.preparing)
const prepareText = computed(() => status.value?.pending_session_id ? '继续准备'
  : status.value?.recovery_required ? '恢复实时源' : '准备实时源')

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

/**
 * 轮询对表。**帧号变了才重取** —— 同一帧重取一次，图上什么都没变，
 * 白等一次构场（断面那一半是秒级的，三维那一半约 1.2 s）。
 *
 * 三维那一块自己跟着 `t-index` 重取（`VolumeView` 里防抖），这里不催它。
 */
const POLL_MS = 5000
let timer: ReturnType<typeof setInterval> | undefined
let pollingStatus = false

onMounted(async () => {
  // 次序：先问库里有不有能用的模型（`hasModel` 由它算出来），
  // 再决定要不要去碰实时源 —— 没有模型的实时源开不了，问了也是白问。
  await models.run()
  if (hasModel.value) await refreshStatus()
  if (!alive) return
  if (ready.value) refetch()
  timer = setInterval(async () => {
    // ⚠️ 这一句**不靠**下面那句顺带挡住（没跑过 `refreshStatus()` 时
    // `status` 是 null）。写成显式的一句是为了把意图放在脸上：
    // 以后谁把 `refreshStatus()` 挪到前面，这一屏就会每 5 秒问一次
    // 一个没法算的服务端。
    if (!hasModel.value || busy.value || pollingStatus) return
    // 暂停时也轻量核对会话，及时发现服务重启；同一会话同一帧不重新构场。
    pollingStatus = true
    const before = status.value
    try {
      await refreshStatus()
      if (ready.value && (status.value?.cursor !== before?.cursor
          || status.value?.session_id !== before?.session_id || before?.state !== 'ready')) refetch()
    } finally { pollingStatus = false }
  }, POLL_MS)
})
onUnmounted(() => { alive = false; statusSeq += 1; if (timer) clearInterval(timer) })

/* ── 文案 ───────────────────────────────────────────────── */

/** `null` 就是后端说的「不报数」—— 不翻成 0，也不留空。 */
const show = (v: number | null): string => (v === null ? '不报数' : v.toFixed(1))

/* ── 指标行与底栏的文案 ─────────────────────────────────── */

/** 棚内均温。`null` 是后端说的「这一卷一个可用格子都没有」—— 不翻成 0。 */
const meanText = computed(() => {
  const m = summary.data.value?.mean
  return m === null || m === undefined ? '不报数' : `${m.toFixed(1)} °C`
})

/**
 * 三维那一块现在是什么状态。**三句都要，次序也不能换。**
 *
 * ⚠️ 这是这一屏最容易说错的一句话，两个坑各踩一次：
 *   1. **先把 `data` 判在前面。** `useAsync` 出错时**不清 `data`**（见那个文件），
 *      所以按下「暂停」之后手里还是上一帧的载荷 —— 那时候屏上确实有场，
 *      「已生成」是实话。把 `error` 判在前面，屏上明明画着场，卡上却写
 *      「取数失败」。
 *   2. **`error` 里那句「实时源还没准备好」不是故障。** 它来自 `frame`/`summary`
 *      自己那个守卫（`if (!s || s.state !== 'ready') throw`），意思是「还没开始」。
 *      不判 `ready` 的话，一台正常的机器刚进这一屏就报「取数失败」——
 *      那是把「等下」说成「坏了」，反过来同样错。
 */
const sceneText = computed(() => {
  if (summary.data.value) return '已生成'
  if (!ready.value) return '未开始'
  return summary.error.value ? '取数失败' : '正在构'
})

/** 本帧时刻。还没取到时说「正在取」，不印一个空的占位。 */
const frameTimeText = computed(() => (
  frame.data.value ? fmtTime(frame.data.value.frame.time) : '正在取'
))

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
  summary.data.value ? buildLiveMeanCurveOption(summary.data.value, palette) : null
))

/* ── 环境参数：均温的环 + 两格真几何（2026-10-12 规格书 §三 D6） ─────── */

/**
 * 圆环那一条弧的比例。
 *
 * ⚠️ 这里算的是一个**显示比例**（哪一段弧填上），**不是温度** ——
 *    全站「前端不做任何数值计算」那条约束管的是温度：读数一个都不是这里算的。
 *    规格书 §三 D6 自己写着「弧长与颜色都来自载荷的 `vmin` / `vmax` 与 `mean`」，
 *    所以它是被许可的那一处。
 */
const meanFrac = computed(() => {
  const p = summary.data.value
  const m = p?.mean
  if (!p || m === null || m === undefined) return 0
  const span = p.vmax - p.vmin
  if (!(span > 0)) return 0
  return Math.min(1, Math.max(0, (m - p.vmin) / span))
})

/**
 * 弧的颜色。**与色标用的是同一个函数、同一组 stops** ——
 * 规格书 §三 D6 的原话是「**环就是一条弯过来的色标**」。
 * 取不到数时给空串，环那一层会兜一个主色。
 */
const meanColor = computed(() => {
  const p = summary.data.value
  const m = p?.mean
  if (!p || m === null || m === undefined) return ''
  const [r, g, b] = valueToColor(m, p.vmin, p.vmax, tempStops())
  return `rgb(${r}, ${g}, ${b})`
})

/**
 * 两格几何。**后端算好的**（`shed_width` / `shed_height`）——
 * 前端不做任何数值计算，所以两个端点即使都在手上也不许在这里相减。
 * ⚠️ 名字是**拱跨宽**与**拱顶高**，不是「棚体长度」：那是沿棚长（y）的跨度。
 */
const widthText = computed(() => (
  summary.data.value ? `${summary.data.value.shed_width.toFixed(2)} m` : '正在取'
))
const heightText = computed(() => (
  summary.data.value ? `${summary.data.value.shed_height.toFixed(2)} m` : '正在取'
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

/* ── 概览那一条（2026-10-12） ─────────────────────────────────────── */

/**
 * 三格。**值全部是已经格式化好的字符串**，语气也在这里定 ——
 * `OverviewStrip` 不认识页⑤，只按 `tone` 上一个类名。
 *
 * ⚠️ 2026-10-16 用户裁定：每格那第三行副文案（「拱形以内、z 不高于 1.10 m」
 * 等三句）**整块删掉**，`OverviewStrip` 那边连 `.sub` 那个元素一起撤了。
 * 理由是这一屏的版面：三维 / 环境参数 / 沿栅均温三块要**同屏不滚动**，
 * 每格省下一行就是几十像素。三句真话的去处分别是 —— 均温那一句搬进了页脚的
 * 「口径与出处」；「这一帧的体网格」在三维那一块的卡片里本来就写着；
 * 「实时数据，动态更新」说了等于没说（它旁边就是「更新时间」那一格）。
 *
 * ⚠️ 参考图那个「（切割 y = 18.00）」仍然**不印**（规格书 §三 D10，没被推翻）：
 * 这一屏演的是三维全场，后端没有「当前剖切位置」这个数，也不该为它编一个。
 */
type Cell = {
  key: string; label: string; value: string; tone: 'plain' | 'ok' | 'warn'
}

const overview = computed<readonly Cell[]>(() => [
  {
    key: 'mean', label: '棚内平均温度', value: meanText.value, tone: 'plain',
  },
  {
    key: 'scene', label: '棚体三维温度场', value: sceneText.value,
    tone: sceneText.value === '取数失败' ? 'warn' : (sceneText.value === '已生成' ? 'ok' : 'plain'),
  },
  {
    key: 'time', label: '更新时间', value: frameTimeText.value, tone: 'plain',
  },
])

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
    <h2>实时模式</h2>

    <p v-if="error" role="alert" class="alert">{{ error }}</p>

    <!-- ⚠️ 整屏都在 `hasModel` 里：没有能用的模型时连状态条、指标卡、
         那几个控件都不给 —— 它们一个都起不了作用，摆着只会让人以为
         再点一下就会有一帧出来。
         ⚠️ 三支空态的**次序不能反**：取数失败时 `data` 也是 `null`，
         「连不上」与「还没回来」两条都成立，先撞上谁由次序定。
         把「连不上」说成「还没有可用的模型」是本仓最忌讳的错法
         （规格书 §七）—— 空库是用户能解决的状态（去训一个），
         连不上不是；说成空库，他会去训一个，然后保存时再撞一次同样的 500。 -->
    <Card v-if="models.error.value">
      <p class="err" role="alert">{{ models.error.value }}</p>
    </Card>

    <Card v-else-if="!modelsLoaded"><!-- 取数还没回来：什么断言都不下 --></Card>

    <Card v-else-if="!hasModel">
      <h3>{{ FIELD_MODEL.none }}</h3>
      <p class="note state">{{ FIELD_MODEL.noneWhy }}</p>
      <p>
        <RouterLink to="/models">{{ FIELD_MODEL.toLibrary }}</RouterLink>
        　
        <RouterLink to="/train">{{ FIELD_MODEL.toTrain }}</RouterLink>
      </p>
    </Card>

    <template v-else>
    <!-- ⚠️ 2026-10-09 用户裁定：这一屏**只留温度场**。这里原先有两条东西，
         整块删掉了 ——
           · 一条状态句：「实时源已就绪：第 N 帧，共 M 帧，5 分钟一帧。」
           · 一排四张指标卡（帧 / 共 / 一帧 / 本帧时刻）
         用户的原话：「实时模式主要就是为了展示构建的温度场，温度场才是重点，
         要让用户一眼就能观察到全貌，不需要向下滚动就能看到全貌，所以把一些
         不重要东西都删掉……第几帧，一共多少帧这几个就没必要展示出来，后端
         系统知道就行」。
         那两条说的都是帧数，而它们在温度场**上面**占了将近一屏的三分之一。
         唯一留下的是「本帧时刻」—— 它挪到了三维影像自己的角上（见下面
         `<VolumeView show-clock>`）。状态句里那句真话（帧历史在内存里）
         也留着，收进了页脚那个「口径与出处」。
         同日还在撤：三维画面上方那两行口径说明（「这一段话也没必要展示了」）
         —— 那是 `VolumeView` 给的，页⑤ 传 `:show-notes="false"` 关掉，页③ 不动；
         以及「看哪一块」那行控件标签，和常驻在屏上的那一句**分级**
         （它折进了页脚，见下面 `<details class="why">` 里那段注释 —— 那是
         有意推翻规格书的一条，不是普通排版）。
         `LiveView.test.ts` 里几条用例钉着这件事：不报帧数、没有指标卡、
         那句真话还在 DOM 里、那两行不在而滑块还在、分级句在折叠里且只有一处、
         以及「看哪一块」没了而分段控件还在。 -->

    <div class="row">
      <button
        v-if="!ready || !!status?.pending_session_id" type="button" data-act="prepare" :disabled="preparing"
        @click="act('prepare')"
      >{{ prepareText }}</button>
      <template v-if="ready">
        <button type="button" data-act="start" :disabled="preparing || !!status?.running || !!status?.pending_session_id"
                @click="act('start')">开始</button>
        <button type="button" data-act="pause" :disabled="preparing || !status?.running || !!status?.pending_session_id"
                @click="act('pause')">暂停</button>
        <button type="button" data-act="next" :disabled="preparing || !!status?.pending_session_id"
                @click="act('next')">下一帧</button>
      </template>
      <button v-if="status?.session_id && !status?.pending_session_id" type="button" data-act="new"
              :disabled="preparing || !!status?.running" @click="act('new')">重新准备</button>
      <span v-if="status?.model_name" class="note live-model" :title="`本次实时会话使用的模型：${status.model_name}`">
        模型：{{ status.model_name }}
      </span>
      <span v-if="busy" class="note">正在处理…</span>
      <span v-else-if="status?.detail" class="note">{{ status.detail }}</span>
    </div>

    <p v-if="!ready" class="note state">
      准备要建一次管线，第一次要等几十秒。这之后每一帧是秒级的。
    </p>

    <template v-else>
      <p v-if="frame.error.value" role="alert" class="alert">{{ frame.error.value }}</p>

      <!-- 视图切换（2026-10-09 用户裁定）。控件摆在内容**上面** ——
           它管的就是下面这一块是谁。
           ⚠️ 用户同日把上面那行 `<legend>看哪一块</legend>` 也圈掉删了 ——
           底下两个按钮本来就写着「断面」「三维」。撤的是那行标签，不是这个
           `fieldset`：`fieldset.rail-box .seg` 是两页共用的那条钩子。 -->
      <fieldset class="rail-box rail-switch">
        <!-- 与页③ 同一条分段控件（spec §九）—— 两页共用一种控件，
             样式各写一份但规则一致，`guards.test.ts` 有一条守卫同时扫这两处。 -->
        <div class="seg">
          <button
            v-for="v in FIELD_VIEWS" :key="v.key"
            type="button" :data-view="v.key" :class="{ on: view === v.key }"
            @click="view = v.key"
          >{{ v.label }}</button>
        </div>
      </fieldset>

      <!-- ⚠️ 两块**互斥**、共用一个位子（2026-10-09 用户裁定）：原先断面那张卡
           没有 `v-if` 拦着，切到三维就成了「断面卡 + 三维块」上下两条 ——
           用户得往下翻才看得全，这一屏的版面因此没法按「一屏」来设计。
           页③ 一直是 `v-if` / `v-else`，只有实时这一屏漏了。
           `LiveView.test.ts` 里那条「切过去是换掉，不是接在下面」两侧都钉着。 -->
      <!-- ⚠️ 2026-10-09 第二轮（参考图）：概览三格回来了。用户原话
           「本帧时刻挪到指标卡」—— 第一轮把它印到三维影像的角上，
           第二轮挪回这一行：它落在这一行里，断面与三维**两档都看得见**，
           而角上那份只有三维那一档有。
           ⚠️ 2026-10-12 起它是一条**长条**（`OverviewStrip`），不再是
           「一排等宽卡片」（`StatRow` + `StatCard` 那一对是页① 的版面，
           见规格书 §六）。三格的名字也跟着规格书那一张表定稿：
           棚内平均温度 / 棚体三维温度场 / 更新时间。
           ⚠️ 三格里一格都不报帧数：「第几帧、一共多少帧没必要展示」那条
           裁定没被推翻（`LiveView.test.ts` 两侧都钉着）。
           一律不带 `prov` 图章：三格上的数都是这次请求现算的，印三个
           一模一样的「算」是重复（与页① 同一年的同一条裁定）。 -->
      <OverviewStrip :cells="overview" />

      <!-- ⚠️ 两块**互斥**、共用一个位子（2026-10-09 第一轮用户裁定）：
           原先断面那张卡没有 `v-if` 拦着，切到三维就成了上下两条。
           页③ 一直是 `v-if` / `v-else`，只有实时这一屏漏了。 -->
      <template v-if="view === 'section'">
        <Card v-if="frame.data.value" class="block">
          <div class="row head">
            <!-- ⚠️ 头不再是「第 N 帧」（2026-10-09 第二轮）：帧号是不报的那几个
                 数之一。这一块画的是三个断面，头就写它是什么。 -->
            <h3>断面温度场</h3>
            <span class="tag">
              {{ calibratedLabel(frame.data.value) }}
            </span>
          </div>
          <p class="note reading">
            这一帧的 24 路实测读数（次序：p1 的 8 个位置，然后 p2、p3）：
            <span class="num">{{ frame.data.value.frame.sensor_temps.map(show).join('、') }}</span>
          </p>

          <EChart v-if="v5" :option="v5" height="420px" @pick="onPick" />
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
      <div v-else class="stage">
        <VolumeView
          :key="status?.session_id ?? 'legacy'"
          :session-id="status?.session_id ?? undefined"
          source="live" :t-index="status?.cursor ?? 0"
          panels="shell" :show-notes="false" stretch
          :clock-time="frame.data.value?.frame.time ?? ''"
        />
      </div>

      <!-- 底栏两块（2026-10-09 第二轮，照参考图下方那两块）；
           ⚠️ 2026-10-12 左块照参考图换成了「环境参数（棚体与周边）」
           （规格书 §三 D7，用户裁定「照参考图换掉」）。**那是一次内容的净损失**：
           棚顶那一组气象读数仍在 `/api/live/frame/{n}` 的返回体里，
           只是这一屏不再印。要恢复，在右栏再加一张卡就行。
           ⚠️ 两块都挂在**帧**这一级，与「看哪一块」无关。 -->
      <div class="foot">
        <Card class="env-card">
          <div class="env-head">
            <Icon name="thermometer" />
            <h3>环境参数</h3>
            <span class="note">（棚体与周边）</span>
          </div>
          <div class="env">
            <GaugeDial
              :frac="meanFrac" :value-text="meanText" :arc-color="meanColor"
              label="棚内平均温度" :size="88"
            />
            <div class="geom-card">
              <div class="geom-head"><Icon name="ruler" /><span class="g-label">拱跨宽</span></div>
              <span class="num g-value">{{ widthText }}</span>
            </div>
            <div class="geom-card">
              <div class="geom-head"><Icon name="cube" /><span class="g-label">拱顶高</span></div>
              <span class="num g-value">{{ heightText }}</span>
            </div>
          </div>
          <!-- ⚠️ 这两格是**后端算好的真几何**（本数据集里是 2.10 m 与 1.30 m），
               不是参考图上那个更大的跨度 —— 那一个是沿棚长方向的走廊跨度。
               见 `routes/field.py::volume_payload`。
               ⚠️ 2026-10-16 第二回：原先压在这两格底下有一句口径说明，撤进
               页脚的「口径与出处」了 —— 与均温那一句同一条处置。 -->
        </Card>

        <Card>
          <h3>{{ MEAN_CURVE_TITLE }}</h3>
          <!-- ⚠️ 高度 2026-10-16 从 240px 收到 150px：这一屏要三块同屏不滚动，
               而这条曲线的形状在 150px 上照样读得出（它说的是「从头到尾哪儿热」
               的趋势，不是要读刻度）。 -->
          <EChart v-if="vCurve" :option="vCurve" height="min(150px, 14vh)" />
          <!-- ⚠️ 这一格**不印后端的原话**：它是底栏的次要一块，把一条接口错误
               原样摊在这里会盖过温度场。而 `routes.smoke.test.ts` 那条禁字形
               扫描是逐页扫整页文本的，一句来路不明的错误文案正是最容易带进
               禁字形的地方。 -->
          <p v-else class="note state">正在取这一帧的沿棚均温…</p>
          <!-- ⚠️ 这一格原来压着一句口径说明，2026-10-16 第二回连同左块那一句
               一起撤进页脚的「口径与出处」了：这一屏要三块同屏不滚动，
               而底栏是全屏最高的那一块，两句话就是将近五十像素。 -->
        </Card>
      </div>

      <!-- 右栏（2026-10-12 规格书 §三 D8）。**三档都在的只有三维那一支**：
           `VolumeView` 自己把三张卡投进 `#shell-side`；断面这一档它根本没挂载，
           所以那一段由这里补上 —— 只有一张问数卡（几何与剖切、视图控制
           服务的是三维，断面档上没有它们的事）。
           ⚠️ **落点不在文档里时 Vue 静默不挂**：这一块会整块消失而不报错。
           `LiveView.test.ts` 自己造落点，正是防这一手。 -->
      <Teleport v-if="view === 'section'" to="#shell-side">
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
    </template>

    <!-- 口径与出处：一页最多一处（spec §八）。收起来，但内容始终在 DOM 里。 -->
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
        图上一个格子只有三种回答：拱外无定义、无测量带里不报数、以及一个带出处的实测值。
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
      <!-- ⚠️ 下面两句 2026-10-16 第二回从底栏那两张卡上撤下来的。**同一个处置**
           （降级不是删除）：底栏是全屏最高的一块，两句话压在卡片底下就是将近
           五十像素，而这一屏的账压在「三块同屏」上。`LiveView.test.ts` 里
           断这两句的那两条**照样绿** —— 内容在 DOM 里。 -->
      <p class="note">
        拱跨宽与拱顶高由后端给，是棚体的几何常量。腔内的平均温度见左边那个环。
      </p>
      <p class="note">
        沿棚位每 3 m 采一片，每一片取拱形以内、实测带以内的平均。
        它说的是「这一棚从头到尾哪儿热」，与断面图说的「这一片里哪儿热」不是一回事。
      </p>
      <p class="note">
        数据集末 144 帧留了出（2026-07-27 12:00 起），模型只在其余 1164 帧上标定过一次。
        这里一帧一帧把它们接进时间轴。
      </p>
      <!-- 原先挂在顶部那条状态句上。整句说的都是帧数，跟着指标卡一起撤了，
           但这一句不是帧数、是**用户该知道的口径**：重启服务这一屏就从头演。 -->
      <p class="note">
        数据源、模型和确认位置随会话保留。计算服务重启后，可恢复到上次确认帧，恢复后保持暂停。
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
    </template>
  </section>
</template>

<style scoped>
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
.foot {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.5fr);
  gap: var(--gap-m);
  margin-top: var(--gap-m);
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
.why { margin-top: var(--gap-m); }
.why summary { font-size: var(--size-label); color: var(--ink-muted); cursor: pointer; }
.why > p { margin-top: var(--gap-s); }
/* 环境参数：温度环与两张几何卡片始终在同一排，收紧占用高度。 */
.env-card { container-type: inline-size; }
.env-head { display: flex; align-items: center; gap: var(--gap-s); margin-bottom: var(--gap-m); }
.env-head :deep(.icon) { --icon-size: 22px; color: var(--edge); }
.env-head .note { margin-left: -4px; }
.env { display: grid; grid-template-columns: 88px repeat(2, minmax(0, 1fr)); align-items: stretch; gap: var(--gap-s); }
.geom-card {
  min-width: 0; min-height: 72px; padding: var(--gap-s) 6px;
  display: flex; flex-direction: column; justify-content: center; gap: var(--gap-s);
  border: 1px solid var(--steel); border-radius: var(--radius);
}
.geom-head { display: flex; align-items: center; gap: 4px; min-width: 0; }
.geom-head :deep(.icon) { --icon-size: 18px; flex: none; color: var(--interact); }
.g-label { font-size: var(--size-label); color: var(--ink-muted); }
.g-value { font-size: var(--size-h3); font-weight: var(--w-strong); white-space: nowrap; }
@container (max-width: 420px) {
  .env { grid-template-columns: 88px repeat(2, minmax(0, 1fr)); gap: 4px; }
  .geom-card { padding: var(--gap-s) 4px; }
  .geom-head { gap: 2px; }
  .geom-head :deep(.icon) { --icon-size: 16px; }
  .g-label { font-size: var(--size-note); }
  .g-value { font-size: var(--size-label); }
}
/* 右栏那张卡：它是 `<Teleport>` 投出去的那个落点里的一块，落点的 `gap`
   管卡片间距，这里只管卡片内部两组之间的间距。 */
.side-card { display: flex; flex-direction: column; }
</style>
