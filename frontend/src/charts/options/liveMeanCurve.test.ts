/**
 * 垂直均温曲线。验证高度坐标和后端汇总数据的对应关系。
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

describe('垂直均温曲线', () => {
  it.each([[-6.18,-5.92],[25.12,25.28],[-.1,.1],[0,0],[30,30]])('纵轴包含 %s 到 %s 的读数并保留可读刻度', (low,high) => {
    const opt=buildLiveMeanCurveOption(makeVolumePayload({height_profile:[{z:0,mean:low},{z:1,mean:high}]}),P) as {
      yAxis:{min:number;max:number;interval:number;axisLabel:{showMinLabel:boolean;showMaxLabel:boolean;formatter:(v:number)=>string}}
    }
    const axis=opt.yAxis
    expect(axis.min).toBeLessThan(low)
    expect(axis.max).toBeGreaterThan(high)
    expect(axis.max-axis.min).toBeLessThanOrEqual(1)
    expect(axis.interval).toBeGreaterThan(0)
    expect(axis.axisLabel.showMinLabel&&axis.axisLabel.showMaxLabel).toBe(true)
    expect(axis.axisLabel.formatter(-0)).toBe('0')
  })
  it('横轴是距地高度，纵轴是后端给出的同高度均温', () => {
    const payload = makeVolumePayload()
    const opt = buildLiveMeanCurveOption(payload, P) as {
      series: { data: [number, number | null][] }[]
      xAxis: {min:number;max:number;name:string}
    }
    expect(opt.series[0].data).toEqual(payload.height_profile!.map(p => [p.z, p.mean]))
    expect(opt.xAxis.min).toBe(payload.z[0])
    expect(opt.xAxis.max).toBe(payload.z_max)
    expect(opt.xAxis.name).toBe('距地高度 (m)')
  })

  it('缺数的片原样传 null，不许折成 0', () => {
    // 折成 0 会画出一条贴着底的假线；删掉则两端被直接连起来、跨过一段
    // 本来「无定义」的棚位。两种都不报错，都只是让人看错。
    const payload = makeVolumePayload()
    payload.height_profile![1].mean = null
    const opt = buildLiveMeanCurveOption(payload, P) as {
      series: { data: [number, number | null][]; connectNulls: boolean }[]
    }
    expect(opt.series[0].data[1]).toEqual([payload.height_profile![1].z, null])
    expect(opt.series[0].connectNulls, '跨过 null 把两端连起来了').toBe(false)
  })

  it('字号与颜色都走调色板，不写死', () => {
    const opt = buildLiveMeanCurveOption(makeVolumePayload(), P) as {
      xAxis: { axisLabel: { fontSize: number; color: string } }
      yAxis: { axisLabel: { fontSize: number; color: string } }
      visualMap: { min: number; max: number; inRange: { color: string[] } }
    }
    expect(opt.xAxis.axisLabel.fontSize).toBe(P.chartAxis)
    expect(opt.yAxis.axisLabel.color).toBe(P.inkMuted)
    expect(opt.visualMap.inRange.color.length).toBeGreaterThan(2)
    const means = makeVolumePayload().height_profile!.flatMap(point => point.mean == null ? [] : [point.mean])
    expect(opt.visualMap.min).toBe(Math.min(...means))
    expect(opt.visualMap.max).toBeGreaterThan(opt.visualMap.min)
  })

  it('旧载荷缺少高度数据时不把沿棚长数据画成高度', () => {
    const opt=buildLiveMeanCurveOption(makeVolumePayload({height_profile:undefined}),P) as {series:{data:unknown[]}[]}
    expect(opt.series[0].data).toEqual([])
  })

  it('线加粗、补一块面积底 —— 深底上细线读不出形状', () => {
    // 2026-10-12：这一屏的底换成深蓝之后，原来 1.4px 的线在上面只剩一条
    // 若有若无的痕（参考图那条线粗得多，而且带一层同色的面积底）。
    // ⚠️ 颜色仍走 `p.leaf` —— 「同一个数在哪儿都是同一个颜色」那条没变，
    // 变的只是**粗细与底**。
    const opt = buildLiveMeanCurveOption(makeVolumePayload(), P) as {
      series: {
        lineStyle: { color: string; width: number }
        areaStyle?: { color: string; opacity: number }
      }[]
    }
    expect(opt.series[0].lineStyle.width, '细线在深蓝底上没有存在感')
      .toBeGreaterThanOrEqual(2.5)
    expect(opt.series[0].areaStyle, '没有面积底就只是一条飘着的线').toBeTruthy()
  })
})
