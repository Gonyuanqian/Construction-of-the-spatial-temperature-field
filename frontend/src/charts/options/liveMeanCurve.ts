/** 高度—均温剖面。温度由后端按当前网格汇总，缺数高度留 null。 */
import type { EChartsOption } from 'echarts'

import type { VolumePayload } from '../../api/types'
import type { Palette } from '../../design/palette'
import { tempStops } from '../scale'

export const MEAN_CURVE_TITLE = '温度分布概览'

export function buildLiveMeanCurveOption(
  payload: VolumePayload, p: Palette,
): EChartsOption {
  const profile = payload.height_profile ?? []
  const means = profile.flatMap(point => point.mean == null ? [] : [point.mean])
  const low = means.length ? Math.min(...means) : payload.vmin
  const high = means.length ? Math.max(...means) : payload.vmax
  // 小图保持约 3 个主刻度；按实际温差留白，避免整度取整把曲线压平。
  const span = Math.max(high - low, 0.2)
  const unit = 10 ** Math.floor(Math.log10(span / 2))
  const interval = ([1, 2, 2.5, 5, 10].find(step => step * unit >= span / 2) ?? 10) * unit
  const axisMin = Number((Math.floor((low - span * 0.1) / interval) * interval).toFixed(8))
  const axisMax = Number((Math.ceil((high + span * 0.1) / interval) * interval).toFixed(8))
  const colors = tempStops()
  return {
    backgroundColor: 'transparent',
    animation: false,
    /* 标题由外层卡片承担，绘图区不要再重复画一遍；把腾出的高度还给曲线。 */
    grid: { left: 48, right: 18, top: 22, bottom: 36 },
    visualMap: {
      show: false, type: 'continuous', dimension: 1,
      min: low, max: high > low ? high : low + 1,
      inRange: { color: [colors[2], colors[4], colors[5]] },
    },
    xAxis: {
      type: 'value',
      min: payload.z[0] ?? 0, max: payload.z_max, splitNumber: 4,
      name: '距地高度 (m)', nameLocation: 'middle', nameGap: 23,
      nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis },
      axisLine: { lineStyle: { color: p.steel } },
      axisTick: { show: false },
      axisLabel: {
        color: p.inkMuted, fontSize: p.chartAxis, hideOverlap: true,
        formatter: (value: number) => String(Number(value.toFixed(2))),
      },
      splitLine: { show: true, lineStyle: { color: p.layerMid, type: 'solid', opacity: 0.5 } },
      minorTick: { show: false, splitNumber: 6 },
      minorSplitLine: { show: true, lineStyle: { color: p.layerMid, type: 'dashed', opacity: 0.22 } },
    },
    yAxis: {
      type: 'value',
      inverse: true,
      // 不强制从 0 起：这一卷的均温可能只横跨两度，从 0 起就压平了。
      scale: true,
      name: '均温 (°C，向下升温)', nameLocation: 'start', nameGap: 6,
      nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis, align: 'left', padding: [0, 0, 0, -35] },
      min: axisMin, max: axisMax, interval,
      axisLine: { lineStyle: { color: p.steel } },
      axisLabel: {
        color: p.inkMuted, fontSize: p.chartAxis, hideOverlap: true,
        showMinLabel: true, showMaxLabel: true,
        formatter: (value: number) => String(Number(value.toFixed(2))),
      },
      splitLine: { lineStyle: { color: p.layerMid, type: 'solid', opacity: 0.5 } },
      minorTick: { show: false, splitNumber: 2 },
      minorSplitLine: { show: true, lineStyle: { color: p.layerMid, type: 'dashed', opacity: 0.22 } },
    },
    tooltip: { trigger: 'axis', formatter: (params: unknown) => {
      const point = (Array.isArray(params) ? params[0] : params) as {value?: [number, number | null]} | undefined
      if (!point?.value) return ''
      const [height, mean] = point.value
      return `距地高度：${Number(height).toFixed(2)} m<br/>均温：${mean == null ? '无数据' : `${Number(mean).toFixed(3)} °C`}`
    } },
    series: [{
      type: 'line',
      name: MEAN_CURVE_TITLE,
      // `[高度, 均温]`；不回退到沿棚长均温，避免把旧数据画到错误坐标上。
      data: profile.map(point => [point.z, point.mean]),
      showSymbol: false,
      smooth: 0.25,
      smoothMonotone: 'x',
      symbolSize: 6,
      connectNulls: false,
      // 2026-10-12 换样式：这一屏的底是深蓝，1.4px 的青线在上面只剩一条
      // 若有若无的痕（参考图那条线粗得多，而且带一层同色的面积底）。
      // 颜色仍走 `p.leaf` —— 全站「同一个数在哪儿都是同一个颜色」那条没变。
      lineStyle: { width: 3 },
      itemStyle: { borderColor: p.paper, borderWidth: 1 },
      // 面积底用**同一个颜色**、靠透明度分层 —— 不用第二个色号，
      // 免得「这条线是什么颜色」在屏上出现两种答案。
      // 反向温度轴的数值上界位于画面下方，面积始终向画面下边界填充。
      areaStyle: { origin: 'end', color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: colors[5] }, { offset: 0.4, color: colors[2] }, { offset: 0.85, color: colors[1] }, { offset: 1, color: 'transparent' }] }, opacity: 0.55 },
      // 线之外不加阴影、不加发光：阴影全站只有一档且只给卡片
      // （`guards.test.ts` 钉着），图表这一层也不破例。
    }],
  } as unknown as EChartsOption
}
