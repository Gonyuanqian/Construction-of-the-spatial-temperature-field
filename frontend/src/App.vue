<script setup lang="ts">
/**
 * 应用外壳。
 *
 * 标题条在**最外层**：它跨模式、跨页面常驻，模式开关与导航都在它下面。
 * 页面的内容只占 `<RouterView />` 那一块 —— 所以任何一页都不需要
 * 重复渲染标题，也就不可能漏渲染。
 *
 * P1 那版 App.vue 里显示数据集摘要的代码**搬去了页①**（Task 8），
 * 这里不再留一行：外壳不显示任何数据。
 *
 * **模式开关现在与路由是同一件事的两种看法。** 之前 `mode` 是一个本地
 * `ref('train')`，而**没有任何人消费它** —— 切到「实时模式」什么都不发生。
 * 现在它从 `route.path` 推出来，写进去就是一次 `router.push`：于是
 * 「开关显示哪个模式」与「现在在哪一页」不可能对不上。
 *
 * 左侧导航**每一页都在**，但内容跟着模式换：训练模式那四页是流水线那四项，
 * 实时模式那一屏是五条演示占位项（`LIVE_NAV_ITEMS`，2026-10-12 照参考图补成五项）。
 * 原先它是**收起**的，
 * 2026-10-09 用户裁定改成「换项不收起」—— 用户给的那张参考图左栏是有导航的。
 *
 * 实时模式那一屏整屏走深色（见 `tokens.css` 的 `:root.theme-live`）。
 */
import { computed, onMounted, ref, watch, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ModeSwitch from './components/ModeSwitch.vue'
import NavRail from './components/NavRail.vue'
import NoDataset from './components/NoDataset.vue'
import TitleBar from './components/TitleBar.vue'
import { useDataset } from './composables/useDataset'
import { LIVE_NAV_ITEMS, NAV_ITEMS } from './design/copy'

const route = useRoute()
const router = useRouter()

/** 数据集的状态与版本号。**全前端唯一一次探测**（规格书 §六、硬约束 3）。 */
const dataset = useDataset()
onMounted(() => { void dataset.probe() })

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
const gate = computed(() => dataset.state.value === 'missing' && route.path !== '/data')

/** 训练模式最后停留的那一页。切回来还回这里 —— 演示时不用重新点一遍。 */
const lastTrainPath = ref('/data')

const isLive = computed(() => route.path.startsWith('/live'))

/** 写进去就是一次跳转；`ModeSwitch` 是 `v-model`，所以走 setter。 */
const mode = computed({
  get: () => (isLive.value ? 'live' : 'train'),
  set: (m: string) => { void router.push(m === 'live' ? '/live' : lastTrainPath.value) },
})

watch(() => route.path, (p) => {
  if (!p.startsWith('/live')) lastTrainPath.value = p
}, { immediate: true })

/**
 * 训练模式最后停留的那一页在 `lastTrainPath` 上，这里只管导航那一列的内容。
 */
const railItems = computed(() => (isLive.value ? LIVE_NAV_ITEMS : NAV_ITEMS))

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
})
</script>

<template>
  <TitleBar />
  <!-- ⚠️ **两处 `<ModeSwitch>` 是有意的**（2026-10-12 页⑤ 仪表盘）。
       参考图的模式页签在**中央工作区顶上**，而不是横跨整屏；而页①②③④
       那四页要维持现状（用户裁定「只需要改动实时模式的页面」）。
       两个 `<ModeSwitch>` 共用一个 `v-model`，所以「开关显示哪个模式」
       与「现在在哪一页」仍然不可能对不上。 -->
  <ModeSwitch v-if="!isLive" v-model="mode" />
  <div class="body" :class="{ live: isLive }">
    <NavRail :items="railItems" />
    <!-- ⚠️ 右栏的**落点**。位置在源码里放在 `main` **前面**：
         字符串选择器的 Teleport 是在挂载期用 `document.querySelector` 找的，
         落点必须在那一页的组件挂起来之前就进文档 —— 放在后面能跑通全靠
         同一次 patch 里的次序，而那是实现细节，不是承诺。
         它**不在 `.page` 里面**：`.page` 是滚动容器，右栏做进它里面，
         内容一超一屏就跟着滚出去，「参数栏」就不成立了（规格书 §三 D1）。 -->
    <aside v-if="isLive" id="shell-side" class="shell-side" />
    <main class="page">
      <ModeSwitch v-if="isLive" v-model="mode" />
      <RouterView v-if="!gate" :key="dataset.version.value" />
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
.body.live > .rail { grid-area: 1 / 1 / 2 / 2; }
.body.live > .page { grid-area: 1 / 2 / 2 / 3; }
/* 右栏自己是一个竖排的列：里面那几张卡的间距由这里的 `gap` 说了算，
   页⑤ 因此不必给每张卡再写一个下边距。 */
.shell-side {
  grid-area: 1 / 3 / 2 / 4;
  display: flex;
  flex-direction: column;
  gap: var(--gap-m);
  min-width: 0;
  overflow-y: auto;
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
  .body.live > .rail { grid-area: 1 / 1 / 3 / 2; }
  .body.live > .page { grid-area: 1 / 2 / 2 / 3; }
  .shell-side {
    grid-area: 2 / 2 / 3 / 3;
    max-height: 42vh;
  }
}
</style>
