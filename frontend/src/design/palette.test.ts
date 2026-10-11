import { describe, expect, it } from 'vitest'

import { readPalette } from './palette'

describe('readPalette', () => {
  // 名字里**不写「几个色」**：这里的 `toEqual` 要求键完全一致，多一个少一个都会红，
  // 数字写进名字只会在下次加令牌时先过期。加令牌的人是被这条测试叫醒的。
  // 2026-10-06 起这个对象里不只有色，还有两个图表字号（`chartAxis`/`chartTitle`）——
  // 名字里说的是「调色板」这个对象，不是「颜色」。
  it('从元素的 CSS 变量读出调色板的每一项（色与图表字号），读不到就抛（不静默给个默认）', () => {
    const el = document.createElement('div')
    el.style.setProperty('--paper', '#F7F6F2')
    el.style.setProperty('--ink', '#211F1C')
    el.style.setProperty('--ink-muted', '#5C5850')
    el.style.setProperty('--steel', '#DEDCD6')
    el.style.setProperty('--leaf', '#14532D')
    el.style.setProperty('--leaf-soft', '#E7EFE9')
    el.style.setProperty('--net', '#0B0F0D')
    el.style.setProperty('--layer-top', '#C44E52')
    el.style.setProperty('--layer-mid', '#4C72B0')
    el.style.setProperty('--layer-low', '#55A868')
    el.style.setProperty('--bar', '#D98C2B')
    el.style.setProperty('--size-chart-axis', '12px')
    el.style.setProperty('--size-chart-title', '14px')
    expect(readPalette(el)).toEqual({
      paper: '#F7F6F2', ink: '#211F1C', inkMuted: '#5C5850',
      steel: '#DEDCD6', leaf: '#14532D', leafSoft: '#E7EFE9', net: '#0B0F0D',
      // 页① 切面图的三层点色（值取自用户给的参考图）。
      layerTop: '#C44E52', layerMid: '#4C72B0', layerLow: '#55A868',
      // 页② 残差图的柱子色（2026-10-08 走查时定的）。
      bar: '#D98C2B',
      // 这两个是**数**不是色：canvas 的 fontSize 不吃 `'12px'`，读出来要 `12`。
      chartAxis: 12, chartTitle: 14,
    })
  })

  it('缺一个变量就抛错，不拿个默认色顶上去', () => {
    // 默认色是最坏的一种兜底：图表照画，颜色是错的，而且没人知道。
    const el = document.createElement('div')
    expect(() => readPalette(el)).toThrow(/--paper/)
  })

  it('字号令牌写成了非数（`12px` 之外的东西）就抛错，不把 NaN 喂给 ECharts', () => {
    // ECharts 拿到 NaN 的 fontSize 会**静默退回默认字号** ——
    // 图照画、字是错的、没人知道。与「读不到颜色」同一套失败语义。
    const el = document.createElement('div')
    for (const t of ['--paper', '--ink', '--ink-muted', '--steel', '--leaf',
      '--leaf-soft', '--net', '--layer-top', '--layer-mid', '--layer-low', '--bar']) {
      el.style.setProperty(t, '#000000')
    }
    el.style.setProperty('--size-chart-axis', '12px')
    el.style.setProperty('--size-chart-title', 'auto')
    expect(() => readPalette(el)).toThrow(/--size-chart-title/)
  })
})
