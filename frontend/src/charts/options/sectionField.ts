/**
 * V5 切面场：三座棚并排，**共用一个色标**。
 *
 * 这张图存在的全部理由是「并排看」—— 所以三个断面的颜色必须代表同一个温度。
 * 各自拉伸色标的话，同一抹橙在 p1 与 p3 是两个温度，而图上不会报任何错。
 *
 * 三条不变量（都有测试钉着）：
 *   · 整个 option 只有**一个** visualMap，恰好绑住三条热力场；
 *   · 没有一个格子自带颜色（自带的那个就脱离了共享色标）；
 *   · 拱外不进热力场（留白），但另挂一条透明遮罩系列接住点击 ——
 *     不然「拱外无定义」这句回答没有入口。
 */
import type { EChartsOption } from 'echarts'

import type { SectionsPayload } from '../../api/types'
import type { Palette } from '../../design/palette'
import { tempStops } from '../scale'
import { interpretPick, pickText } from '../pick'

/** 每个棚占连续 5 个系列下标，块内次序见下面的 `buildShedSeries`。 */
export const SERIES_PER_SHED = 5

/** 系列下标 → 棚号。越界返回 null（调用方据此忽略这次点击）。 */
export function shedOfSeries(payload: SectionsPayload, seriesIndex: number): string | null {
  if (!Number.isInteger(seriesIndex) || seriesIndex < 0) return null
  const i = Math.floor(seriesIndex / SERIES_PER_SHED)
  return payload.sheds[i]?.shed ?? null
}

/** 一格的人话。与侧栏读数共用 —— 两处措辞因此不可能不一致。 */
export function cellTooltip(
  payload: SectionsPayload, shed: string, ix: number, iz: number,
): string {
  return pickText(interpretPick(payload, shed, ix, iz), payload)
}

const GRID_W = 0.27
const GRID_GAP = 0.045
const GRID_LEFT0 = 0.035

export function buildSectionFieldOption(
  payload: SectionsPayload, p: Palette,
): EChartsOption {
  const xs = payload.x.map(String)
  const zs = payload.z.map(String)

  const grid = payload.sheds.map((_, i) => ({
    left: `${(GRID_LEFT0 + i * (GRID_W + GRID_GAP)) * 100}%`,
    width: `${GRID_W * 100}%`,
    top: '14%',
    height: '68%',
    containLabel: false,
  }))

  const axisCommon = {
    type: 'category' as const,
    axisLine: { lineStyle: { color: p.steel } },
    axisTick: { show: false },
    axisLabel: { color: p.inkMuted, fontSize: 10 },
    splitLine: { show: false },
  }

  const xAxis = payload.sheds.map((_, i) => ({
    ...axisCommon, gridIndex: i, data: xs, name: '棚长 x / m',
    nameLocation: 'middle' as const, nameGap: 24,
    nameTextStyle: { color: p.inkMuted, fontSize: 10 },
  }))
  const yAxis = payload.sheds.map((_, i) => ({
    ...axisCommon, gridIndex: i, data: zs, name: i === 0 ? '高度 z / m' : '',
    nameLocation: 'middle' as const, nameGap: 30,
    nameTextStyle: { color: p.inkMuted, fontSize: 10 },
  }))

  return {
    backgroundColor: 'transparent',
    animation: false,
    title: payload.sheds.map((s, i) => ({
      text: `${s.shed}（y = ${s.y} m）`,
      left: `${(GRID_LEFT0 + i * (GRID_W + GRID_GAP) + GRID_W / 2) * 100}%`,
      top: '3%',
      textAlign: 'center',
      textStyle: { color: p.ink, fontSize: 12, fontWeight: 600 },
    })),
    grid,
    xAxis,
    yAxis,
    // ⚠️ **一个对象，不是数组**。数组就是三格各算各的色标 —— 这张图就白画了。
    // seriesIndex 恰好是三条热力场（每棚块内偏移 1）。
    // calculable: false —— 拖把手会过滤数据（超范围的格子不画），
    // 而这里色标条是图例，不是控制器。
    visualMap: {
      type: 'continuous',
      min: payload.vmin,
      max: payload.vmax,
      seriesIndex: payload.sheds.map((_, i) => i * SERIES_PER_SHED + 1),
      inRange: { color: tempStops() },
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemWidth: 14,
      itemHeight: 150,
      precision: 1,
      text: [`${payload.vmax.toFixed(1)} °C`, `${payload.vmin.toFixed(1)} °C`],
      textStyle: { color: p.inkMuted, fontSize: 10 },
    },
    tooltip: {
      trigger: 'item',
      // tooltip 与侧栏读数走**同一个** cellTooltip —— 两处措辞不可能不一致。
      formatter: (params: unknown) => {
        const q = params as { seriesIndex: number; value: unknown }
        const shed = shedOfSeries(payload, q.seriesIndex)
        const v = q.value
        if (!shed || !Array.isArray(v) || v.length < 2) return ''
        return cellTooltip(payload, shed, Number(v[0]), Number(v[1]))
      },
    },
    series: payload.sheds.flatMap((s, i) => buildShedSeries(payload, s, i, p)),
  } as unknown as EChartsOption
}

function buildShedSeries(
  payload: SectionsPayload, s: SectionsPayload['sheds'][number], i: number, p: Palette,
) {
  const gi = i
  const heat: [number, number, number][] = []
  const mask: [number, number][] = []
  for (let iz = 0; iz < s.values.length; iz++) {
    for (let ix = 0; ix < s.values[iz].length; ix++) {
      const v = s.values[iz][ix]
      // 拱外不进热力场 —— 这里**不是**「填个 0 或上一个值」，是根本不画。
      if (v === null) mask.push([ix, iz])
      else heat.push([ix, iz, v])
    }
  }

  return [
    // 0. 拱外遮罩：透明矩形，唯一作用是接住点击。
    {
      type: 'custom',
      xAxisIndex: gi,
      yAxisIndex: gi,
      z: 1,
      silent: false,
      data: mask,
      renderItem: (_params: unknown, api: any) => {
        const c = api.coord([api.value(0), api.value(1)])
        const [w, h] = api.size([1, 1])
        // 透明但**有形状**：ECharts 的命中判定是几何的，不看透明度。
        return {
          type: 'rect',
          shape: { x: c[0] - w / 2, y: c[1] - h / 2, width: w, height: h },
          style: { fill: 'transparent' },
        }
      },
    },
    // 1. 热力场：颜色**只**由那一个 visualMap 决定，数据项不带任何样式。
    {
      type: 'heatmap',
      xAxisIndex: gi,
      yAxisIndex: gi,
      z: 2,
      silent: false,
      data: heat,
      progressive: 0,
      emphasis: { itemStyle: { borderColor: p.ink, borderWidth: 1 } },
    },
    // 2. 实测点位。ECharts 没有内置的「+」，用自定义 path 画十字 ——
    //    与 Streamlit 版同一个记号，读图的人不用重新学。
    {
      type: 'scatter',
      xAxisIndex: gi,
      yAxisIndex: gi,
      z: 4,
      silent: true,
      data: payload.sensors.map((sn) => [String(sn.x), String(sn.z)]),
      symbol: 'path://M4,0 h2 v4 h4 v2 h-4 v4 h-2 v-4 h-4 v-2 h4 z',
      symbolSize: 9,
      itemStyle: { color: p.paper, borderColor: p.ink, borderWidth: 1.2 },
    },
    // 3. 拱线。用载荷给的折线 —— 界面上不重算拱的几何。
    {
      type: 'line',
      xAxisIndex: gi,
      yAxisIndex: gi,
      z: 5,
      silent: true,
      showSymbol: false,
      data: payload.arch.map(([x, z]) => [String(x), String(z)]),
      lineStyle: { color: p.ink, width: 1.1 },
    },
    // 4. 无测量带斜纹：每格三条平行短线。颜色走令牌，不是硬编码。
    {
      type: 'custom',
      xAxisIndex: gi,
      yAxisIndex: gi,
      z: 3,
      silent: true,
      data: s.stripes,
      renderItem: (_params: unknown, api: any) => {
        const c = api.coord([api.value(0), api.value(1)])
        const [w, h] = api.size([1, 1])
        const x0 = c[0] - w / 2
        const y0 = c[1] - h / 2
        const stroke = p.inkMuted
        const seg = (ax: number, ay: number, bx: number, by: number) => ({
          type: 'line',
          shape: { x1: ax, y1: ay, x2: bx, y2: by },
          style: { stroke, lineWidth: 1, opacity: 0.55 },
        })
        // 三条 45° 平行线，都落在格子内部：主对角线 + 左上角 + 右下角两段。
        return {
          type: 'group',
          children: [
            seg(x0, y0 + h, x0 + w, y0),
            seg(x0, y0 + h / 2, x0 + w / 2, y0),
            seg(x0 + w / 2, y0 + h, x0 + w, y0 + h / 2),
          ],
        }
      },
    },
  ]
}
