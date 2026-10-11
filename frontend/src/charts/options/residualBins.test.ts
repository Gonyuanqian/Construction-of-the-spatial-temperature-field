import { describe, expect, it } from 'vitest'

import { buildResidualOption } from './residualBins'
import type { Palette } from '../../design/palette'
import type { ResidualPanel } from '../../api/types'

// `bar` 与 `steel` 给了**不同的哨兵值**：柱子取错令牌时，断言分得出来是哪一个。
const P = {
  paper: '#fff', ink: '#111', inkMuted: '#666', steel: '#888', leaf: '#0a0',
  leafSoft: '#efe', net: '#c00', bar: '#abc',
  layerTop: '#1', layerMid: '#2', layerLow: '#3',
  chartAxis: 12, chartTitle: 14,
} as unknown as Palette

const PANEL: ResidualPanel = {
  key: 'height', label: '残差 vs 高度', axis: '高度 z / m',
  bins: [
    { at: 0.4, mean: 0.03, n: 9000, se: 0.001 },
    { at: 0.7, mean: -0.01, n: 9000, se: null },
    { at: 1.1, mean: null, n: 0, se: null },
  ],
}

describe('残差图', () => {
  it('横轴是箱的位置，纵轴是残差', () => {
    const opt = buildResidualOption(PANEL, P)
    const x = opt.xAxis as { type: string; data: string[] }
    expect(x.type).toBe('category')
    expect(x.data).toEqual(['0.4', '0.7', '1.1'])
    expect((opt.yAxis as { name: string }).name).toBe('残差 / °C')
  })

  it('无值的箱留一根空柱，**不从图上消失**', () => {
    // 那一箱真实存在，藏起来就是漏报（与页② 不藏最差折同一条房规）。
    const opt = buildResidualOption(PANEL, P)
    const bar = (opt.series as { type: string; data: unknown[] }[])[0]
    expect(bar.data).toHaveLength(3)
    expect(bar.data[2]).toBeNull()
  })

  it('柱子用数据色，不用界面线条那个灰', () => {
    // 人眼走查时定的：柱子原先是 `p.steel`，而 `--steel` 在本仓的定义是
    // 「线、分隔、表格框」—— 图上的**数据**被画成了界面**线条**的颜色，
    // 屏上读起来像一块没上色的占位；误差棒用的 `p.ink` 反倒成了最响的东西。
    // 层级反了，柱子改走 `p.bar`（琥珀橙，值定在 tokens.css）。
    // 夹具里 `bar` 与 `steel` 是两个不同的哨兵值，所以取错令牌这条会红。
    const opt = buildResidualOption(PANEL, P)
    const bar = (opt.series as { itemStyle: { color: string } }[])[0]
    expect(bar.itemStyle.color, '柱子又不是数据色了').toBe(P.bar)
  })

  it('有标准误的箱才有误差棒，一个点的箱没有', () => {
    const opt = buildResidualOption(PANEL, P)
    const err = (opt.series as { type: string; data: unknown[] }[])[1]
    expect(err.type).toBe('custom')
    // 0.4 那一箱有 se；0.7 的 se 是 null，1.1 更是什么都没有
    expect(err.data).toHaveLength(1)
    // ⚠️ 上下界是**算出来的** `mean ± se`，不是后端给的常数：`0.03 - 0.001`
    // 在双精度里是 `0.028999999999999998`，与字面量 `0.029` 不是同一个数
    // （`toBe`/`toEqual` 会判失败）。这里比的是「差多少」，不是「是哪一位」。
    const d = err.data[0] as number[]
    expect(d[0]).toBe(0)                    // 第 0 号箱
    expect(d[1]).toBe(0.03)                 // 柱高就是平均残差本身
    expect(d[2]).toBeCloseTo(0.029, 12)     // 下界
    expect(d[3]).toBeCloseTo(0.031, 12)     // 上界
  })

  it('有一条零线 —— 没有它，「有偏」与「噪声」分不出来', () => {
    const opt = buildResidualOption(PANEL, P)
    const bar = (opt.series as { type: string; markLine: { data: { yAxis: number }[] } }[])[0]
    expect(bar.markLine.data[0].yAxis).toBe(0)
  })

  it('箱一个都没有时也要出一张说得出话的图', () => {
    const opt = buildResidualOption({ ...PANEL, bins: [] }, P)
    expect((opt.series as unknown[]).length).toBe(0)
    expect(opt.title).toBeDefined()
  })
})
