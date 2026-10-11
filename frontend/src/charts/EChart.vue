<script setup lang="ts">
/**
 * ECharts 的薄外壳：建实例、喂 option、跟随尺寸、卸载时销毁。
 *
 * **它只负责画。** 取数与 option 的构造都在外面 —— 有一条硬约束
 * （图表组件只负责画，不负责取数）盯着这件事，好处是每个 option
 * 都能在 vitest 里喂假数据单独验，不需要 canvas。
 *
 * 这个组件有自己的单元测试（`EChart.test.ts`）：它测的不是画得对不对，
 * 而是「ECharts 的 click 必须变成组件的 pick 事件」这条线没有断。
 * 画得对不对同样由 Task 14（`routes.smoke.test.ts`）的路由冒烟兜底。
 */
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{ option: echarts.EChartsOption; height?: string }>(),
  { height: '320px' },
)

/**
 * 点选是**拾取**，不是重跑（spec §七 V5）：图形库把「用户点了哪一格」告诉页面，
 * 页面从**已经拿到的载荷**里读那个格的数。所以这里只往外递 ECharts 的原话，
 * 不做任何解释 —— 怎么读那个值的规则在 `charts/pick.ts` 里，只有一处。
 */
const emit = defineEmits<{
  pick: [payload: { seriesIndex: number; value: unknown }]
}>()

const host = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

onMounted(() => {
  if (!host.value) return
  chart = echarts.init(host.value, undefined, { renderer: 'canvas' })
  chart.setOption(props.option)
  chart.on('click', (params) => {
    emit('pick', {
      seriesIndex: (params as { seriesIndex?: number }).seriesIndex ?? -1,
      value: (params as { value?: unknown }).value,
    })
  })
  // 侧栏折叠、窗口缩放都要跟着变 —— 不跟随的话图会一直用挂载那一刻的尺寸。
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(host.value)
})

watch(() => props.option, (o) => {
  // notMerge=true：换数据集时旧图上的系列必须消失，否则两张图会叠在一起。
  chart?.setOption(o, true)
}, { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  chart?.off('click')
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="host" class="chart" :style="{ height: props.height }" />
</template>

<style scoped>
.chart { width: 100%; }
</style>
