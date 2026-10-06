<script setup lang="ts">
/**
 * 一张指标卡：标签 / 读数 / 出处（spec 2026-10-06 §6.1）。
 *
 * **三行恒为三行**：有出处的、没出处的，卡片高度都一样。缺哪一行就留空，
 * 不挤掉 —— 一排高低不齐的卡片是仪表盘的失手。
 *
 * **只收格式化好的字符串**：前端不做任何数值计算（硬约束 1）。
 * `1308` 写成什么样子是 `design/format.ts` 的事，不在这里。
 *
 * ⚠️ 不许用 `<table>`，也不许含 `h2`/`h3`：页③ 的 `FieldView.test.ts` 钉死
 * 「第一张 `<table>` 是读数表」，页② 的 `TrainView.test.ts` 钉死 `findAll('h3')`
 * 恰好是那三段（spec §十三.1）。指标卡排在页面最前，一用表格就顶掉它们。
 *
 * `compact` 是长标识串用的（指纹、时间范围）：收一档字号，卡片高度不变。
 * `muted` 是「这一格本来就不该报数」用的 —— 与 `compact` 是两回事。
 */
import type { ProvKind } from '../design/copy'
import Provenance from './Provenance.vue'

defineProps<{
  label: string
  value: string
  prov?: ProvKind
  compact?: boolean
  muted?: boolean
}>()
</script>

<template>
  <div class="stat">
    <div class="label">{{ label }}</div>
    <div class="value" :class="{ compact, muted }">{{ value }}</div>
    <div class="stamp">
      <Provenance v-if="prov" :kind="prov" />
      <span v-else class="blank" aria-hidden="true">{{ '' }}</span>
    </div>
  </div>
</template>

<style scoped>
.stat {
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: var(--gap-s) var(--gap-m);
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 82px;
}
.label {
  font-size: var(--size-label);
  color: var(--ink-muted);
  line-height: 1.4;
}
.value {
  font-family: var(--font-num);
  font-variant-numeric: tabular-nums;
  font-size: var(--size-readout);
  line-height: 1.15;
  color: var(--ink);
  overflow-wrap: anywhere;
}
.value.compact { font-size: var(--size-h); line-height: 1.5; }
.value.muted { color: var(--ink-muted); }
.stamp { min-height: 15px; }
</style>
