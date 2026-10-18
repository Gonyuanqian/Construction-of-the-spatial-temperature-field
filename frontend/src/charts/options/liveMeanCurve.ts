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
    /* 标题由外层卡片承担，绘图区不要再重复画一遍；把腾出的高度还给曲线。 */
    grid: { left: 70, right: 10, top: 8, bottom: 20 },
    xAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: p.steel } },
      axisTick: { show: false },
      axisLabel: {
        color: p.inkMuted, fontSize: p.chartAxis, hideOverlap: true,
        formatter: '{value} m',
      },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      // 不强制从 0 起：这一卷的均温可能只横跨两度，从 0 起就压平了。
      scale: true,
      splitNumber: 3,
      axisLine: { lineStyle: { color: p.steel } },
      axisLabel: {
        color: p.inkMuted, fontSize: p.chartAxis, hideOverlap: true,
        formatter: '{value} °C',
      },
      splitLine: { lineStyle: { color: p.steel } },
    },
    tooltip: { trigger: 'axis' },
    series: [{
      type: 'line',
      name: MEAN_CURVE_TITLE,
      // `[y, mean]` 成对给：`null` 原样传下去，ECharts 会把线断开。
      data: payload.planes.map((pl) => [pl.y, pl.mean]),
      showSymbol: true,
      symbolSize: 6,
      connectNulls: false,
      // 2026-10-12 换样式：这一屏的底是深蓝，1.4px 的青线在上面只剩一条
      // 若有若无的痕（参考图那条线粗得多，而且带一层同色的面积底）。
      // 颜色仍走 `p.leaf` —— 全站「同一个数在哪儿都是同一个颜色」那条没变。
      lineStyle: { color: p.leaf, width: 3 },
      itemStyle: { color: p.leaf, borderColor: p.paper, borderWidth: 1 },
      // 面积底用**同一个颜色**、靠透明度分层 —— 不用第二个色号，
      // 免得「这条线是什么颜色」在屏上出现两种答案。
      areaStyle: { color: p.leaf, opacity: 0.16 },
      // 线之外不加阴影、不加发光：阴影全站只有一档且只给卡片
      // （`guards.test.ts` 钉着），图表这一层也不破例。
    }],
  } as unknown as EChartsOption
}
