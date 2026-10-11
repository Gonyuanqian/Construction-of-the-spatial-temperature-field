<script setup lang="ts">
/**
 * 左侧导航。
 *
 * 2026-10-06（spec §5.2）：后端版本那一行**搬去了标题条** —— 它一度是因为
 * `/live` 会把导航收起来才搬的，而 2026-10-09 起左栏**每一屏都在**（见下），
 * 搬去标题条这个位置仍然对：那一行说的是「后端是哪一个」，不属于某一列。
 * 未开放项的理由不再堆在栏底：演示时没人会往栏底看，挪到紧贴那一项的地方。
 *
 * 2026-10-09 用户裁定：左栏**不再收起**，而是**换项** —— 训练模式那四页画
 * 流水线那四项（`NAV_ITEMS`），实时模式那一屏画三条演示占位项
 * （`LIVE_NAV_ITEMS`）。所以这一列有了 `items` 属性，默认仍是 `NAV_ITEMS`。
 *
 * ⚠️ 形状不许动：仍是 `nav[aria-label="页面"]`，导航项仍是 `<a>`。
 * `App.test.ts` 断言 `rail.findAll('a')` **精确等于**已开放项，且次序一致
 * （spec §十三.2）——「把导航做成按钮」是这次唯一不能做的控件化改动。
 * 未开放项的理由必须**仍在这个 nav 里**，`App.test.ts:74` 按 `rail.text()` 找它。
 */
import { NAV_ITEMS, type RailItem } from '../design/copy'

/**
 * 这一列画哪几项。**默认 `NAV_ITEMS`** —— 页①②③④ 一个属性都不传，
 * 所以那四页的左栏与改动前逐字相同。
 * 实时模式那一屏传 `LIVE_NAV_ITEMS`（见 `App.vue`）。
 */
const props = withDefaults(defineProps<{ items?: readonly RailItem[] }>(), {
  items: () => NAV_ITEMS,
})
</script>

<template>
  <nav class="rail" aria-label="页面">
    <template v-for="item in props.items" :key="item.key">
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
  /* 项间距由 gap 给（2026-10-06 卡片化）。`.why` 自带的下内边距叠在 gap 上，
     于是「卡片 → 它的说明」8px、「说明 → 下一张卡」16px —— 说明因此读起来
     贴着上面那张灰卡，而不是悬在两张卡中间。 */
  gap: var(--gap-s);
  /* 导航模块自成一「面」（2026-10-06 用户裁定）：浅蓝底，与内容区的暖纸分开。
     这是**面**的区别，不是把激活色搬到这里 —— 激活项仍走 `--nav-blue`。
     `align-self: stretch`：这一列要铺满**整个框**（`.body` 已成为框，见
     `App.vue` 与 `design/base.css`）。不撑的话底色只裹住那几张卡，
     成一条浮在中途的色条，而不是一列。
     `overflow-y: auto`：框闭合之后左栏不能再靠文档滚到底 —— 页③ 往
     `#rail-extra` 投进来的视图切换与时刻游标，窗口一矮就会比框还高，
     不自己滚就是「底下那半截永远够不着」。
     代价认下来：滚动容器裁在**内边距盒**上，而这一列的上内边距是 0，
     所以第一张卡那条 1px 的投影在上缘会被裁掉一像素。 */
  background: var(--nav-tint);
  align-self: stretch;
  overflow-y: auto;
}
/* 每一项是一张卡（2026-10-06 用户裁定）。圆角与阴影走全站那一档
   （spec §四：全站只有一档），这里不新开第二种卡。 */
.item {
  display: block;
  padding: var(--gap-s) 10px;
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  color: var(--ink);
  text-decoration: none;
}
/* 激活态：底色 `--nav-blue` + 字 `--paper`，与模式开关 `.on`（叶底 + 纸字）
   同一套语言。激活色走 `--nav-blue` 而不是 `--leaf`（2026-10-06 用户裁定）：
   导航要与内容区分开，而全站其余地方仍是叶绿。令牌那边记着这个蓝与页①
   中层测点蓝同屏的已知冲突 —— 那是被接受的选择，不是这里写错了。
   **原先那根竖标撤掉了**：底色已经说明「是这一项」，再插一根同色的竖条
   是同一句话说了两遍。 */
.item.router-link-active {
  background: var(--nav-blue);
  color: var(--paper);
  font-weight: var(--w-strong);
}
.item.off { color: var(--ink-muted); cursor: not-allowed; }
.why { display: block; padding: 0 0 var(--gap-s) 10px; }
.rule { border: 0; border-top: var(--rule); width: 100%; margin: var(--gap-m) 0 0; }
.rail-extra:empty { display: none; }
.rail-extra { margin-top: var(--gap-m); display: flex; flex-direction: column; gap: var(--gap-s); }
</style>
