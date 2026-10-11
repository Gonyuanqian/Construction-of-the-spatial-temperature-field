/**
 * 竖直软单调投影的前后对比：约束前 / 约束后 / 逐格差。
 *
 * 这里用**两个**色标，与 V5 的「只有一个」不矛盾：
 * 那一节说的是同一张图里的三个断面必须同一个色标（同一个量，并排看）；
 * 这里是两种不同的量（温度 °C 与温差 °C），本来就不该共用一条。
 *
 * 差异图的值域必须**对称**（[-m, +m]）—— 发散色标的中点要严格落在 0，
 * 否则「没变」会被画成一个有颜色的格子。
 */
import type { EChartsOption } from 'echarts'

import type { ComparePayload } from '../../api/types'
import type { Palette } from '../../design/palette'
import { tickLabel } from '../axis'
import { deltaStops, tempStops } from '../scale'

/** 每个面板占连续 4 个下标：热力场 / 测点 / 拱线 / 斜纹。 */
export const SERIES_PER_PANEL = 4
const GRID_W = 0.27
const GRID_GAP = 0.045
const GRID_LEFT0 = 0.035

/**
 * 门禁那句口径。这是它的**唯一**文案处（面板标题与页面正文共用它）。
 */
export function deltaNote(payload: ComparePayload): string {
  const gate = payload.gate_label
  // 用「时」不用箭头：spec §8.5 明禁箭头连接符，这类科学图里它不承担信息。
  const head = `背景光照 = ${payload.light.toFixed(0)} 时门禁${gate}`
  const diff = `逐格最大差 = ${payload.delta_vmax.toFixed(4)} °C`
  // 「差很小」与「一模一样」是两句话。夜里两张图**逐位相同**，就这么说。
  const tail = payload.identical ? '；两张图逐位相同' : ''
  return `${head} ｜ ${diff}${tail}`
}

export function buildConstraintDeltaOption(
  payload: ComparePayload, p: Palette,
): EChartsOption {
  const xs = payload.x.map(String)
  const zs = payload.z.map(String)
  const titles = [
    `${payload.shed}（y = ${payload.y} m）约束前`,
    // 第二格必须**字面**写出「约束后」：三格的标题是这套图唯一的自述，
    // 而「施加竖直软单调投影之后」说的是**怎么来的**，不是**这是哪一格** ——
    // 读者要能把第二格与第三格里的「约束前 − 约束后」对上号。
    '约束后（施加竖直软单调投影）',
    'ΔT = 约束前 − 约束后（正 = 被压低）',
  ]

  const grid = [0, 1, 2].map((i) => ({
    left: `${(GRID_LEFT0 + i * (GRID_W + GRID_GAP)) * 100}%`,
    width: `${GRID_W * 100}%`,
    top: '14%',
    height: '66%',
  }))

  const axisCommon = {
    type: 'category' as const,
    axisLine: { lineStyle: { color: p.steel } },
    axisTick: { show: false },
    // 与切面场同一处收法（见 `charts/axis.ts`）：这一格就在它正下方，
    // 不收的话两处一起花屏。
    axisLabel: { color: p.inkMuted, fontSize: p.chartAxis, formatter: tickLabel },
    splitLine: { show: false },
  }

  const panels: (number | null)[][][] = [payload.before, payload.after, payload.delta]

  return {
    backgroundColor: 'transparent',
    animation: false,
    title: titles.map((text, i) => ({
      text,
      left: `${(GRID_LEFT0 + i * (GRID_W + GRID_GAP) + GRID_W / 2) * 100}%`,
      top: '2%',
      textAlign: 'center',
      textStyle: { color: p.ink, fontSize: p.chartTitle, fontWeight: 600 },
    })),
    grid,
    xAxis: [0, 1, 2].map((i) => ({
      ...axisCommon, gridIndex: i, data: xs, name: '棚长 x / m',
      nameLocation: 'middle' as const, nameGap: 24,
      nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis },
    })),
    yAxis: [0, 1, 2].map((i) => ({
      ...axisCommon, gridIndex: i, data: zs, name: i === 0 ? '高度 z / m' : '',
      nameLocation: 'middle' as const, nameGap: 30,
      nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis },
    })),
    // 两个色标：温度一套、差异一套。各自绑住自己的那些热力场。
    // 两条都**可以拖着看**（spec §七 V5）。拖动的效果是区间外**压暗**，
    // 不是隐去 —— 这张图的头等大事是夜里「ΔT 是 0」，拖动把格子弄没了，
    // 读者第一眼看到的就是一张假的空图。未拖动时选中区间即整段，画面不变。
    visualMap: [
      {
        type: 'continuous',
        min: payload.vmin,
        max: payload.vmax,
        seriesIndex: [0, SERIES_PER_PANEL],
        inRange: { color: tempStops() },
        outOfRange: { opacity: 0.08 },
        calculable: true,
        orient: 'horizontal',
        left: '16%',
        bottom: 0,
        itemWidth: 14,
        itemHeight: 120,
        precision: 1,
        text: [`${payload.vmax.toFixed(1)} °C`, `${payload.vmin.toFixed(1)} °C`],
        textStyle: { color: p.inkMuted, fontSize: p.chartAxis },
      },
      {
        type: 'continuous',
        // **对称**：中点必须严格落在 0。
        min: -payload.delta_vmax,
        max: payload.delta_vmax,
        seriesIndex: [2 * SERIES_PER_PANEL],
        inRange: { color: deltaStops() },
        outOfRange: { opacity: 0.08 },
        calculable: true,
        orient: 'horizontal',
        left: '68%',
        bottom: 0,
        itemWidth: 14,
        itemHeight: 120,
        precision: 2,
        text: [`+${payload.delta_vmax.toFixed(2)}`, `−${payload.delta_vmax.toFixed(2)}`],
        textStyle: { color: p.inkMuted, fontSize: p.chartAxis },
      },
    ],
    tooltip: {
      trigger: 'item',
      formatter: (params: unknown) => {
        const q = params as { seriesIndex: number; value: unknown }
        const v = q.value
        if (!Array.isArray(v) || v.length < 3) return ''
        const which = ['约束前', '约束后', 'ΔT'][Math.floor(q.seriesIndex / SERIES_PER_PANEL)]
        // 三个面板的单位都是 °C —— ΔT 是温差，同样按 °C 报（格子上写的也是 °C）。
        // 这里原先是 `q.seriesIndex < 2 * SERIES_PER_PANEL ? ' °C' : ' °C'`，
        // 两支一模一样，是个**死三元**：读的人会以为两个分支有区别，
        // 于是去找那个不存在的区别。
        return `${which}：${Number(v[2]).toFixed(4)} °C`
      },
    },
    series: panels.flatMap((values, i) => buildPanelSeries(payload, values, i, p)),
  } as unknown as EChartsOption
}

function buildPanelSeries(
  payload: ComparePayload, values: (number | null)[][], i: number, p: Palette,
) {
  const heat: [number, number, number][] = []
  for (let iz = 0; iz < values.length; iz++) {
    for (let ix = 0; ix < values[iz].length; ix++) {
      const v = values[iz][ix]
      // 拱外一律丢掉：填 0 会把「无定义」画成「零温差」。
      if (v !== null) heat.push([ix, iz, v])
    }
  }

  return [
    { type: 'heatmap', xAxisIndex: i, yAxisIndex: i, z: 2, silent: false, data: heat, progressive: 0 },
    {
      type: 'scatter', xAxisIndex: i, yAxisIndex: i, z: 4, silent: true,
      data: payload.sensors.map((sn) => [String(sn.x), String(sn.z)]),
      symbol: 'path://M4,0 h2 v4 h4 v2 h-4 v4 h-2 v-4 h-4 v-2 h4 z',
      symbolSize: 9,
      itemStyle: { color: p.paper, borderColor: p.ink, borderWidth: 1.2 },
    },
    {
      type: 'line', xAxisIndex: i, yAxisIndex: i, z: 5, silent: true, showSymbol: false,
      data: payload.arch.map(([x, z]) => [String(x), String(z)]),
      lineStyle: { color: p.ink, width: 1.1 },
    },
    {
      type: 'custom', xAxisIndex: i, yAxisIndex: i, z: 3, silent: true,
      // 直接吃载荷送来的下标。**不自己从 x/z/max_measured_z 推** ——
      // 那是把后端的一条规则实现了第二遍（硬约束 1）。
      data: payload.stripes,
      renderItem: (_params: unknown, api: any) => {
        const c = api.coord([api.value(0), api.value(1)])
        const [w, h] = api.size([1, 1])
        const x0 = c[0] - w / 2
        const y0 = c[1] - h / 2
        const seg = (ax: number, ay: number, bx: number, by: number) => ({
          type: 'line', shape: { x1: ax, y1: ay, x2: bx, y2: by },
          style: { stroke: p.inkMuted, lineWidth: 1, opacity: 0.55 },
        })
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
