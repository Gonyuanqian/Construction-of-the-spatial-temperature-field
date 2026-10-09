<script setup lang="ts">
/**
 * 实时模式那一屏：把模型没见过的 144 帧一帧一帧演出来。
 *
 * **这一页不做任何计算**（硬约束 1）：温度、帧号、时间戳、分级文案全部来自
 * 后端，这里的每一个数都是某条接口原样给的。
 *
 * `cursor` 是**服务端**给的（`GET /api/live/status` 的纯读），不是本地推的 ——
 * 时钟在服务端，是 `(started_at, now)` 的纯函数。本地再维护一个「第几帧」
 * 迟早与服务端漂开，而这一屏最不能错的就是「现在演的是第几帧」。
 *
 * ⚠️ **「实时模式」与图章的 `live` 不是一回事**：前者是这一屏的名字，
 * 后者说的是「这个数是这次请求现算的」。四个指标格子都挂 `live` 图章 ——
 * 它们确实都是 `/api/live/*` 现算的。别把两个词混成一个。
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

import type { LiveFramePayload, LiveStatus, PrepareResult } from '../api/types'
import { getJson, postJson } from '../api/client'
import { fetchModels, usableModels } from '../api/models'
import EChart from '../charts/EChart.vue'
import { buildSectionFieldOption, shedOfSeries } from '../charts/options/sectionField'
import { interpretPick, pickText } from '../charts/pick'
import Card from '../components/Card.vue'
import StatCard from '../components/StatCard.vue'
import StatRow from '../components/StatRow.vue'
import { useAsync } from '../composables/useAsync'
import { FIELD_MODEL, FIELD_VIEWS } from '../design/copy'
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
    void frame.run()
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
  if (ready.value) void frame.run()
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
    if (ready.value && status.value?.cursor !== before) void frame.run()
  }, POLL_MS)
})
onUnmounted(() => { if (timer) clearInterval(timer) })

/* ── 文案 ───────────────────────────────────────────────── */

const intervalText = computed(() => {
  const s = status.value?.interval_s ?? 0
  return s >= 60 ? `${Math.round(s / 60)} 分钟一帧` : `${s} 秒一帧`
})

/** `null` 就是后端说的「不报数」—— 不翻成 0，也不留空。 */
const show = (v: number | null): string => (v === null ? '不报数' : v.toFixed(1))

/* ── 断面 + 点选 ────────────────────────────────────────── */

const view = ref<'section' | 'volume'>('section')
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
    <!-- 一行写完，别换行：这一句是要被断言、也是要被读的。 -->
    <p v-if="status" class="note state" role="status">
      实时源{{ ready ? '已就绪' : '还没准备' }}：第 {{ status.cursor }} 帧，共 {{ status.total }} 帧，{{ intervalText }}。帧历史在内存里，重启服务就回到第 0 帧。
    </p>

    <!-- 指标卡片一排（spec §6.2 页⑤）。
         挂在 `status` 上、**不挂在 `frame` 上**：状态是纯读、挂载即到，
         帧要等源准备好了才有。挂在帧上会让这一排在 idle 时整排消失。 -->
    <StatRow v-if="status">
      <StatCard label="帧" :value="`第 ${status.cursor} 帧`" prov="live" compact />
      <StatCard label="共" :value="`${status.total} 帧`" prov="live" compact />
      <StatCard label="一帧" :value="intervalText" prov="live" compact />
      <StatCard
        label="本帧时刻"
        :value="frame.data.value ? fmtTime(frame.data.value.frame.time) : '—'"
        prov="live" compact
      />
    </StatRow>

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
      <!-- 分级必须在屏上。实时是一帧一帧刷过去的，观众只会记住「它在动」；
           分级看不见，就等于把「混合出来的」渲染成「测出来的」。 -->
      <p class="note" data-grading>
        图上一个格子只有三种回答：拱外无定义、无测量带里不报数、以及一个带出处的实测值。
      </p>

      <p v-if="frame.error.value" role="alert" class="alert">{{ frame.error.value }}</p>

      <Card v-if="frame.data.value" class="block">
        <div class="row head">
          <h3>第 {{ frame.data.value.frame.n }} 帧</h3>
          <span class="tag">
            {{ frame.data.value.calibrated ? '已标定' : '未标定（兜底参数）' }}
          </span>
        </div>
        <p class="num">{{ fmtTime(frame.data.value.frame.time) }}</p>
        <p class="note reading">
          棚顶气象：气温 {{ show(frame.data.value.frame.bg_temp) }} °C，
          湿度 {{ show(frame.data.value.frame.bg_rh) }} %，
          光照 {{ show(frame.data.value.frame.bg_light) }} lux。
        </p>
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

      <fieldset class="rail-box rail-switch">
        <legend>看哪一块</legend>
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

      <!-- 三维那一块就是页③ 的那一块，取数口换成实时这条。切过去才懒加载它。 -->
      <VolumeView
        v-if="view === 'volume'"
        source="live" :t-index="status?.cursor ?? 0"
        :clock-time="frame.data.value?.frame.time ?? ''"
      />
    </template>

    <!-- 口径与出处：一页最多一处（spec §八）。收起来，但内容始终在 DOM 里。 -->
    <details class="why">
      <summary>口径与出处</summary>
      <p class="note">
        数据集末 144 帧留了出（2026-07-27 12:00 起），模型只在其余 1164 帧上标定过一次。
        这里一帧一帧把它们接进时间轴。
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
/* 开关那一块：外框去掉，描边交给里面的分段控件（spec §九）。 */
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
