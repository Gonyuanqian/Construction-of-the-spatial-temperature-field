<script setup lang="ts">
import { MODES } from '../design/copy'

const model = defineModel<string>({ default: 'train' })
</script>

<template>
  <nav class="modes" aria-label="模式">
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
    <span v-for="m in MODES.filter((x) => !x.enabled)" :key="m.key + '-why'" class="note">
      {{ m.label }}：{{ m.why }}
    </span>
  </nav>
</template>

<style scoped>
.modes { display: flex; align-items: baseline; gap: var(--gap-m); padding: 0 var(--gap-l) var(--gap-s); }
.mode { padding: 2px 0; border-bottom: 2px solid transparent; color: var(--ink-muted); }
.mode.on { color: var(--leaf); border-bottom-color: var(--leaf); font-weight: var(--w-strong); }
.mode.off { cursor: not-allowed; }
</style>
