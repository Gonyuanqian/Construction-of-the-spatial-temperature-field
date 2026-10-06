<script setup lang="ts">
/**
 * 一排指标卡。**等宽**（`flex: 1 1 0`），不是按内容撑开 ——
 * 等宽才读得出「一排」，撑开就退回成一排带框的字（spec §6.1）。
 *
 * `flex-wrap: wrap` 与 `min-width`：1280px 下五张卡挤不下时**换行**，
 * 而不是压成看不清的窄条，更不许横向滚动（Review Focus 1）。
 */
</script>

<template>
  <div class="stats"><slot /></div>
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
</style>
