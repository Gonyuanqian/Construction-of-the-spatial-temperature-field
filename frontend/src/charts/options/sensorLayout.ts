/**
 * V1 测点与拱（页①）。
 *
 * **纯函数**：进的是后端给的两份载荷与调色板，出的是画法。
 * 这里不取数、不算数 —— 测点的 5 天均值是后端算好的（硬约束 1）。
 *
 * 设计主张 1「拱是坐标系本身」（spec §七）：所以
 *   · 横轴就是棚长 x、纵轴到拱顶 —— 图幅的范围由**几何**定，不由数据定；
 *   · 关掉轴线的框、关掉网格线，拱线本身是这张图的轮廓；
 *   · 拱外不画任何东西（没有填色、没有点），因为棚外没有温度场。
 */
import type { EChartsOption } from 'echarts'

import type { ArchPayload, DatasetPayload, TempStat } from '../../api/types'
import type { Palette } from '../../design/palette'

const GAP_PCT = 3

export function buildSensorLayoutOption(
  ds: DatasetPayload,
  arch: ArchPayload,
  p: Palette,
): EChartsOption {
  const sheds = arch.sheds
  const width = (100 - GAP_PCT * (sheds.length + 1)) / sheds.length

  const grid = sheds.map((_, i) => ({
    left: `${GAP_PCT + i * (width + GAP_PCT)}%`,
    width: `${width}%`,
    top: '14%',
    height: '74%',
  }))

  const xAxis = sheds.map((_, i) => ({
    gridIndex: i,
    type: 'value' as const,
    min: arch.x_min, max: arch.x_max,
    name: i === Math.floor(sheds.length / 2) ? '棚长 x / m' : '',
    nameLocation: 'middle' as const,
    nameGap: 26,
    nameTextStyle: { color: p.inkMuted, fontSize: 12 },
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { show: false },
    axisLabel: { show: false },
  }))

  const yAxis = sheds.map((_, i) => ({
    gridIndex: i,
    type: 'value' as const,
    min: 0, max: arch.z_max,
    name: i === 0 ? '高度 z / m' : '',
    nameTextStyle: { color: p.inkMuted, fontSize: 12 },
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { show: false },
    axisLabel: { show: false },
  }))

  const series: Record<string, unknown>[] = []
  sheds.forEach((shed, i) => {
    // 拱形轮廓 —— 每棚一段，只画弧，不封闭、不填色：拱外没有温度场
    series.push({
      name: '拱形轮廓',
      type: 'line',
      xAxisIndex: i, yAxisIndex: i,
      data: arch.arch,
      showSymbol: false,
      silent: true,
      lineStyle: { color: p.ink, width: 1.2 },
      z: 2,
    })

    // 无测量带分界线：z = 1.10 m 以上不报数
    series.push({
      name: '无测量带',
      type: 'line',
      xAxisIndex: i, yAxisIndex: i,
      data: [[arch.x_min, arch.max_measured_z], [arch.x_max, arch.max_measured_z]],
      showSymbol: false,
      silent: true,
      lineStyle: { color: p.steel, width: 1, type: 'dotted' },
      z: 1,
    })

    const pts = ds.positions.map((pos) => {
      const t = statOf(ds, shed.id, pos.id)
      return [pos.x, pos.z, t ? t.mean : null] as [number, number, number | null]
    })
    series.push({
      name: `${shed.id} 测点`,
      type: 'scatter',
      xAxisIndex: i, yAxisIndex: i,
      data: pts,
      symbolSize: 28,
      itemStyle: { color: p.leaf, borderColor: p.paper, borderWidth: 2 },
      label: {
        position: 'top',
        color: p.ink,
        fontSize: 11,
        // 均值缺失就**不标** —— 编一个数出来比空着糟得多。
        // 这与 Streamlit 版那条 `if (v.max() - v.min()) > 0` 是同一个意思。
        show: (params: { data: [number, number, number | null] }) =>
          params.data[2] !== null,
        formatter: (params: { data: [number, number, number | null] }) =>
          params.data[2] === null ? '' : (params.data[2] as number).toFixed(1),
      },
      z: 3,
    })
  })

  return {
    backgroundColor: p.paper,
    animation: false,
    grid,
    xAxis, yAxis,
    series,
    // 三格共用一个提示：分别配三个的话，鼠标移过一格另外两格不响应，
    // 而这张图存在的理由就是「三座棚并排比」
    tooltip: { trigger: 'item', backgroundColor: p.paper, borderColor: p.steel, textStyle: { color: p.ink } },
  } as unknown as EChartsOption
}

function statOf(ds: DatasetPayload, shed: string, position: string): TempStat | undefined {
  return ds.temperature.find((t) => t.shed === shed && t.position === position)
}
