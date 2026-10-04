<script setup lang="ts">
/** 标题条。**跨模式、跨页面常驻** —— 它是系统的身份，不是某一页的页眉。
 *  切页面时闪一下、或只在某些页出现，就退化成了页眉（spec 2026-10-04 §1.3）。 */
import { SYSTEM_TITLE } from '../design/copy'
</script>

<template>
  <header class="titlebar">
    <h1>{{ SYSTEM_TITLE }}</h1>
  </header>
</template>

<style scoped>
.titlebar {
  border-bottom: var(--rule);
  padding: var(--gap-m) var(--gap-l);
}
.titlebar h1 {
  /* 最大字重 + 遮阳网的近黑：它是这一页唯一该压住全场的东西 */
  color: var(--net);
  font-weight: var(--w-title);
  letter-spacing: 0.01em;
}
</style>
