<script setup lang="ts">
/**
 * 三维这一块面板：取体网格、悬停读数、钉住、坐标查询、时刻口径。
 *
 * **Three 不在这个文件里** —— 它由 `FieldView` 懒加载这一整块时才下载。
 * 这里住的是能被测的那一半：取数、判定、文案、防抖。判定走 `charts/pick.ts`
 * （全前端唯一那处），吸附走 `scene/hover.ts`（纯函数），画的那一半在
 * `VolumeScene.vue`。
 *
 * **这一块不做任何数值计算**（硬约束 1）：温度是查表查出来的，坐标是**吸附**到
 * 已经算好的格点上的，两者都不插值。插值就是在前端把 R2 重算一遍 ——
 * 两条路径漂了不报错。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import type { VolumePayload } from '../api/types'
import { getJson } from '../api/client'
import { interpretVolumePick, pickText } from '../charts/pick'
import { useAsync } from '../composables/useAsync'
import { markerPoint, snapIndex, type HoverPick } from './hover'
import VolumeScene from './VolumeScene.vue'
import {
  SHELL_LENGTH_DEFAULT, SHELL_LENGTH_MAX, SHELL_LENGTH_MIN, buildVolumeSpec,
} from './volumeView'

const props = defineProps<{
  /** 全系统唯一的那个钟（页③ 的时刻游标），三维只跟随、不新增控件。 */
  tIndex: number
  /** 那个钟现在指着的时刻。**由二维那一侧给**，三维不自己算也不自己问。 */
  clockTime: string
  /**
   * 取数口。默认页③ 那条 `GET /api/field/volume?t_index=`；
   * 实时模式那一屏传 `'live'`，走 `GET /api/live/volume/{n}`
   * （规格书 §「前端形态」：三维**懒加载这一块**，实时屏不新写第二份）。
   *
   * ⚠️ 两条路的 `tIndex` **不是同一个东西**：页③ 那个是**管线时间轴**下标，
   * 实时那个是留出段的**帧号 `n`**。这一块从不用它算时间 —— 时刻一律来自
   * 载荷自带的 `time`（`clockTime` 也是外面传进来的），
   * 它在这里只当「换个号就重取一次」的触发量。
   */
  source?: 'field' | 'live'
}>()

const volume = useAsync(() => getJson<VolumePayload>(
  props.source === 'live'
    ? `/api/live/volume/${props.tIndex}`
    : `/api/field/volume?t_index=${props.tIndex}`))

/**
 * 拖时刻滑块要防抖：不防抖的话一次拖动就是十几个 1.2 s 的构体请求，
 * 而只有最后一个用得上（规格书 §7.2）。首次挂载**不**走这条路 ——
 * 一进页面就该开始构，不必等一个窗口。
 */
const DEBOUNCE_MS = 350
let timer: ReturnType<typeof setTimeout> | undefined

function reload() {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => { void volume.run() }, DEBOUNCE_MS)
}

onMounted(() => { void volume.run() })
watch(() => props.tIndex, reload)
onUnmounted(() => { if (timer) clearTimeout(timer) })

/** 拱壳的示意长度 / m。**只改几何、不改场**，所以它不触发任何请求。 */
const shellLength = ref(SHELL_LENGTH_DEFAULT)

/** 点击钉住的那个格点；`null` = 没钉。钉住时读数不跟鼠标跑（规格书 §6.4）。 */
const pinned = ref<HoverPick | null>(null)
/** 鼠标当前指着的格点。 */
const hovered = ref<HoverPick | null>(null)
const shown = computed(() => pinned.value ?? hovered.value)

/**
 * 换了载荷就把悬停清掉 —— 鼠标可能早就不在那一片上了。
 * 钉住的点**留着**：它就是用来盯着一个点看它随时刻怎么变的。
 * 但载荷换了**形状**（片数或格子数变了）时那个下标就无效了，必须放掉 ——
 * 不然下一次读数会拿它去查表，而 `interpretVolumePick` 会抛错。
 */
watch(() => volume.data.value, (p) => {
  hovered.value = null
  const k = pinned.value
  if (k && p && (k.planeIndex >= p.planes.length || k.ix >= p.x.length || k.iz >= p.z.length)) {
    pinned.value = null
  }
})

// 场景那边发上来的两个事件。写成具名函数而不是模板里的内联赋值：
// 在模板里对 ref 赋值要靠编译器的改写规则，而具名函数下一步就能被单测直接调。
function onHover(p: HoverPick | null) { hovered.value = p }
function onPick(p: HoverPick | null) { pinned.value = p }

const spec = computed(() =>
  volume.data.value ? buildVolumeSpec(volume.data.value, shellLength.value) : null)

/** 面板显示的那个格点（钉住的优先），连同它的人话与时刻。 */
const readout = computed(() => {
  const p = volume.data.value
  const k = shown.value
  if (!p || !k) return null
  const [mx, my, mz] = markerPoint(p, k)
  const plane = p.planes[k.planeIndex]
  return {
    time: p.time,
    where: `最近格点 (${mx.toFixed(2)}, ${my.toFixed(2)}, ${mz.toFixed(2)})`,
    text: pickText(interpretVolumePick(p, k.planeIndex, k.ix, k.iz), p.max_measured_z),
    // 「密度即可信度」在读数上也说一遍：这一片是量的，还是算的（规格书 §5.3）。
    layer: plane.measured
      ? `实测断面（${plane.shed} 在 y = ${plane.y.toFixed(2)} m）`
      : `混合出来的片（y = ${plane.y.toFixed(2)} m，不是实测断面）`,
    pinned: pinned.value !== null,
  }
})

/**
 * 「画面还停在上一刻」那句。
 *
 * 三维比二维慢（实测换一帧约 1.2 s），这段时间里两张图**不是同一刻** ——
 * 面板要说出来，而不是等构好了再默默换掉（规格书 §7.2）。
 */
const stale = computed(() => {
  const p = volume.data.value
  if (!p || !props.clockTime || p.time === props.clockTime) return ''
  return `画面仍是 ${p.time} 的场，正在构 ${props.clockTime} 的场。`
})

/* ── 坐标查询 ─────────────────────────────────────────────── */

const query = ref<{ x: number | ''; y: number | ''; z: number | '' }>({ x: '', y: '', z: '' })

/**
 * 三个框都填了、且都是有限数，才算可查。
 *
 * ⚠️ 拿到的值**是 `number | ''`，不是字符串**：`<input type="number">` 上
 * Vue 的 `v-model` 自己会做数字转换（`looseToNumber`），清空时给的是空串。
 * 空串不能当 0（`Number('') === 0`），所以先把它挑出来。
 */
const num = (v: number | ''): number =>
  typeof v === 'string' ? (v.trim() === '' ? Number.NaN : Number(v)) : v

const parsed = computed(() => {
  const n = [num(query.value.x), num(query.value.y), num(query.value.z)]
  return n.every((v) => Number.isFinite(v)) ? { x: n[0], y: n[1], z: n[2] } : null
})

const queryAnswer = ref<{ time: string; where: string; text: string } | null>(null)
const queryError = ref('')

function runQuery() {
  const q = parsed.value
  const p = volume.data.value
  if (!q || !p) return
  const planeIndex = snapIndex(p.planes.map((pl) => pl.y), q.y)
  const ix = snapIndex(p.x, q.x)
  const iz = snapIndex(p.z, q.z)
  if (planeIndex === null || ix === null || iz === null) {
    // **绝不从范围外吸进来**：吸附到最近的边上格点，屏幕上写的还是「最近格点」，
    // 而用户以为自己问的是 100 米处 —— 一个不是他问的答案，看起来却完全正常。
    queryAnswer.value = null
    const y0 = p.planes[0].y
    const y1 = p.planes[p.planes.length - 1].y
    queryError.value =
      '坐标超出这一卷的范围，没有可吸附的格点：' +
      `x ${p.x[0].toFixed(2)} 至 ${p.x[p.x.length - 1].toFixed(2)} m，` +
      `y ${y0.toFixed(2)} 至 ${y1.toFixed(2)} m，` +
      `z ${p.z[0].toFixed(2)} 至 ${p.z[p.z.length - 1].toFixed(2)} m。`
    return
  }
  queryError.value = ''
  const k = { planeIndex, ix, iz }
  const [mx, my, mz] = markerPoint(p, k)
  queryAnswer.value = {
    time: p.time,
    // 吸附后的坐标**必须写出来**：用户输的是 5.4、拿到的是 5.5 的值，
    // 不写出来就是撒谎（规格书 §6.2）。
    where: `最近格点 (${mx.toFixed(2)}, ${my.toFixed(2)}, ${mz.toFixed(2)})`,
    text: pickText(interpretVolumePick(p, k.planeIndex, k.ix, k.iz), p.max_measured_z),
  }
}
</script>

<template>
  <div class="block">
    <div class="row head">
      <h3>棚体三维温度场</h3>
      <span v-if="volume.data.value" class="tag">
        {{ volume.data.value.calibrated ? '已标定' : '未标定（兜底参数）' }}
      </span>
    </div>

    <p v-if="volume.error.value" role="alert" class="alert">{{ volume.error.value }}</p>
    <p v-if="stale" class="note" role="status">{{ stale }}</p>
    <p v-if="volume.loading.value" class="note">正在构体…（{{ clockTime || '…' }}）</p>

    <template v-if="spec && volume.data.value">
      <p class="note">{{ volume.data.value.note }}</p>
      <p class="note">{{ spec.shellNote }}</p>

      <VolumeScene
        :spec="spec" :payload="volume.data.value" :picked="shown"
        @hover="onHover" @pick="onPick"
      />

      <fieldset class="rail-box">
        <legend>棚体示意长度</legend>
        <input
          v-model.number="shellLength" type="range"
          :min="SHELL_LENGTH_MIN" :max="SHELL_LENGTH_MAX" step="0.5"
          aria-label="棚体示意长度"
        >
        <p class="num">{{ shellLength.toFixed(1) }} m（只改几何，不改场）</p>
      </fieldset>

      <table v-if="readout">
        <tbody>
          <tr><th>时刻</th><td class="num">{{ readout.time }}</td></tr>
          <tr><th>位置</th><td class="num">{{ readout.where }}</td></tr>
          <tr><th>这一片</th><td>{{ readout.layer }}</td></tr>
          <tr><th>回答</th><td>{{ readout.text }}</td></tr>
          <tr v-if="readout.pinned">
            <th>已钉住</th>
            <td>
              读数不跟鼠标跑。
              <button type="button" @click="pinned = null">取消钉住</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="note">把鼠标移到棚体上，读最近格点的温度；点一下把读数钉住。</p>

      <fieldset class="rail-box">
        <legend>查一个坐标</legend>
        <div class="row">
          <label>x <input v-model="query.x" type="number" step="0.01"></label>
          <label>y <input v-model="query.y" type="number" step="0.01"></label>
          <label>z <input v-model="query.z" type="number" step="0.01"></label>
        </div>
        <p class="note">
          三格划分出来的是格点，不是连续场。查询<strong>吸附到最近的格点</strong>，不插值；
          吸附后的坐标会在下面写出来。
        </p>
        <button type="button" :disabled="!parsed" @click="runQuery">查询</button>
        <p v-if="queryError" role="alert" class="alert">{{ queryError }}</p>
        <table v-if="queryAnswer">
          <tbody>
            <tr><th>时刻</th><td class="num">{{ queryAnswer.time }}</td></tr>
            <tr><th>位置</th><td class="num">{{ queryAnswer.where }}</td></tr>
            <tr><th>回答</th><td>{{ queryAnswer.text }}</td></tr>
          </tbody>
        </table>
      </fieldset>
    </template>
  </div>
</template>

<style scoped>
.block { margin-bottom: var(--gap-xl); }
.row { display: flex; gap: var(--gap-s); align-items: center; }
.head { justify-content: space-between; }
.alert { color: var(--leaf); border-left: 3px solid var(--leaf); padding-left: var(--gap-s); }
.tag { font-size: var(--size-note); color: var(--ink-muted); }
.rail-box {
  border: var(--rule); padding: var(--gap-s);
  margin: var(--gap-s) 0; font-size: var(--size-note);
}
.rail-box input[type='number'] { width: 6.5em; font: inherit; }
.rail-box button { font: inherit; cursor: pointer; }
</style>
