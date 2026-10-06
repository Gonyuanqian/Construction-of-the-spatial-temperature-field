<script setup lang="ts">
/**
 * 一排指标卡。**等宽**（`flex: 1 1 0`），不是按内容撑开 ——
 * 等宽才读得出「一排」，撑开就退回成一排带框的字（spec §6.1）。
 *
 * `flex-wrap: wrap` 与 `min-width`：1280px 下五张卡挤不下时**换行**，
 * 而不是压成看不清的窄条，更不许横向滚动（Review Focus 1）。
 *
 * `tint`：把这一排的卡片铺上 `--leaf-soft`（页① 那一排用）。**只改底色** ——
 * 圆角、阴影、内边距一个字不动，一档圆角一档阴影是全站的规矩（spec §四）。
 * 开关放在这一排上而不是每张卡各传一次：「这一排是一个整体」只该有一个开关。
 */
defineProps<{ tint?: boolean }>()
</script>

<template>
  <div class="stats" :class="{ tinted: tint }"><slot /></div>
</template>

<style scoped>
.stats {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gap-m);
  margin-bottom: var(--gap-xl);
}
.stats > :deep(*) {
  flex: 1 1 0;
  min-width: 132px;
}
/* 色只从令牌来（`--leaf-soft`），这里不写十六进制 —— `guards.test.ts` 盯着。 */
.stats.tinted > :deep(.stat) { background: var(--leaf-soft); }
</style>
