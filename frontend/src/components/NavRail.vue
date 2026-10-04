<script setup lang="ts">
import { onMounted } from 'vue'

import { getJson } from '../api/client'
import { useAsync } from '../composables/useAsync'
import { NAV_ITEMS } from '../design/copy'

/**
 * 侧栏底部报出后端库版本。
 *
 * 为什么这一行值得占地方：一台机器上同时可能跑着 Streamlit 版与 Vue 版
 * 两个后端，验收对盘时第一个要问的就是「你看的这个数是哪个后端给的」。
 * `/api/health` 的契约里带 version 就是为了回答它（spec 2026-10-03 §5.1）。
 */
const health = useAsync(() => getJson<{ status: string; version: string }>('/api/health'))

onMounted(() => void health.run())
</script>

<template>
  <nav class="rail" aria-label="页面">
    <template v-for="item in NAV_ITEMS" :key="item.key">
      <RouterLink v-if="item.enabled" class="item" :to="item.to">{{ item.label }}</RouterLink>
      <span v-else class="item off" :title="item.why">{{ item.label }}</span>
    </template>

    <hr class="rule" />

    <!-- 未开放的两项把理由写在这里，而不是藏进 title：
         演示时没人会去悬停一个灰掉的按钮。 -->
    <ul class="whys">
      <li v-for="item in NAV_ITEMS.filter((i) => !i.enabled)" :key="item.key + '-why'"
          class="note">
        <strong>{{ item.label }}</strong>：{{ item.why }}
      </li>
    </ul>

    <p class="note backend">
      <template v-if="health.error.value">后端：{{ health.error.value }}</template>
      <template v-else-if="health.data.value">
        后端：{{ health.data.value.status }}，库版本 <span class="num">{{ health.data.value.version }}</span>
      </template>
      <template v-else>后端：检查中</template>
    </p>
  </nav>
</template>

<style scoped>
.rail {
  width: var(--sidebar-w);
  flex: 0 0 var(--sidebar-w);
  padding: 0 var(--gap-m) var(--gap-m) var(--gap-l);
  display: flex;
  flex-direction: column;
}
.item { display: block; padding: 3px 0; color: var(--ink); text-decoration: none; }
.item.router-link-active { color: var(--leaf); font-weight: var(--w-strong); }
.item.off { color: var(--ink-muted); cursor: not-allowed; }
.rule { border: 0; border-top: var(--rule); width: 100%; margin: var(--gap-m) 0; }
.whys { list-style: none; padding: 0; margin: 0; }
.whys li { margin-bottom: var(--gap-s); }
.backend { margin-top: auto; }
</style>
