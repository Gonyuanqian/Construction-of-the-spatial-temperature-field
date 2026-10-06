<script setup lang="ts">
/**
 * 模式开关。**它长得像个开关，而不是一排链接**（spec §5.2）。
 *
 * ⚠️ 形状不许动：仍是 `nav[aria-label="模式"]` + 一串 `<button>`，
 * 未开放项仍是 `disabled` 且 `title` 里带理由 —— `App.test.ts` 按这几条找它。
 * 外面套一层 `.seg` 只为画那个描边条，不动语义标签。
 */
import { MODES } from '../design/copy'

const model = defineModel<string>({ default: 'train' })
</script>

<template>
  <nav class="modes" aria-label="模式">
    <div class="seg">
      <button
        v-for="m in MODES"
        :key="m.key"
        class="mode"
        :class="{ on: m.key === model, off: !m.enabled }"
        :disabled="!m.enabled"
        :aria-current="m.key === model ? 'true' : undefined"
        :title="m.enabled ? '' : m.why"
        @click="model = m.key"
      >
        {{ m.label }}
      </button>
    </div>
    <span v-for="m in MODES.filter((x) => !x.enabled)" :key="m.key + '-why'" class="note">
      {{ m.label }}：{{ m.why }}
    </span>
  </nav>
</template>

<style scoped>
.modes {
  display: flex;
  align-items: center;
  gap: var(--gap-m);
  padding: var(--gap-s) var(--gap-l);
}
.seg {
  display: flex;
  align-items: stretch;
  border: 1px solid var(--steel);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--card);
}
.seg .mode {
  background: transparent;
  border: 0;
  border-radius: 0;
  padding: 3px 14px;
  color: var(--ink-muted);
}
.seg .mode + .mode { border-left: 1px solid var(--steel); }
.seg .mode.on { background: var(--leaf); color: var(--paper); }
.seg .mode.off { cursor: not-allowed; }
</style>
