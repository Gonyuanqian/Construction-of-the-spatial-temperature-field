<script setup lang="ts">
/**
 * 卡片外壳。**全站唯一一处写圆角与阴影的地方**（spec 2026-10-06 §四）。
 *
 * 为什么值得单出一个组件：圆角与阴影各只有一档，是这次的判据。
 * 每页各写一遍自己的圆角与阴影，那条判据就没人守得住 ——
 * 迟早有一张小卡是 8px、有一张大卡压两层阴影。
 * `guards.test.ts` 那条「box-shadow 只能写成 var(--shadow)」守的就是这件事。
 *
 * 不加 `border`：边界由阴影与底色承担，再加一道描边就退回「细线全铺」
 * （spec §十 的判据）。
 */
</script>

<template>
  <div class="card">
    <slot />
  </div>
</template>

<style scoped>
.card {
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: var(--gap-m);
}
:global(.theme-live) .card {
  background-image:
    linear-gradient(var(--edge), var(--edge)), linear-gradient(var(--edge), var(--edge)),
    linear-gradient(var(--edge), var(--edge)), linear-gradient(var(--edge), var(--edge)),
    linear-gradient(var(--edge), var(--edge)), linear-gradient(var(--edge), var(--edge)),
    linear-gradient(var(--edge), var(--edge)), linear-gradient(var(--edge), var(--edge)),
    radial-gradient(ellipse at 50% 0%, color-mix(in srgb, var(--interact) 7%, transparent), transparent 65%);
  background-size: 18px 1px, 1px 18px, 18px 1px, 1px 18px, 18px 1px, 1px 18px, 18px 1px, 1px 18px, 100% 100%;
  background-position: left top, left top, right top, right top, left bottom, left bottom, right bottom, right bottom, center;
  background-repeat: no-repeat;
}
</style>
