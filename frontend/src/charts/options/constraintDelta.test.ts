import { describe, expect, it } from 'vitest'

import type { ComparePayload } from '../../api/types'
import type { Palette } from '../../design/palette'
import {
  buildConstraintDeltaOption, deltaNote, SERIES_PER_PANEL,
} from './constraintDelta'

const PALETTE: Palette = {
  paper: '#F7F6F2', ink: '#211F1C', inkMuted: '#5C5850', steel: '#DEDCD6',
  leaf: '#14532D', leafSoft: '#E7EFE9', net: '#0B0F0D',
}

const GRID_2x2 = [
  [1, 2],
  [3, 4],
]

function makePayload(over: Partial<ComparePayload> = {}): ComparePayload {
  return {
    shed: 'p1', y: 3, t_index: 7, time: '2026-07-23T11:00:00', n_times: 1308,
    preset: 'standard',
    x: [0, 2.1], z: [0, 1.4],
    arch: [[0, 0], [2.1, 0]],
    sensors: [{ id: 'x0_z0', x: 0, z: 0, layer: 'z0' }],
    max_measured_z: 2,
    before: GRID_2x2,
    after: [
      [1.1, 2],
      [3, 4.2],
    ],
    delta: [
      [-0.1, 0],
      [0, -0.2],
    ],
    stripes: [[1, 1]],
    vmin: 1, vmax: 5, delta_vmax: 0.2,
    light: 812, gate_open: true, gate_label: '开（有光照）', identical: false,
    note: '',
    ...over,
  }
}

const opt = (p: ComparePayload) => buildConstraintDeltaOption(p, PALETTE) as any

describe('ΔT 第四格的骨架', () => {
  it('三个面板各占连续 4 条系列，共 12 条', () => {
    const o = opt(makePayload())
    expect(SERIES_PER_PANEL).toBe(4)
    expect(o.series).toHaveLength(3 * SERIES_PER_PANEL)
    expect(o.grid).toHaveLength(3)
  })

  it('三条热力场分别在 0 / 4 / 8', () => {
    const o = opt(makePayload())
    for (const i of [0, 4, 8]) expect(o.series[i].type).toBe('heatmap')
  })

  it('拱线、测点、斜纹都是 silent', () => {
    // 装饰接住点击 = 用户点不动它们盖住的那一格。
    const o = opt(makePayload())
    for (const base of [0, 4, 8]) {
      for (const k of [1, 2, 3]) {
        expect(o.series[base + k].silent, `系列 ${base + k} 该是 silent`).toBe(true)
      }
    }
  })
})

describe('两张温度图共用一个色标，差异图另用一个', () => {
  it('恰好两个 visualMap', () => {
    const o = opt(makePayload())
    expect(Array.isArray(o.visualMap), '约束前/后必须是同一个色标').toBe(true)
    expect(o.visualMap).toHaveLength(2)
  })

  it('第一个绑住「约束前」与「约束后」两条热力场', () => {
    const o = opt(makePayload())
    const w = o.visualMap[0]
    expect(w.seriesIndex).toEqual([0, 4])
    expect(w.inRange.color).toHaveLength(7)
    expect(w.inRange.color[0]).toBe('#00224E')
  })

  it('前两张图共用同一对 vmin/vmax', () => {
    const p = makePayload()
    const o = opt(p)
    expect(o.visualMap[0].min).toBe(p.vmin)
    expect(o.visualMap[0].max).toBe(p.vmax)
  })

  it('第二个绑住差异图，用的是发散色标', () => {
    const o = opt(makePayload())
    const w = o.visualMap[1]
    expect(w.seriesIndex).toEqual([8])
    expect(w.inRange.color).toHaveLength(11)
    expect(w.inRange.color[0]).toBe('#053061')     // 负端：蓝
    expect(w.inRange.color[10]).toBe('#67001F')    // 正端：红
    expect(w.inRange.color[5]).toBe('#F7F7F7')     // 中点：近白
  })

  it('差异的值域**对称**，中点严格落在 0', () => {
    // 不对称的话「没变」会被画成一个有颜色的格子 ——
    // 而「没变」是这张图在夜里要说的第一件事。
    const p = makePayload()
    const o = opt(p)
    expect(o.visualMap[1].min).toBe(-p.delta_vmax)
    expect(o.visualMap[1].max).toBe(p.delta_vmax)
    expect(o.visualMap[1].min).toBe(-o.visualMap[1].max)
  })

  it('两个色标条都不可拖拽', () => {
    const o = opt(makePayload())
    expect(o.visualMap[0].calculable).toBe(false)
    expect(o.visualMap[1].calculable).toBe(false)
  })
})

describe('拱外不进热力场', () => {
  it('null 的格子被丢掉，而不是当成 0', () => {
    const p = makePayload({
      before: [[1, null], [3, 4]],
      after: [[1, null], [3, 4]],
      delta: [[0, null], [0, 0]],
    })
    const o = opt(p)
    // 样本必须 ix ≠ iz：`[0, 0, 1]` 这种对角样本转置之后**仍然**在数据里，
    // 于是「把图整个转置」的 bug 在这条断言下照绿。取值：before[1][0] === 3。
    expect(o.series[0].data).toContainEqual([0, 1, 3])
    // 光断言「没有 null 值」挡不住「把 null 填成 0」：填 0 之后一个 null 也不剩，
    // 而图上那一格会被画成「零温差」—— 拱外没有定义，不是没有变化。
    // 所以还要正着钉：那一格必须**整个不在数据里**。（before[0][1] === null ⇒ ix=1, iz=0）
    expect(o.series[0].data.some((x: any[]) => x[0] === 1 && x[1] === 0),
      '拱外的格子不进热力场，也不能填 0 进来').toBe(false)
    expect(o.series[0].data.some((x: any[]) => x[2] === null)).toBe(false)
    expect(o.series[8].data.some((x: any[]) => x[0] === 1 && x[1] === 0)).toBe(false)
    expect(o.series[8].data.some((x: any[]) => x[2] === null)).toBe(false)
  })

  it('斜纹的下标直接来自载荷，不是前端推出来的', () => {
    // 前端自己从 x / z / max_measured_z 推一遍，就是把后端的一条规则
    // 实现了第二遍（硬约束 1）—— 两条路径漂了不会报错。
    const p = makePayload({ stripes: [[0, 0], [1, 1]] })
    const o = opt(p)
    expect(o.series[3].data).toEqual([[0, 0], [1, 1]])
    expect(o.series[3].data, '原样用，不做任何改写').toBe(p.stripes)
  })
})

describe('门禁那句口径', () => {
  it('报出光照、门禁状态与逐格最大差', () => {
    const t = deltaNote(makePayload())
    expect(t).toContain('812')
    expect(t).toContain('开（有光照）')
    expect(t).toContain('0.2000')
  })

  it('夜里说的是「逐位相同」，不是「差很小」', () => {
    // 「差很小」与「一模一样」是两句话。夜里门禁关闭时两张图**逐位相同** ——
    // 图上要照实说（spec §七 V5）。
    const p = makePayload({
      before: [[1, 2], [3, 4]], after: [[1, 2], [3, 4]],
      delta: [[0, 0], [0, 0]], delta_vmax: 0,
      light: 0, gate_open: false, gate_label: '关（无光照，严格不变）', identical: true,
    })
    const t = deltaNote(p)
    expect(t).toContain('逐位相同')
    expect(t).toContain('关（无光照，严格不变）')
  })

  it('白天不说「逐位相同」', () => {
    expect(deltaNote(makePayload())).not.toContain('逐位相同')
  })
})

describe('三个面板的标题', () => {
  it('写清了哪一棚、以及第三格是「约束前 − 约束后」', () => {
    const texts = (opt(makePayload()).title as any[]).map((t) => t.text)
    expect(texts[0]).toContain('p1')
    expect(texts[0]).toContain('约束前')
    expect(texts[1]).toContain('约束后')
    expect(texts[2]).toContain('约束前 − 约束后')
  })

  it('悬停时报的数说了是哪一格', () => {
    // 这一处原先是 `q.seriesIndex < 2 * SERIES_PER_PANEL ? ' °C' : ' °C'` ——
    // 一个两支一模一样的死三元，修掉之后**没有任何东西守着它**。
    // 而看错一格（把 ΔT 当成约束后的温度）正是这张图最容易读错的地方：
    // 三个面板的热力场各自有下标，标签只能按面板算。
    const f = (opt(makePayload()).tooltip as any).formatter
    expect(f({ seriesIndex: 0, value: [0, 0, 2.5] })).toBe('约束前：2.5000 °C')
    expect(f({ seriesIndex: 4, value: [0, 1, 2.5] })).toBe('约束后：2.5000 °C')
    expect(f({ seriesIndex: 8, value: [0, 0, -0.25] })).toBe('ΔT：-0.2500 °C')
    // 装饰性的三条系列（测点/拱线/斜纹）的数据项只有两个元素，不该弹出数来。
    expect(f({ seriesIndex: 1, value: ['x0_z0', '0'] }), '测点不该报数').toBe('')
  })
})
