/**
 * 折外预测 vs 实测的密度图（规格书 §7.1）。
 *
 * **为什么是密度不是散点**：两万七千对点画成散点是一团墨，y = x 那条
 * 对角线会被糊掉 —— 而那条线是这张图唯一要回答的东西（报高了还是报低了）。
 * 后端的 60×60 计数矩阵让每个格子有确定的深浅。
 *
 * ⚠️ 两个轴**共用同一个范围**：它是对角线图，轴范围不同的话 y = x 就不是
 * 45 度，而读这张图靠的全部是「点落在对角线的哪一侧」。
 */
import type { EChartsOption } from 'echarts'

import type { DiagnosticsPayload, DensityPayload } from '../../api/types'
import type { Palette } from '../../design/palette'
import { tempStops } from '../scale'

/**
 * 计数 → 颜色。
 *
 * ⚠️ 用 `log1p` 而不是线性：二维直方图的计数是长尾的 —— 对角线附近是几千、
 * 别处是零或个位数。「第 n 格 / 最大值」这种线性映射会把除对角线以外的
 * 整个画面压成同一个最浅色，于是图看起来只剩一条线，而不是一片云。
 *
 * ⚠️ 色标复用 `tempStops()`：它是一条**顺序色标**（单调递增），
 * 与温度没有关系，这里借的是它的单调性。`design/guards.test.ts` 不许在
 * `tokens.css` 与 `charts/scale.ts` 之外写十六进制色值，所以这也是唯一
 * 能在不动 `scale.ts` 的前提下拿到一条顺序色标的路。
 */
export function densityColor(count: number, max: number, stops: string[]): string {
  if (max <= 1) return stops[stops.length - 1]
  const t = Math.log1p(count) / Math.log1p(max)
  const i = Math.min(stops.length - 1, Math.floor(t * stops.length))
  return stops[Math.max(0, i)]
}

export function buildOofDensityOption(
  d: DiagnosticsPayload, p: Palette,
): EChartsOption {
  const den: DensityPayload = d.density
  const lo = den.lo
  const hi = den.hi
  if (lo === null || hi === null || den.counts.length === 0) {
    // 一对有限点都没有（整段缺值）。给一张说得出话的空图 ——
    // 一块什么都没有的坐标轴，看起来像图坏了。
    return {
      backgroundColor: 'transparent',
      title: {
        text: '折外预测与实测：这一份数据上没有一对有限点，密度图没算出来',
        left: 'center', top: 'middle',
        textStyle: { color: p.inkMuted, fontSize: p.chartTitle },
      },
      series: [],
    }
  }

  const width = (hi - lo) / den.bins
  const stops = tempStops()
  let max = 0
  den.counts.forEach((row) => row.forEach((c) => { if (c > max) max = c }))

  // 每一格一个矩形。`custom` 而不是 `heatmap`：heatmap 要求两个轴都是
  // category，而 60 个类目在轴上既画不出刻度也读不出数 —— 这里两个轴
  // 都是**连续的数值轴**（它是对角线图），所以要自己算格子的位置与大小。
  const cells: [number, number, number, string][] = []
  den.counts.forEach((row, it) => {
    row.forEach((count, ip) => {
      if (count <= 0) return            // 零格不画：画上去是一层灰底，读不出东西
      cells.push([
        lo + (it + 0.5) * width,
        lo + (ip + 0.5) * width,
        count,
        densityColor(count, max, stops),
      ])
    })
  })

  return {
    backgroundColor: 'transparent',
    animation: false,
    grid: { left: 72, right: 24, top: 40, bottom: 56, containLabel: false },
    // ⚠️ 提示框里**只报后端给的计数**。格子中心的坐标是这一页用
    // `lo + (i + 0.5) * width` 现算的，不是后端送来的任何一行；箱宽是
    // `(hi − lo) / 60`（大约一摄氏度），把它印成两位小数是报了一个
    // 这个箱根本没有的精度，而且违反硬约束 1（前端不做数值计算）。
    // 要说出「这一格在哪」，轴上的刻度已经说了。
    tooltip: {
      trigger: 'item',
      formatter: (params: unknown) => {
        const v = (params as { value: unknown[] }).value
        if (!Array.isArray(v)) return ''
        return `这一格 ${v[2]} 个点`
      },
    },
    xAxis: {
      type: 'value', min: lo, max: hi, name: '实测 / °C',
      nameLocation: 'middle', nameGap: 30,
      nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis },
      axisLine: { lineStyle: { color: p.steel } },
      axisLabel: { color: p.inkMuted, fontSize: p.chartAxis },
      splitLine: { lineStyle: { color: p.steel, opacity: 0.25 } },
    },
    yAxis: {
      type: 'value', min: lo, max: hi, name: '预测 / °C',
      nameLocation: 'middle', nameGap: 48,
      nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis },
      axisLine: { lineStyle: { color: p.steel } },
      axisLabel: { color: p.inkMuted, fontSize: p.chartAxis },
      splitLine: { lineStyle: { color: p.steel, opacity: 0.25 } },
    },
    series: [
      {
        // ⚠️ **不能是 `silent: true`**：静默的要素在 zrender 里不参与命中
        // 测试，上面那个 `trigger: 'item'` 的提示框就永远不会出现 ——
        // 而这一格的点数是这张图上唯一读得到的数。下面那条参考线是装饰，
        // 它 silent 掉没问题，格子不行。
        type: 'custom', z: 2,
        renderItem: (_params: unknown, api: any) => {
          const c = api.coord([api.value(0), api.value(1)])
          const [w, h] = api.size([width, width])
          return {
            type: 'rect',
            shape: { x: c[0] - w / 2, y: c[1] - h / 2, width: w, height: h },
            style: { fill: api.value(3) as string },
          }
        },
        data: cells,
      },
      {
        // y = x 那条线。舍掉它，这张图就只剩「一团东西」——
        // 读者没法说「点在线的哪一侧」。
        type: 'line', silent: true, z: 3, showSymbol: false,
        data: [[lo, lo], [hi, hi]],
        lineStyle: { color: p.ink, width: 1.2, type: 'dashed' },
      },
    ],
  } as unknown as EChartsOption
}
