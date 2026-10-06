<script setup lang="ts">
/**
 * 标题条。**跨模式、跨页面常驻** —— 它是系统的身份，不是某一页的页眉。
 * 切页面时闪一下、或只在某些页出现，就退化成了页眉（spec 2026-10-04 §1.3）。
 *
 * 2026-10-06（spec §5.2）三处改动：
 * ① 整条 `--leaf` 底、`--paper` 字 —— 它是这台界面的**铭牌**，
 *    也是全页唯一一条叶子色面（§三 第 3 条：管的是形状，不是面）；
 * ② 标题**居中**；
 * ③ 后端状态从侧栏底部搬到这里。
 *
 * ⚠️ 居中走 `grid-template-columns: 1fr auto 1fr`，标题占中格 ——
 * **几何居中**。用 flex 居中会被右格里的状态推偏。
 * 中格必须是 `auto`：写成 `1fr` 的话标题会随状态宽度漂。
 *
 * 状态为什么值得占这块地方：一台机器上同时可能跑着 Streamlit 版与 Vue 版
 * 两个后端，验收对盘时第一个要问的就是「你看的这个数是哪个后端给的」
 * （spec 2026-10-03 §5.1）。搬上来的第二个理由更硬：`/live` 收起导航，
 * 导航不在时原来那一行也跟着没了 —— 实时那一屏恰恰最需要确认后端是哪一个。
 */
import { onMounted } from 'vue'

import { getJson } from '../api/client'
import { useAsync } from '../composables/useAsync'
import { SYSTEM_TITLE } from '../design/copy'

const health = useAsync(() => getJson<{ status: string; version: string }>('/api/health'))

onMounted(() => void health.run())
</script>

<template>
  <header class="titlebar">
    <h1>{{ SYSTEM_TITLE }}</h1>
    <p class="backend">
      <template v-if="health.error.value">后端：{{ health.error.value }}</template>
      <template v-else-if="health.data.value">
        后端：{{ health.data.value.status }}，库版本
        <span class="num">{{ health.data.value.version }}</span>
      </template>
      <template v-else>后端：检查中</template>
    </p>
  </header>
</template>

<style scoped>
.titlebar {
  background: var(--leaf);
  padding: var(--gap-s) var(--gap-l);
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: baseline;
  column-gap: var(--gap-m);
}
.titlebar h1 {
  grid-column: 2;
  color: var(--paper);
  font-weight: var(--w-title);
  letter-spacing: 0.01em;
}
.backend {
  grid-column: 3;
  justify-self: end;
  margin: 0;
  color: var(--steel);
  font-size: var(--size-label);
}
</style>
