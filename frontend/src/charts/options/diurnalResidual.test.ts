import { describe, expect, it } from 'vitest'

import { buildDiurnalResidualOption } from './diurnalResidual'
import type { LayerTimeHeightPayload, TimeseriesPayload } from '../../api/types'

const PALETTE = {
  paper: '#F7F6F2', ink: '#211F1C', inkMuted: '#5C5850',
  steel: '#DEDCD6', leaf: '#14532D', leafSoft: '#E7EFE9', net: '#0B0F0D',
  // 页① 切面图的三层点色。这一张图不用它们，但 `Palette` 是整个调色板
  // 一份读出来的 —— 用得着用不着的令牌都在同一个对象上（与 `net` 同理）。
  layerTop: '#C44E52', layerMid: '#4C72B0', layerLow: '#55A868',
}

const N = 4
const TS: TimeseriesPayload = {
  n_times: N,
  time: ['2026-07-23T11:00:00', '2026-07-23T11:05:00',
         '2026-07-23T11:10:00', '2026-07-23T11:15:00'],
  bg_temp: [30, 31, 32, 33],
  sensors: { 'p1|a': [40, 41, 42, 43], 'p1|b': [38, 39, 40, 41] },
  shed_mean: { p1: [39, 40, 41, 42] },
  // ⚠️ 故意**不等于** sensors − bg：99 是个哨兵值。
  // 页面显示后端给的那一个；谁在前端做减法，这条测试就红（Review Focus #4）。
  detrended: { 'p1|a': [99, 99, 99, 99], 'p1|b': [8, 8, 8, 8] },
  detrended_mean: { p1: [7, 7, 7, 7] },
  detrended_domain: [-3, 3],
  note: '减法在后端做',
}

const TH: LayerTimeHeightPayload = {
  step: 1, n_times: N, n_columns: N, time: TS.time,
  x_label: '时刻', source: '实测棚温',
  sheds: {
    p1: {
      labels: ['z0.4', 'z0.7'],
      z: [0.4, 0.7],
      values: [[40, 41, 42, 43], [38, 39, 40, 41]],
    },
  },
}

describe('V2 的 option', () => {
  it('三格：上格全量程、下格减背景、右侧时间×高度', () => {
    const o = buildDiurnalResidualOption(TS, TH, 'p1', PALETTE)
    expect((o.grid as unknown[])).toHaveLength(3)
  })

  it('上格画的是棚温原值，不是减过的', () => {
    const o = buildDiurnalResidualOption(TS, TH, 'p1', PALETTE)
    const s = (o.series as Array<Record<string, any>>).find((x) => x.name === 'p1|a（棚温）')!
    expect(s.data.map((d: [string, number]) => d[1])).toEqual([40, 41, 42, 43])
  })

  it('下格画的是后端给的 detrended，绝不自己减（Review Focus #4）', () => {
    const o = buildDiurnalResidualOption(TS, TH, 'p1', PALETTE)
    const s = (o.series as Array<Record<string, any>>).find((x) => x.name === 'p1|a（减背景）')!
    expect(s.data.map((d: [string, number]) => d[1])).toEqual([99, 99, 99, 99])
    // 如果这里出现的是 10（40−30），说明前端偷偷减了 —— 那正是这条测试要拦的
    expect(s.data.map((d: [string, number]) => d[1])).not.toContain(10)
  })

  it('下格的纵轴范围就用后端给的 ±3，不是按数据自适应', () => {
    const o = buildDiurnalResidualOption(TS, TH, 'p1', PALETTE)
    const y = o.yAxis as Array<Record<string, any>>
    expect(y[1].min).toBe(-3)
    expect(y[1].max).toBe(3)
  })

  it('三格的 x 轴连在一起 —— 不连就看不出联动', () => {
    const o = buildDiurnalResidualOption(TS, TH, 'p1', PALETTE)
    expect((o.axisPointer as { link?: unknown[] }).link).toEqual([
      { xAxisIndex: 'all' },
    ])
  })

  it('时间×高度是热图，格子数 = 层数 × 列数', () => {
    const o = buildDiurnalResidualOption(TS, TH, 'p1', PALETTE)
    const heat = (o.series as Array<Record<string, any>>).find((x) => x.type === 'heatmap')!
    expect(heat.data).toHaveLength(2 * 4)
    expect(heat.data[0]).toEqual([0, 0, 40])
    expect(heat.data[4]).toEqual([0, 1, 38])       // 第二层的第一列
  })

  it('右格的名字里带着棚号 —— 它只画一棚，另两格是三棚合看', () => {
    // 串成一条游标的三格里，右格是唯一「只画一棚」的。不写棚号，
    // 读者会把它当成与另两格同范围的图（最终评审 M1）。
    const o = buildDiurnalResidualOption(TS, TH, 'p1', PALETTE)
    const heat = (o.series as Array<Record<string, any>>).find((x) => x.type === 'heatmap')!
    expect(heat.name).toContain('p1')
  })

  it('换棚就换那一棚的数据，热图的行标签跟着变', () => {
    const other: LayerTimeHeightPayload = {
      ...TH,
      sheds: { p2: { labels: ['z0.4'], z: [0.4], values: [[1, 2, 3, 4]] } },
    }
    const o = buildDiurnalResidualOption(TS, other, 'p2', PALETTE)
    const heat = (o.series as Array<Record<string, any>>).find((x) => x.type === 'heatmap')!
    expect(heat.data).toHaveLength(4)
  })

  it('全图的颜色只来自调色板与正向 cividis，没有第八个颜色', () => {
    const o = buildDiurnalResidualOption(TS, TH, 'p1', PALETTE)
    const flat = JSON.stringify(o)
    // 先证明「它真的画了颜色」—— 否则下面那条 foreign 会在「一个色都没有」时空转通过。
    // 这五个是 V2 真正用到的令牌色（paper/ink/inkMuted/steel/leaf）。
    const used = [PALETTE.paper, PALETTE.ink, PALETTE.inkMuted, PALETTE.steel, PALETTE.leaf]
    for (const c of used) expect(flat.toUpperCase()).toContain(c.toUpperCase())
    // cividis 是**色标名**不是颜色，canvas 的渐变要的是真颜色，只能写成字面量。
    const cividis = ['#00224E', '#12456F', '#4C6C7F', '#7C7B78', '#BE8353', '#EB9A31', '#FFE945']
    const allowed = new Set([...Object.values(PALETTE), ...cividis].map((c) => c.toUpperCase()))
    const hexes = [...flat.matchAll(/#[0-9A-Fa-f]{6}/g)].map((m) => m[0].toUpperCase())
    const foreign = [...new Set(hexes.filter((h) => !allowed.has(h)))]
    expect(foreign, `这些色不在调色板或 cividis 里：${foreign.join('、')}`).toEqual([])
    // 正向 cividis：最低温深蓝、最高温亮黄。若某处误用了反向色标，这条会红。
    const vm = o.visualMap as { inRange: { color: string[] } }
    expect(vm.inRange.color[0]).toBe('#00224E')
    expect(vm.inRange.color[vm.inRange.color.length - 1]).toBe('#FFE945')
    // visualMap 必须**只**作用在热图上。不写 seriesIndex 时，ECharts 5 会
    // 按「最后一个维度」给所有 series 染色 —— 两条折线也会被 cividis 重染，
    // 而折线的调色板色仍留在 lineStyle 里，上面那几条会静默通过。
    const seriesArr = o.series as Array<Record<string, any>>
    const heatIndex = seriesArr.findIndex((x) => x.type === 'heatmap')
    expect((o.visualMap as { seriesIndex?: number }).seriesIndex).toBe(heatIndex)
    // 折线只许用调色板里的色（ink 背景、steel 细线、leaf 均值）——
    // 与上一条互为表里：一个钉住 visualMap 的作用域，一个钉住线的颜色。
    const lineColours = seriesArr
      .filter((x) => x.type === 'line')
      .map((x) => (x.lineStyle.color as string).toUpperCase())
    const paletteLine = new Set([PALETTE.ink, PALETTE.steel, PALETTE.leaf].map((c) => c.toUpperCase()))
    expect(lineColours.every((c) => paletteLine.has(c))).toBe(true)
  })
})
