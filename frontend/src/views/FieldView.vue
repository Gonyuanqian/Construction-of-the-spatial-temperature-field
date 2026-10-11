<script setup lang="ts">
/**
 * 页③ 空间温度场的构建（V5 切面场）。
 *
 * 两块：切面场（旗舰）→ ΔT 第四格。
 * 左栏经 `#rail-extra` 投进去的是视图切换与时刻游标（spec §8.3 的版式）。
 *
 * ⚠️ 2026-10-09：原来这里还有「点选读数」与「单点 5 天曲线」两张卡（点一格看
 * 它是什么、看它 5 天怎么变）。用户看过实机后判定这两张在「空间温度场的构建」
 * 这一页上没必要，连同图上那套点选交互一并撤掉 —— 这一页要讲的是**场**，
 * 某一格的读数与它的单点曲线是另一件事，不该跟三张场挤在同一页。
 *
 * 撤掉的是**这一页的用法**，不是那套能力：后端的 `/api/field/curve` 与
 * `charts/options/pointCurve.ts` 都原样留着（一个字没删），`charts/pick.ts`
 * 的判定仍被三维那一块与实时屏用着。只是页③ 不再有入口。
 *
 * 2026-10-06（spec §6.2 页③）：页顶加一排四张指标卡，四块面板各套一层 `Card`，
 * 散文折进页尾「口径与出处」。第四格是全套界面长在这个题目上的证据：
 * 通用的大数字栅格永远不会有一个格子在拒绝报数。
 */
import { computed, defineAsyncComponent, h, onMounted, ref, watch } from 'vue'

import type { ComparePayload, SectionsPayload } from '../api/types'
import { getJson } from '../api/client'
import { fetchModels, setCurrentModel, usableModels } from '../api/models'
import EChart from '../charts/EChart.vue'
import { buildConstraintDeltaOption, deltaNote } from '../charts/options/constraintDelta'
import { buildSectionFieldOption } from '../charts/options/sectionField'
import Card from '../components/Card.vue'
import Provenance from '../components/Provenance.vue'
import StatCard from '../components/StatCard.vue'
import StatRow from '../components/StatRow.vue'
import { useAsync } from '../composables/useAsync'
import { BORROWED, calibratedLabel, FIELD_MODEL, FIELD_VIEWS } from '../design/copy'
import { fmt1, fmtRange, fmtTime } from '../design/format'
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
/**
 * ΔT 那一格画哪一棚。**固定 `p1`。**
 *
 * 它原来是跟着「点中的格子」走的（点别棚的格子，ΔT 面板就换棚）。点选撤掉
 * 之后，页面上没有第二处能改它了 —— 再挂一个 `ref` 加一条永远不触发的
 * `watch`，只是给读的人出一道「这还会变吗」的谜题。
 */
const SHED = 'p1'

const sections = useAsync(
  () => getJson<SectionsPayload>(`/api/field/sections?t_index=${tIndex.value}`))
const compare = useAsync(
  () => getJson<ComparePayload>(`/api/field/compare?shed=${SHED}&t_index=${tIndex.value}`))

/**
 * 模型库那一支（规格书 §6.4）。**这一页的场从哪来，由用户在这里点**——
 * 系统不再自己找一个模型就开始构建。
 *
 * ⚠️ 这一行必须**先**完成（见 `onMounted`）：`ready` 是由它算出来的，
 * 次序反了的话 `ready` 还是 false，下面那三个取数全被挡掉，首屏永远空白。
 */
const models = useAsync(fetchModels)

/**
 * 能用来构场的那些。**空数组 = 什么都不画**（规格书 D4）。
 *
 * ⚠️ 条件里**不看** `current_id`：「当前模型对不上当前数据集」与「一个能用的
 * 都没有」在界面上是同一件事（都要用户去挑一个）。分开处理会长出一个
 * 半画的状态 —— 画了场、标一句「对不上」，而那个场看着完全正常。
 */
const usable = computed(() => usableModels(models.data.value))
const ready = computed(() => usable.value.length > 0)

/** 下拉的当前值。库里标着当前、且可用的那一行；否则第一行可用的。 */
const modelId = computed<number | null>(() => {
  const id = models.data.value?.current_id ?? null
  if (id !== null && usable.value.some((r) => r.id === id)) return id
  return usable.value[0]?.id ?? null
})

async function onPickModel(e: Event): Promise<void> {
  const id = Number((e.target as HTMLSelectElement).value)
  if (!Number.isFinite(id) || id === modelId.value) return
  await setCurrentModel(id)
  await models.run()
  // ⚠️ **`models.run()` 到这儿还不够。** 它换掉的是「当前模型」这一个标；
  // 屏上那两张场是 `/api/field/sections` 与 `/api/field/compare` 按**旧模型**
  // 算好、已经摆在组件里的像素。不重取，下拉与「当前」都指向新模型，图还是
  // 旧的 —— 而且不报错、不提示，只是端出一张旧模型算的场，正是规格书 D4 说的
  // 「看着对的错场」。
  reload()
}

/** 数印四位（下拉里那个 MAE）。⚠️ 只印后端给的数，null 就印「无值」—— 不补一个 0。 */
function num(v: number | null): string {
  return v === null || !Number.isFinite(v) ? '无值' : v.toFixed(4)
}

function reload(): void {
  // ⚠️ 没有可用模型时那两个 field 接口一个都不打：打了也拿不到场，
  // 只是让后端白算一遍，而用户要多等一轮。
  if (!ready.value) return
  void sections.run()
  void compare.run()
}

onMounted(async () => {
  // 次序：先问库里有什么模型，再决定要不要取场（`ready` 由第一个请求算出来）。
  await models.run()
  reload()
})
watch(tIndex, reload)

/** 视图切换。两项都开着：「断面」是入口，「三维」懒加载（见上面的 defineAsyncComponent）。 */
const view = ref('section')

function step(d: number) {
  const n = sections.data.value?.n_times ?? 1
  tIndex.value = Math.min(n - 1, Math.max(0, tIndex.value + d))
}

function onSeek(e: Event) {
  tIndex.value = Number((e.target as HTMLInputElement).value)
}

const v5 = computed(() =>
  sections.data.value ? buildSectionFieldOption(sections.data.value, palette) : null)
const vDelta = computed(() =>
  compare.data.value ? buildConstraintDeltaOption(compare.data.value, palette) : null)

const dNote = computed(() => compare.data.value ? deltaNote(compare.data.value) : '')

// 任何一路挂了都要报出**是哪一路**（后端的 detail 原话），不许吞成一片空白。
const failure = computed(() =>
  [sections.error.value, compare.error.value].filter(Boolean).join('；'))
</script>

<template>
  <section>
    <h2>空间温度场的构建</h2>

    <!-- 用哪个模型（规格书 §6.4）。**这是需求的原点**：场由用户挑的模型构出来，
         不由系统自己找一个就开始构建。
         ⚠️ 库里的**每一行都列出来**（用户得知道库里有什么、以及为什么某一行
         用不上），三档各有各的样子：
           · 本地的    —— 光一个名字就是它；
           · 借来的    —— 加一个「（借来的）」（2026-10-10 用户裁定：库里有就能
                          挑，不为数据集签名所限；`why` 里有是换了哪一份文件）；
           · 用不了的  —— `disabled`，并把理由印在选项上。
         半画（画了场再标一句「用不了」）等于把一个看着对的错场端给用户。 -->
    <div v-if="ready" class="model-pick">
      <label for="field-model">{{ FIELD_MODEL.pick }}</label>
      <select id="field-model" :value="modelId ?? ''" @change="onPickModel">
        <option v-for="row in models.data.value?.rows ?? []" :key="row.id"
                :value="row.id" :disabled="!row.compatible" :title="row.why">
          {{ row.name }}　{{ row.data_file }}　MAE {{ num(row.mae) }}
          <template v-if="row.borrowed">（{{ BORROWED }}）</template>
          <template v-else-if="!row.compatible">（{{ row.why }}）</template>
        </option>
      </select>
    </div>

    <!-- 空态三支，与「有模型」互斥。⚠️ 取数还没回来那一支**什么都不说**：
         这一页此刻还不知道库里有没有东西，说错一句比不说坏。 -->
    <Card v-else-if="models.error.value">
      <p class="err" role="alert">{{ models.error.value }}</p>
    </Card>

    <Card v-else-if="!models.data.value" />

    <Card v-else>
      <h3>{{ FIELD_MODEL.none }}</h3>
      <!-- ⚠️ `state` 是这一页**此刻**为什么是一片空白的说明，与页② 那句
           「先做参数优选」同一类。`design/prose.test.ts` 是 spec §十二.11 的
           判据本身：不带它这一句会被判成「没归类的散文」，而它确实不是
           口径 —— 口径讲的是这一页怎么读，这一句讲的是这一页现在为什么没有东西。 -->
      <p class="note state">{{ FIELD_MODEL.noneWhy }}</p>
      <p>
        <RouterLink to="/models">{{ FIELD_MODEL.toLibrary }}</RouterLink>
        　
        <RouterLink to="/train">{{ FIELD_MODEL.toTrain }}</RouterLink>
      </p>
    </Card>

    <!-- ⚠️ 整页（含左栏那几个控件）都在 `ready` 里面：没有能用的模型时
         连时刻游标、视图切换都不给 —— 它们没有一个能起作用，
         摆着只会让人以为再点一下就会出来一张场。 -->
    <template v-if="ready">
    <!-- 左栏控件。App.vue 把整列交给了 NavRail，所以这里投进它留的落点
         （spec §8.3：左栏是窄的仪器侧栏，导航 + 视图切换 + 时刻游标）。
         `defer`：落点 `#rail-extra` 由 NavRail 渲染，与本页同在一棵树里；
         Vue 挂载时**先把子挂完再把父插进文档**，所以本页挂载的那一刻，
         `#rail-extra` 还没进文档、按字符串找不着。`defer` 把落点解析推迟到
         整棵树挂完之后的 post-flush —— 那时落点已在文档里。 -->
    <Teleport defer to="#rail-extra">
      <fieldset class="rail-box rail-switch">
        <legend>视图</legend>
        <!-- 分段控件（spec §九）：一条描边的底，里头的按钮无边框、无间距、
             相邻处一条竖线，选中的那个叶子底。原来每个按钮各带圆角边框、
             彼此留缝，读起来是「带框的小表单」——§一 成因 5 说的正是这个。 -->
        <div class="seg">
          <button
            v-for="v in FIELD_VIEWS" :key="v.key"
            type="button" :data-view="v.key"
            :class="{ on: view === v.key }"
            :disabled="!v.enabled"
            :title="v.enabled ? '' : v.why"
            @click="view = v.key"
          >{{ v.label }}</button>
        </div>
        <!-- 未开放的理由留在分段控件外面：它是说明，不是开关的一部分。 -->
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
        <p class="num">{{ sections.data.value ? fmtTime(sections.data.value.time) : '还没取到' }}</p>
        <div class="row">
          <button type="button" @click="step(-1)">上一帧</button>
          <button type="button" @click="step(1)">下一帧</button>
        </div>
      </fieldset>
    </Teleport>

    <p v-if="failure" role="alert" class="alert">{{ failure }}</p>

    <!-- 指标卡片一排（spec §6.2 页③）。第四格**故意不是数**：
         通用的大数字栅格永远不会有一个格子在拒绝报数。 -->
    <StatRow v-if="sections.data.value">
      <StatCard
        label="时刻" :value="fmtTime(sections.data.value.time)" prov="live" compact
      />
      <StatCard
        label="色标"
        :value="fmtRange(sections.data.value.vmin, sections.data.value.vmax, '°C')"
        prov="live" compact
      />
      <StatCard
        label="标定"
        :value="calibratedLabel(sections.data.value)"
        prov="live" compact
      />
      <StatCard
        label="无测量带"
        :value="`z > ${fmt1(sections.data.value.max_measured_z)} m 不报数`"
        compact muted
      />
    </StatRow>

    <template v-if="view === 'section'">
      <!-- 1. 切面场 -->
      <Card class="block">
        <div class="row head">
          <h3>三个断面的温度场</h3>
          <span v-if="sections.data.value" class="tag">
            {{ calibratedLabel(sections.data.value) }}
            <Provenance kind="live" />
          </span>
        </div>
        <EChart v-if="v5" :option="v5" height="420px" />
        <p v-else-if="sections.error.value" class="note state">场没取到，见上方提示。</p>
        <p v-else class="note state">正在取场…（第一次要训练模型，可能要等一会儿）</p>
      </Card>

      <!-- 2. ΔT 第四格 -->
      <Card class="block">
        <h3>竖直软单调投影改了多少</h3>
        <EChart v-if="vDelta" :option="vDelta" height="320px" />
        <p v-else-if="compare.error.value" class="note state">对比没取到，见上方提示。</p>
        <p v-else class="note state">正在取对比…</p>
      </Card>

      <!-- 口径与出处：一页最多一处（spec §八）。收起来，但内容始终在 DOM 里。 -->
      <details class="why">
        <summary>口径与出处</summary>
        <p v-if="sections.data.value" class="note">
          {{ sections.data.value.note }}
          三个断面<strong>共用同一个色标范围</strong>（{{
            fmtRange(sections.data.value.vmin, sections.data.value.vmax, '°C')
          }}），并排看才成立。
        </p>
        <!-- **借来的那一句逐字来自后端**（`deps._BORROWED_NOTE`，跟着载荷的
             `mismatch_note` 过来）。前端不另写一句解释 —— 同一个事实两份措辞，
             迟早一处改了另一处没改。空串（＝这份包就是为这份数据标的）时不印。
             ⚠️ 它在 `details.why` 里：`design/prose.test.ts` 是 spec §十二.11 的
             判据本身，一个裸的 `<p class="note">` 会被判成「没归类的散文」。 -->
        <p v-if="sections.data.value?.mismatch_note" class="note">
          {{ sections.data.value.mismatch_note }}
        </p>
        <!-- ⚠️ 与上面那句**各是一个格**（后端 `deps._artifact_note` → 载荷的
             `artifact_note`）。合成一句会让一份本地的模型自称「借来的」。
             ⚠️ 必须留**在同一个 `details.why` 里面**，不要新开一块 ——
             两句都是「口径与出处」，而 `design/prose.test.ts` 判的是
             「解释只有一处」。 -->
        <p v-if="sections.data.value?.artifact_note" class="note">
          {{ sections.data.value.artifact_note }}
        </p>
        <p v-if="dNote" class="note">{{ dNote }}</p>
        <p v-if="compare.data.value" class="note">{{ compare.data.value.note }}</p>
      </details>
    </template>

    <!-- 5. 三维棚体（懒加载的一块）。时刻跟着上面那个钟走，三维不新增时间控件。 -->
    <VolumeView v-else :t-index="tIndex" :clock-time="sections.data.value?.time ?? ''" />
    </template>
  </section>
</template>

<style scoped>
.block { margin-bottom: var(--gap-xl); }
/* 选模型那一行。它在页首、正文之上 —— 场是它构出来的，先读它再读场。 */
.model-pick {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gap-s);
  margin-bottom: var(--gap-m);
}
.model-pick label { font-size: var(--size-note); color: var(--ink-muted); }
.model-pick select { flex: 1 1 320px; min-width: 0; }
.row { display: flex; gap: var(--gap-s); align-items: center; }
.head { justify-content: space-between; }
.alert { color: var(--leaf); border-left: 3px solid var(--leaf); padding-left: var(--gap-s); }
.tag { font-size: var(--size-note); color: var(--ink-muted); }
.rail-box {
  border: var(--rule); padding: var(--gap-s);
  margin: 0 0 var(--gap-s); font-size: var(--size-note);
}
/* 开关那一块：外框去掉，描边交给里面的分段控件（spec §九）。
   只加在视图切换上，不动三维面板里另外两个 `rail-box`（它们真的是表单）。 */
.rail-switch { border: 0; padding: 0; margin: 0 0 var(--gap-m); }
.rail-switch > legend { padding: 0; font-size: var(--size-label); color: var(--ink-muted); }
.seg {
  display: flex;
  align-items: stretch;
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
/* 圆角由首末两个按钮自己收 —— 不用 `overflow: hidden`：那一句会把
   `:focus-visible` 伸出按钮盒 2px 的焦点环裁掉（终审 M-8，`guards.test.ts` 有守卫）。 */
.seg button:first-child { border-radius: var(--radius) 0 0 var(--radius); }
.seg button:last-child { border-radius: 0 var(--radius) var(--radius) 0; }
.seg button + button { border-left: 1px solid var(--steel); }
.seg button.on { background: var(--leaf); color: var(--paper); }
.seg button:disabled { cursor: not-allowed; }
.why { margin-top: var(--gap-l); }
.why summary { font-size: var(--size-label); color: var(--ink-muted); cursor: pointer; }
.why > p { margin-top: var(--gap-s); }
</style>
