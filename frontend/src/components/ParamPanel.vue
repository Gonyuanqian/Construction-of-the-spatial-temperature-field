<script setup lang="ts">
/**
 * 页② 的参数面板：**一套值，两条来路**（规格书 §一）。
 *
 * 十二个可调参数分两组（XGBoost 八个、IDW 四个），每行三件东西：
 * 中文名（后端给的 `label`）、键、控件。控件只有两种 —— 滑块与下拉，
 * 正是参考图上的那两种。
 *
 * ⚠️ **这一页一个数都不算**：滑块的档位是**下标**，`raw[index]` 是后端早就
 * 给好的那个值。这里不插值、不取整、不做单位换算（硬约束 1）。
 * 所以 `pick` 发出去的是 `raw[index]` 而不是下标 —— 换算规则只有一处，
 * 就是这里；再往外传下标，就等于每个消费它的人都得知道那条规则。
 *
 * ⚠️ **每一维的全部候选值都印在屏上**（规格书 §2.2）：下拉把选项列全，
 * 滑块把每一档的标签排在轨道下面。这不是装饰 —— 它让「点之前就知道要搜
 * 什么」这条从页② 第一版就有的判据，在控件化之后仍然成立
 * （`views/TrainView.test.ts` 那条「第二段在点之前就列出十二个待优选参数」
 * 因此**原样不变**地继续绿）。
 *
 * ⚠️ **不做卡片套卡片**（规格书 §2.1）：本仓只有一档卡片，`Card.vue` 是全站
 * 唯一写圆角与阴影的地方。在这张卡里再塞两张 `Card`，就是同一个面上叠两层
 * 阴影。所以这里是「一张卡里并排的两个区块」，中间一道 `--rule`。
 */
import { computed } from 'vue'

import type { CalibrationPanel, FixedRow, PanelRow, ParamValue } from '../api/types'

const props = defineProps<{
  panel: CalibrationPanel
  /** 当前值。键是 `PanelRow.key`，值是**原始类型**（数字 / 布尔 / 字符串）。 */
  values: Record<string, ParamValue>
}>()

const emit = defineEmits<{ pick: [key: string, value: ParamValue] }>()

/**
 * 下拉只给这两维：`objective` 的值是字符串，拖不出意义；
 * `cross_shed` 只有两档，用滑块是两个档位之间跳一根长条。
 *
 * ⚠️ 为什么 `cross_shed` 不做成复选框：一个复选框只能印出**当前**那个状态，
 * 「关」这个候选值就没地方摆了 —— 与上面那条「候选值全部印在屏上」冲突。
 */
const DROPDOWN = new Set(['trend.objective', 'cross_shed'])

const groups = computed(() => [
  { title: 'XGBoost', rows: props.panel.trend, fixed: [] as FixedRow[] },
  { title: 'IDW', rows: props.panel.idw, fixed: props.panel.fixed },
])

/**
 * 控件与 `<label for>` 共用的 DOM id。
 *
 * ⚠️ **键里的 `.` 要换掉**。别把坏处说大：`for` 的关联、读屏软件找目标、
 * `getElementById`，用的都是 **id 字符串逐字匹配**，带点的 id 一样对得上，
 * 这几样**没有**塌。塌的是**走选择器的取法**：`#param-metric.power` 在 CSS 里
 * 读成「id = param-metric 且 class = power」，于是 `querySelector` / `matches`
 * 这一路（也就是 `@vue/test-utils` 的 `find('#…')`）指不到那个控件。
 * 本仓就有这种取法：`ParamPanel.test.ts` 那条「`for` 与 `id` 对得上」
 * 正是按 `find('#' + id)` 走的，所以 id 得能当选择子用。
 * 屏上印的仍是**原样的键**（`.key` 那个 span）：键是数据，id 是选择子。
 */
function domId(row: PanelRow): string {
  return `param-${row.key.replace(/\./g, '-')}`
}

/**
 * 当前值在候选里的下标。**不另存一份状态**：屏上的位置就是值的函数。
 *
 * 后端保证 `current` 一定在 `raw` 里（不在就并进去，见 `_panel`），
 * 所以这里正常不会得到 `-1`；真得到 `-1` 时滑块停在最左、`.now` 印空白，
 * 是**看得见**的坏，不是静默的错值。
 */
function indexOf(row: PanelRow): number {
  return row.raw.indexOf(props.values[row.key])
}

function onSlide(row: PanelRow, e: Event): void {
  emit('pick', row.key, row.raw[Number((e.target as HTMLInputElement).value)])
}

function onSelect(row: PanelRow, e: Event): void {
  emit('pick', row.key, row.raw[Number((e.target as HTMLSelectElement).value)])
}
</script>

<template>
  <div class="panel">
    <section v-for="g in groups" :key="g.title" class="group">
      <h4>{{ g.title }}</h4>

      <div v-for="row in g.rows" :key="row.key" class="row">
        <label class="name" :for="domId(row)">
          {{ row.label }}<span class="key num">{{ row.key }}</span>
        </label>

        <template v-if="DROPDOWN.has(row.key)">
          <select :id="domId(row)" :value="indexOf(row)"
                  @change="onSelect(row, $event)">
            <option v-for="(v, i) in row.values" :key="i" :value="i">{{ v }}</option>
          </select>
        </template>

        <template v-else>
          <!-- `max` 是**下标的上界**，不是值的运算：候选有 n 个，档位就是 0..n-1。 -->
          <input :id="domId(row)" type="range"
                 :min="0" :max="row.raw.length - 1" step="1"
                 :value="indexOf(row)" @input="onSlide(row, $event)">
          <div class="ticks">
            <span v-for="(v, i) in row.values" :key="i">{{ v }}</span>
          </div>
        </template>

        <span class="now num">{{ row.values[indexOf(row)] }}</span>
      </div>

      <!-- `state` 是 `design/prose.test.ts` 放行的那几个类之一（规格书 §7.1）。 -->
      <!-- ⚠️ 这一行**没有控件**，但**键照印**：与上面每一行是同一条规矩
           （规格书 §2.1：标签 = 中文名 + 键），而且 `metric.ly` 在屏上是
           「固定值那句说明还在」的凭据（上一份 spec 的 T2）。
           键前面那个 `&nbsp;` 不是排版手滑：这一行是 `<p class="note">`（正文），
           没有控件行那种 flex 把两者推到两头上，中间不留东西就会读成
           「IDW y 方向尺度 / mmetric.ly」一串 —— 键成了中文名的尾巴。
           用实体而不是敲一个普通空格，是因为**编译器会把模板里的纯空格折掉**
           （试过：空格还在模板里，渲染出来就没了），实体才是稳的那一个；
           顺带也不让键在折行时被甩到下一行去。
           `.note .key` 那条间距管观感，这个实体管**文本**里它们是不是两段。 -->
      <p v-for="f in g.fixed" :key="f.key" class="note state">
        {{ f.label }}<span class="key num">&nbsp;{{ f.key }}</span>：{{ f.value }}，{{ f.note }}
      </p>
    </section>
  </div>
</template>

<style scoped>
/* 两个区块并排，中间一道竖线。**不做卡片**（见脚本里的说明）。 */
.panel { display: flex; gap: var(--gap-l); }
.group { flex: 1 1 0; min-width: 0; }
.group + .group { border-left: var(--rule); padding-left: var(--gap-l); }

/* 一行 = 标签（占满） + 控件 + 当前值；滑块的刻度标签另占一行。 */
.row {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  column-gap: var(--gap-s);
  row-gap: 2px;
  padding: var(--gap-s) 0;
}
.name {
  grid-column: 1 / -1;
  display: flex;
  justify-content: space-between;
  gap: var(--gap-s);
}
.key { color: var(--ink-muted); font-size: var(--size-note); }
.ticks {
  grid-column: 1;
  display: flex;
  justify-content: space-between;
  color: var(--ink-muted);
  font-size: var(--size-label);
}
.now { grid-column: 2; }

select { font: inherit; color: inherit; }

/* 固定值那一行（`<p class="note">`）是正文，没有控件行那种 flex 把中文名与键
   推在两头，所以靠间距分开 —— 不留这点空，键就贴着中文名的尾巴。
   键本身吃 `.num`（base.css）的等宽体，字体与正文不同，一眼认得出那是键。 */
.note .key { margin-left: var(--gap-s); }

/* 滑块的档位色。**只给一条主色**，不写 `::-webkit-slider-thumb` 之类 ——
   那要按住浏览器的实现细节、三份前缀各写一遍，而本仓的规矩是不做装饰
   （spec 2026-10-06 §一）。原生的轨道与把手配上主色，键盘、读屏、
   `prefers-reduced-motion` 全部免费。

   ⚠️ **写在这个 scoped 块里，不写进 `design/base.css`** —— 规格书 §7.1
   末段明写：`base.css` 里没有 `input` 规则，写进去会让 `FieldView.vue:177`
   与 `VolumeView.vue:209` 那两个原生滑块跟着变色，而那两页这次一个字都不该动。
   scoped 块只打在本组件自己的 `<input>` 上（编译成 `data-v-` 属性选择器），
   别处不受影响。 */
input[type='range'] { accent-color: var(--leaf); }
</style>
