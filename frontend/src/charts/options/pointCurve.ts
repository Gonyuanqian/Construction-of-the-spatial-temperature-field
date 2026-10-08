/**
 * 单点在整个时间轴上的温度。
 *
 * ⚠️ 这条曲线**没有**竖直软单调投影：软投影要同一时刻的竖直邻点，
 * 单点没有邻点可投影。界面上必须照实标注（载荷的 `note` 就是那句话）。
 *
 * 缺数的时刻留 **null**：填 0 会画出一条贴着底的假线，删掉则两端被直接连起来、
 * 跨过一段本来「无定义」的时间 —— 两种都不报错，都只是让人看错。
 */
import type { EChartsOption } from 'echarts'

import type { CurvePayload } from '../../api/types'
import type { Palette } from '../../design/palette'

export const CURVE_NO_MONOTONIC_NOTE =
  '这条曲线没有施加竖直软单调投影：软投影要同一时刻的竖直邻点，单点没有邻点可投影。'

export function buildPointCurveOption(
  payload: CurvePayload, p: Palette,
): EChartsOption {
  return {
    backgroundColor: 'transparent',
    animation: false,
    title: {
      text: payload.label,
      left: 0,
      top: 0,
      textStyle: { color: p.ink, fontSize: p.chartTitle, fontWeight: 600 },
    },
    grid: { left: 56, right: 16, top: 40, bottom: 40 },
    xAxis: {
      type: 'category',
      data: payload.time,
      axisLine: { lineStyle: { color: p.steel } },
      axisTick: { show: false },
      axisLabel: { color: p.inkMuted, fontSize: p.chartAxis },
    },
    yAxis: {
      type: 'value',
      name: '温度 / °C',
      scale: true,          // 不强制从 0 起：这一段温差可能只有几度，从 0 起就压平了
      nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis },
      axisLine: { lineStyle: { color: p.steel } },
      axisLabel: { color: p.inkMuted, fontSize: p.chartAxis },
      splitLine: { lineStyle: { color: p.steel } },
    },
    tooltip: { trigger: 'axis' },
    series: [{
      type: 'line',
      name: payload.label,
      data: payload.values,          // null 原样传下去：ECharts 会把 null 断开
      showSymbol: false,
      connectNulls: false,           // 不许跨过 null 把两端连起来
      lineStyle: { color: p.leaf, width: 1.2 },
      itemStyle: { color: p.leaf },
    }],
  } as unknown as EChartsOption
}
