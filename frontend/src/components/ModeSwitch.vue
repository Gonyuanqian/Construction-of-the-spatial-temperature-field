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
  background: var(--card);
}
.seg .mode {
  background: transparent;
  border: 0;
  border-radius: 0;
  padding: 3px 14px;
  color: var(--ink-muted);
}
/* 圆角由首末两个按钮自己收 —— 不用 `overflow: hidden`。那一句会把
   `:focus-visible` 的 `outline-offset: 2px` 伸出按钮盒的那一圈裁掉，
   键盘用户看到的焦点环是断的（终审 M-8）。 */
.seg .mode:first-child { border-radius: var(--radius) 0 0 var(--radius); }
.seg .mode:last-child { border-radius: 0 var(--radius) var(--radius) 0; }
.seg .mode + .mode { border-left: 1px solid var(--steel); }
/* 选中项是**交互态**：走 `--interact` / `--on-face`（2026-10-12）。
   实时那一档使用深色导航区，因此继续走交互蓝，与参考图的层级一致。 */
.seg .mode.on { background: var(--interact); color: var(--on-face); }
.seg .mode.off { cursor: not-allowed; }
</style>
