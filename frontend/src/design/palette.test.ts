import { describe, expect, it } from 'vitest'

import { readPalette } from './palette'

describe('readPalette', () => {
  // 名字里**不写「几个色」**：这里的 `toEqual` 要求键完全一致，多一个少一个都会红，
  // 数字写进名字只会在下次加令牌时先过期。加令牌的人是被这条测试叫醒的。
  it('从元素的 CSS 变量读出调色板的每一个色，读不到就抛（不静默给个默认灰）', () => {
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
    expect(readPalette(el)).toEqual({
      paper: '#F7F6F2', ink: '#211F1C', inkMuted: '#5C5850',
      steel: '#DEDCD6', leaf: '#14532D', leafSoft: '#E7EFE9', net: '#0B0F0D',
      // 页① 切面图的三层点色（值取自用户给的参考图）。
      layerTop: '#C44E52', layerMid: '#4C72B0', layerLow: '#55A868',
    })
  })

  it('缺一个变量就抛错，不拿个默认色顶上去', () => {
    // 默认色是最坏的一种兜底：图表照画，颜色是错的，而且没人知道。
    const el = document.createElement('div')
    expect(() => readPalette(el)).toThrow(/--paper/)
  })
})
