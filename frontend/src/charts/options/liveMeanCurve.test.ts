/**
 * 沿棚均温那条曲线。**只断它与载荷的对应**，不断画出来的样子
 * （那由 `EChart.test.ts` 与页③ 那一组兜着）。
 */
import { describe, expect, it } from 'vitest'

import type { Palette } from '../../design/palette'
import { makeVolumePayload } from '../../test/fixtures'
import { buildLiveMeanCurveOption } from './liveMeanCurve'

/** 测试文件里允许出现十六进制（`guards.test.ts` 只扫非测试文件）。 */
const P: Palette = {
  paper: '#000000', ink: '#111111', inkMuted: '#222222', steel: '#333333',
  leaf: '#444444', leafSoft: '#555555', net: '#666666',
  layerTop: '#777777', layerMid: '#888888', layerLow: '#999999', bar: '#aaaaaa',
  chartAxis: 12, chartTitle: 14,
}

describe('沿棚均温曲线', () => {
  it('横轴是棚位 y，纵轴是那一片的均温', () => {
    const payload = makeVolumePayload()
    const opt = buildLiveMeanCurveOption(payload, P) as {
      series: { data: [number, number | null][] }[]
    }
    expect(opt.series[0].data).toEqual(payload.planes.map((p) => [p.y, p.mean]))
  })

  it('缺数的片原样传 null，不许折成 0', () => {
    // 折成 0 会画出一条贴着底的假线；删掉则两端被直接连起来、跨过一段
    // 本来「无定义」的棚位。两种都不报错，都只是让人看错。
    const payload = makeVolumePayload()
    payload.planes[1].mean = null
    const opt = buildLiveMeanCurveOption(payload, P) as {
      series: { data: [number, number | null][]; connectNulls: boolean }[]
    }
    expect(opt.series[0].data[1]).toEqual([payload.planes[1].y, null])
    expect(opt.series[0].connectNulls, '跨过 null 把两端连起来了').toBe(false)
  })

  it('字号与颜色都走调色板，不写死', () => {
    const opt = buildLiveMeanCurveOption(makeVolumePayload(), P) as {
      xAxis: { axisLabel: { fontSize: number; color: string } }
      yAxis: { axisLabel: { fontSize: number; color: string } }
      series: { lineStyle: { color: string } }[]
    }
    expect(opt.xAxis.axisLabel.fontSize).toBe(P.chartAxis)
    expect(opt.yAxis.axisLabel.color).toBe(P.inkMuted)
    expect(opt.series[0].lineStyle.color).toBe(P.leaf)
  })
})
