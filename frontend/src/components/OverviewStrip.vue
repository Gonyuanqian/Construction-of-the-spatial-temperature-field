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
 * ⚠️ 副文案用 `.sub` 而不是 `.note`：`prose.test.ts` 那条「正文里不许有
 * 没归类的 `p.note`」的守卫**够不着** `p.sub`。写在这里，免得下一个人以为
 * 它被守着了 —— 这一条的盲区就是「换个类名就绕开了」。
 */
defineProps<{
  cells: readonly {
    key: string
    label: string
    /** 已经格式化好的字符串。这一层不做任何数值格式化。 */
    value: string
    /** 副文案。已经定稿的真话，不是这里拼的。 */
    sub: string
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
      <p class="sub">{{ c.sub }}</p>
    </div>
  </div>
</template>

<style scoped>
/* 一条长条：几格**等分**，格与格之间一条竖线（参考图那条分隔线）。
   ⚠️ `min-width: 0` 在窄屏上让文案自己折行，而不是把这一条撑出横向滚动。 */
.strip {
  display: flex;
  align-items: stretch;
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: var(--gap-m);
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
.sub { margin: 2px 0 0; font-size: var(--size-note); color: var(--ink-muted); }
</style>
