<script setup lang="ts">
/**
 * 数据预览表的窗口（页① 第二块的下半）。
 *
 * **这一件事**：给一批列定义和一批行，画一张固定高度的只读表。
 * 取数、切片、列名、行数上限全在别处 —— 这里只负责画。
 *
 * 用户对这一块的原话是「做成上下左右滑动的窗口形式」：
 *   - 上下左右：`.win` 两个方向都开滚动，26 列在 1280px 下一定溢出，500 行一定过高
 *   - 窗口：给它一个高度上限。不限高的话它跟着内容往上长，页面变长，**永远滚不起来**
 *   - 表头与首列粘住：横滚 26 列时得知道自己在看哪一列，竖滚 500 行时得知道
 *     自己在看哪一时刻 —— 少了哪一半，这个窗口都只剩下一堆数
 *
 * ⚠️ **不在这里算任何数**（硬约束 1）。`fmt1` / `fmtTime` 只决定印出来长什么样；
 * 截断本身是后端切的（见 `GET /api/dataset/preview`）。
 *
 * ⚠️ `null` 印成「—」，**不印 0**。后端把 NaN 翻成 null 说的就是「这段没有值」
 * （`dataset.py:_finite`），而 0 °C 在温棚里是个有意义的读数 —— 用 0 代替
 * 「没有」，看的人分不出来。
 */
import type { PreviewColumn } from '../api/types'
import { fmt1, fmtTime } from '../design/format'

defineProps<{
  columns: PreviewColumn[]
  time: string[]
  /** 行优先：`values[行][列]`，与 `columns` 同序。 */
  values: (number | null)[][]
}>()
</script>

<template>
  <div class="win">
    <table>
      <thead>
        <tr>
          <th class="t">时刻</th>
          <th v-for="c in columns" :key="c.key" class="num">{{ c.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, ri) in values" :key="time[ri]">
          <td class="t">{{ fmtTime(time[ri]) }}</td>
          <td v-for="(v, ci) in row" :key="columns[ci].key" class="num">
            <span v-if="v === null" class="nil">—</span>
            <template v-else>{{ fmt1(v) }}</template>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
/* 高度上限 + 两个方向都开滚动。这两条一起才叫「窗口」：
   只有滚动没有上限，表把页面撑长，滚动条长在 `<body>` 上 —— 那不是一个窗口，
   是一张很长的表。 */
.win {
  max-height: 420px;
  overflow-x: auto;
  overflow-y: auto;
}
/* 全局那条 `border-collapse: collapse` 在这里必须让开：折叠模式下边框属于表格
   而不属于单元格，粘住的表头滚起来会**把底下那道线留下**。分离模式 + 零间距
   是同一个视觉，边框跟着格子走。 */
table {
  border-collapse: separate;
  border-spacing: 0;
}
th,
td {
  padding: 4px 12px;
}
/* 数值列：等宽数字来自全局的 `.num`（`base.css`），这里只管对齐与不折行。
   右对齐 + 等宽，小数点才在一条竖线上 —— 26 列里找异常值靠的正是这个。 */
td.num,
th.num {
  text-align: right;
  white-space: nowrap;
}
/* 表头粘在上沿。底色必须是不透明的：半透明或透明的话，底下的行会从字缝里透出来。 */
thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--card);
}
/* 首列粘在左边。「时刻」是这一行的身份 —— 横滚到第 20 列时它还在，
   才知道那一排数是哪个时刻的。 */
th.t,
td.t {
  position: sticky;
  left: 0;
  z-index: 1;
  background: var(--card);
  white-space: nowrap;
  /* 压过来的列与它之间要有一条线分开，否则读到的是「p1·B3」还是
     「p1 的值 3」要靠猜。 */
  border-right: var(--rule);
}
/* 左上角那一格两个方向都粘，得压在表头与首列**两层之上**。 */
thead th.t {
  z-index: 3;
}
.nil {
  color: var(--ink-muted);
}
</style>
