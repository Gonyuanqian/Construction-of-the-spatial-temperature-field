<script setup lang="ts">
/**
 * 实时模式那一屏。**本任务只放一个占位**，下一任务（Task 12）写全。
 *
 * 之所以现在就建：`router/index.ts` 里 `/live` 是懒加载的，测试解析这条路由
 * 时要求文件存在 —— 不建的话本任务的测试跑不起来，任务就不自成闭环。
 *
 * 文案里没有三种连接符（中点串 / 带空格的破折号 / 箭头），与页① 到页③
 * 同一口径：`test_on_screen_copy.py` 会扫这个文件。
 */
</script>

<template>
  <p class="note">正在加载实时模块…</p>
</template>

<style scoped>
.note { color: var(--ink-muted); padding: var(--gap-l) 0; }
</style>
