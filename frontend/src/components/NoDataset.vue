<script setup lang="ts">
/**
 * 空态：系统启动时（或换了数据集之前）②③④ 与实时模式都显示这一块。
 *
 * **不显示任何状态码、不显示「错误」二字** —— 空态是系统的**起点**，
 * 不是故障（规格书 §二.1）。把它画成一张错误卡，验收的人第一次打开系统
 * 就会以为哪里坏了。
 *
 * 文案取自 `design/copy.ts` 的 `NO_DATASET`：五个页面共用同一句，
 * 各写一句迟早漂成五种说法 —— 而这五处说的是同一件事。
 *
 * ⚠️ **一句话里要把「下一步做什么」说全**（去哪儿、做什么）。只说
 * 「还没有数据」等于把用户丢在原地；那个「去哪儿」正是页①的名字。
 */
import Card from './Card.vue'
import { NO_DATASET } from '../design/copy'
</script>

<template>
  <Card class="block">
    <h3>{{ NO_DATASET.headline }}</h3>
    <p class="note">{{ NO_DATASET.why }}</p>
  </Card>
</template>

<style scoped>
.block { max-width: 46ch; }
/* 字号走全局标尺（原来写死 `1.05rem` —— 全树唯一一处不走令牌的字号，
   改标尺时它不跟着动，空态标题就成了唯一一处没放大的字）。 */
h3 { margin: 0 0 var(--gap-s); color: var(--ink); }
.note { margin: 0; color: var(--ink-muted); line-height: 1.7; }
</style>
