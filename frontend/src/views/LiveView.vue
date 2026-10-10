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
import { getJson, postJson } from '../api/client'
import { fetchModels, usableModels } from '../api/models'
import EChart from '../charts/EChart.vue'
import { buildLiveMeanCurveOption, MEAN_CURVE_TITLE } from '../charts/options/liveMeanCurve'
import { buildSectionFieldOption, shedOfSeries } from '../charts/options/sectionField'
import { interpretPick, pickText } from '../charts/pick'
import Card from '../components/Card.vue'
import StatCard from '../components/StatCard.vue'
import StatRow from '../components/StatRow.vue'
import { useAsync } from '../composables/useAsync'
import { calibratedLabel, FIELD_MODEL, FIELD_VIEWS } from '../design/copy'
import { fmtTime } from '../design/format'
import { readPalette } from '../design/palette'

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

async function refreshStatus() {
  try {
    status.value = await getJson<LiveStatus>('/api/live/status')
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function act(name: 'prepare' | 'start' | 'pause' | 'next') {
  busy.value = true
  try {
    // ⚠️ 回执**不拿来当状态用**。`prepare` 回的是 `{state, seconds}`（规格书 §五），
    // 不是一份 `LiveStatus` —— 把回执赋给 `status` 会让状态条渲染出空的帧号，
    // 还会让下面 `frame` 拼出 `/frame/undefined`（真后端 422），而这是实时模式
    // 唯一的入口动作。所以四个动作一律**问完再重新问一次状态**：
    // 多一次纯读的 GET（`status` 永不失败、永不建管线），换四条路只有一种收尾。
    await postJson<LiveStatus | PrepareResult>(`/api/live/${name}`)
    error.value = ''
    await refreshStatus()
    refetch()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}

/* ── 当前这一帧 ─────────────────────────────────────────── */

const ready = computed(() => status.value?.state === 'ready')

const frame = useAsync(async () => {
  const s = status.value
  if (!s || s.state !== 'ready') throw new Error('实时源还没准备好')
  return getJson<LiveFramePayload>(`/api/live/frame/${s.cursor}`)
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
  return getJson<VolumePayload>(`/api/live/volume/${s.cursor}?y_step=${SUMMARY_Y_STEP}`)
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

onMounted(async () => {
  // 次序：先问库里有不有能用的模型（`hasModel` 由它算出来），
  // 再决定要不要去碰实时源 —— 没有模型的实时源开不了，问了也是白问。
  await models.run()
  if (hasModel.value) await refreshStatus()
  if (ready.value) refetch()
  timer = setInterval(async () => {
    // ⚠️ 这一句**不靠**下面那句顺带挡住（没跑过 `refreshStatus()` 时
    // `status` 是 null）。写成显式的一句是为了把意图放在脸上：
    // 以后谁把 `refreshStatus()` 挪到前面，这一屏就会每 5 秒问一次
    // 一个没法算的服务端。
    if (!hasModel.value) return
    // 暂停时不轮询（规格书 §6.3，也是 §8.2 验收清单里的一条）：暂停时服务端
    // 什么都不动，这一问必然什么都没变。控件点完是 `act()` 去问状态，
    // 不走这里 —— 于是「下一帧」在暂停下照样立刻更新。
    if (!status.value?.running) return
    const before = status.value?.cursor
    await refreshStatus()
    if (ready.value && status.value?.cursor !== before) refetch()
  }, POLL_MS)
})
onUnmounted(() => { if (timer) clearInterval(timer) })

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

/**
 * 「棚顶气象」那三格。与 `show` 同一条规矩：`null` 就是「不报数」。
 *
 * ⚠️ 计划把这三句摆在 `view` 那两行之后，这里改放在这一块 —— 上面那个小节
 * 标题（「指标行与底栏的文案」）点名的正是它们，摆在一起比夹在点选逻辑里
 * 读得顺。行为一个字节都没变。
 */
const bgTemp = computed(() => {
  const v = frame.data.value?.frame.bg_temp
  return v === null || v === undefined ? '不报数' : `${v.toFixed(1)} °C`
})
const bgRh = computed(() => {
  const v = frame.data.value?.frame.bg_rh
  return v === null || v === undefined ? '不报数' : `${v.toFixed(1)} %`
})
const bgLight = computed(() => {
  const v = frame.data.value?.frame.bg_light
  return v === null || v === undefined ? '不报数' : `${v.toFixed(0)} lux`
})

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
</script>

<template>
  <section>
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
        v-if="!ready" type="button" data-act="prepare" :disabled="busy"
        @click="act('prepare')"
      >准备实时源</button>
      <template v-else>
        <button type="button" data-act="start" :disabled="busy || !!status?.running"
                @click="act('start')">开始</button>
        <button type="button" data-act="pause" :disabled="busy || !status?.running"
                @click="act('pause')">暂停</button>
        <button type="button" data-act="next" :disabled="busy"
                @click="act('next')">下一帧</button>
      </template>
      <span v-if="busy" class="note">正在处理…</span>
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
      <!-- ⚠️ 2026-10-09 第二轮（参考图）：指标行回来了。用户原话
           「本帧时刻挪到指标卡」—— 第一轮把它印到三维影像的角上，
           这一轮挪回指标行：它落在指标行里，断面与三维**两档都看得见**，
           而角上那份只有三维那一档有。
           ⚠️ 三张里一张都不报帧数：「第几帧、一共多少帧没必要展示」那条
           裁定没被推翻（`LiveView.test.ts` 两侧都钉着）。
           一律不带 `prov` 图章：三张卡上的数都是这次请求现算的，印三个
           一模一样的「算」是重复（与页① 同一年的同一条裁定）。 -->
      <StatRow>
        <StatCard label="棚内均温" :value="meanText" />
        <StatCard label="三维温度场" :value="sceneText" />
        <StatCard label="本帧时刻" :value="frameTimeText" />
      </StatRow>
      <p class="note reading">
        均温只算拱形以内、z 不高于 {{ zLimitText }} m 的那些格子。拱外没有定义，
        再往上那一条是按外推补出来的，都不进平均。
      </p>

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

          <table v-if="readout">
            <tbody>
              <tr><th>位置</th><td class="num">{{ readout.where }}</td></tr>
              <tr><th>回答</th><td>{{ readout.text }}</td></tr>
            </tbody>
          </table>
          <p v-else class="note state">点一个格子看它的读数。</p>
        </Card>
        <p v-else-if="frame.loading.value" class="note state">正在取这一帧…</p>
      </template>

      <!-- 三维那一块就是页③ 的那一块，取数口换成实时这条。切过去才懒加载它。
           三个开关都在这一屏给：
             · `show-notes` 关掉 —— 2026-10-09 第一轮用户裁定「这一段话也没必要
               展示了」：画面上方那两行口径说明也撤了，画面顶上去。
               规格书 §5.3「棚体示意」那条要求没丢，由左栏滑块的标题与读数接着。
             · `show-view-controls` 打开 —— 第二轮用户裁定「旋转/缩放/平移按钮
               可以做」。
             · ⚠️ **不再传 `show-clock`** —— 第二轮把本帧时刻挪进了指标行，
               角上那份留着就是同一件事印两处。
             · ⚠️ `clock-time` **仍然要传**：它是 `VolumeView` 的必填 prop，而且
               不走那枚钟也仍然读它 —— `VolumeView.vue:263` 那句「正在构体…」
               括号里的时刻、以及 :165 那句「画面仍是 X 的场」，说的都是它。
               计划给的模板漏了这一个 —— 少了它 `vue-tsc` 当场报
               TS2345「Property 'clockTime' is missing … but required」
               （2026-10-09 删掉这一行实测过一次，不是猜的），这里补回来。 -->
      <VolumeView
        v-else
        source="live" :t-index="status?.cursor ?? 0"
        show-view-controls :show-notes="false"
        :clock-time="frame.data.value?.frame.time ?? ''"
      />

      <!-- 底栏两块（2026-10-09 第二轮，照参考图下方那两块）。
           ⚠️ 两块都挂在**帧**这一级，与「看哪一块」无关 —— 第一轮之前
           「棚顶气象」只写在断面那张卡里，切到三维就没了，而它是帧的属性。 -->
      <div class="foot">
        <Card>
          <h3>棚顶气象</h3>
          <StatRow>
            <StatCard compact label="气温" :value="bgTemp" />
            <StatCard compact label="湿度" :value="bgRh" />
            <StatCard compact label="光照" :value="bgLight" />
          </StatRow>
          <p class="note reading">
            棚顶那一组气象读数，这一帧的后端原样给的。
          </p>
        </Card>

        <Card>
          <h3>{{ MEAN_CURVE_TITLE }}</h3>
          <EChart v-if="vCurve" :option="vCurve" height="240px" />
          <!-- ⚠️ 这一格**不印后端的原话**：它是底栏的次要一块，把一条接口错误
               原样摊在这里会盖过温度场。而 `routes.smoke.test.ts` 那条禁字形
               扫描是逐页扫整页文本的，一句来路不明的错误文案正是最容易带进
               禁字形的地方。 -->
          <p v-else class="note state">正在取这一帧的沿棚均温…</p>
          <p class="note reading">
            沿棚位每 3 m 采一片，每一片取拱形以内、实测带以内的平均。
            它说的是「这一棚从头到尾哪儿热」，与断面图说的「这一片里哪儿热」不是一回事。
          </p>
        </Card>
      </div>
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
      <p class="note">
        数据集末 144 帧留了出（2026-07-27 12:00 起），模型只在其余 1164 帧上标定过一次。
        这里一帧一帧把它们接进时间轴。
      </p>
      <!-- 原先挂在顶部那条状态句上。整句说的都是帧数，跟着指标卡一起撤了，
           但这一句不是帧数、是**用户该知道的口径**：重启服务这一屏就从头演。 -->
      <p class="note">
        帧历史只在内存里，服务一重启，就得从头准备一次。
      </p>
      <!-- 正在用的那一份包不是为当前这份数据标的时的那句话。**逐字来自后端**
           （`deps._BORROWED_NOTE` → 载荷的 `mismatch_note`），前端不另写一句
           —— 与页③ 同一句，同一个来源。对得上时它是空串，这一格不印。
           ⭐ 这一档 2026-10-10 才有：在那之前「不是为这份数据标的」的模型
           在这一屏上**根本走不进来**（闸门卡在数据集签名上），而实时模式
           本来就是拿一份别人标好的模型去套没见过的数据。 -->
      <p v-if="frame.data.value?.mismatch_note" class="note">
        {{ frame.data.value.mismatch_note }}
      </p>
    </details>
    </template>
  </section>
</template>

<style scoped>
.block { margin-bottom: var(--gap-xl); }
.row { display: flex; gap: var(--gap-s); align-items: center; }
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
.seg button.on { background: var(--leaf); color: var(--paper); }
.seg button:disabled { cursor: not-allowed; }
.why { margin-top: var(--gap-l); }
.why summary { font-size: var(--size-label); color: var(--ink-muted); cursor: pointer; }
.why > p { margin-top: var(--gap-s); }
</style>
