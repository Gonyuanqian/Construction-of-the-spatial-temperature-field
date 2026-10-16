<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref } from 'vue'
const expanded = ref(false)
const host = ref<HTMLElement | null>(null)
let animation: Animation | undefined
async function toggle() {
  const el = host.value
  if (!el) return
  const before = el.getBoundingClientRect()
  animation?.cancel()
  expanded.value = !expanded.value
  await nextTick()
  const after = el.getBoundingClientRect()
  if (typeof el.animate === 'function' && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    animation = el.animate([
      { transformOrigin: 'top left', transform: `translate(${before.left - after.left}px, ${before.top - after.top}px) scale(${before.width / after.width}, ${before.height / after.height})`, opacity: .65 },
      { transformOrigin: 'top left', transform: 'none', opacity: 1 },
    ], { duration: 320, easing: 'cubic-bezier(0.22,1,0.36,1)' })
  }
}
onBeforeUnmount(() => animation?.cancel())
</script>
<template>
  <div ref="host" class="card" :class="{ 'is-expanded': expanded }" @keydown.esc="expanded && toggle()">
    <button class="panel-expand" type="button" :aria-expanded="expanded" :aria-label="expanded ? '收起面板' : '展开面板'" @click="toggle">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <path :d="expanded ? 'M9 3v6H3m18 6h-6v6M3 9l6-6m6 18 6-6' : 'M3 9V3h6m6 18h6v-6M3 3l6 6m6 6 6 6'" />
      </svg>
    </button>
    <slot />
  </div>
</template>
<style scoped>
.card { position: relative; background: var(--glass); border: 1px solid var(--steel); border-radius: var(--radius); box-shadow: var(--shadow); padding: var(--gap-m); backdrop-filter: blur(16px); transition: transform 320ms var(--ease-cockpit); }
.card::after { content: ''; position: absolute; inset: 0; pointer-events: none; border: 1px solid var(--leaf); border-radius: inherit; opacity: .12; animation: panel-breathe 3.5s ease-in-out infinite; }
.card:hover { transform: translateY(-2px); }
.card:hover::after { animation: none; opacity: .65; }
.is-expanded:hover { transform: none; }
.panel-expand { position: absolute; top: 8px; right: 8px; z-index: 2; padding: 4px; display: flex; opacity: .45; }
.panel-expand:hover, .panel-expand:focus-visible { opacity: 1; }
.is-expanded { position: fixed; inset: 116px 30px 24px 248px; z-index: 20; overflow: auto; background: var(--card); }
@media (max-width: 760px) { .is-expanded { inset: 160px 12px 16px; } }
</style>
