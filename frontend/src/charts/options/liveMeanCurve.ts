/**
 * 沿棚长方向的均温剖面：横轴是棚位 y，纵轴是**那一整片**的拱内均温。
 *
 * 它回答的是「这一棚从头到尾哪儿热」—— 断面图回答的是「这一片里哪儿热」，
 * 三维回答的是「整个棚体长什么样」。三个问题，不是同一张图的三种画法。
 *
 * ⚠️ 每个点都是 `VolumePlane.mean`，**后端算的**（口径见
 * `backend/api/routes/field.py::_mean_in_arch`）。这里一个温度都不重算。
 *
 * ⚠️ 缺数的片留 `null`：折成 0 会画出一条贴着底的假线，删掉则两端被直接
 * 连起来、跨过一段本来「无定义」的棚位。两种都不报错，都只是让人看错
 * （与 `pointCurve.ts` 同一条规矩）。
 */
import type { EChartsOption } from 'echarts'

import type { VolumePayload } from '../../api/types'
import type { Palette } from '../../design/palette'
import { tempStops } from '../scale'

export const MEAN_CURVE_TITLE = '温度分布概览'

export function buildLiveMeanCurveOption(
  payload: VolumePayload, p: Palette,
): EChartsOption {
  const means = payload.planes.flatMap(plane => plane.mean == null ? [] : [plane.mean])
  const low = means.length ? Math.min(...means) : payload.vmin
  const high = means.length ? Math.max(...means) : payload.vmax
  const colors = tempStops()
  return {
    backgroundColor: 'transparent',
    animation: false,
    /* 标题由外层卡片承担，绘图区不要再重复画一遍；把腾出的高度还给曲线。 */
    grid: { left: 44, right: 18, top: 30, bottom: 25 },
    visualMap: {
      show: false, type: 'continuous', dimension: 1,
      min: low, max: high > low ? high : low + 1,
      inRange: { color: [colors[2], colors[4], colors[5]] },
    },
    xAxis: {
      type: 'value',
      min: payload.y_min, max: payload.y_max, splitNumber: 3,
      interval: (payload.y_max - payload.y_min) / 3 || 1,
      axisLine: { lineStyle: { color: p.steel } },
      axisTick: { show: false },
      axisLabel: {
        color: p.inkMuted, fontSize: p.chartAxis, hideOverlap: true,
        formatter: '{value} m',
      },
      splitLine: { show: true, lineStyle: { color: p.layerMid, type: 'solid', opacity: 0.5 } },
      minorTick: { show: false, splitNumber: 6 },
      minorSplitLine: { show: true, lineStyle: { color: p.layerMid, type: 'dashed', opacity: 0.22 } },
    },
    yAxis: {
      type: 'value',
      // 不强制从 0 起：这一卷的均温可能只横跨两度，从 0 起就压平了。
      scale: true,
      name: '温度 (°C)', nameLocation: 'end',
      nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis, align: 'left', padding: [0, 0, 0, -35] },
      min: (extent: { min: number }) => Math.floor(extent.min),
      max: (extent: { max: number }) => Math.ceil(extent.max) + (Number.isInteger(extent.max) ? 1 : 0),
      splitNumber: 3,
      axisLine: { lineStyle: { color: p.steel } },
      axisLabel: {
        color: p.inkMuted, fontSize: p.chartAxis, hideOverlap: true,
        formatter: '{value}',
      },
      splitLine: { lineStyle: { color: p.layerMid, type: 'solid', opacity: 0.5 } },
      minorTick: { show: false, splitNumber: 2 },
      minorSplitLine: { show: true, lineStyle: { color: p.layerMid, type: 'dashed', opacity: 0.22 } },
    },
    tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => value == null ? '无数据' : `${Number(value).toFixed(3)} °C` },
    series: [{
      type: 'line',
      name: MEAN_CURVE_TITLE,
      // `[y, mean]` 成对给：`null` 原样传下去，ECharts 会把线断开。
      data: payload.planes.map((pl) => [pl.y, pl.mean]),
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
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: colors[5] }, { offset: 0.4, color: colors[2] }, { offset: 0.85, color: colors[1] }, { offset: 1, color: 'transparent' }] }, opacity: 0.55 },
      // 线之外不加阴影、不加发光：阴影全站只有一档且只给卡片
      // （`guards.test.ts` 钉着），图表这一层也不破例。
    }],
  } as unknown as EChartsOption
}
