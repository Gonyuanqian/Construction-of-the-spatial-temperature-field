<script setup lang="ts">
/**
 * 模型库。列表与详情是**同一个功能的两态**，所以共用一个组件、两条路由
 * （规格书 §6.1）。
 *
 * ⚠️ 它**不进 `NAV_ITEMS`**：入口是标题条右侧那个图标（规格书 D8），
 * 而左导航那一列有测试钉着「`<a>` 的数量与次序精确等于已开放项」。
 */
import { MODELS } from '../design/copy'
</script>

<template>
  <section>
    <h2>{{ MODELS.title }}</h2>
  </section>
</template>
