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
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import Icon from './Icon.vue'
import { NAV_ITEMS, type RailItem } from '../design/copy'

/**
 * 这一列画哪几项。**默认 `NAV_ITEMS`** —— 训练模式使用流程导航，
 * 实时模式由 `App.vue` 传入另一份演示导航清单。
 * 实时模式那一屏传 `LIVE_NAV_ITEMS`（见 `App.vue`）。
 */
const props = withDefaults(defineProps<{
  items?: readonly RailItem[]
  /**
   * 这一列长什么样。**默认 `'plain'`（训练模式的浅色导航）**。
   *
   * `'live'` 是 2026-10-16 精修那一档：连续的菜单行（图标在左、文字在右，
   * 选中项左缘一道青条），与参考图一致。
   *
   * ⚠️ 为什么是**加一个可选属性**而不是另写一个组件：这一列的形状钉在
   * `App.test.ts` 与 `NavRail.test.ts` 上（仍是 `nav[aria-label="页面"]`、
   * 导航项仍是 `<a>`、未开放项的理由仍在这个 nav 里），另写一个就得分叉两份
   * 守卫；而分叉出来的那一份，正是最容易在半年后没跟上的一处。
   */
  variant?: 'plain' | 'live'
}>(), {
  items: () => NAV_ITEMS,
  variant: 'plain',
})

const isLive = computed(() => props.variant === 'live')
const route = useRoute()
// 独立详情路由仍属于同一导航模块，例如 /models/1 高亮“模型库”。
function isActive(path: string): boolean {
  return route.path === path || route.path.startsWith(`${path}/`)
}
</script>

<template>
  <nav class="rail" :class="{ live: isLive, training: !isLive }" aria-label="页面">
    <div v-if="!isLive" class="rail-heading">工作空间</div>
    <template v-for="item in props.items" :key="item.key">
      <!-- 图标在左、文字在右；训练和实时导航都使用同一份线框图标。 -->
      <RouterLink v-if="item.enabled" class="item" :to="item.to"
                  :class="{ 'router-link-active': isActive(item.to) }"
                  :aria-current="isActive(item.to) ? 'page' : undefined">
        <Icon v-if="item.icon" :name="item.icon" class="ico" />
        <span class="label">{{ item.label }}</span>
      </RouterLink>
      <template v-else>
        <span class="item off" aria-disabled="true">
          <Icon v-if="item.icon" :name="item.icon" class="ico" />
          <span class="label">{{ item.label }}</span>
          <span v-if="!isLive" class="availability">待开放</span>
        </span>
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
.rail:not(.live) {
  width: clamp(200px, 17vw, 240px);
  flex-basis: clamp(200px, 17vw, 240px);
  padding: 16px 12px 20px;
  background: var(--card);
  border-right: var(--rule);
  gap: 4px;
}
.rail-heading {
  padding: 4px 10px 12px;
  margin: 0 0 4px;
  color: var(--ink-muted);
  font-size: var(--size-note);
  font-weight: var(--w-strong);
  letter-spacing: .04em;
  border-bottom: var(--rule);
}
.rail:not(.live) .item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 46px;
  padding: 0 10px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  box-shadow: none;
  color: var(--ink-muted);
  text-decoration: none;
  transition: background-color .16s ease, color .16s ease, border-color .16s ease;
}
.rail:not(.live) .item .ico { width: 19px; height: 19px; color: var(--leaf); opacity: .82; }
.rail:not(.live) .item .label { min-width: 0; flex: 1 1 auto; }
.rail:not(.live) .item.router-link-active {
  position: relative;
  background: var(--leaf-soft);
  color: var(--leaf);
  border-color: var(--steel);
  font-weight: var(--w-strong);
}
.rail:not(.live) .item.router-link-active::before {
  content: '';
  position: absolute;
  inset: 8px auto 8px -1px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--leaf);
}
.rail:not(.live) .item.router-link-active .ico { opacity: 1; }
.rail:not(.live) .item:not(.off):hover { background: var(--leaf-soft); color: var(--leaf); }
.rail:not(.live) .item:focus-visible { outline: 2px solid var(--interact); outline-offset: 2px; }
.rail:not(.live) .item.off { color: var(--ink-muted); cursor: default; }
.availability {
  flex: none;
  padding: 2px 6px;
  border-radius: 999px;
  background: var(--paper);
  color: var(--ink-muted);
  font-size: 11px;
  font-weight: var(--w-body);
}
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
/* 训练侧使用清爽的浅色菜单行；实时侧保留另一套深色仪表盘导航。 */
.rail:not(.live) .item {
  display: block;
  padding: var(--gap-s) 10px;
  background: transparent;
  border-radius: var(--radius);
  box-shadow: none;
  color: var(--ink);
  text-decoration: none;
}
/* 深色实时侧栏的激活态；训练侧在上方单独覆盖为浅绿选中态。 */
.item.router-link-active {
  background: var(--nav-blue);
  color: var(--paper);
  font-weight: var(--w-strong);
}
.item.off { color: var(--ink-muted); cursor: not-allowed; }
.why { display: block; padding: 0 0 var(--gap-s) 10px; }
.rail:not(.live) .why { padding: 2px 8px 10px 39px; line-height: 1.5; }
.rule { border: 0; border-top: var(--rule); width: 100%; margin: var(--gap-m) 0 0; }
.rail:not(.live) .rule { width: calc(100% - 8px); margin: 12px 4px 8px; }
.rail-extra:empty { display: none; }
.rail-extra { margin-top: var(--gap-m); display: flex; flex-direction: column; gap: var(--gap-s); }
.rail:not(.live) .rail-extra { margin-top: 0; }

/* ── 页⑤ 精修（2026-10-16）：实时那一屏的左栏 ────────────────────────
   行，不是卡：项高统一、通到两边（左边那道高亮条要贴着栏的边缘），
   默认态是**透明的深蓝底**、浅蓝的字与低亮度的线框图标。
   ⚠️ 卡片那一套改挂在 `.rail:not(.live)` 上了（见上）。 */
.rail.live {
  /* 行要通到边上，所以内边距从**列**挪到了**行**上。 */
  padding: 0;
  gap: 0;
  /* 右边缘那条低透明度的青线。
     ⚠️ 用的是 `--edge-line`（一个带 alpha 的青），不是「`--edge` 加 opacity」：
     opacity 是整件元素的事，而这条线是**栏的边框**。
     也正因为走 `border-right` 而不是一条绝对定位的伪元素，它不会跟着内容滚 ——
     `.rail` 是 `overflow-y: auto`，伪元素会滚走，边框不会。
     `box-sizing: border-box` 是全局的（`base.css`），所以栏宽仍是 210px。 */
  border-right: 1px solid var(--edge-line);
}
.rail.live .item {
  display: flex;
  align-items: center;
  gap: var(--gap-s);
  /* 用户给的是 52–58px，取中间。用 `min-height` 而不是 `height`：
     窄屏上文字折行时写死高度会把字切掉（`--titlebar-h` 那条同一个理由）。 */
  min-height: 54px;
  padding: 0 var(--gap-m) 0 var(--gap-l);
  background: transparent;
  border-radius: 0;
  color: var(--ink-muted);
  font-size: var(--size-body);
  /* 悬停要「平滑过渡」（用户原话）。只过渡这两个会变的属性：
     写 `all` 会把布局属性也带上，那是在为一件不会变的事付钱。 */
  transition: background-color 0.18s ease, color 0.18s ease;
  /* 选中项左缘那道青条要贴在这一行的边上。 */
  position: relative;
}
/* 悬停：比页底亮一档的深蓝。⚠️ 占位项不参与 —— 它点不动，给反馈是在骗人。 */
.rail.live .item:not(.off):hover {
  background: var(--card);
  color: var(--ink);
}
/* 图标默认是三成半暗。⚠️ 走 `opacity` 而不是另一个颜色：图标是 `currentColor`
   上色的（`Icon.vue`），压暗它就等于压暗那一行的字，而字不该跟着暗。 */
.rail.live .item .ico { opacity: 0.75; }

/* 选中态：亮蓝的底 + 左缘一道青 + 外发光 + 图标文字提亮（用户第二部分要求）。 */
.rail.live .item.router-link-active {
  background: var(--nav-blue);
  color: var(--on-face);
  font-weight: var(--w-strong);
  box-shadow: var(--glow-lift);
}
/* 左缘那道 3px 的青条。
   ⚠️ 它 2026-10-06 被**撤掉**过一次，当时的理由是「底色已经说明是这一项，
   再插一根同色的竖条是同一句话说了两遍」。2026-10-16 用户点名要它回来，
   而且两处都变了：当年是同色的竖标，现在是与底色**不同色**的青。
   所以那句话不再成立 —— 底色说「是这一项」，这道青说「这一屏是活的」。 */
.rail.live .item.router-link-active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--edge);
}
.rail.live .item.router-link-active .ico { opacity: 1; }

/* 未开放项那三句理由。⚠️ 暂时**留着可见**（见本轮要求采集 R9）——
   参考图上那三行是干净的，所以页⑤ 的左栏会比参考图多三行小字。
   这是「默认不动没被点名的东西」，已向用户点出、等他点头。 */
.rail.live .why { padding: 0 var(--gap-m) var(--gap-s) var(--gap-l); }
</style>
