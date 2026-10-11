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

export const MEAN_CURVE_TITLE = '沿棚均温'

export function buildLiveMeanCurveOption(
  payload: VolumePayload, p: Palette,
): EChartsOption {
  return {
    backgroundColor: 'transparent',
    animation: false,
    title: {
      text: MEAN_CURVE_TITLE,
      left: 0,
      top: 0,
      textStyle: { color: p.ink, fontSize: p.chartTitle, fontWeight: 600 },
    },
    grid: { left: 56, right: 16, top: 40, bottom: 34 },
    xAxis: {
      type: 'value',
      name: '棚位 / m',
      nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis },
      axisLine: { lineStyle: { color: p.steel } },
      axisTick: { show: false },
      axisLabel: { color: p.inkMuted, fontSize: p.chartAxis },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      name: '温度 / °C',
      // 不强制从 0 起：这一卷的均温可能只横跨两度，从 0 起就压平了。
      scale: true,
      nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis },
      axisLine: { lineStyle: { color: p.steel } },
      axisLabel: { color: p.inkMuted, fontSize: p.chartAxis },
      splitLine: { lineStyle: { color: p.steel } },
    },
    tooltip: { trigger: 'axis' },
    series: [{
      type: 'line',
      name: MEAN_CURVE_TITLE,
      // `[y, mean]` 成对给：`null` 原样传下去，ECharts 会把线断开。
      data: payload.planes.map((pl) => [pl.y, pl.mean]),
      showSymbol: true,
      symbolSize: 5,
      connectNulls: false,
      lineStyle: { color: p.leaf, width: 1.4 },
      itemStyle: { color: p.leaf },
    }],
  } as unknown as EChartsOption
}
