<script setup lang="ts">
/**
 * ECharts 的薄外壳：建实例、喂 option、跟随尺寸、卸载时销毁。
 *
 * **它只负责画。** 取数与 option 的构造都在外面 —— 有一条硬约束
 * （图表组件只负责画，不负责取数）盯着这件事，好处是每个 option
 * 都能在 vitest 里喂假数据单独验，不需要 canvas。
 *
 * 这个组件自己**没有单元测试**：它是纯粹的 DOM 管道，jsdom 里没有 canvas，
 * 硬测只会测到 mock。它由 Task 11 的路由冒烟覆盖。
 */
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{ option: echarts.EChartsOption; height?: string }>(),
  { height: '320px' },
)

const host = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

onMounted(() => {
  if (!host.value) return
  chart = echarts.init(host.value, undefined, { renderer: 'canvas' })
  chart.setOption(props.option)
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
