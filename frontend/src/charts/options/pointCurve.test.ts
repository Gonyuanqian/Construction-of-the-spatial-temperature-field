import { describe, expect, it } from 'vitest'

import type { CurvePayload } from '../../api/types'
import type { Palette } from '../../design/palette'
import { buildPointCurveOption, CURVE_NO_MONOTONIC_NOTE } from './pointCurve'

const PALETTE: Palette = {
  paper: '#F7F6F2', ink: '#211F1C', inkMuted: '#5C5850', steel: '#DEDCD6',
  leaf: '#14532D', leafSoft: '#E7EFE9', net: '#0B0F0D',
  // 页① 切面图的三层点色。这一张图不用它们，但 `Palette` 是整个调色板
  // 一份读出来的 —— 用得着用不着的令牌都在同一个对象上（与 `net` 同理）。
  layerTop: '#C44E52', layerMid: '#4C72B0', layerLow: '#55A868',
  // 页② 残差图的柱子色。这一张图也不用它，同上。
  bar: '#D98C2B',
  // 图表字号。**是数不是色** —— canvas 的 fontSize 不吃 `'12px'`。
  chartAxis: 12, chartTitle: 14,
}

function makePayload(over: Partial<CurvePayload> = {}): CurvePayload {
  return {
    shed: 'p1', x: 0.8, y: 3, z: 1.1, label: 'p1  x 0.80  z 1.10',
    n_times: 4, time: ['t0', 't1', 't2', 't3'],
    values: [40.1, 41.2, 39.8, 38.5],
    defined: true, note: '这条曲线没有施加竖直软单调投影：……',
    ...over,
  }
}

const opt = (p: CurvePayload) => buildPointCurveOption(p, PALETTE) as any

describe('单点曲线', () => {
  it('横轴是时刻，纵轴是温度', () => {
    const p = makePayload()
    const o = opt(p)
    expect(o.xAxis.data).toEqual(p.time)
    expect(o.yAxis.name).toContain('°C')
  })

  it('缺数的时刻留成 null，不填 0、不删掉、也不跨过它连线', () => {
    // 填 0：画出一条贴着底的假线。
    // 删掉：两端的点被直接连起来，跨过一段本来「无定义」的时间。
    // 三种都不报错，都只是让人看错。
    const p = makePayload({ values: [40.1, null, null, 38.5] })
    const o = opt(p)
    expect(o.series[0].data).toEqual([40.1, null, null, 38.5])
    // 第三种画法：null 留在数据里（上面那条照绿），ECharts 却把 40.1 直接连到 38.5 ——
    // 数据数组看上去完全正常，图上还是跨过了一段「无定义」的时间。
    // 也就是说 `connectNulls: true` 是上面那种「删掉」错的**另一种画法**，而 `toEqual` 看不见它。
    // 这一格只能靠这个开关钉住。
    expect(o.series[0].connectNulls).toBe(false)
  })

  it('线的颜色来自令牌，不是硬编码', () => {
    const o = opt(makePayload())
    expect(o.series[0].lineStyle.color).toBe(PALETTE.leaf)
  })

  it('标题是载荷给的标签', () => {
    // `title` 这里是**一个对象**（只有一条标题），不是数组 ——
    // 写成 `title[0].text` 会取到 `undefined` 再 `.text`，直接 TypeError。
    expect(opt(makePayload()).title.text).toContain('p1  x 0.80  z 1.10')
  })

  it('全 null 时也只有一条空系列（页面负责不画它）', () => {
    const p = makePayload({ values: [null, null, null, null], defined: false })
    const o = opt(p)
    expect(o.series).toHaveLength(1)
    expect(o.series[0].data).toEqual([null, null, null, null])
  })

  it('兜底文案里也写明了没有竖直软单调投影', () => {
    // 三个词**分开**断言挡不住「词都在、话不是那句」（'没有竖直方向的投影' 也过）——
    // 而这句话是显示给用户看的**口径**（载荷的 note 为空时用它），口径错等于没说。
    expect(CURVE_NO_MONOTONIC_NOTE).toContain('没有施加竖直软单调投影')
    // 顺带钉住它说了**为什么**没有 —— 只说「没做」读者会以为是漏做，
    // 说清「单点没有竖直邻点可投影」才是「做不了」。
    expect(CURVE_NO_MONOTONIC_NOTE).toContain('邻点')
  })
})
