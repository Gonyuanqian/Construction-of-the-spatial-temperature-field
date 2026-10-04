import { describe, expect, it } from 'vitest'

import { buildSensorLayoutOption } from './sensorLayout'
import type { ArchPayload, DatasetPayload } from '../../api/types'

const PALETTE = {
  paper: '#F7F6F2', ink: '#211F1C', inkMuted: '#5C5850',
  steel: '#DEDCD6', leaf: '#14532D', leafSoft: '#E7EFE9', net: '#0B0F0D',
}

const ARCH: ArchPayload = {
  x_min: 0, x_max: 2.1, z_max: 1.3017, max_measured_z: 1.1,
  arch: [[0, 0.4535], [1.05, 1.3017], [2.1, 0.4535]],
  sheds: [{ id: 'p1', y: 3 }, { id: 'p2', y: 9 }, { id: 'p3', y: 15 }],
}

function ds(positions = 8): DatasetPayload {
  return {
    signature: 'x', file: 'f.xlsx', n_times: 1308, n_columns: 52,
    time_start: '', time_end: '',
    sheds: { p1: 3, p2: 9, p3: 15 },
    positions: Array.from({ length: positions }, (_, i) => ({
      id: `x${i}_z0.4`, x: i * 0.1, z: 0.4, layer: 'z0.4',
    })),
    temperature: (['p1', 'p2', 'p3'] as const).flatMap((shed) =>
      Array.from({ length: positions }, (_, i) => ({
        shed, position: `x${i}_z0.4`,
        mean: 40 + i, min: 30 + i, max: 50 + i,
      }))),
    fix: {
      n_rows: 1308, fixed_indices: [], monotonic_before: false,
      monotonic_after: true, spacing_seconds: 300, n_gaps: 0,
    },
    checks: [], checks_note: '',
  }
}

describe('V1 的 option', () => {
  it('一座棚一格，三格并排且从左到右', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE)
    const grids = o.grid as Array<{ left: string }>
    expect(grids).toHaveLength(3)
    const lefts = grids.map((g) => parseFloat(g.left))
    expect(lefts[0]).toBeLessThan(lefts[1])
    expect(lefts[1]).toBeLessThan(lefts[2])
  })

  it('纵轴顶到拱顶，横轴就是棚长 —— 图幅的轮廓由几何定，不是由数据定', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE)
    const xs = o.xAxis as Array<{ min: number; max: number }>
    const ys = o.yAxis as Array<{ min: number; max: number }>
    expect(xs[0].min).toBe(0)
    expect(xs[0].max).toBe(2.1)
    expect(ys[0].min).toBe(0)
    expect(ys[0].max).toBe(1.3017)
  })

  it('拱线用的是后端给的那条，一个点不加一个点不减', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE)
    const series = (o.series as Array<{ name?: string; data?: unknown[] }>)
    const arches = series.filter((s) => s.name === '拱形轮廓')
    expect(arches).toHaveLength(3)
    expect(arches[0].data).toEqual(ARCH.arch)
  })

  it('无测量带那条线画在 1.10 m，且用的是虚线与令牌色', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE)
    const series = o.series as Array<Record<string, unknown>>
    const band = series.find((s) => s.name === '无测量带') as {
      data: number[][]; lineStyle: { type: string; color: string }
    }
    expect(band.data[0][1]).toBe(1.1)
    expect(band.lineStyle.type).toBe('dotted')
    expect(band.lineStyle.color).toBe(PALETTE.steel)
  })

  it('每个测点带均值标注，且标注的数就是后端给的那个', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE)
    const series = o.series as Array<Record<string, any>>
    const scatter = series.filter((s) => s.type === 'scatter')
    expect(scatter).toHaveLength(3)
    const first = scatter[0].data[0] as [number, number, number]
    expect(first[0]).toBe(0)            // x
    expect(first[1]).toBe(0.4)          // z
    expect(first[2]).toBe(40)           // p1 的第 0 个测点的均值
    expect(scatter[0].label.formatter({ data: first })).toBe('40.0')
  })

  it('均值缺失时不编一个数出来（null 就显示空）', () => {
    const bad = ds(2)                     // 两个测点，方便逐个对
    bad.temperature = []                  // 后端一个均值都没给
    const o = buildSensorLayoutOption(bad, ARCH, PALETTE)
    const scatter = (o.series as Array<Record<string, any>>).filter((s) => s.type === 'scatter')
    expect(scatter[0].data).toEqual([[0, 0.4, null], [0.1, 0.4, null]])
    expect(scatter[0].label.show({ data: scatter[0].data[0] })).toBe(false)
  })

  it('没有矩形外框：轴线与刻度线都关掉', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE)
    const xs = o.xAxis as Array<Record<string, any>>
    const ys = o.yAxis as Array<Record<string, any>>
    expect(xs[0].axisLine.show).toBe(false)
    expect(xs[0].splitLine.show).toBe(false)
    expect(ys[0].axisLine.show).toBe(false)
    expect(ys[0].splitLine.show).toBe(false)
  })

  it('全图的颜色只来自调色板，且没有第八个颜色', () => {
    const flat = JSON.stringify(buildSensorLayoutOption(ds(), ARCH, PALETTE))
    // 先证明「它真的画了颜色」—— 否则下面那条 foreign 会在「一个色都没有」时空转通过。
    // 这五个是 V1 真正用到的令牌色（paper/ink/inkMuted/steel/leaf）。
    const used = [PALETTE.paper, PALETTE.ink, PALETTE.inkMuted, PALETTE.steel, PALETTE.leaf]
    for (const c of used) expect(flat.toUpperCase()).toContain(c.toUpperCase())
    // 而且**没有第八个颜色** —— 有一个不在调色板里的色值，就说明有人就地写了一个
    const allowed = new Set(Object.values(PALETTE).map((c) => c.toUpperCase()))
    const hexes = [...flat.matchAll(/#[0-9A-Fa-f]{6}/g)].map((m) => m[0].toUpperCase())
    const foreign = [...new Set(hexes.filter((h) => !allowed.has(h)))]
    expect(foreign, `这些色不在调色板里：${foreign.join('、')}`).toEqual([])
  })
})
