<script setup lang="ts">
/**
 * 中央工作区顶部那一条概览：**一条带竖分隔线的长条**，不是一排等宽卡片。
 *
 * ⚠️ **不用 `StatRow` + `StatCard`**（2026-10-12 规格书 §六 版面纪律）：
 * 那两个是「一排等宽卡片、每个恒为三行」，页① 靠它；参考图这一条是长条。
 * 硬塞进 `StatCard` 会把那条规矩弄乱，而那条规矩是页① 的版面本身。
 *
 * ⚠️ 图标是**具名插槽**（`icon-<key>`），本轮一律空着 —— 用户裁定的
 * 「先复现整体结构，再精修图标」。空插槽渲染不出东西，所以本轮屏上只有字。
 *
 * ⚠️ 这一层**不做任何判断**：值是不是「取数失败」由页面说了算
 * （`LiveView` 的 `sceneText`），这里只按 `tone` 上一个类名。
 *
 * ⚠️ **一格只有两行：标签、值。** 2026-10-16 用户裁定把原先那第三行副文案
 * （「拱形以内、z 不高于 1.10 m」「这一帧的体网格」「实时数据，动态更新」）
 * 整块删掉 —— 中央那一屏要三维 / 环境参数 / 沿栅均温三块**同屏不滚动**，
 * 每格一行就是几十像素，而那三句在这一屏上各块自己下面都还说得到。
 * 均温那一句没丢：它搬进了页脚的「口径与出处」（`LiveView.vue` 的
 * `<details class="why">`），与 2026-10-09 那句分级句同一条处置 ——
 * **降级不是删除**，从「常驻」变成「点一下」。
 *
 * ⚠️ 顺带说一句原先写在这里的：那个 `.sub` 类名曾经是 `prose.test.ts`
 * 那条「正文里不许有没归类的 `p.note`」守卫的**盲区**（换个类名就绕开了）。
 * 现在这一层一个 `p` 都不多写，那条盲区也就没有实例了 —— 但盲区本身还在，
 * 下一个人新加一个 `p.xxx` 照样绕得过去。
 */
defineProps<{
  cells: readonly {
    key: string
    label: string
    /** 已经格式化好的字符串。这一层不做任何数值格式化。 */
    value: string
    /** 值那一行的语气。默认 `plain`。 */
    tone?: 'plain' | 'ok' | 'warn'
  }[]
}>()
</script>

<template>
  <div class="strip">
    <div v-for="c in cells" :key="c.key" class="cell">
      <p class="label">
        <span class="ico"><slot :name="`icon-${c.key}`" /></span>{{ c.label }}
      </p>
      <p class="value num" :class="c.tone ?? 'plain'">{{ c.value }}</p>
    </div>
  </div>
</template>

<style scoped>
/* 一条长条：几格**等分**，格与格之间一条竖线（参考图那条分隔线）。
   ⚠️ `min-width: 0` 在窄屏上让文案自己折行，而不是把这一条撑出横向滚动。
   ⚠️ 纵向内边距 2026-10-16 从 `--gap-m` 收到 `--gap-s`（省 16px）。
   **横向那一档不能跟着收**：`.cell:first-child` 不缩进，为的就是让最左那一格
   与下面那些卡片的左边缘对齐，横向一收就错开了。 */
.strip {
  display: flex;
  align-items: stretch;
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: var(--gap-s) var(--gap-m);
}
.cell { flex: 1 1 0; min-width: 0; padding: 0 var(--gap-m); }
.cell + .cell { border-left: 1px solid var(--steel); }
/* 最左一格不缩进：它要与下面那些卡片的左边缘对齐。 */
.cell:first-child { padding-left: 0; }
.label {
  margin: 0;
  display: flex; align-items: center; gap: var(--gap-s);
  font-size: var(--size-label);
  color: var(--ink-muted);
}
.ico { display: inline-flex; align-items: center; }
.value { margin: var(--gap-s) 0 0; font-size: var(--size-h3); font-weight: var(--w-strong); }
/* 语气只动颜色，不动字号与字重 —— 层级由 `--size-*` 那一组定，不由语气定。 */
.value.ok { color: var(--ok); }
.value.warn { color: var(--leaf); }
</style>
