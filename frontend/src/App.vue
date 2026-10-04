<script setup lang="ts">
/**
 * 应用外壳。
 *
 * 标题条在**最外层**：它跨模式、跨页面常驻，模式开关与导航都在它下面。
 * 页面的内容只占 `<RouterView />` 那一块 —— 所以任何一页都不需要
 * 重复渲染标题，也就不可能漏渲染。
 *
 * P1 那版 App.vue 里显示数据集摘要的代码**搬去了页①**（Task 8），
 * 这里不再留一行：外壳不显示任何数据。
 */
import { ref } from 'vue'

import ModeSwitch from './components/ModeSwitch.vue'
import NavRail from './components/NavRail.vue'
import TitleBar from './components/TitleBar.vue'

const mode = ref('train')
</script>

<template>
  <TitleBar />
  <ModeSwitch v-model="mode" />
  <div class="body">
    <NavRail />
    <main class="page">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.body { display: flex; align-items: flex-start; gap: var(--gap-m); padding: var(--gap-m) 0; }
.page { flex: 1 1 auto; min-width: 0; padding-right: var(--gap-l); }
</style>
