<script setup lang="ts">
/**
 * 左侧导航。
 *
 * 2026-10-06（spec §5.2）：后端版本那一行**搬去了标题条** —— `/live` 收起导航，
 * 导航不在时那一行也跟着没了，而实时那一屏最需要确认「后端是哪一个」。
 * 未开放项的理由不再堆在栏底：演示时没人会往栏底看，挪到紧贴那一项的地方。
 *
 * ⚠️ 形状不许动：仍是 `nav[aria-label="页面"]`，导航项仍是 `<a>`。
 * `App.test.ts` 断言 `rail.findAll('a')` **精确等于**已开放项，且次序一致
 * （spec §十三.2）——「把导航做成按钮」是这次唯一不能做的控件化改动。
 * 未开放项的理由必须**仍在这个 nav 里**，`App.test.ts:74` 按 `rail.text()` 找它。
 */
import { NAV_ITEMS } from '../design/copy'
</script>

<template>
  <nav class="rail" aria-label="页面">
    <template v-for="item in NAV_ITEMS" :key="item.key">
      <RouterLink v-if="item.enabled" class="item" :to="item.to">{{ item.label }}</RouterLink>
      <template v-else>
        <span class="item off">{{ item.label }}</span>
        <span class="why note">{{ item.why }}</span>
      </template>
    </template>

    <!-- 页面自带的侧栏控件从这里投进来（页③ 的视图切换与时刻游标）。
         页① ② 不用它，所以它平时是空的 —— :empty 时不占高度，
         免得那两页的下方多出一块莫名其妙的空白。 -->
    <div id="rail-extra" class="rail-extra" />

    <hr class="rule" />
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
.item {
  display: block;
  position: relative;
  padding: 3px 0 3px 10px;
  color: var(--ink);
  text-decoration: none;
}
.item.router-link-active { color: var(--leaf); font-weight: var(--w-strong); }
/* 选中态的竖标走 CSS，不加字符 —— 加了会被 `routes.smoke.test.ts` 的
   渲染文本扫描看见，也会被读屏软件念出来（spec §十三.2）。 */
.item.router-link-active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 3px;
  bottom: 3px;
  width: 2px;
  background: var(--leaf);
}
.item.off { color: var(--ink-muted); cursor: not-allowed; }
.why { display: block; padding: 0 0 var(--gap-s) 10px; }
.rule { border: 0; border-top: var(--rule); width: 100%; margin: var(--gap-m) 0 0; }
.rail-extra:empty { display: none; }
.rail-extra { margin-top: var(--gap-m); display: flex; flex-direction: column; gap: var(--gap-s); }
</style>
