<script setup lang="ts">
/**
 * 应用外壳。
 *
 * 标题条在最外层跨页面常驻，内容由路由决定，导航按账号角色展示。
 * 页面的内容只占 `<RouterView />` 那一块 —— 所以任何一页都不需要
 * 重复渲染标题，也就不可能漏渲染。
 *
 * P1 那版 App.vue 里显示数据集摘要的代码**搬去了页①**（Task 8），
 * 这里不再留一行：外壳不显示任何数据。
 *
 * 左侧导航**每一页都在**，但内容跟着模式换：训练模式那四页是流水线那四项，
 * 实时模式那一屏是五条演示占位项（`LIVE_NAV_ITEMS`，2026-10-12 照参考图补成五项）。
 * 原先它是**收起**的，
 * 2026-10-09 用户裁定改成「换项不收起」—— 用户给的那张参考图左栏是有导航的。
 *
 * 实时模式那一屏整屏走深色（见 `tokens.css` 的 `:root.theme-live`）。
 */
import { computed, onUnmounted, watch, watchEffect } from 'vue'
import { useRoute } from 'vue-router'

import NavRail from './NavRail.vue'
import NoDataset from './NoDataset.vue'
import TitleBar from './TitleBar.vue'
import { useDataset } from '../composables/useDataset'
import { useAuth } from '../composables/useAuth'
import { provideTrainingWorkspace } from '../composables/useTrainingWorkspace'
import { provideWeatherTraining } from '../composables/useWeatherTraining'
import {provideModelTraining} from '../composables/useModelTraining'
import { DEVELOPER_NAV_ITEMS, USER_NAV_ITEMS } from '../design/copy'

const route = useRoute()
const auth = useAuth()

/** 数据集的状态与版本号。**全前端唯一一次探测**（规格书 §六、硬约束 3）。 */
const dataset = useDataset()
provideTrainingWorkspace()
provideWeatherTraining()
provideModelTraining()

/**
 * 空态闸门。**判断只在这一处** —— ②③④ 与实时模式各写一遍就是五处判断，
 * 而它们一定会分家（四个页面说没数据、一个页面说有）。
 *
 * 页① 例外：它就是那个入口，空态下它渲染导入块，不渲染空态提示。
 *
 * ⚠️ `state === 'missing'` 而不是「不是 ok」：`probing` 与 `error` 都不该
 * 走这条路 —— 后者的代价最重，它会把「后端挂了」说成「你还没开始」，
 * 让用户去导一份数据集来解决一个后端没起来的问题。
 *
 * `probing` 走的这一条**有个代价，写在明面上**：探测落地之前页面会真挂一次、
 * 真取一次数。拿它换的是「已经导过数据集的人不会先看见一屏『先导入数据集』」。
 * 两害相权，取后者 —— 一瞬的取数没人看得见，一瞬的假空态每个人都会看见。
 */
/**
 * ⚠️ 2026-10-16：`/live` 从这道闸门里**放行**。页⑤ 从这一天起读
 * `configs/live/` 下两份固定文件，与「当前数据集」没有关系；而 `configs/live/`
 * 存在**不算**「有数据集」—— 算进去的话页②③④ 会在没导入时跟着亮，而那三页
 * 拿的是另一份数据。代价：重启后页⑤ 能用、页① 仍写「先导入数据集」，
 * 两个页面各说各话。这是**有意**的：它们确实各用各的数据源。
 */
const isDeveloperWorkspace = computed(() => auth.isAdmin.value && route.meta.workspace === 'developer')
const isLive = computed(() => route.meta.theme === 'live')
const isAssistantChat = computed(() => route.path === '/assistant')
const isDesign = computed(() => ['greenhouse-design','greenhouse-control','alert-log'].includes(String(route.name)))
watch(isDeveloperWorkspace, active => { if (active) void dataset.probe() }, { immediate: true })

const gate = computed(() => auth.isAdmin.value && dataset.state.value === 'missing'
  && ['train', 'field'].includes(String(route.name))
  && route.path !== '/data'
  && !isLive.value)

/** 当前页面与账号角色共同决定导航内容。 */
const railItems = computed(() => isDeveloperWorkspace.value ? DEVELOPER_NAV_ITEMS : USER_NAV_ITEMS)
// 实时监测不依赖训练数据集，后台导入不重置用户工作台。
const pageKey = computed(() => ['live','greenhouse-design','greenhouse-control','alert-log'].includes(String(route.name))
  ? String(route.name)
  : `${route.name === 'model-detail' ? 'models' : String(route.name)}:${dataset.version.value}`)

/**
 * 实时模式那一屏整屏走深色。
 *
 * ⚠️ **挂在 `documentElement` 上，不是挂在模板根上**，两个理由：
 *   1. `App.vue` 的模板是**片段**，`:class` 没有那一个元素可落；
 *   2. 更要紧的是 `LiveView` 与 `VolumeScene` 都按 `readPalette()` 读
 *      `document.documentElement` 上的令牌（ECharts 的 canvas 不认 `var()`）。
 *      类挂在 `documentElement` 上，CSS、图表、三维才是**同一份颜色**。
 *
 * `watchEffect` 在 setup 里**立刻跑一次**，早于任何子组件渲染 —— 所以
 * 页⑤ 第一次 `readPalette()` 时读到的就已经是深色那一档。
 */
watchEffect(() => {
  document.documentElement.classList.toggle('theme-live', isLive.value)
  document.documentElement.classList.toggle('theme-management', ['models', 'model-detail'].includes(String(route.name)))
})
onUnmounted(() => document.documentElement.classList.remove('theme-management'))
</script>

<template>
  <TitleBar />
  <div class="body" :class="{ live: isLive, 'monitoring-shell': route.name==='live', 'design-shell':isDesign, 'training-shell': route.name==='train', 'assistant-shell': route.path.startsWith('/assistant'), 'assistant-chat-shell': isAssistantChat }">
    <div v-if="isLive" class="live-nav-stack">
      <div class="user-workspace-label">{{ isDeveloperWorkspace ? '开发者后台' : '用户工作台' }}</div>
      <NavRail :items="railItems" variant="live" />
    </div>
    <NavRail v-else :items="railItems" variant="plain" />
    <!-- ⚠️ 右栏的**落点**。位置在源码里放在 `main` **前面**：
         字符串选择器的 Teleport 是在挂载期用 `document.querySelector` 找的，
         落点必须在那一页的组件挂起来之前就进文档 —— 放在后面能跑通全靠
         同一次 patch 里的次序，而那是实现细节，不是承诺。
         它**不在 `.page` 里面**：`.page` 是滚动容器，右栏做进它里面，
         内容一超一屏就跟着滚出去，「参数栏」就不成立了（规格书 §三 D1）。 -->
    <aside v-if="isLive && !isAssistantChat && !isDesign" id="shell-side" class="shell-side" />
    <main class="page">
      <!-- 实时工作台跨路由保留；更换数据集后使用新的实例。 -->
      <RouterView v-if="!gate" v-slot="{ Component }">
        <KeepAlive include="LiveView,GreenhouseDesignView" :max="2">
          <component :is="Component" :key="pageKey" />
        </KeepAlive>
      </RouterView>
      <NoDataset v-else />
    </main>
  </div>
</template>

<style scoped>
/* 滚的是右边这一列，不是整个文档（`#app` 已钉成框，见 `design/base.css`）。
   `min-height: 0` 不是可选项：flex 子项默认**不低于内容**，不减这一条
   `.page` 就永远由内容撑高，它的 `overflow-y: auto` 永远不会生效。
   `overflow: hidden` 把溢出挡在框里，两列于是各自滚。
   `align-items: stretch`（原先是 `flex-start`）：两列都要满高 —— `.page`
   不满高就没有可滚的高度，`.rail` 不满高则只剩一条浮在中途的色条。 */
.body {
  display: flex;
  align-items: stretch;
  gap: var(--gap-m);
  padding: var(--gap-m) 0;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}
.page { flex: 1 1 auto; min-width: 0; padding-right: var(--gap-l); overflow-y: auto; }
.body:not(.live) { padding-top: 12px; padding-bottom: 8px; }
.user-workspace-label { padding: 22px 20px 12px; color: var(--ink-muted); font-size: var(--size-note); }
.body.live.weather-shell { grid-template-columns: var(--sidebar-w) minmax(0, 1fr); grid-template-rows: minmax(0, 1fr); }
.body.live.weather-shell > .page { margin-right: var(--gap-m); }

/* ── 实时那一屏的三栏（2026-10-12 用户裁定） ──────────────────────────
   `.body.live` 把外壳从「导航 + 内容」换成三列：左 210px（`--sidebar-w`
   在实时那一档的取值）、中自适应、右 390px（`--side-w`）。
   ⚠️ 三块都用 `grid-area` **显式定位**，不靠自动排列：自动排列会按源码次序
   填格，而窄屏那一档（只有两列）会把 `main` 排到第二行的第一格 ——
   也就是塞到导航底下。显式定位与源码次序无关。
   ⚠️ 中列写 `minmax(0, 1fr)` 而不是 `1fr`：写成 `1fr` 时格子的下限是
   **内容宽度**，画布会先把页宽撑破，而不是自己缩（与页① 那条左右分栏同一条理由）。 */
.body.live {
  display: grid;
  grid-template-columns: var(--sidebar-w) minmax(0, 1fr) var(--side-w);
  grid-template-rows: minmax(0, 1fr);
}
.body.live > .live-nav-stack { grid-area: 1 / 1 / 2 / 2; }
/* 实时三栏统一由 grid gap 留白，移除两栏布局遗留的右内边距。 */
.body.live > .page { grid-area: 1 / 2 / 2 / 3; padding-right: 0; }
.live-nav-stack { display: flex; flex-direction: column; min-height: 0; }
.live-nav-stack :deep(.rail.live) { width: auto; flex: 1 1 0; min-height: 0; }
/* ⚠️ 2026-10-16：中栏在实时这一档还是一条**竖排的弹性列**（页⑤ 要三块同屏，
   见 `LiveView.vue` 那两条）。`.page` 自己的 `overflow-y: auto` **原样保留**
   —— 装得下就不滚，顶到里面各块的下限才滚。这一条与上面 `.page` 那条写在
   两个选择器里不是重复：`.page` 是所有页共用的，这一条只管实时那一档。 */
.body.live > .page { display: flex; flex-direction: column; overflow-x: hidden; }
.body.live > .page, .body.live > .shell-side, .live-nav-stack :deep(.rail.live) { scrollbar-width: none; }
.body.live > .page::-webkit-scrollbar, .body.live > .shell-side::-webkit-scrollbar, .live-nav-stack :deep(.rail.live::-webkit-scrollbar) { display: none; }
/* 右栏自己是一个竖排的列：里面那几张卡的间距由这里的 `gap` 说了算，
   页⑤ 因此不必给每张卡再写一个下边距。 */
.shell-side {
  grid-area: 1 / 3 / 2 / 4;
  display: flex;
  flex-direction: column;
  gap: var(--gap-m);
  min-width: 0;
  overflow-y: auto;
  overflow-x: hidden;
}
/* 监测页两列共享行高和滚动范围，让底栏与右侧建议卡片底边对齐。 */
@media (min-width: 1200px) {
  .body.live.monitoring-shell { grid-template-rows: minmax(min-content, 1fr); overflow-y: auto; }
  .body.live.monitoring-shell > .page,
  .body.live.monitoring-shell > .shell-side { overflow: visible; }
  .body.live.monitoring-shell > .shell-side :deep(.agronomy-card) { margin-top: 0; flex: 1 0 310px; height: auto; }
}
/* 1200–1440px：右栏收窄。参考图那 390px 在 1280 的屏上是「中央只剩 680px」，
   三维会紧得看不出棚体（规格书 §九 第一条风险）。 */
@media (max-width: 1439px) {
  .body.live { grid-template-columns: var(--sidebar-w) minmax(0, 1fr) 320px; }
}
/* < 1200px：右栏落到中央列**下方**，两栏变一栏 —— 左右不挤，也不出横向滚动条。 */
@media (max-width: 1199px) {
  .body.live {
    grid-template-columns: var(--sidebar-w) minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) auto;
  }
  .body.live > .live-nav-stack { grid-area: 1 / 1 / 3 / 2; }
  .body.live > .page { grid-area: 1 / 2 / 2 / 3; }
  .shell-side {
    grid-area: 2 / 2 / 3 / 3;
    max-height: 42vh;
  }
}
/* 助手窄屏按阅读顺序滚动，避免固定导航将问答区挤到不足一个输入框。 */
@media (max-width: 700px) {
  .body.training-shell{flex-direction:column;gap:8px;padding-top:8px;}
  .training-shell > :deep(.rail){width:auto;flex:none;flex-direction:row;flex-wrap:wrap;padding:6px 12px;gap:4px;border-right:0;border-bottom:var(--rule);}
  .training-shell :deep(.rail-heading),.training-shell :deep(.rail .rule),.training-shell :deep(.rail-extra){display:none;}
  .training-shell :deep(.rail .item){min-height:32px;padding:5px 8px;font-size:12px;}
  .training-shell :deep(.rail .item .ico){width:15px;height:15px;}
  .body.training-shell > .page{padding:8px 12px;}
  .body.live.weather-shell { display: flex; flex-direction: column; overflow-y: auto; }
  .weather-shell > .live-nav-stack { flex: none; }
  .body.live.weather-shell > .page { flex: none; overflow: visible; margin: 0 var(--gap-m); padding-bottom: var(--gap-m); }
  .body.live.assistant-shell { display:flex; flex-direction:column; overflow-y:auto; }
  .assistant-shell > .live-nav-stack { flex:none; }
  .assistant-shell .live-nav-stack :deep(.rail.live) { flex:none; }
  .body.live.assistant-shell > .page { flex:none; overflow:visible; }
  .assistant-shell > .shell-side { flex:none; max-height:none; overflow:visible; }
}
/* 复用实时模式原有外框与导航；聊天面板占满其右侧工作区。 */
.body.live.assistant-chat-shell {
  display:grid;
  grid-template-columns:var(--sidebar-w) minmax(0,1fr);
  grid-template-rows:minmax(0,1fr);
}
.assistant-chat-shell > .live-nav-stack {grid-area:1/1/2/2;}
.body.live.assistant-chat-shell > .page {
  grid-area:1/2/2/3;
  min-height:0;
  overflow:hidden;
  margin-right:var(--gap-m);
  background:var(--assistant-paper);
  border:1px solid var(--steel);
  border-radius:6px;
}
.body.live.design-shell{grid-template-columns:var(--sidebar-w) minmax(0,1fr);grid-template-rows:minmax(0,1fr)}
.body.live.design-shell>.page{grid-area:1/2/2/3;margin-right:var(--gap-m);display:block}
@media(max-width:700px){.body.live.design-shell{display:flex;flex-direction:column;overflow-y:auto}.design-shell>.live-nav-stack{flex:none}.design-shell .live-nav-stack :deep(.rail.live){flex:none}.body.live.design-shell>.page{flex:none;overflow:visible;margin:0 12px}}
</style>
