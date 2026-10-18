/**
 * V2 昼夜与残差（页①）。
 *
 * 三格共享一条时间游标，但**范围不一样**：
 *   · 上格 全量程（背景温度 + 24 路棚温）—— 看得见昼夜循环
 *   · 下格 减去背景后的 ±3 °C 带 —— 看得见真正的空间信号
 *   · 右格 时间 × 高度热图 —— **只画 `shed` 那一个棚**（上、下两格是三棚合看）
 *
 * 右格为什么只画一棚：热图讲的是「同一棚内各层随时间的相对变化」，
 * 把几个棚的层堆在一张热图上，纵轴就不是一个可比的量了。代价是范围比另两格窄，
 * 所以那一个棚的名字必须**写在图名里**（series.name）——并排三格共用一条游标，
 * 不写清楚，读者会默认它们同范围。
 *
 * **下格的数据是后端算好的 `detrended`，这里一个减法都不做。**
 * 这不是洁癖：前端再减一遍，界面上显示的数与后端算出的数就成了两条
 * 独立的计算路径，漂了不报错（硬约束 1，Review Focus #4）。
 *
 * 缺失值（后端线上给的 null）在这里**画成断口**，不填 0、不编数 ——
 * line 数据点给 null 即断开，heatmap 格子给 null 即留白。
 */
import type { EChartsOption } from 'echarts'

import type { LayerTimeHeightPayload, TimeseriesPayload } from '../../api/types'
import type { Palette } from '../../design/palette'
import { tempStops } from '../scale'

type Pair = [string, number | null]

export function buildDiurnalResidualOption(
  ts: TimeseriesPayload,
  th: LayerTimeHeightPayload,
  shed: string,
  p: Palette,
): EChartsOption {
  const left = 6
  const leftW = 56
  const right = left + leftW + 6
  const rightW = 100 - right - 3

  const grid = [
    { left: `${left}%`, width: `${leftW}%`, top: '8%', height: '34%' },
    { left: `${left}%`, width: `${leftW}%`, top: '52%', height: '34%' },
    { left: `${right}%`, width: `${rightW}%`, top: '8%', height: '78%' },
  ]

  const dayOf = (iso: string) => iso.slice(5, 10)

  const xAxis = [
    axisTime(0, p, true, dayOf),
    axisTime(1, p, true, dayOf),
    {
      gridIndex: 2,
      type: 'category' as const,
      data: th.time,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { color: p.inkMuted, fontSize: p.chartAxis, formatter: dayOf, hideOverlap: true },
    },
  ]

  const yAxis = [
    value(0, '温度 / °C', p),
    // 下格的纵轴**就用后端给的 ±3**，不按数据自适应：
    // 自适应的话，最热那天和凉快那天纵轴不一样，横着比就失效了。
    { ...value(1, '棚温 − 背景 / °C', p), min: ts.detrended_domain[0], max: ts.detrended_domain[1] },
    {
      gridIndex: 2,
      type: 'category' as const,
      data: th.sheds[shed]?.labels ?? [],
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { color: p.inkMuted, fontSize: p.chartAxis },
    },
  ]

  const series: Record<string, unknown>[] = [
    {
      name: '背景温度',
      type: 'line', xAxisIndex: 0, yAxisIndex: 0,
      data: ts.time.map((t, i): Pair => [t, ts.bg_temp[i]]),
      showSymbol: false, silent: true,
      lineStyle: { color: p.ink, width: 1.4 }, z: 4,
    },
  ]

  for (const [key, values] of Object.entries(ts.sensors)) {
    series.push({
      name: `${key}（棚温）`,
      type: 'line', xAxisIndex: 0, yAxisIndex: 0,
      data: ts.time.map((t, i): Pair => [t, values[i]]),
      showSymbol: false, silent: true, sampling: 'lttb',
      lineStyle: { color: p.steel, width: 0.6 }, z: 1,
    })
  }
  for (const [shedId, values] of Object.entries(ts.shed_mean)) {
    series.push({
      name: `${shedId} 棚内均值`,
      type: 'line', xAxisIndex: 0, yAxisIndex: 0,
      data: ts.time.map((t, i): Pair => [t, values[i]]),
      showSymbol: false, sampling: 'lttb',
      lineStyle: { color: p.leaf, width: 1.6 }, z: 3,
    })
  }

  for (const [key, values] of Object.entries(ts.detrended)) {
    series.push({
      name: `${key}（减背景）`,
      type: 'line', xAxisIndex: 1, yAxisIndex: 1,
      data: ts.time.map((t, i): Pair => [t, values[i]]),
      showSymbol: false, silent: true, sampling: 'lttb',
      lineStyle: { color: p.steel, width: 0.6 },
    })
  }
  for (const [shedId, values] of Object.entries(ts.detrended_mean)) {
    series.push({
      name: `${shedId} 棚内均值（减背景）`,
      type: 'line', xAxisIndex: 1, yAxisIndex: 1,
      data: ts.time.map((t, i): Pair => [t, values[i]]),
      showSymbol: false, sampling: 'lttb',
      lineStyle: { color: p.leaf, width: 1.6 },
    })
  }

  const rows = th.sheds[shed]?.values ?? []
  const heat: [number, number, number | null][] = []
  rows.forEach((row, r) => row.forEach((v, c) => heat.push([c, r, v])))
  // 色标范围由**有值的格子**定；null 不参与（null 进 Math.min 会被当成 0，
  // 那就等于给缺测时刻编了一个数）。全格缺失时退回 [0, 1] 的可画区间。
  const finite = rows.flat().filter((v): v is number => v !== null)

  // 热图在 series 里的下标：折线数量随数据变（24 路棚温 + 各棚均值），
  // 所以不能写死「第 3 条」—— 记下它推进去时的位置，visualMap 要靠它定位。
  const heatIndex = series.length
  series.push({
    name: `时间 × 高度（${shed}）`,
    type: 'heatmap',
    xAxisIndex: 2, yAxisIndex: 2,
    data: heat,
    // 色标：正向 turbo（spec §8.1）。vmin/vmax 由数据定 ——
    // 这一格讲的是「同一棚内各层随时间的相对变化」，不是跨棚比较。
    itemStyle: { borderWidth: 0 },
  })

  return {
    // 底色由外层的卡片给，图自己不铺，免得在卡片里留一块颜色不同的方板
    // （原委见 `sensorLayout.ts` 同一处）。
    backgroundColor: 'transparent',
    animation: false,
    grid, xAxis, yAxis, series,
    // 一条游标贯穿三格 —— 这是这张图存在的全部理由（spec §七 V2）
    axisPointer: { link: [{ xAxisIndex: 'all' }], label: { backgroundColor: p.ink } },
    tooltip: {
      trigger: 'axis',
      backgroundColor: p.paper, borderColor: p.steel,
      textStyle: { color: p.ink },
    },
    visualMap: {
      show: true,
      // ⚠️ 必须写 seriesIndex。ECharts 5 的顶层 visualMap 默认作用于**所有**
      // series，数据维度默认取最后一个 —— 对折线来说最后一个维度正好也是温度，
      // 于是两条折线会被色标重染，而 lineStyle 里的调色板色还在，
      // 「没有第八个颜色」那条测试会静默通过。钉死在热图这一条上。
      seriesIndex: heatIndex,
      min: finite.length ? Math.min(...finite) : 0,
      max: finite.length ? Math.max(...finite) : 1,
      calculable: false,
      orient: 'vertical',
      right: 0, top: '40%',
      itemHeight: 120,
      inRange: { color: tempStops() },
      textStyle: { color: p.inkMuted, fontSize: p.chartAxis },
    },
  } as unknown as EChartsOption
}

function axisTime(
  gridIndex: number, p: Palette, showLabel: boolean,
  fmt: (iso: string) => string,
) {
  return {
    gridIndex,
    type: 'time' as const,
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { show: false },
    axisLabel: showLabel
      ? { color: p.inkMuted, fontSize: p.chartAxis, formatter: (v: number) =>
            fmt(new Date(v).toISOString()), hideOverlap: true }
      : { show: false },
  }
}

function value(gridIndex: number, name: string, p: Palette) {
  return {
    gridIndex,
    type: 'value' as const,
    name,
    nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis },
    nameGap: 12,
    scale: true,
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { show: true, lineStyle: { color: p.steel, type: 'dashed' as const } },
    axisLabel: { color: p.inkMuted, fontSize: p.chartAxis },
  }
}
