<script setup lang="ts">
/**
 * 页③ 空间温度场的构建（V5 切面场）。
 *
 * 三块：切面场（旗舰）→ 点选读数 → 单点曲线 → ΔT 第四格。
 * 左栏经 `#rail-extra` 投进去的是视图切换与时刻游标（spec §8.3 的版式）。
 *
 * **这一页不做任何计算**（硬约束 1）。连"这一格是多少度"都是从**已经拿到的**
 * 载荷里读的 —— 点选是拾取，不是重跑（spec §七 V5）。所以点一下是秒回的，
 * 而且屏幕上显示的数和图上那个格子必然相等。
 */
import { computed, defineAsyncComponent, h, onMounted, ref, watch } from 'vue'

import type { ComparePayload, CurvePayload, SectionsPayload } from '../api/types'
import { getJson } from '../api/client'
import EChart from '../charts/EChart.vue'
import { buildConstraintDeltaOption, deltaNote } from '../charts/options/constraintDelta'
import { buildPointCurveOption, CURVE_NO_MONOTONIC_NOTE } from '../charts/options/pointCurve'
import { buildSectionFieldOption, shedOfSeries } from '../charts/options/sectionField'
import { interpretPick, pickText } from '../charts/pick'
import Provenance from '../components/Provenance.vue'
import { useAsync } from '../composables/useAsync'
import { FIELD_VIEWS } from '../design/copy'
import { readPalette } from '../design/palette'

// 三维那一块**整块懒加载**：`import()` 的路径是**字面量**，打包器静态可分析，
// Vite 会自己切出一个 chunk，不需要 `rollupOptions.manualChunks`。
// 这不违反 `router/index.ts` 那条「静态 import、不用动态 import()」的规矩 ——
// 那条规矩说的是 `views/` 的**视图表**，理由是「模板字符串路径打包器分析不了」。
// 这里没有模板字符串，`VolumeView` 也不是一个视图，它是页③ 里的一块。
//
// 占位那块用 `h()` 写，不用 `template:` 字符串：打包出来的 `vue` 解析到的是
// `vue.runtime.esm-bundler.js`（**没有运行时编译器**，`vite.config.ts` 里也没
// 有把它 alias 到带编译器的那份）。字符串模板只有测试环境能编译 —— vitest 走
// `node` 条件、解析到带编译器的 `index.mjs`，所以在测试里是绿的，真跑起来只会
// 抛一句「runtime compilation is not supported」，占位就没了。
const VolumeView = defineAsyncComponent({
  loader: () => import('../scene/VolumeView.vue'),
  loadingComponent: {
    name: 'VolumeLoading',
    render: () => h('p', { class: 'note' }, '正在加载三维模块…'),
  },
  delay: 0,
})

const palette = readPalette()

const tIndex = ref(0)
/** 「你正在看哪一棚」。初始 p1；点中别棚的格子就跟着走。 */
const activeShed = ref('p1')
/** 点中的格子。`null` = 还没点过。 */
const picked = ref<{ shed: string; ix: number; iz: number } | null>(null)

const sections = useAsync(
  () => getJson<SectionsPayload>(`/api/field/sections?t_index=${tIndex.value}`))
const compare = useAsync(
  () => getJson<ComparePayload>(
    `/api/field/compare?shed=${activeShed.value}&t_index=${tIndex.value}`))
const curve = useAsync(async () => {
  const p = picked.value
  const s = sections.data.value
  // `run()` 只在点中之后被调用，所以走到这里就是 bug —— 抛出去，
  // 别拿 `!` 把问题盖住。
  if (!p || !s) throw new Error('还没点选任何格子，不该去取曲线')
  return getJson<CurvePayload>(
    `/api/field/curve?shed=${p.shed}&x=${s.x[p.ix]}&z=${s.z[p.iz]}`)
})

function reload() {
  void sections.run()
  void compare.run()
}

onMounted(reload)
watch(tIndex, reload)
watch(activeShed, () => void compare.run())

/** 视图切换。两项都开着：「断面」是入口，「三维」懒加载（见上面的 defineAsyncComponent）。 */
const view = ref('section')

function step(d: number) {
  const n = sections.data.value?.n_times ?? 1
  tIndex.value = Math.min(n - 1, Math.max(0, tIndex.value + d))
}

function onSeek(e: Event) {
  tIndex.value = Number((e.target as HTMLInputElement).value)
}

/**
 * 点选。**只从已经拿到的载荷里读**，不再打接口 —— 见文件顶部那段。
 * 认不出的系列（装饰性的拱线、测点、斜纹都是 silent，本来也不会来）直接忽略。
 */
function onPick(ev: { seriesIndex: number; value: unknown }) {
  const s = sections.data.value
  if (!s) return
  const shed = shedOfSeries(s, ev.seriesIndex)
  if (!shed || !Array.isArray(ev.value) || ev.value.length < 2) return
  picked.value = { shed, ix: Number(ev.value[0]), iz: Number(ev.value[1]) }
  activeShed.value = shed
  void curve.run()
}

const v5 = computed(() =>
  sections.data.value ? buildSectionFieldOption(sections.data.value, palette) : null)
const vDelta = computed(() =>
  compare.data.value ? buildConstraintDeltaOption(compare.data.value, palette) : null)
const vCurve = computed(() => {
  const c = curve.data.value
  return c && c.defined ? buildPointCurveOption(c, palette) : null
})

/** 点选读数：位置 + 三种回答里的一种（判定在 `charts/pick.ts`，只有那一处）。 */
const readout = computed(() => {
  const s = sections.data.value
  const p = picked.value
  if (!s || !p) return null
  return {
    where: `${p.shed}　x ${s.x[p.ix].toFixed(2)} m　z ${s.z[p.iz].toFixed(2)} m`,
    text: pickText(interpretPick(s, p.shed, p.ix, p.iz), s.max_measured_z),
  }
})

// 载荷的 `note` 为空就用兜底 —— 这句「没有施加竖直软单调投影」一旦无声消失，
// 看图的人会以为曲线经过了投影。是 `||` 不是 `??`：空串也算「没带」。
// 只在**有曲线可谈**的时候说它：还没点过格子、或该点无定义（不画线）时，
// 这句是在讲一条不存在的线，读者会去找那条线。
const curveNote = computed(() =>
  curve.data.value?.defined ? (curve.data.value.note || CURVE_NO_MONOTONIC_NOTE) : '')
const dNote = computed(() => compare.data.value ? deltaNote(compare.data.value) : '')

// 任何一路挂了都要报出**是哪一路**（后端的 detail 原话），不许吞成一片空白。
const failure = computed(() =>
  [sections.error.value, compare.error.value, curve.error.value].filter(Boolean).join('；'))
</script>

<template>
  <section>
    <h2>空间温度场的构建</h2>

    <!-- 左栏控件。App.vue 把整列交给了 NavRail，所以这里投进它留的落点
         （spec §8.3：左栏是窄的仪器侧栏，导航 + 视图切换 + 时刻游标）。
         `defer`：落点 `#rail-extra` 由 NavRail 渲染，与本页同在一棵树里；
         Vue 挂载时**先把子挂完再把父插进文档**，所以本页挂载的那一刻，
         `#rail-extra` 还没进文档、按字符串找不着。`defer` 把落点解析推迟到
         整棵树挂完之后的 post-flush —— 那时落点已在文档里。 -->
    <Teleport defer to="#rail-extra">
      <fieldset class="rail-box">
        <legend>视图</legend>
        <button
          v-for="v in FIELD_VIEWS" :key="v.key"
          type="button"
          :class="{ on: view === v.key }"
          :disabled="!v.enabled"
          :title="v.enabled ? '' : v.why"
          @click="view = v.key"
        >{{ v.label }}</button>
        <p v-for="v in FIELD_VIEWS.filter((x) => !x.enabled)" :key="`why-${v.key}`" class="note">
          {{ v.label }}：{{ v.why }}
        </p>
      </fieldset>

      <fieldset class="rail-box">
        <legend>时刻</legend>
        <input
          type="range" min="0"
          :max="Math.max(0, (sections.data.value?.n_times ?? 1) - 1)"
          :value="tIndex" aria-label="时刻游标" @input="onSeek"
        >
        <!-- 占位不写破折号：spec §8.5 禁的正是这种装饰性连接符。 -->
        <p class="num">{{ sections.data.value?.time ?? '还没取到' }}</p>
        <div class="row">
          <button type="button" @click="step(-1)">上一帧</button>
          <button type="button" @click="step(1)">下一帧</button>
        </div>
      </fieldset>
    </Teleport>

    <p v-if="failure" role="alert" class="alert">{{ failure }}</p>

    <template v-if="view === 'section'">
      <!-- 1. 切面场 -->
      <div class="block">
        <div class="row head">
          <h3>三个断面的温度场</h3>
          <span v-if="sections.data.value" class="tag">
            {{ sections.data.value.calibrated ? '已标定' : '未标定（兜底参数）' }}
            <Provenance kind="live" />
          </span>
        </div>
        <p v-if="sections.data.value" class="note">
          {{ sections.data.value.note }}
          三个断面<strong>共用同一个色标范围</strong>（{{ sections.data.value.vmin.toFixed(1) }} 至
          {{ sections.data.value.vmax.toFixed(1) }} °C），并排看才成立。
        </p>
        <p class="note">
          点一个格子看它的读数与 5 天曲线。一共只有三种回答：拱外无定义 /
          无测量带不报数 / 一个带出处的数。
        </p>
        <EChart v-if="v5" :option="v5" height="420px" @pick="onPick" />
        <p v-else-if="sections.error.value" class="note">场没取到，见上方提示。</p>
        <p v-else class="note">正在取场…（第一次要训练模型，可能要等一会儿）</p>
      </div>

      <!-- 2. 点选读数 -->
      <div class="block">
        <h3>这一格是什么</h3>
        <p v-if="!readout" class="note">还没点任何格子。上图里点一下。</p>
        <table v-else>
          <tbody>
            <tr><th>位置</th><td class="num">{{ readout.where }}</td></tr>
            <tr><th>回答</th><td>{{ readout.text }}</td></tr>
          </tbody>
        </table>
      </div>

      <!-- 3. 单点 5 天曲线 -->
      <div class="block">
        <h3>这一点的 5 天</h3>
        <EChart v-if="vCurve" :option="vCurve" height="300px" />
        <p v-else-if="curve.loading.value" class="note">正在取曲线…</p>
        <p v-else-if="curve.data.value && !curve.data.value.defined" class="note">
          该点无定义（拱外或在无测量带里），不画曲线。
        </p>
        <p v-else class="note">点一个格子看它在整个时间轴上怎么变。</p>
        <p v-if="curveNote" class="note">{{ curveNote }}</p>
      </div>

      <!-- 4. ΔT 第四格 -->
      <div class="block">
        <h3>竖直软单调投影改了多少</h3>
        <p v-if="dNote" class="note">{{ dNote }}</p>
        <p v-if="compare.data.value" class="note">{{ compare.data.value.note }}</p>
        <EChart v-if="vDelta" :option="vDelta" height="320px" />
        <p v-else-if="compare.error.value" class="note">对比没取到，见上方提示。</p>
        <p v-else class="note">正在取对比…</p>
      </div>
    </template>

    <!-- 5. 三维棚体（懒加载的一块）。时刻跟着上面那个钟走，三维不新增时间控件。 -->
    <VolumeView v-else :t-index="tIndex" :clock-time="sections.data.value?.time ?? ''" />
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
.rail-box button { font: inherit; cursor: pointer; }
.rail-box button.on { font-weight: var(--w-strong); }
</style>
