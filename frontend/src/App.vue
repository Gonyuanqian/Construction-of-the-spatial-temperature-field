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
 * 导航按 `route.meta.rail` 收起。实时模式那一屏把导航收起来，因为它
 * 是全程唯一「不提数据」的一列 —— 演示时它只是噪声，而且「实时源的状态」
 * 才是这一屏要说的事。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ModeSwitch from './components/ModeSwitch.vue'
import NavRail from './components/NavRail.vue'
import NoDataset from './components/NoDataset.vue'
import TitleBar from './components/TitleBar.vue'
import { useDataset } from './composables/useDataset'

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

const showRail = computed(() => route.meta.rail !== false)
</script>

<template>
  <TitleBar />
  <ModeSwitch v-model="mode" />
  <div class="body">
    <NavRail v-if="showRail" />
    <main class="page">
      <RouterView v-if="!gate" :key="dataset.version.value" />
      <NoDataset v-else />
    </main>
  </div>
</template>

<style scoped>
.body { display: flex; align-items: flex-start; gap: var(--gap-m); padding: var(--gap-m) 0; }
.page { flex: 1 1 auto; min-width: 0; padding-right: var(--gap-l); }
</style>
