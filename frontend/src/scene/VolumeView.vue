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
import { computed, onMounted, onUnmounted, ref, watch, withDefaults } from 'vue'

import type { VolumePayload } from '../api/types'
import { getJson } from '../api/client'
import { interpretVolumePick, pickText } from '../charts/pick'
import { tempStops } from '../charts/scale'
// 三栏各是一张卡片（2026-10-09 用户裁定）。用全站那一档，不自己写圆角与阴影 ——
// 各写一遍，`guards.test.ts` 守着的「一处圆角、一处阴影」就名存实亡了。
import Card from '../components/Card.vue'
import ViewControls from '../components/ViewControls.vue'
import { useAsync } from '../composables/useAsync'
import { calibratedLabel } from '../design/copy'
import { fmtTime } from '../design/format'
import { markerPoint, snapIndex, type HoverPick } from './hover'
import VolumeScene from './VolumeScene.vue'
import type { ViewCmd } from './viewCmd'
import {
  SHELL_LENGTH_DEFAULT, SHELL_LENGTH_MAX, SHELL_LENGTH_MIN, buildVolumeSpec,
} from './volumeView'

const props = withDefaults(defineProps<{
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
  /**
   * 画面上要不要挂一枚时刻（2026-10-09 用户裁定）。
   *
   * 实时那一屏把指标卡整排撤了（「第几帧，一共多少帧……后端系统知道就行」），
   * 但「手上这一屏画的是哪一刻」得一直看得见 —— 用户的话是「这个时间可以放到
   * 生成的三维影像图中的左上角或者右上角就行了」。
   *
   * ⚠️ **默认关**：页③ 的时刻在上面那条滑块那一路上一直写着，同一个数在同一屏
   * 里说两遍不是澄清。这一块是两页共用的 —— 要不要这枚读数由**页**来定。
   */
  showClock?: boolean
  /**
   * 画面上方那两行口径说明要不要摆出来。
   *
   * 两行是**两个来路**：头一行是**后端给的**（载荷的 `note`，前端只负责摆
   * 上去，不重写它），第二行是 `volumeView.ts` 的 `SHELL_NOTE`。
   *
   * ⚠️ **默认开**：与 `showClock` 一样，两个开关的默认值取的都是「页③ 现在
   * 是什么样」—— 这一块两页共用，改哪一页由**页**说，不由这一块替两页一起定。
   *
   * 实时那一屏 2026-10-09 用户裁定关掉（「这一段话也没必要展示了」）：那一屏
   * 只留温度场，画面顶上去。`SHELL_NOTE` 挂着的规格书 §5.3「图上必须标明
   * 『棚体示意』、不允许读成『测了这么长』」**撤了它仍然成立** —— 滑块的标题
   * 就叫「棚体示意长度」，底下读数写着「只改几何，不改场」。
   * `VolumeView.test.ts` 最后那一组把这件事两面都钉着。
   *
   * ⚠️ 不复用 `source`：那个说的是「这份数从哪条取数口来」，这个说的是
   * 「这一屏要不要那几行字」。绑在一起，以后哪一页想换个摆法就得先动取数口。
   */
  showNotes?: boolean
  /**
   * 画不画「旋转 / 缩放 / 平移」那一组按钮（2026-10-09 用户裁定「旋转/缩放/平移
   * 按钮可以做」）。**默认关** —— 与 `showClock` / `showNotes` 同一条规矩：
   * 默认值取「页③ 现在什么样」，页③ 因此一个字符都不用改（用户裁定
   * 「训练模式不用动」）。只有实时模式那一屏传真。
   *
   * ⚠️ 只负责**转发**：这一层不做这个开关的判断，画不画由 `VolumeScene` 说。
   * 这一层存在的理由是接力 —— `LiveView` 说 `show-view-controls`、
   * 这里的 props 键是 `showViewControls`、转发给 `VolumeScene` 的键也是它,
   * 三处名字里错一个**不报错**，只是按钮永远不出现（`VolumeView.test.ts`
   * 那条透传用例钉的就是这个）。
   */
  showViewControls?: boolean
  /**
   * 这一块渲染哪几栏（2026-10-12 页⑤ 仪表盘）。
   *
   * - `'all'`（**默认**）：三栏都在这一块里，屏上 `[几何, 中栏, 问数]`。
   *   默认值取「页③ 现在什么样」，所以页③ 一个字符都不用改。
   * - `'shell'`：只留中栏；「问数」与「几何与剖切」两张卡用
   *   `<Teleport to="#shell-side">` 投进外壳的右栏（`App.vue` 渲染的
   *   `<aside id="shell-side">`），次序是**问数在前**。
   *
   * ⚠️ 为什么是 `Teleport` 而不是把这十几项状态提上去：右栏吸附的格点
   *   **必须与画面画的是同一份**（规格书 §三 D4）。投出去的是同一份
   *   `volume.data.value` 渲染出来的同一段模板 —— 两边分不了家。
   *   提上去再传下来是同一件事的第二条路，还多一处「载荷有两个来源」的隐患。
   *
   * ⚠️ 落点不存在时 Vue **静默不挂**：页⑤ 上右栏会整块消失而不报错。
   *   `VolumeView.test.ts` 里那一组自己造落点，正是防这一手。
   */
  panels?: 'all' | 'shell'
}>(), {
  // 默认**摆**：页③ 一直摆着，页⑤ 显式关掉。默认值取「页③ 现在什么样」，
  // 于是页③ 一个字符都不用改 —— 这次裁定动的是页⑤。
  showNotes: true,
  // 同上：默认关，页③ 与改动前逐字相同。
  showViewControls: false,
  // 默认取「页③ 现在什么样」——与 `showClock` / `showNotes` / `showViewControls`
  // 同一条规矩：改哪一页由**页**说，不由这一块替两页一起定。
  panels: 'all',
})

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
    // 时刻走 `fmtTime`：这一块是页③ 与实时屏共用的，两个页面上的断面读数
    // 都走它，三维这一半跟上 —— 否则「同一个数四页同一种写法」在**同一页内**
    // 就先破了（终审 I-3）。
    time: fmtTime(p.time),
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
  return `画面仍是 ${fmtTime(p.time)} 的场，正在构 ${fmtTime(props.clockTime)} 的场。`
})

/* ── 剖切刀 ───────────────────────────────────────────────── */

/**
 * 刀口的位置（米）。**由页级管**：刀原来住在 `VolumeScene` 里，2026-10-09 版面
 * 改成三栏、它要摆到左栏去，就搬上来了 —— 那一层的文件头写着的正是「只做 Three
 * 的调用，不做任何判断」。它现在只收这个数、写进裁剪面。
 *
 * **`null` = 还没被人动过 = 不切**（切到最远的那一片）。写成 `null` 而不是
 * 「一拿到载荷就把最远那片填进来」，是因为填初值要挑一个「载荷到了、画的那一半
 * 还没挂」的时刻 —— 那只能靠 watch 的刷新次序去凑。`null` 没有这个问题：它自己
 * 的含义就是「不切」，`cutAt` 随时算得出。
 */
const cutY = ref<number | null>(null)
const cutMin = computed(() => volume.data.value?.planes[0]?.y ?? 0)
const cutMax = computed(() => {
  const ps = volume.data.value?.planes
  return ps && ps.length > 0 ? ps[ps.length - 1].y : 0
})
const cutAt = computed(() => cutY.value ?? cutMax.value)

/** 场景那一半报上来的：它到底画出来没有。没画出来就不挂剖切刀。 */
const sceneOk = ref(false)
function onSceneReady(ok: boolean) { sceneOk.value = ok }

/**
 * 相机动作的入口。**只在场景真的建起来之后**才有东西可调 ——
 * 拿不到就当无事发生（场景那一半是懒挂的，测试里还是替身）。
 */
const scene = ref<InstanceType<typeof VolumeScene> | null>(null)
function nudge(cmd: ViewCmd): void {
  const s: { nudge?: (c: ViewCmd) => void } | null = scene.value
  s?.nudge?.(cmd)
}

/**
 * 色标那条横条。**颜色来自 `charts/scale.ts` 的采样点**，不在这里写色值 ——
 * 全仓的十六进制只许出现在 `tokens.css` 与 `scale.ts`（`guards.test.ts` 钉着），
 * 而 `tempStops()` 正是那两个例外之一。于是屏上这条色标、三维纹理、
 * 与页②③ 的热图用的是**同一组** stops。
 *
 * ⚠️ 里面那个百分比是**色块的位置**（第几个采样点摆在横条的百分之几），
 * 不是任何物理量。全仓「前端不做数值计算」那条约束管的是温度。
 */
function scaleGradient(): string {
  const stops = tempStops()
  const n = stops.length - 1
  return `linear-gradient(to right, ${
    stops.map((c, i) => `${c} ${((i / n) * 100).toFixed(1)}%`).join(', ')
  })`
}

function onCut(e: Event) {
  cutY.value = Number((e.target as HTMLInputElement).value)
}

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
    time: fmtTime(p.time),
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
        {{ calibratedLabel(volume.data.value) }}
      </span>
    </div>

    <p v-if="volume.error.value" role="alert" class="alert">{{ volume.error.value }}</p>
    <p v-if="stale" class="note" role="status">{{ stale }}</p>
    <p v-if="volume.loading.value" class="note">正在构体…（{{ clockTime ? fmtTime(clockTime) : '…' }}）</p>

    <template v-if="spec && volume.data.value">
      <!-- 这两行是这一块的「图例」：头一行是**后端的原话**，第二行说明滑块
           动的只是几何。哪一屏要不要它们由页面说（`showNotes`，见 props）。
           ⚠️ 第二行撤掉时规格书 §5.3 那条要求**由左栏的滑块接管** ——
           它的标题就叫「棚体示意长度」，读数写着「只改几何，不改场」。 -->
      <p v-if="showNotes" class="note">{{ volume.data.value.note }}</p>
      <p v-if="showNotes" class="note">{{ spec.shellNote }}</p>

      <!-- 三栏（2026-10-09 用户裁定）：**左＝改几何/切法，中＝看场，右＝问数**。
           原来是从上到下一条：画布 `width:100%` 横铺整页，剖切刀、棚体示意长度、
           读数表、坐标查询在下面各占一整行 —— 宽屏上画布占满整幅而三维内容只是
           它中间的一条，几块控件又拉得老长。分栏之后画布被限制在中栏那一个区域里。

           ⚠️ 三栏各是一张 `<Card>`（同日第二次裁定）：分栏之后三个部分直接浮在
           纸底上，只靠栏里那几个 `<fieldset>` 的细线互相区分，而同一页的
           「三个断面的温度场」「ΔT」都是 `<Card class="block">` ——
           **三维这一块是唯一一块没套卡片的**。补上它，页③ 才是一条一致的卡片列。

           ⚠️ 2026-10-12 页⑤ 那一档只留中栏，左右两栏投进外壳右栏。
           源码次序因此与页③ 的屏上次序**不是一回事**：源码写成
           `[问数, 中栏, 几何]`，页③ 的栏位由下面 CSS 的 `grid-column` 显式定死，
           而投出去的次序正好就是参考图要的「问数在前」。
           `VolumeView.test.ts` 的 `columns()` 按**类名**取栏，不按位置 ——
           按位置取的话源码次序一改就会读反，而它给出的每一条断言照样绿。 -->
      <div class="vol-grid" :class="{ 'stage-only': panels === 'shell' }">
        <Teleport to="#shell-side" :disabled="panels === 'all'">
          <Card class="vol-side vol-ask">
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
          </Card>
        </Teleport>

        <Card class="vol-stage">
          <!-- 画面角上那枚时刻（2026-10-09 用户裁定）。它读的是**载荷自己的**
               `time`，不是外面传进来的 `clockTime`：这枚读数回答的是「画面上
               这一屏是哪一刻」，而两者错开的那一秒（正在构体）正是它最该说话
               的时候 —— 那时候载荷还是旧的，印出来就该是旧的，与上面那句
               「画面仍是…的场」说的是同一件事。
               `v-if` 里那个 `volume.data.value` 不能省：`fmtTime(null)` 会拼出
               个坏值，而那一瞬间屏上本来就写着「正在构体…」。 -->
          <p v-if="showClock && volume.data.value" class="stage-clock num">
            {{ fmtTime(volume.data.value.time) }}
          </p>
          <VolumeScene
            ref="scene"
            :spec="spec" :payload="volume.data.value" :picked="shown" :cut-y="cutAt"
            :show-view-controls="showViewControls"
            @hover="onHover" @pick="onPick" @ready="onSceneReady"
          />

          <!-- 页⑤ 才摆的两条画布外标记：色标与棚位两端（规格书 §六 版面纪律）。
               ⚠️ **只有端点，没有中间的刻度**：0/6/12/18 m 那种刻度要在前端
               把一个跨度等分 —— 那正是本仓不许的数值计算。可用的数就是载荷
               自己报的 `vmin/vmax` 与 `y_min/y_max`，所以只印两端。
               ⚠️ 它们是画布**外**的 HTML 叠层，不碰 `VolumeScene` 的几何，
               页③ 也因此零影响。 -->
          <template v-if="panels === 'shell' && volume.data.value">
            <div class="stage-scale">
              <span class="num scale-end">{{ volume.data.value.vmin.toFixed(1) }} °C</span>
              <span class="scale-bar" :style="{ background: scaleGradient() }" />
              <span class="num scale-end">{{ volume.data.value.vmax.toFixed(1) }} °C</span>
            </div>
            <p class="note num stage-axis">
              棚位 y {{ volume.data.value.y_min.toFixed(2) }} 至
              {{ volume.data.value.y_max.toFixed(2) }} m
            </p>
          </template>
        </Card>

        <Teleport to="#shell-side" :disabled="panels === 'all'">
          <Card class="vol-side vol-geom">
            <!-- 剖切刀。⚠️ **只在场景报「画得出来」之后才挂** —— 没有 WebGL 时
                 刀切的是一个不存在的画面，一个对自己无效的控件比没有更难看。
                 （这条不变量原先挂在 `VolumeScene.test.ts` 上，控件搬上来，
                 守它的测试也跟着搬上来了。） -->
            <fieldset v-if="sceneOk" class="rail-box">
              <legend>剖切刀（沿棚长 y）</legend>
              <input
                :value="cutAt" type="range"
                :min="cutMin" :max="cutMax" :step="volume.data.value.y_step"
                aria-label="剖切刀" @input="onCut"
              >
              <p class="num">切到 y = {{ cutAt.toFixed(2) }} m 为止</p>
            </fieldset>

            <fieldset class="rail-box">
              <legend>棚体示意长度</legend>
              <input
                v-model.number="shellLength" type="range"
                :min="SHELL_LENGTH_MIN" :max="SHELL_LENGTH_MAX" step="0.5"
                aria-label="棚体示意长度"
              >
              <p class="num">{{ shellLength.toFixed(1) }} m（只改几何，不改场）</p>
            </fieldset>
          </Card>

          <!-- 三维视图控制那张卡**只在页⑤** 上出现：页③ 用的是压在画布角上
               的那一组（`showViewControls`），两处摆法共用一个 `ViewControls`。 -->
          <Card v-if="panels === 'shell'" class="vol-side">
            <fieldset class="rail-box">
              <legend>三维视图控制</legend>
              <ViewControls :run="nudge" :ok="sceneOk" />
              <p class="note">拖动鼠标可查看三维模型。</p>
            </fieldset>
          </Card>
        </Teleport>
      </div>
    </template>
  </div>
</template>

<style scoped>
.block { margin-bottom: var(--gap-xl); }
.row { display: flex; gap: var(--gap-s); align-items: center; }
.head { justify-content: space-between; }
.alert { color: var(--leaf); border-left: 3px solid var(--leaf); padding-left: var(--gap-s); }
.tag { font-size: var(--size-note); color: var(--ink-muted); }
/* 三栏：左＝改几何/切法，中＝看场，右＝问数（2026-10-09 用户裁定）。
   中栏写 `minmax(0, 1fr)` 而不是 `1fr` —— 与页① 那条左右分栏同一条理由：
   写成 `1fr` 时格子的下限是**内容宽度**，画布会先把页宽撑破，而不是自己缩。
   `align-items: start`：三栏各按自己的高度，硬拉齐只会在短的那栏底下留白。 */
.vol-grid {
  display: grid;
  grid-template-columns: 14rem minmax(0, 1fr) 18rem;
  gap: var(--gap-l);
  align-items: start;
  margin-top: var(--gap-m);
}
/* 两栏都是内容可能比格子宽的那种（右边那三个坐标框尤其），允许格子窄于内容。 */
.vol-side { min-width: 0; }
/* ⚠️ 2026-10-12 起源码次序是 `[问数, 中栏, 几何]`（投出去时问数在前），
   所以页③ 的三个栏位**必须显式定死** —— 靠自动排列的话会变成
   问数在左、几何在右，而那是反的。 */
.vol-ask { min-width: 0; grid-column: 3; }
.vol-geom { min-width: 0; grid-column: 1; }
/* `position: relative` 是给角上那枚时刻当落点的（画布铺满这一栏的内容盒）。 */
.vol-stage { min-width: 0; position: relative; grid-column: 2; }
/* 页⑤ 那一档只剩中栏：一栏的栅格模板，且中栏本来就该铺满。 */
.vol-grid.stage-only { grid-template-columns: minmax(0, 1fr); }
/* 色标：一条横条，两端各一个端点读数。 */
.stage-scale {
  display: flex; align-items: center; gap: var(--gap-s);
  margin-top: var(--gap-m);
}
.scale-bar { flex: 1 1 auto; height: 10px; border-radius: var(--radius); }
.scale-end { font-size: var(--size-note); color: var(--ink-muted); white-space: nowrap; }
.stage-axis { margin-top: var(--gap-s); }
/* 画面右上角那枚时刻。落点是 `--gap-m`（卡片自己的内边距）再加一点点 ——
   画布铺满内容盒，所以这个位置正好是画面右上角往里缩一个 `--gap-s`。
   ⚠️ `pointer-events: none` 不能省：它压在画布上，挡住的正是鼠标悬停读温
   的那一片区域。 */
.stage-clock {
  position: absolute; z-index: 1;
  top: calc(var(--gap-m) + var(--gap-s));
  right: calc(var(--gap-m) + var(--gap-s));
  margin: 0;
  pointer-events: none;
  font-size: var(--size-note);
  color: var(--ink-muted);
}
/* 栏里那几个 `<fieldset>`（剖切刀 / 棚体示意长度 / 查一个坐标）**不再自己画线**：
   一栏一张卡片已经给了界限，里面再套一道细线就成了框中框
   （2026-10-09 用户裁定）。legend 留着 —— 它还是这一组的名字，
   现在读作小标题而不是压在框线上的一行字。
   ⚠️ 这几条只落在本文件：类是 `rail-box`，页③/页⑤ 那两个视图切换的
   `fieldset.rail-box` 有自己的 scoped 规则（它们真的是表单，仍要框）。 */
.rail-box {
  border: 0; padding: 0;
  /* 各组之间只靠间距分 —— 上边距仍是 0（它们各自住在一栏里，不是竖着排的两行）。 */
  margin: 0 0 var(--gap-m); font-size: var(--size-note);
}
.rail-box:last-child { margin-bottom: 0; }
.rail-box legend { padding: 0; font-weight: var(--w-strong); }
.rail-box input[type='number'] { width: 6.5em; font: inherit; }
.rail-box button { font: inherit; cursor: pointer; }
/* 右栏比原来那一整行窄得多，三个坐标框放不下就折行 —— 不折的话它们会把
   右栏撑破（`min-width: 0` 只保证格子不撑破，格子里的内容还是会溢出来）。 */
.vol-side .row { flex-wrap: wrap; }
</style>
