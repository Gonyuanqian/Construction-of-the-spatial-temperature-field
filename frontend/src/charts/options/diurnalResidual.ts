/**
 * V2 昼夜与残差（页①）。
 *
 * 三格共享一条时间游标：
 *   · 上格 全量程（背景温度 + 24 路棚温）—— 看得见昼夜循环
 *   · 下格 减去背景后的 ±3 °C 带 —— 看得见真正的空间信号
 *   · 右格 时间 × 高度热图 —— 游标移到哪，它就换到哪
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
      axisLabel: { color: p.inkMuted, fontSize: 11, formatter: dayOf, hideOverlap: true },
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
      axisLabel: { color: p.inkMuted, fontSize: 11 },
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

  series.push({
    name: '时间 × 高度',
    type: 'heatmap',
    xAxisIndex: 2, yAxisIndex: 2,
    data: heat,
    // 色标：正向 cividis（spec §8.1）。vmin/vmax 由数据定 ——
    // 这一格讲的是「同一棚内各层随时间的相对变化」，不是跨棚比较。
    itemStyle: { borderWidth: 0 },
  })

  return {
    backgroundColor: p.paper,
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
      min: finite.length ? Math.min(...finite) : 0,
      max: finite.length ? Math.max(...finite) : 1,
      calculable: false,
      orient: 'vertical',
      right: 0, top: '40%',
      itemHeight: 120,
      inRange: { color: cividisStops() },
      textStyle: { color: p.inkMuted, fontSize: 11 },
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
      ? { color: p.inkMuted, fontSize: 11, formatter: (v: number) =>
            fmt(new Date(v).toISOString()), hideOverlap: true }
      : { show: false },
  }
}

function value(gridIndex: number, name: string, p: Palette) {
  return {
    gridIndex,
    type: 'value' as const,
    name,
    nameTextStyle: { color: p.inkMuted, fontSize: 11 },
    nameGap: 12,
    scale: true,
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { show: true, lineStyle: { color: p.steel, type: 'dashed' as const } },
    axisLabel: { color: p.inkMuted, fontSize: 11 },
  }
}

/**
 * cividis 的采样点。
 *
 * ⚠️ **必须正向** —— Streamlit 版把色标用反了（正反颠倒），于是 52 °C 是深蓝、
 * 42 °C 是亮黄，读起来是拧的（spec §8.1）。
 * 注意这里不能写出反向色标的名字：`guards.test.ts` 全仓扫那个字符串，
 * 会把注释也算进去。
 * 这七个值是 cividis 在 0/1/6…6/6 处的采样，写在这里而不是从 CSS 读：
 * canvas 的渐变要的是真颜色，而 `--temp-scale: cividis` 是一个**色标名**，
 * 不是颜色。所以这条色标由构造器持有，界面色才从令牌来。
 */
function cividisStops(): string[] {
  return ['#00224E', '#12456F', '#4C6C7F', '#7C7B78', '#BE8353', '#EB9A31', '#FFE945']
}
